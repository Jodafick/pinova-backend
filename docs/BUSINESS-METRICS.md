# Métriques business FOTOCE — PostHog

Ce document décrit les funnels, cohortes, revenus et KPIs du dashboard **FOTOCE — Business** (PostHog EU). Il sert de référence produit / data pour interpréter les chiffres sans double comptage.

## Prérequis

| Variable | Usage |
|----------|--------|
| `VITE_POSTHOG_KEY` / `EXPO_PUBLIC_POSTHOG_KEY` | Clients web & mobile |
| `POSTHOG_API_KEY` | Backend (webhook FedaPay → revenue) |
| `POSTHOG_PERSONAL_API_KEY` | Script dashboard (API privée PostHog) |
| `POSTHOG_PROJECT_ID` | ID projet PostHog |

Création / mise à jour du dashboard :

```bash
cd fotoce-backend
export POSTHOG_PERSONAL_API_KEY=phx_...
export POSTHOG_PROJECT_ID=12345
python scripts/setup_posthog_business_dashboard.py
```

Configuration de référence : `docs/posthog/business-dashboard.json`.

---

## Événements clés

| Événement | Source | Rôle |
|-----------|--------|------|
| `landing_viewed` | Web (invité) | Entrée funnel acquisition |
| `register_started` / `register_completed` | Web, mobile | Inscription |
| `register_with_ref_code` | Backend | Inscription avec parrainage |
| `referral_link_opened` | Backend (`POST referrals/intent/`) | Ouverture lien parrain |
| `onboarding_completed` | Web, mobile | Fin onboarding |
| `first_foto_published` | Web, mobile (`trackOnce`) | Activation produit |
| `premium_viewed` → `checkout_started` → `checkout_success` | Clients | Funnel monétisation (UX) |
| `revenue_recorded` | Backend webhook FedaPay | **Revenu authoritative** (`$revenue`, `$currency`) |
| `retention_cohort_j1/j7/j30` | Web, mobile (`trackOnce`) | Cohortes rétention |

### Propriétés communes

- `signup_platform` : `web` | `mobile`
- `signup_channel` : `web` | `mobile` | `referral` | `organic`
- `revenue_source` : `fedapay_webhook` (ARPU) vs `client_estimate` (funnel UX uniquement)
- `tracking_role` : `revenue` | `funnel`
- `flow` : `premium` | `boost` | `campaign` | `tip` (selon checkout)

---

## Funnels PostHog

### 1. Acquisition

```
landing_viewed → register_started → onboarding_completed → first_foto_published
```

**Interprétation**

- Mesure le parcours visiteur → utilisateur activé (premier foto publié).
- Fenêtre recommandée : 14 jours entre la première et la dernière étape.
- Breakdown utile : `signup_platform`, `signup_channel`.

**Activation rate (< 24 h)** — insight séparé :

- Numérateur : utilisateurs avec `first_foto_published` dans les 24 h après `register_completed`.
- Dénominateur : `register_completed` sur la même période.
- HogQL (approximation) :

```sql
SELECT
  countIf(
    dateDiff('hour', reg.timestamp, fp.timestamp) <= 24
  ) / count() AS activation_rate_24h
FROM (
  SELECT distinct_id, min(timestamp) AS timestamp
  FROM events WHERE event = 'register_completed' GROUP BY distinct_id
) reg
LEFT JOIN (
  SELECT distinct_id, min(timestamp) AS timestamp
  FROM events WHERE event = 'first_foto_published' GROUP BY distinct_id
) fp ON reg.distinct_id = fp.distinct_id
```

---

### 2. Monétisation (par flow)

```
premium_viewed → checkout_started → checkout_success
```

Filtrer **`checkout_success`** et **`revenue_recorded`** sur :

- `platform = backend` **OU** `revenue_source = fedapay_webhook` pour les montants réels.
- Breakdown : `flow` (`premium`, `boost`, `campaign`, …).

**Important** : les clients envoient aussi `checkout_success` avec `revenue_source = client_estimate` (retour checkout). Ne **pas** les additionner au revenu — utiliser uniquement `revenue_recorded` / webhook.

---

### 3. Viralité (parrainage)

```
referral_link_opened → register_with_ref_code
```

Alternative : `referral_link_opened → register_completed` avec filtre `has_ref_code = true`.

**Interprétation**

- Taux de conversion lien → inscription parrainée.
- Breakdown : `ref_code` (top parrains), `signup_channel = referral`.

---

## Cohortes rétention J1 / J7 / J30

Événements émis une fois par utilisateur (`trackOnce`) :

- `retention_cohort_j1` — jour ≥ 1 après inscription
- `retention_cohort_j7` — jour ≥ 7
- `retention_cohort_j30` — jour ≥ 30

Breakdown recommandé : **`signup_channel`** (`web`, `mobile`, `referral`).

**Interprétation**

- Ce ne sont pas des cohortes PostHog « classiques » (retour J+N sur une action) mais des **marqueurs de passage** émis au premier lancement après le seuil.
- Pour une rétention stricte « % actifs J7 », croiser avec `trackPageview` ou une action produit (ex. `foto_viewed`) dans une cohorte PostHog basée sur `register_completed`.

---

## Revenus (FedaPay → PostHog)

Le webhook FedaPay approuvé appelle `capture_revenue_recorded()` puis `capture_checkout_success()` côté backend avec :

- `$revenue` : montant en unité majeure (XOF sans division)
- `$currency` : ex. `XOF`
- `flow`, `transaction_id`, `revenue_source = fedapay_webhook`

**ARPU (période)** :

```
SUM($revenue) WHERE event = revenue_recorded AND revenue_source = fedapay_webhook
───────────────────────────────────────────────────────────────────────────────
COUNT(DISTINCT person_id) avec au moins un revenue_recorded sur la période
```

Ou insight PostHog **Revenue** natif filtré sur `revenue_recorded`.

---

## KPIs dashboard

| KPI | Formule / filtre | Notes |
|-----|------------------|-------|
| **Activation rate 24 h** | `first_foto_published` ≤ 24 h après `register_completed` | Voir HogQL ci-dessus |
| **Guest conversion rate** | `register_completed` avec props guest (`guest_conversion_*`) / sessions invité | Props `guestConversion` sur register |
| **ARPU** | `revenue_recorded` + `$revenue`, source webhook uniquement | Exclure `client_estimate` |
| **Boost attach rate** | `checkout_success` ou `revenue_recorded` où `flow = boost` / total checkouts premium+boost | Numérateur : flows `boost` ; dénominateur : tous les `revenue_recorded` payants |

### Boost attach rate (HogQL)

```sql
SELECT
  countIf(flow = 'boost') / nullIf(count(), 0) AS boost_attach_rate
FROM events
WHERE event = 'revenue_recorded'
  AND properties.revenue_source = 'fedapay_webhook'
  AND timestamp >= now() - INTERVAL 30 DAY
```

---

## Pièges courants

1. **Double comptage checkout** : client + backend émettent `checkout_success` — filtrer par `revenue_source` ou `platform`.
2. **ARPU gonflé** : ne jamais sommer les montants `client_estimate`.
3. **Referral** : `referral_link_opened` est capturé côté backend à l’intent ; l’inscription parrainée est confirmée par `register_with_ref_code`.
4. **Mobile vs web** : comparer via `signup_platform`, pas via l’événement seul.

---

## Fichiers instrumentation

| Zone | Fichier |
|------|---------|
| Schéma événements | `packages/fotoce-shared/src/analytics/` |
| Revenue serveur | `fotoce-backend/fotoce_backend/analytics.py` |
| Webhook FedaPay | `fotoce-backend/monetization/webhook_processing.py` |
| Referral intent | `fotoce-backend/referrals/views.py` |
| Dashboard script | `fotoce-backend/scripts/setup_posthog_business_dashboard.py` |
