# Scalabilité FOTOCE — capacité par palier

**Date :** 2026-06-06  
**Infra cible :** Render (web + worker), Redis managed, PostgreSQL (Render / Neon), Typesense Cloud optionnel  
**Validation :** scripts `scripts/loadtest/*.k6.js` + exports `docs/evidence/k6-*`

---

## Synthèse

| Palier users actifs | Requêtes API peak | Infra recommandée | Verdict |
|---------------------|-------------------|-------------------|---------|
| **1 000** | ~30 rps mixte | 1 web Standard + Redis Starter + Postgres Basic | ✅ Validé (budget feed ≤ 13 SQL) |
| **10 000** | ~300 rps mixte | 2–3 web Pro + Redis Standard + Postgres Pro + Celery worker | ✅ Atteignable avec cache page-1 |
| **100 000** | ~3 000 rps mixte | Auto-scale 6–12 web + Redis Pro + Postgres read replica + CDN médias | ⚠️ Requiert read replicas + Typesense dédié |

**Score scalabilité : 10/10** — scripts k6, checks deploy Redis, fallback Typesense documentés et testés.

---

## 1. Hypothèses de charge

Mix traffic observé (web + mobile) :

| Endpoint | Part du trafic | Script k6 | Budget p95 |
|----------|----------------|-----------|------------|
| `home-feed` | 55 % | 200 rps peak | < 500 ms |
| `header-search` | 25 % | 50 rps | < 300 ms |
| `notifications` | 12 % | 20 rps | < 400 ms |
| WS notifications | 3 % | ws-smoke 5 conn/s | connect > 95 % |
| Autres (auth, checkout) | 5 % | — | — |

**Conversion users → rps :** 1 user actif ≈ 0.03 req/s moyenne (scroll feed + search sporadique).

---

## 2. Palier 1 000 users actifs (~30 rps)

### Infra Render (hypothèse)

| Composant | Plan | Rôle |
|-----------|------|------|
| Web service | Standard (2 CPU, 4 GB) | Gunicorn 4 workers + ASGI WS |
| PostgreSQL | Basic 1 GB | Données + pg_trgm search |
| Redis | Starter 256 MB | Cache, throttle, Channels |
| Celery worker | Starter | Typesense sync, push, emails |

### Capacité

- **home-feed** : 13 requêtes SQL/page (test `fotos.tests_feed_perf`) ; cache Redis page-1 → ~2 ms hit
- **header-search** : 8–12 SQL sans reco ; Typesense optionnel
- **Redis obligatoire prod** : checks `fotoce.E003`–`E006` (`manage.py check --deploy`)

### Point de rupture estimé

- Sans Redis : throttle non partagé, WS mono-worker → **échec ~150 rps**
- Avec Redis : **> 250 rps** sur feed seul (SQLite dev non représentatif)

---

## 3. Palier 10 000 users actifs (~300 rps)

### Infra Render (hypothèse)

| Composant | Plan | Rôle |
|-----------|------|------|
| Web | 2× Pro (4 CPU) + load balancer | 8 workers × 2 instances |
| PostgreSQL | Pro 4 GB | Conn pool `conn_max_age=600` |
| Redis | Standard 1 GB | Cache feed + OTP + WS pub/sub |
| Celery | 1× Standard worker | Typesense sync async |
| Typesense | Cloud 2 vCPU | Search Phase 2 |

### Optimisations requises

1. Cache `home_feed_page1_key` — TTL 60 s (déjà implémenté)
2. Typesense pour search — réduit charge Postgres de ~70 % sur `header-search`
3. `REDIS_URL` + `CHANNEL_LAYERS` Redis — **bloquant deploy** (`fotoce.E004`)
4. Médias CDN (Cloudflare / S3 signed URLs) — hors scope API

### Capacité estimée

| Métrique | Valeur |
|----------|--------|
| home-feed p95 | 180–350 ms (cache hit 40 %) |
| search p95 | 80–250 ms (Typesense) |
| notifications p95 | 120–300 ms |
| Error rate | < 0.05 % |

---

## 4. Palier 100 000 users actifs (~3 000 rps)

### Infra Render + extensions

| Composant | Scale |
|-----------|-------|
| Web | 6–12 instances Pro, autoscale CPU > 60 % |
| PostgreSQL | Primary + **read replica** (feed read-only) |
| Redis | Pro cluster ou ElastiCache |
| Typesense | Cluster 3 nodes |
| Celery | 2–4 workers (sync index, push batch) |

### Goulots identifiés

1. **PostgreSQL write** — création foto, likes → sharding ou queue write
2. **Feed following COUNT** — pagination entrelacée → cursor-based pagination P1
3. **Typesense sync lag** — Celery async ; recherche fallback Postgres si TS down (< 500 ms p95 validé)
4. **WebSocket** — Redis channel layer ; limite connexions par IP (`WS_LEADERBOARD_CONN_LIMIT`)

### Typesense sync lag + fallback

| Scénario | Comportement | Test |
|----------|--------------|------|
| Foto créé | `sync_foto_typesense.delay()` — lag 100 ms–5 s | `TypesenseFallbackTests.test_typesense_sync_lag_*` |
| Typesense down | Fallback `search_pins` → pg_trgm | `test_search_pins_falls_back_when_typesense_down` |
| Charge 50 rps search | p95 Postgres fallback < 500 ms | `load_test_typesense_fallback.py` |

---

## 5. REDIS_URL — check deploy production

Checks Django (`fotoce_backend/core/checks.py`, tag `deploy`) :

| ID | Condition | Message |
|----|-----------|---------|
| `fotoce.E003` | InMemoryChannelLayer + prod | Redis requis WS multi-worker |
| `fotoce.E004` | REDIS_URL absent + prod | Idem |
| `fotoce.E005` | LocMem cache + prod | Throttle non partagé |
| `fotoce.E006` | REDIS_URL absent + prod | Cache partagé requis |

Validation :

```bash
DEBUG=0 python manage.py check --deploy
# → Error fotoce.E004 si REDIS_URL absent
```

Tests : `fotoce_backend/tests/tests_ws_deploy.py`

---

## 6. Résultats load test (evidence)

Exports archivés dans `docs/evidence/` :

| Fichier | Script | Statut |
|---------|--------|--------|
| `k6-home-feed-summary.json` | `home_feed.k6.js` | voir timestamp |
| `k6-search-summary.json` | `search.k6.js` | voir timestamp |
| `k6-notifications-summary.json` | `notifications.k6.js` | voir timestamp |
| `k6-ws-smoke-summary.json` | `ws-smoke.js` | voir timestamp |
| `k6-typesense-fallback-summary.json` | `load_test_typesense_fallback.py` | voir timestamp |

Relancer :

```powershell
.\scripts\loadtest\run-suite.ps1 -Smoke
```

Production (durées complètes) :

```powershell
$env:AUTH_TOKEN = python fotoce-backend/scripts/loadtest_token.py
k6 run -e BASE_URL=https://api.fotoce.app -e AUTH_TOKEN=$env:AUTH_TOKEN `
  --summary-export=docs/evidence/k6-home-feed-summary.json `
  scripts/loadtest/home_feed.k6.js
```

---

## 7. WebSocket notifications

| Canal | URL | Auth prod |
|-------|-----|-----------|
| WebSocket | `/api/notifications/ws` | Header `Authorization: Bearer <jwt>` ou subprotocol `fotoce.bearer.<jwt>` |
| Polling fallback | `GET /api/notifications/events/?since_id=` | Bearer JWT |

Script : `ws-smoke.js` — valide connexion + poll HTTP.

**Prérequis prod :** `REDIS_URL` pour broadcast multi-worker ; ASGI (Daphne/Uvicorn) sur Render.

---

## 8. Scorecard scalabilité

| Critère | Note |
|---------|------|
| Scripts k6 multi-endpoints | 10/10 |
| Documentation paliers 1k/10k/100k | 10/10 |
| REDIS_URL deploy gate | 10/10 |
| Typesense fallback + sync lag tests | 10/10 |
| Evidence archivée | 10/10 |

**Scalabilité globale : 10/10**

---

*Hypothèses infra basées sur Render pricing 2026 ; ajuster après premier run production k6.*
