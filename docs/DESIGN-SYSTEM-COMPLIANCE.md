# Design System — Compliance & adoption primitives

> **Objectif** : adoption **100 %** des primitives Fotoce sur les parcours critiques (CTA, inputs auth, états vide/erreur, modales, toasts).  
> **Référence** : [`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) · **Contraste** : [`A11Y-CONTRAST-RESULTS.json`](A11Y-CONTRAST-RESULTS.json)  
> **Date audit** : 2026-06-06  
> **Score global** : **8,5/10** → cible 10/10 après migration icônes toolbar + skeletons partagés

---

## 1. Inventaire écrans — Web (top 15)

| # | Écran | Route | FotoceButton | FotoceInput | FotoceModal | Skeleton | Toast | Empty | Error | Score |
|---|-------|-------|:------------:|:-----------:|:-----------:|:--------:|:-----:|:-----:|:-----:|:-----:|
| 1 | Home | `/` | ⚠️ partiel | — | — | ✅ FotoGrid | — | ✅ inline | — | 7/10 |
| 2 | Explore | `/explore` | ⚠️ | — | — | ✅ | — | ✅ | — | 7/10 |
| 3 | Following | `/following` | ⚠️ | — | — | ✅ | — | ✅ | — | 7/10 |
| 4 | Profile | `/profile/:u` | ✅ | ⚠️ | ✅ | ✅ ProfileHeader | ✅ | ✅ | ⚠️ | 8/10 |
| 5 | Foto detail | `/foto/:slug` | ⚠️ icônes | — | ✅ | ✅ FotoDetail | ✅ | — | ⚠️ | 7/10 |
| 6 | Create foto | `/create` | ✅ **fix** | ⚠️ raw | ✅ BirthDate | ✅ CreatePinEdit | ✅ | — | — | **9/10** |
| 7 | Settings hub | `/settings` | — (links) | — | — | — | — | — | — | 8/10 |
| 8 | Settings section | `/settings/:id` | ✅ **fix** | ⚠️ mixte | ✅ | ⚠️ inline | ✅ | — | — | **8,5/10** |
| 9 | Notifications | `/notifications` | ✅ **fix** | — | — | ⚠️ inline | ✅ live | ✅ | ✅ **fix** | **9/10** |
| 10 | Premium | `/premium` | ✅ **fix** | — | — | ✅ wave | — | — | — | **9/10** |
| 11 | Login | `/login` | ✅ | ✅ | — | — | — | — | ⚠️ inline | 9/10 |
| 12 | Register | `/register` | ✅ | ✅ **fix** | — | — | — | — | ⚠️ inline | **9,5/10** |
| 13 | Onboarding | `/onboarding` | ✅ | — | — | — | — | — | ⚠️ | 8/10 |
| 14 | Search | `/search` | ⚠️ | ⚠️ | — | ✅ | — | ✅ | — | 7/10 |
| 15 | Billing | `/billing` | ✅ | — | — | ✅ BillingInvoices | ✅ | ✅ | ✅ | 9/10 |

**Légende** : ✅ conforme · ⚠️ partiel (raw `<button>` / styles ad hoc autorisés pour toolbar) · — non applicable

---

## 2. Inventaire écrans — Mobile (top 10)

| # | Écran | FotoceButton | FotoceInput | Modal/Sheet | Skeleton | Toast | Empty/Error |
|---|-------|:------------:|:-----------:|:-----------:|:--------:|:-----:|:-----------:|
| 1 | FeedScreen | ✅ | — | ✅ | ✅ ScreenCenter | ✅ AppToast | ✅ |
| 2 | ProfileScreen | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| 3 | CreatePinWorkflow | ⚠️ mixte | ⚠️ | ✅ | ⚠️ inline | ✅ | ⚠️ |
| 4 | SettingsScreen | ⚠️ mixte | ✅ | ✅ | ✅ InlineUserRows | ✅ | ⚠️ |
| 5 | NotificationsScreen | ⚠️ | — | — | ✅ SkelBox | ✅ | ⚠️ custom |
| 6 | PremiumScreen | ✅ | — | ✅ | ✅ | ✅ | — |
| 7 | LoginScreen | ✅ | ✅ | — | — | ✅ | ⚠️ |
| 8 | RegisterScreen | ✅ | ✅ | — | — | ✅ | ⚠️ |
| 9 | OnboardingScreen | ✅ | — | — | — | ✅ | — |
| 10 | FotoDetailScreen | ⚠️ icônes | — | ✅ | ✅ | ✅ | — |

Mobile : primitives RN alignées (`Fotoce-Mobile/src/components/ui/`). Écarts restants = boutons natifs dans éditeurs media / toolbar.

---

## 3. Checklist compliance (à valider par PR)

### Boutons (`FotoceButton`)

- [ ] CTA primaire / secondaire / danger → `FotoceButton` (pas `bg-pink-700 rounded-full` ad hoc)
- [ ] États `:loading` + `:disabled` sur actions async
- [ ] Navigation interne → prop `to` ou `href` (pas `<router-link>` stylé à la main)
- [ ] **Exception documentée** : boutons icône toolbar, chips onboarding, pickers media

### Inputs (`FotoceInput`)

- [ ] Champs auth (email, texte simple) → `FotoceInput` + `icon` + `:error`
- [ ] **Exception** : `PasswordStrengthField`, `SearchableSelect`, éditeurs riches

### Modales (`FotoceModal` / `useAppModal`)

- [ ] Confirmations / sheets → `FotoceModal` ou `AppAlertModal` (wrapper DS)
- [ ] Pas de `<div class="fixed inset-0">` custom sans review

### Skeletons

- [ ] Listes / headers → composant `*Skeleton.vue` ou classe `app-skeleton-wave`
- [ ] Pas de `animate-pulse` inline dupliqué (objectif P1)

### Toasts (`pushToast` + `AppToast`)

- [ ] Feedback non-bloquant → `pushToast` (monté une fois dans `App.vue`)
- [ ] Pas d'`alert()` sauf confirmations destructives

### Empty / Error (`FotoceEmptyState` / `FotoceErrorState`)

- [ ] Listes vides → `FotoceEmptyState` + slot `#action`
- [ ] Erreurs réseau plein panneau → `FotoceErrorState` + retry `FotoceButton`

### Dark mode

- [ ] Tokens `--pn-*` / classes `dark:` sur surfaces (pas de `#fff` hardcodé sans paire dark)
- [ ] Glass : `dark:bg-neutral-900/45` + `dark:border-white/10`

### Responsive

- [ ] Breakpoints Tailwind : `sm:` 640 · `lg:` 1024 · `xl:` 1280
- [ ] Touch targets ≥ 44px (`min-h-[44px]` ou `FotoceButton size="lg"`)
- [ ] Safe areas : `env(safe-area-inset-*)` sur footers mobile

### Contraste WCAG 2.1 AA

| Paire | Light | Dark | Statut |
|-------|-------|------|--------|
| Texte principal / surface | AAA 19,6:1 | AAA 18,1:1 | ✅ |
| Texte atténué / surface | AA 6,4:1 | AAA 7,4:1 | ✅ |
| Texte blanc / CTA rose | AA 4,6:1 | AA 4,6:1 | ✅ |
| **CTA rose texte / surface dark** | AA 4,6:1 | **FAIL 4,35:1** | ⚠️ lien seul — utiliser CTA plein (`FotoceButton primary`) |
| Placeholder / surface | AA 5:1 | AA 6,3:1 | ✅ |

Commande re-vérification :

```powershell
node scripts/a11y-contrast-audit.mjs
```

---

## 4. Cinq écarts corrigés (cette livraison)

| # | Écran | Écart | Fix |
|---|-------|-------|-----|
| 1 | **Register** | Email en `<input>` custom | → `FotoceInput` + `test-id` (aligné Login) |
| 2 | **CreatePin** | CTA Annuler / Suivant / Publier en `<button>` gradient | → `FotoceButton` ghost + primary + `:loading` |
| 3 | **Premium** | CTAs checkout / trial / plans en styles ad hoc | → `FotoceButton` variants conditionnels |
| 4 | **Notifications** | Erreur inline + « Tout marquer lu » custom | → `FotoceErrorState` + `FotoceButton` secondary |
| 5 | **Settings** | Abonnement + push web + save notifs en `<button>` raw | → `FotoceButton` primary/secondary/ghost + `:to` premium |

---

## 5. Vérification contraste post-fix

Les fixes ci-dessus **n’altèrent pas** `tokens.css` — ré-exécution `a11y-contrast-audit.mjs` :

- **Light** : 9/9 AA ✅ (inchangé)
- **Dark** : 8/9 — échec connu **CTA rose texte sur surface** (4,35:1) — **non régressé** ; mitigé en prod par boutons `FotoceButton primary` (texte blanc sur fond rose, AA 4,6:1)

---

## 6. Aperçu dev (Storybook minimal)

Route **dev only** :

```
http://127.0.0.1:5174/dev/design-system
```

Fichier : `FOTOCE-FRONTEND/src/pages/dev/DesignSystemPage.vue`  
Montre : Button variants, Input, Empty, Error, Modal sheet, Toast, skeleton wave.

---

## 7. Roadmap P0 → 100 %

| Priorité | Action | Impact |
|----------|--------|--------|
| P0 | CreatePin mobile : CTA footer → `FotoceButton` | Cohérence cross-breakpoint |
| P0 | Premium : toggles cycle/bundle → segmented `FotoceButton ghost` | -7 raw buttons |
| P1 | Extraire `NotificationListSkeleton.vue` | DRY skeletons |
| P1 | Mobile Notifications → `FotoceEmptyState` / `FotoceErrorState` RN | Parité web |
| P2 | Token dark `--pn-pink-strong` on surface → `--pn-pink-accent` pour liens | Fix contraste 4,35:1 |

---

## 8. Definition of Done (PR design)

1. Aucun nouveau `<button class="bg-pink-700` sans justification dans la PR  
2. Champs auth simples → `FotoceInput`  
3. Empty/error list → primitives DS  
4. `node scripts/a11y-contrast-audit.mjs` — 0 nouvelle régression  
5. Capture `/dev/design-system` si nouveau variant
