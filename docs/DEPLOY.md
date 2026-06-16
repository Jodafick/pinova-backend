# Déploiement Fotoce Backend

Guide pour **API web**, **worker Celery** et **beat Celery** (Render, Railway, ou VPS).

## Prérequis communs

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL |
| `REDIS_URL` / `PINNOVA_REDIS_URL` | Cache feed + broker Celery |
| `DJANGO_SECRET_KEY` | Secret Django |
| `ALLOWED_HOSTS` | Hôtes API |
| `CORS_ALLOWED_ORIGINS` | Origines frontend |

Celery (optionnel en dev avec `CELERY_TASK_ALWAYS_EAGER=True`) :

| Variable | Défaut |
|----------|--------|
| `CELERY_BROKER_URL` | `REDIS_URL` ou `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | = broker |
| `CELERY_TASK_TIME_LIMIT` | `300` (secondes) |
| `CELERY_RESULT_EXPIRES` | `86400` |

## Services à déployer

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Web (API)  │     │ Celery Worker│     │ Celery Beat │
│  gunicorn   │     │  tâches async│     │  planif.    │
└──────┬──────┘     └──────┬───────┘     └──────┬──────┘
       │                   │                    │
       └───────────────────┴────────────────────┘
                           │
                    ┌──────▼──────┐
                    │    Redis    │
                    │ broker/cache│
                    └─────────────┘
```

### 1. Web — API Django

**Start command :**

```bash
gunicorn fotoce_backend.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

**Health :** `GET /api/health/` (liveness), `GET /api/health/ready/` (readiness Render/k8s), `GET /api/health/celery/` (détail Celery). Voir `docs/OBSERVABILITY.md`.

### 2. Celery Worker

**Start command :**

```bash
celery -A fotoce_backend worker -l info --concurrency=2
```

Consomme la queue `default`. Retry automatique : **3× backoff exponentiel** (max 600 s, jitter). Échec final → log `fotoce.celery` **dead letter**.

### 3. Celery Beat (un seul instance)

**Start command :**

```bash
celery -A fotoce_backend beat -l info
```

> Un seul process beat par environnement (évite les doublons de tâches planifiées).

## Beat schedule (UTC)

Documenté dans `fotoce_backend/celery.py` :

| Clé beat | Tâche | Fréquence |
|----------|-------|-----------|
| `fotos-send-weekly-pro-digest` | `fotos.send_weekly_pro_digest` | Lundi 09:00 |
| `fotos-purge-ephemeral-stories` | `fotos.purge_expired_ephemeral_stories` | Chaque heure :15 |
| `fotos-publish-scheduled` | `fotos.publish_scheduled_fotos` | */5 min |
| `accounts-enforce-subscriptions` | `accounts.enforce_subscriptions_due` | */10 min |
| `accounts-purge-deletions` | `accounts.purge_scheduled_account_deletions` | Quotidien 03:00 |
| `referrals-reward-scan` | `referrals.referral_reward_scan` | */15 min |
| `referrals-retention-scan` | `referrals.referral_retention_scan` | Quotidien 04:00 |

Les commandes `manage.py` restent disponibles pour exécution manuelle ou secours cron.

## Render

Créer **3 Web Services** (ou 1 Web + 2 Background Workers) depuis le même repo `fotoce-backend` :

| Service | Type | Build | Start |
|---------|------|-------|-------|
| `fotoce-api` | Web | `pip install -r requirements.txt && python manage.py collectstatic --noinput` | gunicorn … |
| `fotoce-celery-worker` | Worker | idem | `celery -A fotoce_backend worker -l info` |
| `fotoce-celery-beat` | Worker | idem | `celery -A fotoce_backend beat -l info` |

- Lier le **Redis Render** ; injecter `REDIS_URL` sur les 3 services.
- Même `DATABASE_URL` et secrets Django sur les 3.
- Health check API : `/api/health/ready/` (readiness) ; `/api/health/` (liveness).

## Railway

Créer **3 services** dans le même projet :

1. **API** — Dockerfile ou Nixpacks, start `gunicorn …`
2. **Worker** — start `celery -A fotoce_backend worker -l info`
3. **Beat** — start `celery -A fotoce_backend beat -l info`

Ajouter le plugin **Redis** ; Railway expose `REDIS_URL` automatiquement.

Variables partagées via Railway **Shared Variables** ou **Reference Variables**.

## Développement local

```bash
cd fotoce-backend
python -m venv .venv && source .venv/bin/activate  # ou .venv\Scripts\activate
pip install -r requirements.txt
export REDIS_URL=redis://127.0.0.1:6379/0

# Terminal 1 — API
python manage.py runserver

# Terminal 2 — worker
celery -A fotoce_backend worker -l info

# Terminal 3 — beat
celery -A fotoce_backend beat -l info
```

Sans Redis : `CELERY_TASK_ALWAYS_EAGER=True` (tâches synchrones, pas de worker requis).

## Vérifications post-déploiement

```bash
curl -s https://api.example.com/api/health/celery/ | jq
python manage.py check --deploy
```

Réponse attendue (broker OK, workers actifs) :

```json
{
  "status": "ok",
  "broker": {"ok": true, "detail": "ok"},
  "workers": {"ok": true, "detail": "ok", "count": 1},
  "beat_schedule": ["accounts-enforce-subscriptions", "..."]
}
```

## Fichiers Celery

| Fichier | Rôle |
|---------|------|
| `fotoce_backend/celery.py` | App, `FotoceTask`, beat schedule |
| `fotos/tasks.py` | Digest, stories, publication planifiée |
| `accounts/tasks.py` | Abonnements, suppressions compte |
| `referrals/tasks.py` | Récompenses + rétention |
| `fotoce_backend/health_views.py` | `/api/health/celery/` |
