# Audit performance PINOVA — N+1 et budgets requêtes

**Date** : 6 juin 2026  
**Méthode** : `assertNumQueries`, revue code, tests `pins.tests_feed_perf`  
**Budget feed** : **≤ 15 requêtes SQL / page** (objectif interne : ≤ 13 mesuré sur `home-feed`)

---

## Synthèse

| Endpoint | Budget mesuré | Verdict | N+1 résiduel |
|----------|---------------|---------|--------------|
| `GET /api/pins/home-feed/` | **13** requêtes | **PASS** | Non (prefetch batch) |
| `GET /api/pins/following/` | **5** requêtes (core) + 3 blocks | **PASS** | Non |
| `GET /api/pins/active-stories/` | ~8–15+ selon visibilité | **ATTENTION** | Oui (filtrage Python) |
| `GET /api/notifications/` | ~3–5 / page | **PASS** | Faible (i18n metadata) |
| `GET /api/pins/header-search/` | ~10–20 selon `q` | **ATTENTION** | Oui si reco ON |

---

## 1. Feed / home-feed

### Budget mesuré (2026-06-06)

Test : `pins.tests_feed_perf.FeedQueryBudgetTests.test_home_feed_http_query_budget`

| # | Requête | Rôle |
|---|---------|------|
| 1 | `profile_following` M2M | Liste auteurs suivis |
| 2–3 | `userblock` bidirectionnel | Exclusion mutuelle |
| 4 | `COUNT` following | Pagination entrelacée |
| 5 | `COUNT` discover | Pagination entrelacée |
| 6 | `SELECT` slice following | Pins page (optimisé) |
| 7–9 | Prefetch hashtags / variants / boards | following slice |
| 10 | `SELECT` slice discover | Pins discover |
| 11–13 | Prefetch discover | Même pattern |

**Correctif appliqué** : `optimize_pin_feed_queryset()` **avant** `fetch_pins_for_slots()` dans `home_feed` — évite un second `pk__in` (+5 requêtes).

### N+1 éliminés

- Compteurs likes/comments/saves → `Subquery` + `annotate_pin_feed`
- `is_liked`, `is_saved`, `is_boosted`, `can_comment` → `Exists` / `Case`
- `is_following` auteur → `_viewer_following_profile_ids` en mémoire
- Boards pin → `Prefetch(pin_board_memberships)`

### Piste d'amélioration (non bloquante, < 15 req)

Fusionner les prefetches following + discover en une passe `pk__in` unique → gain ~3 requêtes (13 → 10).

---

## 2. Stories (`active-stories`)

**Fichier** : `pins/views.py` → `active_stories`

### Pattern actuel

```python
pool = list(qs.order_by(...)[:150])
visible = [pin for pin in pool if pin_is_visible_for_request(pin, request)]
```

### N+1 / coût résiduel

| Problème | Impact | Recommandation |
|----------|--------|----------------|
| Filtrage visibilité en **Python** sur 150 pins | CPU + requêtes si `pin_is_visible_for_request` touche la DB | Pousser filtres story/visibility en SQL (`get_queryset` déjà riche) |
| Re-fetch `Pin.objects.filter(id__in=...)` si reco ON | +1 SELECT + prefetches | Réutiliser le pool déjà prefetch |
| `_story_ring_groups_from_pins` + sérialisation | OK si prefetch `author__profile` | Déjà `select_related` |

**Verdict** : acceptable pour ≤80 stories affichées ; surveiller p95 si pool 150 + reco.

---

## 3. Notifications

**Fichier** : `notifications/views.py`, `NotificationSerializer`

### Optimisations présentes

- `select_related('sender', 'sender__profile')`
- `.only(...)` champs stricts
- Filtre blocks en une requête

### N+1 résiduels

| Point | Requêtes extra | Mitigation |
|-------|----------------|------------|
| `build_versioned_media_url` avatar | 0 si avatar en prefetch | OK |
| `localize_notification_strings` | 0 (metadata JSON) | OK |
| `unread_count` action séparée | 1 COUNT | Endpoint dédié — acceptable |

**Verdict** : **PASS** — pas de N+1 sériel sur liste paginée.

---

## 4. Search (`header-search`)

**Fichier** : `pins/views.py` → `header_search`

### Pattern

- Filtre trigram / discover SQL
- Si `notifications_recommendations` : `_build_topic_scores` + tri Python sur subset
- Réutilise `optimize_pin_feed_queryset` via `_feed_response_with_ads`

### N+1 résiduels

| Scénario | Risque |
|----------|--------|
| Reco ON + pool 300 pins | Tri Python + possible double matérialisation |
| Requête `q` vide vs pleine | COUNT + SELECT + prefetches ≈ 8–12 |
| Boost batch | 1 requête `active_boosted_pin_ids()` — OK |

**Verdict** : **ATTENTION** — budget proche de 15 en reco ; désactiver reco ou limiter pool si p95 dégrade.

---

## 5. Tests automatisés

```bash
cd pinova-backend
REDIS_URL= python manage.py test pins.tests_feed_perf -v 2
```

| Test | Seuil |
|------|-------|
| `test_home_feed_http_query_budget` | ≤ 13 requêtes SQL |
| `test_home_feed_p95_latency_under_500ms` | p95 < 500 ms (local) |
| `test_following_feed_page_five_queries` | 5 requêtes core |
| `test_feed_serialization_zero_extra_queries` | 0 requête sérialisation |

---

## 6. Preuves charge & frontend

| Artefact | Commande |
|----------|----------|
| `docs/evidence/loadtest-home-feed.json` | `.\scripts\run_loadtest.ps1` |
| `docs/evidence/lighthouse-home.json` | `.\scripts\run_lighthouse.ps1` |
| `docs/evidence/lighthouse-settings.json` | idem |

**Seuils load test** : error rate < 0,1 %, p95 < 500 ms @ 200 req/s × 5 min.  
**Seuils Lighthouse** : Performance score > 90 (mobile simulé).

---

## 7. Checklist prod

- [ ] `REDIS_URL` — cache feed page 1 (60 s) + discover
- [ ] Index `(author_id, created_at)`, `(created_at)` — migration `0006_pin_feed_indexes`
- [ ] `python manage.py warm_discover_feed_cache` cron ~90 s
- [ ] nginx : pas de bypass `/media/` ; gzip JSON API
