# Runbook fiabilité FOTOCE

**Date** : 6 juin 2026  
**Tests** : `python manage.py test fotoce_backend.tests_failure_modes -v 2`  
**Probes** : `/api/health/` (liveness), `/api/health/ready/` (readiness)

---

## 1. Matrice dépendances

| Dépendance | Critique readiness | Symptôme panne | Dégradation |
|------------|-------------------|----------------|-------------|
| PostgreSQL | Oui | 503 ready | Aucune — incident P0 |
| Redis (`REDIS_URL`) | Oui si défini | 503 ready, health `degraded` | Cache/throttle non partagés ; OTP/WS fail-open |
| Celery broker | Oui | 503 ready | Exports, emails batch, purge en retard |
| Celery workers | Non (optionnel health) | `no_workers` dans health | Tâches beat en file |
| FedaPay | Non | Checkout 502/503 lisible | Paiements indisponibles |
| SMTP / Resend | Non | `email_delivery_unavailable` | Register/OTP bloqués ; export async OK |
| Sentry | Non | Pas d’alertes | Observabilité réduite |

---

## 2. Probes Kubernetes / Render

```yaml
livenessProbe:
  httpGet:
    path: /api/health/
    port: 8000
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /api/health/ready/
    port: 8000
  periodSeconds: 10
  failureThreshold: 3
```

| Endpoint | 200 | 503 |
|----------|-----|-----|
| `/api/health/` | DB up (status `ok` ou `degraded`) | DB down |
| `/api/health/ready/` | DB + Redis (si requis) + broker Celery | Toute dépendance critique down |
| `/api/health/celery/` | Broker up | Broker down |

**Chaos validé** : `REDIS_URL` pointant vers un Redis injoignable → `/api/health/ready/` **503** (`not_ready`), `/api/health/` **200** avec `checks.redis.ok=false`.

---

## 3. Redis indisponible

### Comportement

| Composant | Panne Redis | Stratégie |
|-----------|-------------|-----------|
| Health `/ready/` | `ok=false` | Retirer trafic (503) |
| Feed cache (`fotos/feed_cache.py`) | Miss systématique | DB seule, latence ↑ |
| Throttle DRF / django-ratelimit | Compteurs locaux ou erreur | LocMem si pas de `REDIS_URL` au boot |
| OTP lockout/resend (`accounts/otp_security.py`) | **Fail-open** | Pas de lockout ; cooldown ignoré |
| WS conn limit (`websocket/ratelimit.py`) | **Fail-open** | Connexions autorisées |
| Notifications WS (`notifications/realtime.py`) | Push-only | `group_send` échoue → log `degraded` |

### Actions incident

1. Vérifier `/api/health/ready/` → `checks.redis.detail`
2. Restaurer Redis managé (Render/Railway/Upstash)
3. Si urgence : retirer temporairement `REDIS_URL` → LocMem (throttle **non partagé** entre workers — documenter risque abus)
4. Cron : `python manage.py warm_discover_feed_cache` après retour Redis

---

## 4. FedaPay — circuit breaker

**Implémentation** : `monetization/fedapay_client.py` — seuil **5 échecs**, recovery **60 s**.

| Endpoint | Circuit ouvert | HTTP |
|----------|----------------|------|
| `POST /api/subscription/checkout/` | `FedaPay temporarily unavailable` | **503** |
| Boost / tip / promo checkout | Message dans `error` | **502** |
| Health `checks.fedapay` | `detail=circuit_open` | Non bloquant readiness |

**Logs** : `fotoce.resilience` (JSON structuré, champ `outcome`).

**Action** : attendre recovery ou `FEDAPAY_CIRCUIT.record_success()` après correction ; vérifier statut sandbox/live cohérent avec `FEDAPAY_ENV`.

---

## 5. Email (SMTP / Resend)

**Chaîne** : `accounts/mail_delivery.py` → Resend (retry 3×) → fallback SMTP → `EmailDeliveryUnavailable`.

| Flux | Code | HTTP | Notes |
|------|------|------|-------|
| `POST /api/register/` | `email_delivery_unavailable` | **400** | Compte créé puis rollback validation email |
| `POST /api/resend-otp/` | `email_delivery_unavailable` | **503** | Message UX français |
| `POST /api/account/export-data/` | — | **202** | Job Celery ; échec email ready = **log warning**, ZIP disponible via token |

Variables : `RESEND_API_KEY`, `EMAIL_HOST*`, `DEFAULT_FROM_EMAIL`.

---

## 6. Celery Beat — tâches critiques

Lancer en prod :

```bash
celery -A fotoce_backend worker -l info --concurrency=4
celery -A fotoce_backend beat -l info
```

| Clé beat | Tâche | Schedule (UTC) | Fallback manage.py |
|----------|-------|----------------|-------------------|
| `fotos-send-weekly-pro-digest` | `fotos.send_weekly_pro_digest` | Lun 09:00 | — |
| `fotos-purge-ephemeral-stories` | `fotos.purge_expired_ephemeral_stories` | `:15` chaque heure | `purge_expired_ephemeral_stories` |
| `fotos-publish-scheduled` | `fotos.publish_scheduled_fotos` | `*/5 min` | `publish_scheduled_fotos` |
| `accounts-enforce-subscriptions` | `accounts.enforce_subscriptions_due` | `*/10 min` | — |
| `accounts-purge-deletions` | `accounts.purge_scheduled_account_deletions` | 03:00 daily | — |
| `referrals-reward-scan` | `referrals.referral_reward_scan` | `*/15 min` | — |
| `referrals-retention-scan` | `referrals.referral_retention_scan` | 04:00 daily | — |
| `accounts-discovery-streak-reminder` | `accounts.discovery_streak_reminder` | 18:00 daily | — |
| `accounts-reactivation-j7-email` | `accounts.reactivation_j7_email` | 10:00 daily | `send_reactivation_j7_emails` |
| `accounts-reactivation-j30-email` | `accounts.reactivation_j30_email` | 10:30 daily | `send_reactivation_j30_emails` |
| `fotos-reindex-typesense-nightly` | `fotos.reindex_typesense` | 02:30 daily | — |

**Tâche async critique (hors beat)** : `accounts.export_user_data` — export RGPD.

**Retry policy** (`FotoceTask`) : 3 tentatives, backoff exponentiel, dead-letter log `celery dead letter`.

**Vérification** : `GET /api/health/celery/` → champ `beat_schedule` (11 clés).

---

## 7. Alertes Sentry recommandées

Configurer dans Sentry → Alerts (prod, env `production`).

### Redis / cache

| Alerte | Condition | Action |
|--------|-----------|--------|
| Readiness Redis down | Log ou synthetic : `/api/health/ready/` 503 + `redis.ok=false` | Pager ops ; restaurer Redis |
| Spike `ConnectionError` django-redis | >10 events / 5 min, message `redis` | Même runbook §3 |

### Celery

| Alerte | Condition | Action |
|--------|-----------|--------|
| Queue depth | Broker queue length > 500 pendant 10 min (metric Redis `LLEN celery`) | Scale workers |
| Dead letter | Log `celery dead letter` ≥ 1 / heure | Inspecter args + relancer commande manage.py |
| No workers | Health `workers.detail=no_workers` 3× / 15 min | Redémarrer worker |

### Webhooks FedaPay

| Alerte | Condition | Action |
|--------|-----------|--------|
| Webhook failure | Tag `fedapay.webhook=failure` (via `capture_fedapay_webhook_failure`) ≥ 5 / h | Vérifier signature, idempotence, circuit |
| Circuit open | Health `fedapay.detail=circuit_open` | Pause checkout marketing ; contacter FedaPay |

### API lente (existant)

| Alerte | Condition |
|--------|-----------|
| Slow API | Message `Slow API` level warning, tag `slow_api=true`, p95 > 1 s |

**PII** : `scrub_sentry_event` filtre JWT, emails, clés sensibles — ne pas activer `send_default_pii`.

---

## 8. Checklist observabilité (10/10)

- [ ] `SENTRY_DSN` + `SENTRY_ENVIRONMENT=production` + `SENTRY_RELEASE` (git SHA)
- [ ] Alertes §7 activées (Redis ready, Celery queue, webhook FedaPay)
- [ ] `REDIS_URL` identique worker / web / beat
- [ ] Probes `/api/health/` + `/api/health/ready/` configurées
- [ ] `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` prod (pas de wildcard credentials)
- [ ] Beat + worker déployés (pas seulement web)
- [ ] Tests panne CI : `fotoce_backend.tests_failure_modes`
- [ ] Runbook partagé on-call (lien vers ce fichier)
- [ ] Post-mortem template : dépendance, blast radius, MTTR, action préventive

---

## 9. Commandes diagnostic rapide

```bash
# Health
curl -sS https://api.example.com/api/health/ | jq '.status, .checks.redis, .checks.celery'
curl -sS https://api.example.com/api/health/ready/ | jq '.status'

# Celery inspect
celery -A fotoce_backend inspect ping
celery -A fotoce_backend inspect active_queues

# Tests panne locaux
cd fotoce-backend
python manage.py test fotoce_backend.tests_failure_modes fotoce_backend.tests.tests_health -v 2
```
