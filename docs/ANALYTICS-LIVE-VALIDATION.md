# Validation analytics live FOTOCE — PostHog EU

**Date** : 6 juin 2026  
**Dashboard** : `FOTOCE — Business`  
**Evidence machine** : `docs/evidence/posthog-analytics-live.json` (généré par le script setup)

---

## 1. Déploiement dashboards (conditions réelles)

```powershell
cd fotoce-backend
$env:POSTHOG_PERSONAL_API_KEY = "phx_..."   # Personal API key PostHog
$env:POSTHOG_PROJECT_ID = "12345"            # ID projet (Settings → Project)
$env:POSTHOG_HOST = "https://eu.posthog.com" # optionnel, défaut EU
python scripts/setup_posthog_business_dashboard.py
```

Le script :

1. Crée ou réutilise le dashboard **FOTOCE — Business**
2. Ajoute les 11 insights depuis `docs/posthog/business-dashboard.json` (sans doublon)
3. Vérifie les 19 événements business via l’API + HogQL 90 jours
4. Écrit `docs/evidence/posthog-analytics-live.json`

Vérification events seule :

```bash
python scripts/verify_posthog_business_events.py --json docs/evidence/posthog-events-validation.json
```

---

## 2. URLs dashboards (à compléter après déploiement)

| Ressource | URL |
|-----------|-----|
| **Dashboard business** | `https://eu.posthog.com/project/{PROJECT_ID}/dashboard/{DASHBOARD_ID}` |
| Live events | `https://eu.posthog.com/project/{PROJECT_ID}/events` |
| Event definitions | `https://eu.posthog.com/project/{PROJECT_ID}/data-management/events` |
| HogQL | `https://eu.posthog.com/project/{PROJECT_ID}/insights/new#hogql` |

> Remplacez `{PROJECT_ID}` / `{DASHBOARD_ID}` par les valeurs de `posthog-analytics-live.json` → `dashboard.url`.

---

## 3. Événements requis — définition & source

| Événement | Source | Définition produit |
|-----------|--------|-------------------|
| `landing_viewed` | Web (`HomePage`, invité) | Première vue landing / home sans session |
| `register_started` | Web, mobile | Soumission formulaire inscription |
| `register_completed` | Web, mobile | Compte créé + OTP envoyé |
| `register_with_ref_code` | Backend | Inscription avec code parrain consommé |
| `onboarding_started` | Web, mobile | Début parcours onboarding (`trackOnce`) |
| `onboarding_step_viewed` | Web, mobile | Affichage étape N |
| `onboarding_step_completed` | Web, mobile | Étape validée |
| `onboarding_step_skipped` | Web, mobile | Étape ignorée |
| `onboarding_completed` | Web, mobile | Onboarding terminé (`trackOnce`) |
| `first_foto_published` | Web, mobile | Premier foto/story publié (`trackOnce`) |
| `premium_viewed` | Web, mobile | Page Premium / Boost vue |
| `checkout_started` | Web, mobile | Clic paiement FedaPay (props `flow`) |
| `checkout_returned` | Web, mobile | Retour URL callback checkout |
| `checkout_success` | Client + backend | Paiement confirmé (filtrer `revenue_source`) |
| `revenue_recorded` | **Backend webhook** | Revenu authoritative (`$revenue`, FedaPay) |
| `referral_link_opened` | Backend intent | Ouverture lien `?ref=` |
| `retention_cohort_j1` | Web, mobile | Passage J+1 (`trackOnce`, canal) |
| `retention_cohort_j7` | Web, mobile | Passage J+7 |
| `retention_cohort_j30` | Web, mobile | Passage J+30 |

**Propriétés transverses** : `signup_platform`, `signup_channel`, `flow`, `revenue_source`, `platform`.

---

## 4. Insights dashboard — interprétation

| Insight | Question business | Lecture |
|---------|-------------------|---------|
| Acquisition — landing → first foto | Où perd-on les visiteurs ? | 4 étapes, fenêtre 14 j, breakdown `signup_channel` |
| Monétisation premium / boost | Conversion payante par flow | `premium_viewed` → `checkout_started` → `revenue_recorded` webhook |
| Viralité referral | Efficacité parrainage | `referral_link_opened` → `register_with_ref_code` |
| Rétention J1/J7/J30 | Canaux qui reviennent | Volume `retention_cohort_j*` par `signup_channel` |
| Revenue FedaPay | CA réel | Somme `$revenue` où `revenue_source=fedapay_webhook` |
| Activation < 24 h | Time-to-value | `register_completed` → `first_foto_published` ≤ 1 jour |
| Guest conversion | Invité → compte | `register_completed` avec props guest |
| ARPU | Revenu / payeur | Voir HogQL §5 |
| Boost attach rate | Part boost dans revenus | Part `flow=boost` |

---

## 5. HogQL copiables — Activation rate & ARPU

### Activation rate 24 h

Utilisateurs ayant publié un premier foto dans les 24 h après inscription :

```sql
SELECT
  round(
    countIf(dateDiff('hour', reg.ts, fp.ts) <= 24) * 100.0 / nullIf(count(), 0),
    2
  ) AS activation_rate_pct_24h
FROM (
  SELECT distinct_id, min(timestamp) AS ts
  FROM events
  WHERE event = 'register_completed'
    AND timestamp >= now() - INTERVAL 30 DAY
  GROUP BY distinct_id
) reg
LEFT JOIN (
  SELECT distinct_id, min(timestamp) AS ts
  FROM events
  WHERE event = 'first_foto_published'
  GROUP BY distinct_id
) fp ON reg.distinct_id = fp.distinct_id
```

### ARPU 30 jours (revenu webhook uniquement)

```sql
SELECT
  round(
    sum(toFloat64OrNull(JSONExtractString(properties, '$revenue'))) /
    nullIf(count(DISTINCT distinct_id), 0),
    2
  ) AS arpu_30d
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL 30 DAY
```

### ARPU par flow

```sql
SELECT
  JSONExtractString(properties, 'flow') AS flow,
  round(sum(toFloat64OrNull(JSONExtractString(properties, '$revenue'))), 0) AS revenue,
  count(DISTINCT distinct_id) AS payers,
  round(
    sum(toFloat64OrNull(JSONExtractString(properties, '$revenue'))) /
    nullIf(count(DISTINCT distinct_id), 0),
    2
  ) AS arpu
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL 30 DAY
GROUP BY flow
ORDER BY revenue DESC
```

---

## 6. Pourquoi les users partent — funnel abandon register → first foto

### Funnel PostHog (copier dans Insights → Funnels)

```
register_completed → onboarding_completed → first_foto_published
```

Fenêtre : **14 jours**. Breakdown : `signup_channel`, `signup_platform`.

### Taux d’abandon par étape (formules PostHog)

Dans un funnel PostHog, pour chaque étape `i` :

```
drop_off_rate(step_i) = 1 - (users_step_i / users_step_0)
```

**HogQL — abandon après register sans onboarding** :

```sql
SELECT
  count(DISTINCT reg.distinct_id) AS registered,
  count(DISTINCT ob.distinct_id) AS onboarding_done,
  count(DISTINCT fp.distinct_id) AS first_pin,
  round((1 - count(DISTINCT ob.distinct_id) / nullIf(count(DISTINCT reg.distinct_id), 0)) * 100, 1)
    AS pct_abandon_before_onboarding,
  round((1 - count(DISTINCT fp.distinct_id) / nullIf(count(DISTINCT ob.distinct_id), 0)) * 100, 1)
    AS pct_abandon_onboarding_to_pin
FROM (
  SELECT distinct_id, min(timestamp) AS ts
  FROM events WHERE event = 'register_completed'
    AND timestamp >= now() - INTERVAL 30 DAY
  GROUP BY distinct_id
) reg
LEFT JOIN (
  SELECT distinct_id FROM events WHERE event = 'onboarding_completed'
) ob ON reg.distinct_id = ob.distinct_id
LEFT JOIN (
  SELECT distinct_id FROM events WHERE event = 'first_foto_published'
) fp ON reg.distinct_id = fp.distinct_id
```

### Interprétation « pourquoi ils partent »

| Signal | Hypothèse | Action produit |
|--------|-----------|----------------|
| Fort abandon register → onboarding | OTP email, friction formulaire | Vérifier `email_delivery_unavailable`, simplifier register |
| Abandon onboarding (steps skipped élevés) | Trop long / pas pertinent | A/B `onboarding_v2`, réduire étapes |
| Onboarding OK mais pas de first foto | Peur de publier, UX create | Push create foto, templates, tutoriel |
| `guest_action_blocked` ↑ avant register | Mur invité trop tôt | Ajuster `guestConversion` (voir `guestConversionAnalytics.ts`) |
| Referral drop après `referral_link_opened` | Landing ref faible | Optimiser page `?ref=` + intent backend |
| Activation 24 h < 20 % | Time-to-value lent | Email J0 « publie ton premier foto » |

### Funnel complémentaire — étapes onboarding

```
onboarding_started → onboarding_step_completed (step_id=interests)
  → onboarding_step_completed (step_id=follow)
  → onboarding_completed → first_foto_published
```

Filtrer `properties.step_id` dans PostHog pour localiser l’étape exacte d’abandon.

---

## 7. Consentement cookies → PostHog (e2e)

Test Playwright : `FOTOCE-FRONTEND/e2e/analytics-consent.spec.ts`

| Choix bannière | `fotoce_analytics_consent` | `fotoce_analytics_opt_out` | Capture PostHog |
|----------------|---------------------------|---------------------------|-----------------|
| Nécessaires seuls | `denied` | `1` | Bloquée |
| Accepter analytics | `granted` | `0` | Autorisée (`landing_viewed`) |

---

## 8. Checklist analytics 10/10

- [ ] `POSTHOG_PERSONAL_API_KEY` + `POSTHOG_PROJECT_ID` configurés en CI/CD secrets
- [ ] `setup_posthog_business_dashboard.py` exécuté → `posthog-analytics-live.json` commité ou archivé
- [ ] 19/19 événements présents (`events_validation.ok = true`)
- [ ] `VITE_POSTHOG_KEY` prod + `POSTHOG_API_KEY` backend (webhook revenue)
- [ ] Dashboard partagé équipe produit (lien §2)
- [ ] Alertes : chute `first_foto_published`, spike `guest_action_blocked`
- [ ] e2e consent vert en CI

---

## Fichiers

| Fichier | Rôle |
|---------|------|
| `fotoce-backend/scripts/setup_posthog_business_dashboard.py` | Déploiement dashboard |
| `fotoce-backend/scripts/verify_posthog_business_events.py` | Audit events |
| `docs/posthog/business-dashboard.json` | Spec insights |
| `docs/BUSINESS-METRICS.md` | Référence KPIs |
| `packages/fotoce-shared/src/analytics/` | Schéma événements |
| `FOTOCE-FRONTEND/e2e/analytics-consent.spec.ts` | Test consent → PostHog |
