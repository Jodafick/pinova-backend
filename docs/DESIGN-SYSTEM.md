# Fotoce Design System — Primitives unifiées (Web + Mobile)

Objectif : **cohérence 10/10** entre `FOTOCE-FRONTEND` (Vue) et `Fotoce-Mobile` (React Native) via tokens partagés et composants miroirs.

---

## Tokens

| Couche | Web | Mobile |
|--------|-----|--------|
| Palette | `src/theme/tokens.css` (`--pn-*`) | `src/theme/tokens.ts` (`FotoceTheme`) |
| Platform | `src/theme/platformTokens.ts` | `ThemeProvider` + `useAppTheme()` |
| Boutons CSS | `src/style.css` → `.pds-btn` | `FotoceButton.tsx` (StyleSheet) |

Couleurs clés : `fotokStrong` `#db2777`, `fotok700` `#be185d`, surfaces `bgPage` / `bgSurface`, texte `ink` / `inkMuted`.

---

## Primitives Web (`FOTOCE-FRONTEND/src/components/ui/`)

### FotoceButton.vue

Variants : `primary` | `secondary` | `ghost` | `floating` | `danger`  
Sizes : `sm` | `md` | `lg` | `icon`  
Props : `loading`, `block`, `disabled`, `to`, `href`, `density`, `platform`

```vue
<FotoceButton variant="primary" size="lg" block :loading="busy" @click="save">
  Enregistrer
</FotoceButton>
```

**Aperçu (primary)**

```
┌─────────────────────────────────────┐
│         Enregistrer                 │  ← fond rose #db2777, texte blanc
└─────────────────────────────────────┘
     border-radius: var(--fotoce-radius-md)
```

### FotoceInput.vue

Label, hint, error, icône Material (`icon="mail"`), slots `prefix` / `suffix`, dark mode natif.

```vue
<FotoceInput v-model="email" label="Email" icon="mail" :error="errors.email" />
```

### FotoceEmptyState.vue

```vue
<FotoceEmptyState icon="notifications" :title="t('notifications.empty')" :description="hint">
  <template #action>
    <FotoceButton variant="primary" block>Explorer</FotoceButton>
  </template>
</FotoceEmptyState>
```

### FotoceErrorState.vue

État erreur plein écran ou section avec slot `#action` (retry).

---

## Primitives Mobile (`Fotoce-Mobile/src/components/ui/`)

### FotoceButton.tsx

API alignée web : mêmes variants / sizes, `useFotoceStyles` + `FotoceTheme`.

```tsx
<FotoceButton variant="primary" block loading={busy} onPress={save}>
  <FotoceButtonText variant="primary">Enregistrer</FotoceButtonText>
</FotoceButton>
```

### FotoceInput.tsx

```tsx
<FotoceInput label="Email" value={email} onChangeText={setEmail} error={err} hint="Format valide" />
```

### FotoceEmptyState.tsx / FotoceErrorState.tsx

Miroirs web — icônes Material, tokens thème.

### AppToastHost.tsx + `useAppToast.ts`

Remplace `Alert.alert` pour feedback **non-bloquant** :

```ts
import { appToast, appToastSuccess, appToastError } from '../lib/appToast'

appToastSuccess('Boost activé', 'Votre foto sera promu sous peu.')
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
| ✅ 100 % | Classes legacy `app-btn` → `FotoceButton` |
| ✅ | Auth : Login, Register, Forgot, Reset, VerifyOTP |
| ✅ | Settings, Profile, Board, Billing, modales (`AppAlertModal`, `ReportContentModal`) |
| ✅ | Checkout, GuestAuth, Onboarding, Notifications (empty + retry) |
| ⏳ | Boutons icône / éditeurs story (hors scope DS standard) |

Règle : **tout CTA primaire/secondaire** → `FotoceButton`. Les boutons icône toolbar restent `<button>` natifs.

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

1. Nouveau bouton action → `FotoceButton` / `FotoceButton.tsx`
2. Nouveau champ formulaire → `FotoceInput`
3. Liste vide → `FotoceEmptyState`
4. Erreur chargement → `FotoceErrorState` + retry
5. Feedback mobile non-bloquant → `appToast*` (pas `Alert.alert`)
6. Pas de nouvelles classes `app-btn`

---

## Fichiers de référence

```
FOTOCE-FRONTEND/src/components/ui/FotoceButton.vue
FOTOCE-FRONTEND/src/components/ui/FotoceInput.vue
FOTOCE-FRONTEND/src/components/ui/FotoceEmptyState.vue
FOTOCE-FRONTEND/src/components/ui/FotoceErrorState.vue
FOTOCE-FRONTEND/src/style.css                    # .pds-btn
Fotoce-Mobile/src/components/ui/FotoceButton.tsx
Fotoce-Mobile/src/components/ui/FotoceInput.tsx
Fotoce-Mobile/src/components/AppToastHost.tsx
Fotoce-Mobile/src/lib/useAppToast.ts
```
