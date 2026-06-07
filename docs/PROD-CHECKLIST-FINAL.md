# Checklist production FINALE — PINOVA Prompt 30/30

Cocher chaque item **avant** mise en production. Preuves à archiver dans `docs/evidence/` (captures, exports JSON, liens dashboards).

---

## Infrastructure

- [ ] **Redis cache + channel layer** — `REDIS_URL` ou `PINNOVA_REDIS_URL` défini ; `/api/health/ready/` → Redis OK  
  _Preuve : curl health + `docs/OBSERVABILITY.md`_

- [ ] **Celery worker + beat** — worker actif + beat schedule (`pinova_backend/celery.py`)  
  _Preuve : `/api/health/celery/` 200 ; tâches purge/export/reactivation planifiées_

- [ ] **PostgreSQL** — migrations appliquées (`python manage.py migrate`)  
  _Preuve : `python manage.py showmigrations` sans `[ ]` en prod_

---

## Observabilité & analytics

- [ ] **Sentry actif** — `SENTRY_DSN` + `SENTRY_ENVIRONMENT=production`  
  _Preuve : erreur test contrôlée visible dashboard ; voir `docs/SENTRY.md`_

- [ ] **PostHog actif** — `POSTHOG_API_KEY` backend + clés web/mobile ; dashboard business créé  
  _Preuve : event `revenue_recorded` webhook ; script `pinova-backend/scripts/setup_posthog_business_dashboard.py`_

---

## Sécurité

- [ ] **FEDAPAY_WEBHOOK_SECRET set** — jamais vide si `DEBUG=False`  
  _Preuve : `monetization/tests_fedapay_webhook.py` ; pentest §3_

- [ ] **DEBUG=False** — `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` configurés  
  _Preuve : `python manage.py check --deploy`_

- [ ] **HSTS on** — `SECURE_HSTS_SECONDS` (défaut 1 an si `DEBUG=False`)  
  _Preuve : `curl -I https://api...` → `Strict-Transport-Security`_

- [ ] **CDN médias signed URLs** — bucket privé ; pas d’accès direct S3 ; `MEDIA_SIGNING_SECRET` unique  
  _Preuve : pin privé → 403 sans sig ; pentest §1_

- [ ] **JWT HttpOnly refresh** — `JWT_AUTH_HTTPONLY=1` en prod  
  _Preuve : DevTools → cookie `pinova-refresh-token` HttpOnly+Secure_

---

## Performance & qualité

- [ ] **Lighthouse web > 90 performance** — page d’accueil PWA production  
  _Preuve : rapport Lighthouse PDF/JSON dans `docs/evidence/` ; voir `docs/PERF-WEB.md`_

- [ ] **Load test k6 home_feed** — 200 req/s × 5 min, erreurs < 0.1 %  
  _Preuve : `docs/loadtest-home-feed.json` export k6_

---

## Livraison prompts 1–29

- [ ] **Tous prompts 1–29 mergés** — branche `main` / release tag contient :  
  - Sécurité auth/médias/webhook (prompts 1–8)  
  - Perf search/cache/frontend (9–13)  
  - Fiabilité Celery/health (14–16)  
  - Analytics PostHog (17–19)  
  - UX onboarding/rétention (20–23)  
  - Design system + a11y (24–25)  
  - `@pinova/shared` (26)  
  - Scalabilité search Typesense (27)  
  - Dashboard business (28)  
  - RGPD export/cookies/mineurs (29)  

  _Preuve : tag git + `PINOVA-30-PROMPTS-10-10.pdf`_

---

## RGPD & juridique (prompt 29 — staging validé 6 juin 2026)

- [x] **Export RGPD async** — `POST /api/account/export-data/` → Celery eager/staging → e-mail → ZIP 24 h  
  _Preuve : `accounts/tests_gdpr.py` ; e2e `gdpr-account.spec.ts` (download `504b` ZIP) ; `docs/evidence/rgpd/backend-tests-gdpr.log`_

- [x] **Bannière cookies → consent API → PostHog opt-in** — `POST /api/account/consent/` + localStorage  
  _Preuve : e2e `gdpr-account.spec.ts` + `analytics-consent.spec.ts` ; capture `docs/evidence/rgpd/cookie-consent-flow.md`_

- [x] **Mineurs** — `< 13` rejeté (PATCH birth_date) ; `13–17` publish bloqué  
  _Preuve : `accounts/age_policy.py` ; `accounts/tests_gdpr.py` ; e2e mineurs dans `gdpr-account.spec.ts`_

- [x] **Suppression compte 30 j** — confirmation SUPPRIMER/DELETE → e-mail → export optionnel → purge planifiée  
  _Preuve : `AccountDeletionRequestView` ; e2e suppression dans `gdpr-account.spec.ts` ; `docs/evidence/rgpd/deletion-flow.md`_

- [x] **Textes légaux à jour** — `pins/legal_defaults.py` (privacy + CGU 6 juin 2026) + section revue avocat (placeholder)  
  _Preuve : `docs/evidence/rgpd/legal-defaults-dates.json`_

- [x] **E2E Playwright sans mocks métier** — `e2e/gdpr-account.spec.ts` contre API locale `127.0.0.1:8000`  
  _Preuve : `docs/evidence/rgpd/playwright-gdpr.log` ; `playwright.config.ts` (webServer backend + frontend)_

---

## Commandes de validation rapide

```bash
# Backend
cd pinova-backend
python manage.py check --deploy
python manage.py test pinova_backend.tests_pentest_internal -v 1
curl -s https://<API>/api/health/ready/ | jq .

# Load test (staging)
k6 run -e BASE_URL=https://<API> -e AUTH_TOKEN=<jwt> \
  --summary-export=docs/loadtest-home-feed.json \
  scripts/loadtest/home_feed.k6.js

# Pentest automatisé complet
python manage.py test pinova_backend.tests_pentest_internal \
  pinova_backend.tests_media_access monetization.tests_fedapay_webhook \
  accounts.tests_otp_security accounts.tests_gdpr -v 2
```

---

## Sign-off

| Rôle | Nom | Date | OK |
|------|-----|------|-----|
| Tech lead | | | [ ] |
| Sécurité | | | [ ] |
| Produit | | | [ ] |
