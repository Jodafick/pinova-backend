# Performance mobile Pinova (PROMPT 13)

Cold start, lazy screens et politique cache images pour **Pinova-Mobile** (Expo / React Native).

## Résumé

| Objectif | Implémentation |
|----------|----------------|
| **Cold start** | Écrans secondaires en `React.lazy` + `Suspense` (splash skeleton) |
| **Eager (bundle initial)** | `FeedScreen`, `LoginScreen`, `RegisterScreen`, `BottomTabHost` |
| **TTI < 2 s** | Marqueurs custom `startupMarks.ts` (proxy TTI = `feed_first_frame`) |
| **Images** | `useDataSaver` → `cachePolicy` + `priority` expo-image ; prefetch feed désactivé en mode léger |

## Architecture lazy screens

```
index.js                    → markStartup('native_entry')
App.tsx                     → app_mount, app_boot_ready
AuthContext                 → auth_ready
RootNavigator               → navigator_interactive (+ BootSplash auth)
FeedScreen                  → feed_mounted, feed_first_frame (TTI)
lazyScreens.tsx             → 30+ écrans secondaires (Suspense + ScreenCenterSkeleton)
```

### Eager (import statique)

- `src/screens/FeedScreen.tsx`
- `src/screens/auth/LoginScreen.tsx`
- `src/screens/auth/RegisterScreen.tsx`
- `src/components/BottomTabHost.tsx` (dans `App.tsx`)

### Lazy (`src/navigation/lazyScreens.tsx`)

Profile, Search, CreatePin, Settings, Contest, Billing, PinDetail, Onboarding, auth secondaire (OTP, forgot password…), etc.

Fallback Suspense : `ScreenCenterSkeleton` (plus léger que le `BootSplash` animé).

## Mesure startup

Module : `src/performance/startupMarks.ts`

| Marqueur | Moment |
|----------|--------|
| `native_entry` | `index.js` avant `registerRootComponent` |
| `app_mount` | premier render `AppBoot` |
| `app_boot_ready` | nav persistence + screen cache hydratés |
| `auth_ready` | fin bootstrap JWT / profil |
| `navigator_interactive` | stack visible (hors BootSplash) |
| `feed_mounted` | mount `FeedScreen` |
| `feed_first_frame` | `requestAnimationFrame` après mount feed |

**TTI estimé** = `feed_first_frame − native_entry` (ms).

En dev, un résumé s’affiche dans la console Metro :

```
[Pinova startup] TTI≈1420ms (cible <2000ms) ✓
```

### Procédure benchmark (Android milieu de gamme)

1. Build release : `eas build --profile preview` ou dev client production-like
2. Fermer l’app (swipe away), relancer à froid
3. Lire les logs Metro / `adb logcat | grep Pinova startup`
4. Répéter 5× ; médiane TTI < 2000 ms

Alternative : intégrer plus tard [`expo-startup-performance`](https://docs.expo.dev/) si besoin de métriques natives Hermes.

## expo-image + `useDataSaver`

Hook : `src/hooks/useDataSaver.ts`

| Mode | `cachePolicy` | `priority` | Prefetch feed |
|------|---------------|------------|---------------|
| Normal (Wi‑Fi) | `memory-disk` | `normal` | Oui |
| Économie (`CELLULAR` ou override `on`) | `disk` | `low` | Non |

Composants alignés :

- `CachedImage.tsx` — grille pins (`PinCard`)
- `FeedStoriesStrip.tsx` — anneaux stories
- `prefetchPinMedia.ts` — prefetch conditionnel dans `PinsFeedList`

Clé AsyncStorage partagée avec le web : `pinova_low_data_override` (`auto` | `on` | `off`).

## Commandes

```bash
cd Pinova-Mobile
yarn typecheck
yarn start
```

## Pistes futures

- Preload ciblé des onglets tab (`search`, `profile`) après TTI via `InteractionManager.runAfterInteractions`
- Migrer les `Image` expo-image restants (Login, Profile…) vers `CachedImage`
- Hermes bytecode + `inlineRequires` dans Metro pour réduire encore le parse initial
