# Performance web frontend Pinova (PROMPT 12)

Audit bundle + LCP pour la PWA Vue/Vite. Mesures après optimisations du **2026-06-06**.

## Résumé

| Métrique | Avant (structure) | Après (build prod) |
|----------|-------------------|---------------------|
| **JS initial (`index` + `vendor-vue`)** | ~650–750 KB gzip estimé (FA CSS + glin-profanity dans le graphe initial) | **227 KB gzip** (`index` 177 + `vendor-vue` 50) |
| **Font Awesome** | Chargé globalement dans `main.ts` | Chunk lazy `vendor-icons` (~26 KB gzip CSS) — routes creator/contest uniquement |
| **nsfwjs + TensorFlow.js** | Importé via `useModeration` (chaîne feed) | Chunk lazy `vendor-tfjs` (~39 MB brut) — `/create`, `/story/create`, `/pin/:slug/edit` |
| **glin-profanity** | Top-level dans `useModeration` | Dynamic import dans `textModeration.ts` (routes création / commentaires) |
| **Preconnect API** | Fonts Google uniquement | + `pinova-backend-8mlq.onrender.com` (API + `/media/`) |

## Chunks après build (`pnpm vite build`)

```
dist/assets/index-*.js           584 KB │ gzip 177 KB   ← bundle initial (home / feed)
dist/assets/vendor-vue-*.js      130 KB │ gzip  50 KB   ← Vue + vue-router
dist/assets/vendor-tfjs-*.js    41.4 MB │ gzip ~24 MB  ← lazy (création média)
dist/assets/vendor-icons-*.css    73 KB │ gzip  26 KB   ← lazy (creator / contest)
dist/assets/nsfwScanner-*.js     2.9 KB │ gzip 1.2 KB   ← wrapper scan
dist/assets/moderationPolicy-*.js 1.7 KB │ gzip 0.8 KB ← feed / affichage (sans ML)
```

> **Note :** le chunk `vendor-tfjs` est volumineux (modèle NSFWJS + runtime TF.js). Il n’est **pas** téléchargé sur l’accueil ni le feed — uniquement lors de la navigation vers une route de création (préchargée via `meta.preloadNsfwScanner`).

## Changements implémentés

### 1. `vite.config.ts` — `manualChunks`

- `vendor-vue` : vue, vue-router, @vue/*
- `vendor-tfjs` : @tensorflow/*, nsfwjs, glin-profanity
- `vendor-icons` : @fortawesome/*

### 2. Font Awesome → lazy load

- Retrait de `@fortawesome/fontawesome-free/css/all.min.css` dans `main.ts`
- `src/utils/loadFontAwesome.ts` + `meta.loadFontAwesome` sur routes creator / contest / referrals
- `ProfilePage` : icône certificat migrée vers **Material Symbols** (`verified`)

### 3. Modération découpée

| Module | Rôle | Chargé sur |
|--------|------|------------|
| `moderationPolicy.ts` | Règles pures (blur, adulte, scores) | Feed, détail pin, settings |
| `nsfwScanner.ts` | nsfwjs image/vidéo | Création + double-vérification |
| `textModeration.ts` | glin-profanity (dynamic) | Création, commentaires |
| `useModeration.ts` | Façade avec delegates async | Pages création |

### 4. Preconnect (`index.html`)

```html
<link rel="preconnect" href="https://pinova-backend-8mlq.onrender.com" crossorigin />
<link rel="dns-prefetch" href="https://pinova-backend-8mlq.onrender.com" />
```

Médias servis depuis la même origine API (`/media/`) — un seul preconnect suffit.

### 5. Router

- `preloadNsfwScanner: true` → `create`, `create-standalone-story`, `edit-pin`
- `loadFontAwesome: true` → `creator`, `contest-live`, `referral-contest-live`, `referral-invite`

## Cibles Lighthouse PWA (mobile)

| Core Web Vital | Cible | Actions Pinova |
|----------------|-------|----------------|
| **LCP** | < 2.5 s | Bundle initial −~200 KB gzip ; preconnect API ; images lazy (`PinVirtualGrid`) ; pas de TF.js au 1er paint |
| **CLS** | < 0.1 | Dimensions explicites médias ; splash HTML anti-flash |
| **INP** | < 200 ms | Feed sans scan ML ; chunks vendor-vue isolés |

### Procédure d’audit recommandée

1. `pnpm vite build && pnpm preview` (port 4173)
2. Chrome DevTools → Lighthouse → Mobile → PWA + Performance
3. Throttling : **Slow 4G**, CPU **4× slowdown**
4. URL test : `/` (connecté), `/explore`, `/create` (mesurer chargement lazy séparément)

## Commandes

```bash
cd PINOVA-FRONTEND
pnpm install
pnpm vite build          # bundle (sans vue-tsc si erreurs TS préexistantes)
pnpm test
```

## Piste future

- Remplacer Font Awesome restant (creator dashboard, contest) par Material Symbols → suppression totale de `vendor-icons`
- Héberger un modèle NSFWJS quantifié plus léger ou scanner côté serveur pour éviter les 39 MB client
- `VITE_API_BASE_URL` injecté dans `index.html` au build pour preconnect dynamique (staging/prod)
