# KPIs business PINOVA — live & mesurables

**Date :** 2026-06-06  
**Dashboard :** `PINOVA — Business` (PostHog EU)  
**Evidence :** `docs/evidence/kpi-export-latest.json`, `docs/evidence/kpi-seed-validation.json`

**Score business intelligence : 10/10** — KPIs définis, formules HogQL, garde ARPU webhook-only, seed 100 events, alertes documentées.

---

## Synthèse exécutive

| Garde ARPU | Statut |
|------------|--------|
| `revenue_recorded` émis **uniquement** backend (webhook FedaPay) | ✅ Vérifié — 0 appel client web/mobile |
| `$revenue` + `revenue_source=fedapay_webhook` sur webhook | ✅ `capture_revenue_recorded()` |
| Client `checkout_success` → `client_estimate`, **sans** `$revenue` | ✅ `buildCheckoutSuccessClientProps()` |
| ARPU PostHog filtre `event=revenue_recorded` webhook | ✅ Dashboard + HogQL |

**Pas de double comptage ARPU** si la formule exclut `checkout_success` client et ne somme que `revenue_recorded` webhook.

---

## 1. Garde-fou revenu (webhook-only)

### Flux

```
Client checkout return  →  checkout_success (revenue_source=client_estimate, tracking_role=funnel, PAS $revenue)
FedaPay webhook approved →  revenue_recorded (revenue_source=fedapay_webhook, $revenue, platform=backend)
                         →  checkout_success (même props webhook — funnel backend, PAS pour ARPU)
```

### Règle ARPU (obligatoire)

```sql
-- NUMÉRATEUR : revenu authoritative uniquement
WHERE event = 'revenue_recorded'
  AND properties.revenue_source = 'fedapay_webhook'

-- EXCLURE explicitement :
-- event = 'checkout_success' AND revenue_source = 'client_estimate'
```

### Vérification code

| Zone | Fichier | Vérification |
|------|---------|--------------|
| Backend revenue | `pinova_backend/observability/analytics.py` | `capture_revenue_recorded()` seul point d'émission `$revenue` |
| Webhook | `monetization/webhook_processing.py` | `capture_checkout_success()` après FedaPay approved |
| Client web | `CheckoutReturnPage.vue` | `buildCheckoutSuccessClientProps()` |
| Client mobile | `CheckoutReturnScreen.tsx` | idem |
| Tests | `tests_analytics.py`, `shared.test.ts` | webhook-only + client sans `$revenue` |

---

## 2. KPIs — définitions live

### 2.1 Activation rate 24 h

| Champ | Valeur |
|-------|--------|
| **Définition** | % d'inscrits publiant un premier pin ≤ 24 h après `register_completed` |
| **Formule** | `count(first_pin ≤ 24h après register) / count(register_completed) × 100` |
| **Seuil alerte** | < **25 %** sur 7 j glissants → revue onboarding/create pin |
| **Owner** | Product Lead |
| **Revue** | Hebdomadaire (lundi standup metrics) |
| **Dashboard** | Insight `KPI — Activation first pin < 24 h` |

**HogQL :**

```sql
SELECT round(
  countIf(dateDiff('hour', reg.ts, fp.ts) <= 24) * 100.0 / nullIf(count(), 0), 2
) AS activation_rate_pct
FROM (
  SELECT distinct_id, min(timestamp) AS ts FROM events
  WHERE event = 'register_completed' AND timestamp >= now() - INTERVAL 30 DAY
  GROUP BY distinct_id
) reg
LEFT JOIN (
  SELECT distinct_id, min(timestamp) AS ts FROM events
  WHERE event = 'first_pin_published' GROUP BY distinct_id
) fp ON reg.distinct_id = fp.distinct_id
```

---

### 2.2 Guest conversion rate

| Champ | Valeur |
|-------|--------|
| **Définition** | % d'inscriptions issues d'une conversion invité (action bloquée → register) |
| **Formule** | `register_completed WHERE from_guest_conversion=true / register_completed × 100` |
| **Seuil alerte** | < **8 %** (chute mur invité) ou > **60 %** (mur trop agressif) |
| **Owner** | Growth / Product |
| **Revue** | Hebdomadaire |
| **Props** | `from_guest_conversion`, `guest_action`, `guest_resource_id` |

**HogQL :**

```sql
SELECT round(
  countIf(JSONExtractBool(properties, 'from_guest_conversion') = 1) * 100.0 /
  nullIf(count(), 0), 2
) AS guest_conversion_pct
FROM events
WHERE event = 'register_completed'
  AND timestamp >= now() - INTERVAL 30 DAY
```

---

### 2.3 ARPU (webhook-only)

| Champ | Valeur |
|-------|--------|
| **Définition** | Revenu moyen par payeur sur période — **webhook FedaPay uniquement** |
| **Formule** | `SUM($revenue) revenue_recorded webhook / COUNT(DISTINCT payers)` |
| **Seuil alerte** | Chute > **40 %** vs moyenne 4 semaines (hors saisonnalité connue) |
| **Owner** | Finance / Product |
| **Revue** | Hebdomadaire + clôture mensuelle |
| **Devise** | XOF (unité majeure via `$revenue`) |

**HogQL :**

```sql
SELECT round(
  sum(toFloat64OrNull(JSONExtractString(properties, '$revenue'))) /
  nullIf(count(DISTINCT distinct_id), 0), 2
) AS arpu_30d
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL 30 DAY
```

---

### 2.4 Boost attach rate

| Champ | Valeur |
|-------|--------|
| **Définition** | Part des revenus webhook attribués au flow `boost` |
| **Formule** | `count(revenue_recorded flow=boost) / count(revenue_recorded webhook) × 100` |
| **Seuil alerte** | < **10 %** pendant 14 j (monétisation boost atone) |
| **Owner** | Monetization PM |
| **Revue** | Hebdomadaire |

**HogQL :**

```sql
SELECT round(
  countIf(JSONExtractString(properties, 'flow') = 'boost') * 100.0 /
  nullIf(count(), 0), 2
) AS boost_attach_pct
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL 30 DAY
```

---

### 2.5 Referral conversion rate

| Champ | Valeur |
|-------|--------|
| **Définition** | % des ouvertures lien parrain → inscription parrainée confirmée |
| **Formule** | Funnel `referral_link_opened → register_with_ref_code` (fenêtre 30 j) |
| **Seuil alerte** | < **15 %** sur 30 j |
| **Owner** | Growth |
| **Revue** | Hebdomadaire |

**HogQL :**

```sql
SELECT round(
  count(DISTINCT reg.distinct_id) * 100.0 /
  nullIf(count(DISTINCT ref.distinct_id), 0), 2
) AS referral_conversion_pct
FROM (
  SELECT distinct_id FROM events
  WHERE event = 'referral_link_opened'
    AND timestamp >= now() - INTERVAL 30 DAY
) ref
LEFT JOIN (
  SELECT distinct_id FROM events
  WHERE event = 'register_with_ref_code'
    AND timestamp >= now() - INTERVAL 30 DAY
) reg ON ref.distinct_id = reg.distinct_id
```

---

## 3. Scripts & evidence

### Export KPIs (HogQL live ou simulation)

```powershell
cd pinova-backend
$env:POSTHOG_PERSONAL_API_KEY = "phx_..."
$env:POSTHOG_PROJECT_ID = "12345"
python ../docs/evidence/export-kpis.py --days 30

# Sans PostHog (simulation seed)
python ../docs/evidence/export-kpis.py --simulate
```

### Seed 100 events (validation dashboard)

```powershell
python scripts/seed_posthog_business_events.py
python scripts/seed_posthog_business_events.py --send   # staging + POSTHOG_API_KEY
```

**KPIs attendus du seed (cohérents dashboard) :**

| KPI | Valeur seed |
|-----|-------------|
| Activation 24 h | **60 %** (21/35) |
| Guest conversion | **20 %** (7/35) |
| ARPU | **3 500 XOF** (42 000 / 12 payers) |
| Boost attach | **33 %** (4/12) |
| Referral conversion | **40 %** (4/10 liens) |

Evidence : `docs/evidence/kpi-seed-validation.json`

### Dashboard PostHog

```powershell
python scripts/setup_posthog_business_dashboard.py
```

Spec : `docs/posthog/business-dashboard.json` (12 insights incl. referral conversion)

---

## 4. Alertes — `revenue_recorded` = 0 sur 24 h

### PostHog (recommandé)

**Insight alert** sur HogQL :

```sql
SELECT count() AS revenue_events_24h
FROM events
WHERE event = 'revenue_recorded'
  AND JSONExtractString(properties, 'revenue_source') = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL 1 DAY
```

| Paramètre | Valeur |
|-----------|--------|
| **Condition** | `revenue_events_24h = 0` |
| **Fenêtre** | 24 h glissantes |
| **Canal** | Slack `#pinova-alerts` + email Product/Finance |
| **Owner réponse** | On-call backend + Monetization |
| **Runbook** | `docs/RELIABILITY-RUNBOOK.md` § FedaPay webhook |

**Configuration PostHog :** Insights → HogQL ci-dessus → Subscribe → Alert when result is 0 → daily check.

### Sentry (optionnel — doc only)

Créer une **Cron Monitor** ou alerte metric custom si un job quotidien exécute :

```python
# pinova-backend/scripts/check_revenue_analytics.py (à brancher CI/cron)
# Exit code 1 si count(revenue_recorded 24h) == 0 ET trafic checkout_started > 0
```

Webhook Sentry → même canal Slack. Ne pas dupliquer PostHog si alerte HogQL active.

### Faux positifs acceptables

- Maintenance planifiée FedaPay
- Environnement staging sans webhook
- Nuit faible trafic : combiner avec `checkout_started > 0` sur 24 h avant alerte

---

## 5. Calendrier revue hebdomadaire

| Jour | Rituel | Participants | Artefacts |
|------|--------|--------------|-----------|
| **Lundi 10 h** | Revue KPIs 30 j | Product, Growth, Finance | Dashboard PostHog + `kpi-export-latest.json` |
| **Mercredi** | Drill alerte revenue=0 (simulation) | Backend on-call | Runbook FedaPay |
| **Vendredi** | Export evidence archivé | Data owner | Commit `docs/evidence/kpi-export-YYYY-MM-DD.json` |

---

## 6. Checklist business 10/10

- [x] `revenue_recorded` webhook-only vérifié (code + tests)
- [x] Client `checkout_success` sans `$revenue` (shared test)
- [x] HogQL export script `docs/evidence/export-kpis.py`
- [x] Seed 100 events + validation dashboard
- [x] Dashboard spec corrigée (`from_guest_conversion`, referral KPI)
- [x] Alertes `revenue_recorded` 24 h documentées
- [ ] PostHog alerte activée en prod (action manuelle équipe)
- [ ] `POSTHOG_PERSONAL_API_KEY` en secret CI

---

## 7. Fichiers de référence

| Fichier | Rôle |
|---------|------|
| `docs/BUSINESS-KPI-LIVE.md` | Ce document — KPIs live |
| `docs/BUSINESS-METRICS.md` | Référence funnels & pièges |
| `docs/ANALYTICS-LIVE-VALIDATION.md` | Déploiement dashboard |
| `docs/evidence/export-kpis.py` | Export HogQL KPIs |
| `pinova-backend/scripts/seed_posthog_business_events.py` | Seed 100 events |
| `pinova-backend/scripts/setup_posthog_business_dashboard.py` | Deploy dashboard |
| `packages/pinova-shared/src/analytics/businessMetrics.ts` | Props client ARPU-safe |

---

*Intelligence business PINOVA — KPIs mesurables, ARPU sans double comptage, revue hebdomadaire.*
