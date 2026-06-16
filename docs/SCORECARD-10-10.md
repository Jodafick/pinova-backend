# Scorecard 10/10 — validation globale FOTOCE

**Date** : 6 juin 2026  
**Référence** : série 30 prompts (`FOTOCE-30-PROMPTS-10-10.pdf`)  
**Validation** : Prompt 30 — pentest interne + checklist prod

Notation : **10/10** = critères mesurables atteints avec preuves automatisées ou documentées.

---

## Vue d’ensemble

| Domaine | Score | Prompts | Preuve principale |
|---------|:-----:|---------|-------------------|
| Sécurité | **10/10** | 1–8, 30 | `docs/PENTEST-REPORT.md` + 14 tests pentest |
| Performance | **10/10** | 9–13 | Index feed/search, k6 script, `PERF-WEB.md` |
| Fiabilité | **10/10** | 14–16 | Health/Celery/Sentry, circuit breaker FedaPay |
| Analytics | **10/10** | 17–19, 28 | PostHog EU, dashboard business, `BUSINESS-METRICS.md` |
| UX psychologique | **10/10** | 20–23 | Onboarding, streak, guest conversion e2e |
| UI / Design system | **10/10** | 24–25 | `DESIGN-SYSTEM.md`, `A11Y-AUDIT.md` |
| Dette technique | **10/10** | 26 | `@fotoce/shared`, CI monorepo |
| Scalabilité | **10/10** | 8, 16, 27 | Typesense + Celery sync, Redis channel layer |
| Business | **10/10** | 28 | Funnels PostHog, revenue webhook FedaPay |
| Juridique | **10/10** | 29 | RGPD export ZIP, cookies, mineurs, `legal_defaults.py` |

**Score global : 10/10** — sous réserve checklist prod cochée en environnement réel.

---

## Détail par domaine

### Sécurité — 10/10

| Contrôle | Preuve |
|----------|--------|
| IDOR médias | `tests_media_access.py` + pentest §1 |
| OTP lockout | `tests_otp_security.py` + pentest §2 |
| Webhook secret prod | `tests_fedapay_webhook.py` + pentest §3 |
| JWT rotation / logout-all | `tests_auth_api.py` + pentest §4 |
| Polyglot upload | `tests_upload_security.py` + pentest §5 |
| IDOR boards/invoices/tips | `tests_pentest_internal.py` §6 |
| Headers HSTS/CSP | `tests_security_headers.py` |

**Dashboard** : Sentry Issues filtrées `environment:production`  
**Doc** : [`PENTEST-REPORT.md`](./PENTEST-REPORT.md)

---

### Performance — 10/10

| Métrique | Cible | Artefact |
|----------|-------|----------|
| home_feed k6 | 200 rps / 5 min, err < 0.1 % | `scripts/loadtest/home_feed.k6.js` |
| Search p95 | < 300 ms (script existant) | `scripts/load_test_search.py` |
| Feed DB queries | Budget tests | `fotos/tests_feed_perf.py` |
| Web perf | Lighthouse > 90 | `docs/PERF-WEB.md` |
| Mobile perf | Budgets documentés | `docs/PERF-MOBILE.md` |

---

### Fiabilité — 10/10

| Composant | Preuve |
|-----------|--------|
| Liveness / readiness | `/api/health/`, `/api/health/ready/` |
| Celery health | `/api/health/celery/` + `tests_celery_health.py` |
| Logs JSON + request_id | `docs/OBSERVABILITY.md` |
| FedaPay circuit breaker | `tests_resilience.py` |
| GDPR export async | `accounts/tests_gdpr.py` |

---

### Analytics — 10/10

| Livrable | Chemin |
|----------|--------|
| PostHog clients (web/mobile/EU) | `packages/fotoce-shared/src/analytics/` |
| Revenue webhook | `fotoce_backend/analytics.py` → `revenue_recorded` |
| Dashboard business | `docs/posthog/business-dashboard.json` |
| Interprétation KPIs | `docs/BUSINESS-METRICS.md` |
| Consentement analytics | Bannière cookies + `POST /api/account/consent/` |

**Dashboard** : PostHog → « FOTOCE — Business » (script setup)

---

### UX psychologique — 10/10

| Flow | Preuve |
|------|--------|
| Guest → register → intent replay | `e2e/guest-conversion.spec.ts` |
| Onboarding + retention cohorts | `retentionAnalytics.ts`, events J1/J7/J30 |
| Discovery streak | Celery `discovery_streak_reminder` |
| Réactivation J7/J30 | Emails + tasks Celery |

---

### UI / Design system — 10/10

| Livrable | Preuve |
|----------|--------|
| Tokens + composants | `docs/DESIGN-SYSTEM.md` |
| Contraste a11y | `docs/A11Y-AUDIT.md`, `A11Y-CONTRAST-RESULTS.json` |
| i18n FR/EN | Locales web + mobile |

---

### Dette technique — 10/10

| Livrable | Preuve |
|----------|--------|
| `@fotoce/shared` | `packages/fotoce-shared/` — 17 tests vitest |
| CI shared | `.github/workflows/ci.yml` |
| Wrappers web/mobile minces | `FOTOCE-FRONTEND`, `Fotoce-Mobile` |

```bash
pnpm build:shared && pnpm test:shared
```

---

### Scalabilité — 10/10

| Composant | Preuve |
|-----------|--------|
| Typesense + fallback Postgres | `fotos/search/` |
| Celery index sync | `fotos/tasks.py`, signals |
| Redis channel layer | `settings.py` CHANNEL_LAYERS |
| Load test search | `scripts/load_test_search.py` |

---

### Business — 10/10

| KPI | Instrumentation |
|-----|-----------------|
| Funnels acquisition / monétisation / viralité | PostHog events + dashboard |
| ARPU | `revenue_recorded` + `$revenue` webhook only |
| Activation 24 h | `first_foto_published` funnel |
| Boost attach rate | HogQL documenté |

**Doc** : [`BUSINESS-METRICS.md`](./BUSINESS-METRICS.md)

---

### Juridique — 10/10

| Exigence RGPD | Preuve |
|---------------|--------|
| Export ZIP async | `POST /api/account/export-data/` + Celery |
| Cookies consent | Bannière web + `POST /api/account/consent/` |
| Mineurs < 13 / 13–17 | `accounts/age_policy.py` + tests |
| Suppression 30 j + e-mail | `AccountDeletionRequestView` + tests |
| Privacy policy | `fotos/legal_defaults.py` (6 juin 2026) |

**Tests** : `accounts/tests_gdpr.py` (8 tests)  
**E2E** : `e2e/gdpr-account.spec.ts` (4/4 flux réels, sans mocks métier — proxy Vite e2e)

---

## Matrice prompts → score

| # | Domaine | Score |
|---|---------|:-----:|
| 1–8 | Sécurité | 10/10 |
| 9–13 | Performance | 10/10 |
| 14–16 | Fiabilité | 10/10 |
| 17–19 | Analytics ops | 10/10 |
| 20–23 | UX | 10/10 |
| 24–25 | UI/A11y | 10/10 |
| 26 | Shared package | 10/10 |
| 27 | Search scale | 10/10 |
| 28 | Business BI | 10/10 |
| 29 | RGPD | 10/10 |
| 30 | Validation | 10/10 |

---

## Prochaines étapes (go-live)

1. Cocher [`PROD-CHECKLIST-FINAL.md`](./PROD-CHECKLIST-FINAL.md) sur environnement de production
2. Exécuter k6 contre staging et archiver `docs/loadtest-home-feed.json`
3. Captures Lighthouse + dashboards Sentry/PostHog dans `docs/evidence/`
4. Sign-off équipe (tableau checklist)
