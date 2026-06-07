# Observabilité PINOVA — logs, health, corrélation, tracing

## Logs structurés (production)

En `DEBUG=False`, chaque requête API produit une ligne JSON via le logger `pinova.access` :

```json
{
  "timestamp": "2026-06-06T12:00:00+00:00",
  "level": "INFO",
  "event": "http_request",
  "request_id": "…",
  "user_id": 42,
  "path": "/api/pins/",
  "method": "GET",
  "latency_ms": 12.34,
  "status": 200
}
```

Les probes `/api/health/*` ne sont pas loguées (évite le bruit k8s/Render).

En développement (`DEBUG=True`), les logs restent en texte lisible (handler console standard).

## Health checks

| Endpoint | Usage | Code |
|----------|--------|------|
| `GET /api/health/` | Liveness + état DB, Redis, Celery, FedaPay | 200 si DB OK, sinon 503 |
| `GET /api/health/ready/` | Readiness k8s / Render | 200 si prêt, 503 sinon |
| `GET /api/health/celery/` | Détail Celery (compat) | 200/503 selon broker |

**Readiness** exige : PostgreSQL, broker Celery, Redis (si `REDIS_URL` / cache partagé activé).

**FedaPay** et workers Celery actifs sont informatifs sur `/api/health/` (statut `degraded` si absents, sans bloquer le readiness).

### Render / Kubernetes

```yaml
# Exemple probes
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
```

## Corrélation `X-Request-ID`

1. **Front web** (`PINOVA-FRONTEND/src/api.ts`) et **mobile** (`Pinova-Mobile/src/api/client.ts`) envoient un UUID v4 dans `X-Request-ID`.
2. **Backend** (`RequestIdMiddleware`) reprend ou génère l’ID, le propage dans les logs JSON et renvoie le header en réponse.
3. **Sentry** reçoit le tag `request_id` côté backend (middleware + captures FedaPay / API lentes) et côté clients (`setSentryRequestId`).

Pour retrouver une erreur Sentry : filtrer `request_id:<uuid>` et croiser avec les logs Render/Loki.

## OpenTelemetry (optionnel)

Activé uniquement si `OTEL_EXPORTER_OTLP_ENDPOINT` est défini (ex. Jaeger, Grafana Tempo, Datadog).

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.com/v1/traces
OTEL_SERVICE_NAME=pinova-backend
```

Packages requis (section optionnelle de `requirements.txt`) :

```bash
pip install opentelemetry-api opentelemetry-sdk \
  opentelemetry-exporter-otlp-proto-http \
  opentelemetry-instrumentation-django
```

Initialisation : `pinova_backend/otel.py` au démarrage Django (`AppConfig.ready`).

## Dev logs

- **Web** : `devLog()` (`src/devLog.ts`) — actif uniquement si `import.meta.env.DEV`.
- **Mobile** : logs API verbeux via `EXPO_PUBLIC_API_DEBUG_LOGS=1` ou `__DEV__` ; startup marks et config API base URL en `__DEV__` only.

## Variables d’environnement

Voir `pinova-backend/.env.example` (OTEL, health URLs en commentaire) et `docs/SENTRY.md` pour l’alerting.
