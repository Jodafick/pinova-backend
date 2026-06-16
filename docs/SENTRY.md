# Sentry — observabilité FOTOCE

## Projets Sentry (3 apps)

| App | Package | Projet Sentry | Release CI |
|-----|---------|---------------|------------|
| Web | `@sentry/vue` | `fotoce-web` | `fotoce-web@${GITHUB_SHA}` |
| Mobile | `@sentry/react-native` | `fotoce-mobile` | `fotoce-mobile@${GITHUB_SHA}` |
| Backend | `sentry-sdk[django]` | `fotoce-backend` | `fotoce-backend@${GITHUB_SHA}` |

## Variables d'environnement

### Web (Vite / Vercel)
```env
VITE_SENTRY_DSN=https://...@sentry.io/...
VITE_SENTRY_RELEASE=fotoce-web@<git-sha>
SENTRY_AUTH_TOKEN=...          # CI uniquement
SENTRY_ORG=fotoce
SENTRY_PROJECT_WEB=fotoce-web
```

### Mobile (EAS / Expo)
```env
EXPO_PUBLIC_SENTRY_DSN=https://...@sentry.io/...
EXPO_PUBLIC_SENTRY_RELEASE=fotoce-mobile@<git-sha>
```

### Backend (Render / Railway)
```env
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=fotoce-backend@<git-sha>   # ou RENDER_GIT_COMMIT auto
SENTRY_TRACES_SAMPLE_RATE=0.1
```

## CI — source maps

Workflow `.github/workflows/sentry-release.yml` :
- Build web (`pnpm vite build`) avec `@sentry/vite-plugin` + source maps `hidden`
- Upload source maps vers Sentry
- Crée releases git-linked (`sentry-cli releases set-commits --auto`) pour web, backend, mobile

Secrets GitHub requis : `SENTRY_AUTH_TOKEN`, `VITE_SENTRY_DSN` (build web).

## Filtrage données sensibles

`beforeSend` / `scrubSentryEvent` sur les 3 apps :
- JWT / Bearer tokens
- Emails
- Clés `token`, `password`, `refresh`, `authorization`, `otp`, etc.

## perfMonitor (web)

Long tasks **> 50 ms** → breadcrumb Sentry `performance.longtask` (branché dans `src/lib/sentry.ts`).

## Alertes Sentry recommandées

Configurer dans **Sentry → Alerts → Create Alert** :

### 1. Error rate > 1 %
- Type : **Issues**
- Condition : `percentage(sessions_with_errors)` **> 1%** over **1 hour**
- Filtre : `environment:production`
- Action : Slack / email équipe

### 2. p95 API > 1 s
- Type : **Performance**
- Metric : `transaction.duration` p95
- Condition : **> 1000 ms**
- Filtre transaction : `transaction:/api/*` (backend Django)
- Fenêtre : 15 min

Le middleware `SentryApiTimingMiddleware` émet aussi un event `warning` pour chaque requête `/api/*` **≥ 1 s** (corrélation immédiate).

### 3. Webhook FedaPay failures
- Type : **Issues**
- Condition : message contains `FedaPay webhook failure`
- Tag : `fedapay.webhook=failure`
- Action : Pager / Slack #payments

Émis depuis `monetization/fedapay_webhook.py` via `capture_fedapay_webhook_failure`.

## Dashboard releases

1. Sentry → **Releases** → lier repo GitHub (Settings → Integrations → GitHub)
2. Activer **Suspect Commits** et **Release Health**
3. Dashboard custom :
   - Crash-free sessions par release (`fotoce-web@*`, `fotoce-mobile@*`, `fotoce-backend@*`)
   - Apdex / p95 latency API
   - Volume `fedapay.webhook` failures

## Vérification locale

```bash
# Backend
SENTRY_DSN=... python manage.py check

# Web (sans upload maps)
VITE_SENTRY_DSN=... pnpm vite build

# Test scrub
cd fotoce-backend && python manage.py test fotoce_backend.tests_sentry
```
