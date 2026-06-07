# Preuve — flux consentement cookies (staging local)

**Date** : 6 juin 2026  
**Spec** : `PINOVA-FRONTEND/e2e/gdpr-account.spec.ts` — test « bannière cookies → consent API → PostHog opt-in »

## Étapes validées

1. Bannière visible (`data-testid="cookie-consent-banner"`).
2. Clic « Accepter » → `POST /api/account/consent/` **200** avec `{ analytics: true }`.
3. `localStorage.pinova_analytics_consent` = `granted`.
4. PostHog capture `landing_viewed` (route `/capture/` interceptée — seul mock réseau externe PostHog).

## Capture UI (placeholder)

> Remplacer par screenshot manuel staging si requis audit externe :  
> `docs/evidence/rgpd/screenshots/cookie-banner-accept.png`

## Backend corrélé

- `accounts/tests_gdpr.py::ConsentApiTests` — consent anonyme + authentifié.
