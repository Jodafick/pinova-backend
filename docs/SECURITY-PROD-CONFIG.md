# Configuration sécurité production PINOVA

**Date** : 6 juin 2026  
**Périmètre** : `pinova-backend` (API Django)  
**Validation** : `python manage.py check --deploy` + `audit_public_api_permissions --fail-on-findings`

---

## Variables obligatoires (`DEBUG=False`)

| Variable | Valeur attendue | Rôle | Check Django |
|----------|-----------------|------|--------------|
| `DEBUG` | `False` ou `0` | Désactive mode debug, active HSTS/CSP | `pinova.E001` |
| `DJANGO_SECRET_KEY` | Clé forte (≠ dev) | Sessions, JWT signing | `pinova.E002` |
| `ALLOWED_HOSTS` | Hôtes API (CSV) | Host header validation | Django natif |
| `CORS_ALLOWED_ORIGINS` | Origines web (CSV) | Pas de wildcard CORS | Django natif |
| `REDIS_URL` | `redis://…` | Cache partagé, throttles, Channels | `pinova.E003`–`E006` |
| `FEDAPAY_WEBHOOK_SECRET` | Secret partagé FedaPay | Validation webhooks paiement | `pinova.E007` |
| `MEDIA_SIGNING_SECRET` | Secret dédié (≠ `SECRET_KEY`) | URLs médias signées HMAC | `pinova.E008` |
| `JWT_AUTH_HTTPONLY` | `1` (défaut si `DEBUG=False`) | Refresh token cookie HttpOnly | `pinova.E009` |

---

## Durcissement automatique quand `DEBUG=False`

Défini dans `pinova_backend/settings.py` :

| Contrôle | Comportement |
|----------|--------------|
| **HSTS** | `SECURE_HSTS_SECONDS=31536000` (1 an), sous-domaines activés |
| **SSL** | `SECURE_SSL_REDIRECT=True`, `SECURE_PROXY_SSL_HEADER` pour reverse proxy |
| **CSP** | En-tête via `ContentSecurityPolicyMiddleware` — `default-src 'self'`, PostHog EU autorisé |
| **Cookies** | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `JWT_AUTH_SECURE=True` |
| **JWT HttpOnly** | `REST_AUTH['JWT_AUTH_HTTPONLY']=True` — refresh **uniquement** cookie `pinova-refresh-token` |
| **CORS** | Origines explicites obligatoires (`CORS_ALLOWED_ORIGINS`) |

### Exemple `.env` production

```env
DEBUG=False
DJANGO_SECRET_KEY=<générer-50+-chars>
ALLOWED_HOSTS=api.pinova.app
CORS_ALLOWED_ORIGINS=https://app.pinova.app
CSRF_TRUSTED_ORIGINS=https://app.pinova.app
REDIS_URL=redis://default:xxx@redis-host:6379/0
FEDAPAY_WEBHOOK_SECRET=<secret-fourni-ou-généré>
MEDIA_SIGNING_SECRET=<secret-dédié-médias>
JWT_AUTH_HTTPONLY=1
SECURE_HSTS_PRELOAD=True
```

---

## Redis — pourquoi obligatoire

Sans `REDIS_URL`, le backend bascule sur :

- `LocMemCache` → throttles DRF / OTP **non partagés** entre workers Gunicorn
- `InMemoryChannelLayer` → WebSockets non synchronisés multi-instance

En production, **tous les workers doivent partager le même compteur** (OTP, login, webhooks).

---

## Secrets paiement et médias

### `FEDAPAY_WEBHOOK_SECRET`

- Vérifié sur chaque `POST /api/subscription/webhook/fedapay/`
- Sans secret en prod : `get_fedapay_webhook_secret()` lève une exception au démarrage du traitement
- Throttle : `WebhookIPThrottle` (100/min/IP) + `django-ratelimit`

### `MEDIA_SIGNING_SECRET`

- HMAC-SHA256 sur `relative_path:exp:uid`
- TTL par défaut : 3600 s (`MEDIA_SIGNED_URL_TTL_SECONDS`)
- Ne **pas** réutiliser `DJANGO_SECRET_KEY` — rotation indépendante

---

## Audit permissions API

```bash
cd pinova-backend
python manage.py audit_public_api_permissions --fail-on-findings
```

Endpoints `AllowAny` avec throttle dédié (documentés dans `permissions_audit.py`) :

- `VerifyOTPView` — `OtpVerifyIPThrottle` + ratelimit
- `ResendOTPView` — `OtpResendEmailThrottle` + ratelimit
- `SubscriptionWebhookView` — `WebhookIPThrottle` + ratelimit

Tous les autres endpoints publics héritent des throttles DRF par défaut (`AnonIPRateThrottle`, etc.).

---

## Commandes de validation CI

```bash
cd pinova-backend
python manage.py test pinova_backend.tests.tests_pentest_internal \
  pinova_backend.tests.tests_media_access \
  pinova_backend.tests.tests_security_headers \
  monetization.tests_fedapay_webhook accounts.tests_otp_security -v 1
python manage.py audit_public_api_permissions --fail-on-findings
python manage.py check --deploy
```

Voir aussi : `scripts/run_pentest_validation.ps1`, `docs/PENTEST-EXTERNAL-SIMULATION.md`, `docs/evidence/pentest-2026-06-06.json`.
