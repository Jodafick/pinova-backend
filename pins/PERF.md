# Performance — fils de pins (feed)

Pattern pour servir une page de **10 pins** en **≤ 5 requêtes SQL** (hors auth/session).

## Budget requêtes (page feed 10 pins)

| # | Requête | Rôle |
|---|---------|------|
| 1 | `COUNT(*)` | Pagination DRF (`PinFeedPagination`) |
| 2 | `SELECT pins …` | Pins + `select_related(author, topic)` + annotations viewer |
| 3 | Prefetch `hashtags` | M2M hashtags |
| 4 | Prefetch `pin_board_memberships` + `board` | Boards ordonnés par position |
| 5 | Prefetch `variant_assets` | Variantes story / ratios |

La **sérialisation** (`PinSerializer`) ne doit ajouter **aucune** requête si le queryset passe par `optimize_pin_feed_queryset`.

## Module `feed_queryset.py`

```python
from pins.feed_queryset import optimize_pin_feed_queryset, feed_serializer_context

qs = PinViewSet().get_queryset()
qs = optimize_pin_feed_queryset(qs, request)
page = list(qs[:10])
ctx = feed_serializer_context(request, {'request': request})
PinSerializer(page, many=True, context=ctx).data  # 0 requête supplémentaire
```

### Annotations queryset (Subquery / Exists)

Sur le queryset **parent**, avant pagination :

- `_feed_likes_count`, `_feed_comments_count`, `_feed_saves_count` — `Subquery` + `Coalesce` (préfixés : pas de conflit avec `@property` du modèle)
- `_is_liked`, `_is_saved` — `Exists(Like/Save)`
- `_is_boosted` — `Exists(PinBoost actif)`
- `_can_comment` — `Case/When` + `Exists` followers
- `_viewer_has_reported_pin` — `Exists(ContentReport)` (déjà présent sur `get_queryset`, non dupliqué)

`PinSerializer` lit ces champs via `getattr(obj, '_is_liked', None)` et retombe sur une requête unitaire hors feed (retrieve, etc.).

### Prefetch relations

```python
prefetch_related(
    'hashtags',
    'variant_assets',
    Prefetch(
        'pin_board_memberships',
        queryset=PinBoard.objects.select_related('board').order_by('position', 'id'),
    ),
)
```

`get_boards()` utilise `obj.pin_board_memberships.all()` (cache prefetch), plus `PinBoard.objects.filter(pin=obj)`.

## Following feed — `is_following` sans N+1

Une seule requête M2M au début de l’action `following` :

```python
rows = list(request.user.profile.following.values_list('pk', 'user_id'))
request._viewer_following_profile_ids = frozenset(r[0] for r in rows)
```

`feed_serializer_context` propage `_viewer_following_profile_ids` à `ProfileSerializer.get_is_following` (lookup en mémoire).

En mode feed, `followers_count` / `following_count` retournent `0` (évite 2×N requêtes auteur).

## Recommendations — boosts batch

`recommendation_engine.rank_recommendations_for_user` :

1. `active_boosted_pin_ids()` — **1 requête** pour tous les boosts actifs
2. Passe `boosted_pin_ids` à `recommendation_score` (plus de `PinBoost.objects.filter(pin=…).exists()` par pin)
3. Applique `annotate_pin_feed` + `prefetch_pin_feed_relations` avant le tri Python

## Intégration ViewSet

Actions feed : `list`, `discover`, `following`, `home_feed`, `recommendations`, `header_search`.

- `get_queryset()` : pas de prefetch générique sur ces actions (délégué à `optimize_pin_feed_queryset`)
- `_feed_response_with_ads` / `_feed_response_with_ads_paginated` : appellent `_optimize_feed_page_items`
- `get_serializer_context()` : injecte `feed_mode` + following IDs

## Tests

```bash
python manage.py test pins.tests_feed_perf -v 2
```

- `test_following_feed_http_max_five_queries` — endpoint HTTP, `assertNumQueries(5)`
- `test_feed_serialization_zero_extra_queries` — sérialisation après prefetch, `assertNumQueries(0)`

## Debug

Activer `django-debug-toolbar` ou logger :

```python
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as ctx:
    ...
print(len(ctx.captured_queries))
```

Objectif prod : **p95 < 200 ms** page 1 (10 pins) avec ce pattern + indexes `(created_at)`, `(author_id, created_at)` (voir migration `0006_pin_feed_indexes`).

## Cache Redis (feed + stats)

Module `pins/feed_cache.py` — TTL et clés versionnées :

| Scope | TTL | Clé | Invalidation |
|-------|-----|-----|--------------|
| `home_feed` page 1 | 60 s | `pinova:feed:home:v{ver}:{user_id}:p1:…` | Bump `ver` abonnés quand un auteur suivi publie |
| `discover` page 1 global | 120 s | `pinova:feed:discover:g{gver}:global:p1:…` | Bump `gver` à chaque pin public |
| `discover` page 1 user | 120 s | `pinova:feed:discover:g{gver}:u{uver}:{user_id}:…` | Bump `uver` / `gver` |
| `creator_stats` | 90 s | `pinova:creator_stats:v{ver}:{user_id}:…` | Bump `ver` à chaque pin auteur |

- Header debug : **`X-Cache: HIT|MISS`**
- Bypass : `?no_cache=1`
- Logs JSON : logger `pinova.cache` (`event`, `cache_scope`, `cache_key`, `user_id`)
- Redis : `REDIS_URL` ou `PINNOVA_REDIS_URL` → `django-redis` ; sinon LocMem
- Cron warming : `python manage.py warm_discover_feed_cache` (toutes les ~90 s)

```bash
python manage.py test pins.tests_feed_cache -v 2
```
