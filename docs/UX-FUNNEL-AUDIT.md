# Audit UX psychologique — Funnel FOTOCE

> **Périmètre** : parcours web invité → monétisation (checkout success)  
> **Méthode** : cartographie code (`FOTOCE-FRONTEND`), events PostHog, heuristiques Nielsen (1–10), charge cognitive par écran  
> **Date** : 2026-06-06  
> **Quick wins mergés** : preuve sociale landing + register, onboarding v2 à 100 %, minimum intérêts 2→2

---

## 1. Funnel ASCII & taux cibles

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                    FUNNEL CONVERSION FOTOCE                  │
                    └─────────────────────────────────────────────────────────────┘

  landing_viewed          register_started       otp_verified        onboarding_started
  (invité fil visible)    register_completed                          onboarding_completed
        │                       │                    │                       │
        ▼                       ▼                    ▼                       ▼
   ┌─────────┐             ┌──────────┐         ┌─────────┐            ┌──────────────┐
   │ INVITÉ  │─── CTA ───▶│ REGISTER │── OTP ─▶│  OTP    │── auth ──▶│ ONBOARDING   │
   │ HomePage│   8–12%     │RegisterPg│  65–75% │VerifyOTP│  85–92%  │OnboardingPg  │
   └─────────┘             └──────────┘         └─────────┘            └──────┬───────┘
        │                                                                      │
        │ guest_action_blocked                                                   │ 70–85%
        │ (like/save bloqué)                                                     ▼
        │                                                               ┌──────────────┐
        │                                                               │  FIRST PIN   │
        │                                                               │ CreatePinPg  │
        │                                                               │first_foto_pub │
        │                                                               └──────┬───────┘
        │                                                                      │ 25–40%
        │                                                                      ▼
        │                                                               ┌──────────────┐
        │                                                               │ FIRST FOLLOW │
        │                                                               │ toggleFollow │
        │                                                               │ first_follow │
        │                                                               └──────┬───────┘
        │                                                                      │ 15–25%
        │                                                                      ▼
        │                                                               ┌──────────────┐
        │                                                               │   PREMIUM    │
        │                                                               │ PremiumPage  │
        │                                                               │premium_viewed│
        │                                                               └──────┬───────┘
        │                                                                      │ 3–8%
        │                                                                      ▼
        │                                                               ┌──────────────┐
        └──────────────────────────────────────────────────────────────▶│   CHECKOUT   │
                                                                        │CheckoutReturn│
                                                                        │checkout_succ │
                                                                        └──────────────┘

Taux cibles (benchmark SaaS social / freemium, à calibrer PostHog prod) :

| Transition                    | Taux cible | Signal PostHog principal        |
|------------------------------|-----------|----------------------------------|
| Invité → Register started    | 8–12 %    | `register_started` / `landing_viewed` |
| Register → OTP verified      | 65–75 %   | `otp_verified` / `register_completed` |
| OTP → Onboarding completed   | 70–85 %   | `onboarding_completed` / `otp_verified` |
| Onboarding → First foto       | 25–40 %   | `first_foto_published` / `onboarding_completed` |
| First foto → First follow     | 15–25 %   | `first_follow` / `first_foto_published` |
| Actif → Premium viewed       | 15–25 %   | `premium_viewed` / MAU           |
| Premium → Checkout success   | 3–8 %     | `checkout_success` / `premium_viewed` |
```

---

## 2. Cartographie par étape

### 2.1 Invité — `HomePage.vue`

| Dimension | Détail |
|-----------|--------|
| **Events PostHog** | `landing_viewed` (once, via `useReferralIntent`), `guest_action_blocked` (like/save/comment gate) |
| **Composants UI** | Hero compact, fil fotos immédiat, `TopicScroller`, `FotoGrid`, bannière cookies |
| **Charge cognitive** | 0 champs ; 1 décision (Google vs login vs scroll) |
| **Récompense** | Contenu immédiat (fil), curiosité visuelle |
| **Frictions connues** | CTA principal = Google (pas email) ; pas de compteur social avant quick win ; gate actions sans message de valeur claire |

**Quick win mergé** : ligne `home.landing.socialProof` + `data-testid="landing-social-proof"`.

---

### 2.2 Register — `RegisterPage.vue`

| Dimension | Détail |
|-----------|--------|
| **Events** | `register_started`, `register_completed` (+ props referral / guest conversion) |
| **Composants** | Hero desktop, `PasswordStrengthField`, checkbox CGU, Google OAuth |
| **Charge cognitive** | 3 champs effectifs (email, password, CGU) + règles mot de passe (4 critères) |
| **Récompense** | Hero « Rejoignez la communauté » ; pas de micro-récompense post-submit |
| **Frictions** | Politique mot de passe stricte ; pas de preuve sociale mobile ; double voie Google/email sans priorisation claire |

**Quick win mergé** : `register.socialProof` + `data-testid="register-social-proof"`.

---

### 2.3 OTP — `VerifyOTPPage.vue`

| Dimension | Détail |
|-----------|--------|
| **Events** | `otp_verified` uniquement (pas de `otp_failed`, `otp_viewed`) |
| **Composants** | Input 6 chiffres, resend cooldown, redirect 1,2 s post-succès |
| **Charge cognitive** | 1 champ ; attente email externe |
| **Récompense** | Animation succès ; redirect auto |
| **Frictions** | Délai 1,2 s avant redirect ; pas d’event échec ; OTP non auto-focus paste mobile |

---

### 2.4 Onboarding — `OnboardingPage.vue`

| Dimension | Détail |
|-----------|--------|
| **Events** | `onboarding_started`, `onboarding_step_viewed`, `onboarding_step_completed`, `onboarding_step_skipped`, `onboarding_completed` |
| **Composants v2** | 3 étapes : intérêts+langue, localisation (skip), créateurs suggérés |
| **Charge cognitive v2** | ~2 clics intérêts + 0–2 selects geo + 0–N follows (skippable) |
| **Récompense** | Barre progression, badges étapes, suggestions créateurs personnalisées |
| **Frictions (avant quick wins)** | Min 3 intérêts ; v1 encore 50 % rollout ; birthdate v1 ; pas de testids e2e |

**Quick wins mergés** :
- `MIN_INTERESTS = 2` (était 3)
- `onboarding_v2` rollout **100 %** (`featureFlags.ts`)
- `data-testid` : `onboarding-progress`, `onboarding-interest-{slug}`, `onboarding-continue`

**Note analytics** : `first_follow` n’est émis que via `toggleFollow` — les follows onboarding ne déclenchent pas `first_follow`.

---

### 2.5 First foto — `CreateFotoPage.vue`

| Dimension | Détail |
|-----------|--------|
| **Events** | `first_foto_published` (once) |
| **Composants** | Flux 2 étapes desktop, upload drag-drop, modération NSFW, catégorie, toast succès |
| **Charge cognitive** | 3 champs obligatoires (titre, catégorie, média) + scan modération async |
| **Récompense** | Toast `create.foto.success`, redirect `/foto/{slug}` |
| **Frictions** | Média obligatoire ; birth_date requis si absent ; scan NSFW bloque CTA ; mobile 3 sous-étapes |

**Testids e2e ajoutés** : `create-foto-title`, `create-foto-category`, `create-foto-file`, `create-foto-next`, `create-foto-publish`.

---

### 2.6 First follow — profil / feed

| Dimension | Détail |
|-----------|--------|
| **Events** | `first_follow` (`useAuth.toggleFollow`, once) |
| **Composants** | Bouton follow fiche profil, suggestions onboarding |
| **Charge cognitive** | 1 clic |
| **Récompense** | Feed « Abonnements » enrichi ; notification créateur (si activée) |
| **Frictions** | Pas de CTA post-first-pin « Suivre 3 créateurs » ; follows onboarding non trackés `first_follow` |

---

### 2.7 Premium — `PremiumPage.vue`

| Dimension | Détail |
|-----------|--------|
| **Events** | `premium_viewed` (onMounted) |
| **Composants** | Plans Free/Plus/Pro, cycles mensuel/annuel, bundles seats, `TrustCenterSection` |
| **Charge cognitive** | 3+ décisions (plan, cycle, bundle) — comparaison avancée optionnelle |
| **Récompense** | Trial éligible, prix localisés XOF/EUR |
| **Frictions** | Trop de plans visibles d’emblée ; `premium_viewed` sans variante plan ; chargement pricing async |

---

### 2.8 Checkout success — `CheckoutReturnPage.vue` + `checkoutFlow.ts`

| Dimension | Détail |
|-----------|--------|
| **Events** | `checkout_started`, `checkout_returned`, `checkout_success` |
| **Composants** | Page retour PSP, activation abonnement |
| **Charge cognitive** | 0 (post-paiement) |
| **Récompense** | Confirmation + accès features premium |
| **Frictions** | Retour PSP peut échouer silencieusement ; double fire `checkout_success` possible |

---

## 3. Heatmap des frictions (Nielsen × sévérité)

Légende : 🔴 P0 (bloquant conversion) · 🟠 P1 (forte friction) · 🟡 P2 (optimisation)

| Écran | H1 Visibilité | H2 Monde réel | H3 Contrôle | H4 Cohérence | H5 Prévention erreurs | H6 Reconnaissance | H7 Flexibilité | H8 Design minimal | H9 Recovery | H10 Aide |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Landing** | 🟡 | 🟢 | 🟢 | 🟡 | 🟢 | 🟢 | 🟢 | 🟠 | 🟢 | 🟡 |
| **Register** | 🟢 | 🟢 | 🟡 | 🟢 | 🟠 | 🟡 | 🟢 | 🟠 | 🟡 | 🟡 |
| **OTP** | 🟢 | 🟡 | 🟡 | 🟢 | 🟠 | 🟡 | 🟡 | 🟢 | 🟠 | 🔴 |
| **Onboarding** | 🟢 | 🟢 | 🟢 | 🟡 | 🟡 | 🟠 | 🟢 | 🟠→🟡 | 🟡 | 🟡 |
| **CreatePin** | 🟢 | 🟡 | 🟡 | 🟢 | 🟠 | 🟡 | 🟡 | 🔴 | 🟠 | 🟡 |
| **Premium** | 🟡 | 🟢 | 🟢 | 🟡 | 🟢 | 🟠 | 🟡 | 🔴 | 🟢 | 🟡 |
| **Checkout** | 🟢 | 🟡 | 🟡 | 🟢 | 🟠 | 🟢 | 🟡 | 🟢 | 🟠 | 🟡 |

**Zones les plus chaudes (P0 cumulé)** :
1. **CreatePin** — média + birth_date + modération = triple barrière avant dopamine « publié »
2. **Premium** — surcharge choix plans
3. **OTP** — absence d’aide contextuelle + analytics échec

---

## 4. Recommandations P0 / P1 par écran

### Register

| Priorité | Recommandation | Impact psychologique |
|----------|----------------|-------------------|
| **P0** | ✅ Preuve sociale sous titre (mergé) | Réduit anxiété inscription (norme sociale Cialdini) |
| **P0** | Afficher critères mot de passe seulement après focus password | Réduit charge cognitive initiale |
| **P1** | Event `register_abandoned` on `beforeunload` avec step | Mesure friction réelle |
| **P1** | CTA secondaire « Continuer avec email » sur landing hero | Alignement CTA landing ↔ register |

### Onboarding

| Priorité | Recommandation | Impact |
|----------|----------------|--------|
| **P0** | ✅ Min 2 intérêts + v2 100 % (mergé) | −33 % clics obligatoires, flow 3 vs 5 étapes |
| **P0** | Émettre `first_follow` aussi pour follows onboarding | Funnel analytics complet |
| **P1** | Micro-toast « Profil personnalisé ✓ » fin étape intérêts | Renforcement variable ratio |
| **P1** | Pré-sélectionner langue navigateur (chip active visible) | H6 reconnaissance |

### CreatePin

| Priorité | Recommandation | Impact |
|----------|----------------|--------|
| **P0** | Wizard post-onboarding : deeplink `/create?welcome=1` avec empty state guidé | Moment « aha » dans les 5 min post-signup |
| **P0** | Collecte birth_date inline (modal existant) **avant** upload si absent — déjà partiel | Évite dead-end bannière settings |
| **P1** | ✅ Testids e2e (mergé) | Regression UX automatisée |
| **P1** | Célébration first foto : confetti léger + streak day 1 | Dopamine + rétention J1 |

### Premium

| Priorité | Recommandation | Impact |
|----------|----------------|--------|
| **P0** | Vue simplifiée par défaut : 2 cartes (Free vs Plus recommandé) | Hick's law — moins de paralysie |
| **P1** | `premium_viewed` + props `{ source, plan_highlight }` | Segmentation funnel |
| **P1** | Bandeau social proof « X créateurs Pro cette semaine » | Preuve sociale prix |

---

## 5. Quick wins implémentés (cette livraison)

| # | Changement | Fichiers | Effort |
|---|-----------|----------|--------|
| 1 | Preuve sociale hero landing invité | `HomePage.vue`, `fr.ts`, `en.ts` | 15 min |
| 2 | Preuve sociale page Register | `RegisterPage.vue`, `fr.ts`, `en.ts` | 10 min |
| 3 | Onboarding v2 100 % + min 2 intérêts | `featureFlags.ts`, `OnboardingPage.vue` | 20 min |

**E2E UX** : `FOTOCE-FRONTEND/e2e/ux-funnel-guest-first-pin.spec.ts`  
Assertions : social proof landing/register, progression onboarding `(2/2+)`, toast publication, URL foto.

```powershell
cd FOTOCE-FRONTEND
pnpm exec playwright test e2e/ux-funnel-guest-first-pin.spec.ts
```

---

## 6. Pourquoi les users partent (hypothèses code + heuristiques)

| Moment de sortie | Cause probable | Levier |
|-----------------|----------------|--------|
| Landing → bounce | Fil vide ou lent ; pas de valeur perçue immédiate | Seed contenu invité + social proof ✅ |
| Register abandon | Mot de passe strict + CGU | Progressif disclosure + preuve « 2 min » ✅ |
| OTP drop | Email spam / délai | Resend visible + event `otp_failed` |
| Onboarding exit | Trop d'étapes / champs geo | v2 + 2 intérêts ✅ |
| Sans first foto | Peur qualité + média obligatoire | Template foto / brouillon sans image |
| Sans follow | Graph social vide post-onboarding | CTA « Suivre » post-first-pin |
| Premium bounce | Paralysie choix | Default Plus recommandé |
| Checkout abandon | Prix vs valeur perçue | Trial 7j + garantie remboursement |

---

## 7. Prochaines mesures (PostHog)

Dashboard funnel recommandé ( séquence ) :

```
landing_viewed → register_started → register_completed → otp_verified
→ onboarding_completed → first_foto_published → first_follow
→ premium_viewed → checkout_started → checkout_success
```

Scripts existants : `scripts/setup_posthog_business_dashboard.py`, `docs/ANALYTICS-LIVE-VALIDATION.md`.

---

## 8. Score UX funnel (auto-évaluation post-livraison)

| Critère | Avant | Après quick wins |
|---------|-------|------------------|
| Confiance landing/register | 6/10 | **8/10** |
| Friction onboarding | 5/10 | **8/10** |
| Time-to-first-pin | 5/10 | 6/10 (e2e couvert, produit inchangé) |
| Observabilité funnel | 7/10 | 7/10 |
| **Global funnel UX** | **6/10** | **7,5/10** → cible 10/10 avec P0 CreatePin + Premium |
