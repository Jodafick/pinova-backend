# Pinova Design System — Primitives unifiées (Web + Mobile)

Objectif : **cohérence 10/10** entre `PINOVA-FRONTEND` (Vue) et `Pinova-Mobile` (React Native) via tokens partagés et composants miroirs.

---

## Tokens

| Couche | Web | Mobile |
|--------|-----|--------|
| Palette | `src/theme/tokens.css` (`--pn-*`) | `src/theme/tokens.ts` (`PinovaTheme`) |
| Platform | `src/theme/platformTokens.ts` | `ThemeProvider` + `useAppTheme()` |
| Boutons CSS | `src/style.css` → `.pds-btn` | `PinovaButton.tsx` (StyleSheet) |

Couleurs clés : `pinkStrong` `#db2777`, `pink700` `#be185d`, surfaces `bgPage` / `bgSurface`, texte `ink` / `inkMuted`.

---

## Primitives Web (`PINOVA-FRONTEND/src/components/ui/`)

### PinovaButton.vue

Variants : `primary` | `secondary` | `ghost` | `floating` | `danger`  
Sizes : `sm` | `md` | `lg` | `icon`  
Props : `loading`, `block`, `disabled`, `to`, `href`, `density`, `platform`

```vue
<PinovaButton variant="primary" size="lg" block :loading="busy" @click="save">
  Enregistrer
</PinovaButton>
```

**Aperçu (primary)**

```
┌─────────────────────────────────────┐
│         Enregistrer                 │  ← fond rose #db2777, texte blanc
└─────────────────────────────────────┘
     border-radius: var(--pinova-radius-md)
```

### PinovaInput.vue

Label, hint, error, icône Material (`icon="mail"`), slots `prefix` / `suffix`, dark mode natif.

```vue
<PinovaInput v-model="email" label="Email" icon="mail" :error="errors.email" />
```

### PinovaEmptyState.vue

```vue
<PinovaEmptyState icon="notifications" :title="t('notifications.empty')" :description="hint">
  <template #action>
    <PinovaButton variant="primary" block>Explorer</PinovaButton>
  </template>
</PinovaEmptyState>
```

### PinovaErrorState.vue

État erreur plein écran ou section avec slot `#action` (retry).

---

## Primitives Mobile (`Pinova-Mobile/src/components/ui/`)

### PinovaButton.tsx

API alignée web : mêmes variants / sizes, `usePinovaStyles` + `PinovaTheme`.

```tsx
<PinovaButton variant="primary" block loading={busy} onPress={save}>
  <PinovaButtonText variant="primary">Enregistrer</PinovaButtonText>
</PinovaButton>
```

### PinovaInput.tsx

```tsx
<PinovaInput label="Email" value={email} onChangeText={setEmail} error={err} hint="Format valide" />
```

### PinovaEmptyState.tsx / PinovaErrorState.tsx

Miroirs web — icônes Material, tokens thème.

### AppToastHost.tsx + `useAppToast.ts`

Remplace `Alert.alert` pour feedback **non-bloquant** :

```ts
import { appToast, appToastSuccess, appToastError } from '../lib/appToast'

appToastSuccess('Boost activé', 'Votre pin sera promu sous peu.')
appToastError('Une erreur est survenue.')
```

- Pile max 3 toasts
- Swipe horizontal / vers le bas pour dismiss
- Monté une fois dans `App.tsx`

**Conserver `Alert.alert`** pour confirmations destructives (suppression compte, quitter siège, etc.).

---

## Migration boutons web (≈80 % des CTAs action)

| Statut | Périmètre |
|--------|-----------|
| ✅ 100 % | Classes legacy `app-btn` → `PinovaButton` |
| ✅ | Auth : Login, Register, Forgot, Reset, VerifyOTP |
| ✅ | Settings, Profile, Board, Billing, modales (`AppAlertModal`, `ReportContentModal`) |
| ✅ | Checkout, GuestAuth, Onboarding, Notifications (empty + retry) |
| ⏳ | Boutons icône / éditeurs story (hors scope DS standard) |

Règle : **tout CTA primaire/secondaire** → `PinovaButton`. Les boutons icône toolbar restent `<button>` natifs.

---

## Captures d'écran (à générer)

Placer les PNG dans `docs/screenshots/design-system/` :

| Fichier | Contenu |
|---------|---------|
| `button-variants-web.png` | Grille primary / secondary / ghost / danger sur fond clair + dark |
| `button-variants-mobile.png` | Même grille sur simulateur iOS |
| `input-states-web.png` | Default, focus, error + hint |
| `empty-error-states.png` | Notifications vide + erreur réseau |
| `toast-stack-mobile.png` | 2–3 toasts empilés avec swipe |

Commande rapide web (dev) : ouvrir `/login`, `/settings`, `/notifications` en light + dark, capturer la barre d'actions.

---

## Checklist contributeur

1. Nouveau bouton action → `PinovaButton` / `PinovaButton.tsx`
2. Nouveau champ formulaire → `PinovaInput`
3. Liste vide → `PinovaEmptyState`
4. Erreur chargement → `PinovaErrorState` + retry
5. Feedback mobile non-bloquant → `appToast*` (pas `Alert.alert`)
6. Pas de nouvelles classes `app-btn`

---

## Fichiers de référence

```
PINOVA-FRONTEND/src/components/ui/PinovaButton.vue
PINOVA-FRONTEND/src/components/ui/PinovaInput.vue
PINOVA-FRONTEND/src/components/ui/PinovaEmptyState.vue
PINOVA-FRONTEND/src/components/ui/PinovaErrorState.vue
PINOVA-FRONTEND/src/style.css                    # .pds-btn
Pinova-Mobile/src/components/ui/PinovaButton.tsx
Pinova-Mobile/src/components/ui/PinovaInput.tsx
Pinova-Mobile/src/components/AppToastHost.tsx
Pinova-Mobile/src/lib/useAppToast.ts
```
