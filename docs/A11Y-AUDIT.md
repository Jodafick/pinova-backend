# Audit accessibilité Fotoce — Prompt 25

Date : 2026-06-06  
Périmètre : web (`FOTOCE-FRONTEND`), mobile (`Fotoce-Mobile`), tokens partagés.

## Résumé exécutif

| Domaine | Statut | Notes |
|---------|--------|-------|
| Dark mode parité | ✅ | Web : Clair / Sombre / **Système** (`useAppearance`). Mobile : idem + sync OS optionnelle. |
| Contraste WCAG 2.1 AA | ✅* | Audit automatisé ; 1 paire limite en dark (voir ci-dessous). |
| Focus visible | ✅ | Anneau global + classe `.fotoce-focus-ring`. |
| `aria-label` icônes seules | ✅ | Like, save, menu owner (web + mobile). |
| `prefers-reduced-motion` | ✅ | CSS global web + `ConfettiBurst` ; hook mobile `useReducedMotion`. |

\* Le rose CTA (`#db2777`) sur surface dark (`#08080b`) = **4,35:1** — conforme **AA texte large / composants UI** (seuil 3:1), légèrement sous 4,5:1 pour texte normal. Les icônes dark utilisent `--pn-pink-accent` (`#f472b6`) pour le contraste surface.

---

## 1. Thème & apparence

### Web
- `useAppearance.ts` : préférence `light | dark | system`, écoute `prefers-color-scheme`.
- `SettingsPage.vue` : 3 boutons avec `aria-pressed`, persistance profil `theme_mode`.
- `SettingsProfileExtended.vue` : déjà aligné (personnalisation).

### Mobile
- `ThemeProvider.tsx` : `ThemePreference`, écoute `Appearance.addChangeListener`.
- `SettingsScreen.tsx` : chips Clair / Sombre / Système + interrupteur « Synchroniser avec le système » (réactive le mode système après un choix manuel).
- Stockage : `fotoce_mobile_theme_pref`, `fotoce_mobile_theme_sync_os`.

---

## 2. Audit contrastes automatisé

**Script :** `scripts/a11y-contrast-audit.mjs`  
**Résultats JSON :** `docs/A11Y-CONTRAST-RESULTS.json`

```bash
node scripts/a11y-contrast-audit.mjs
```

### Corrections tokens appliquées

| Token | Avant | Après | Motif |
|-------|-------|-------|-------|
| `--pn-text-placeholder` (light) | `#a898a3` (2,73:1) | `#756d74` (≥4,5:1) | Placeholders inputs |
| `--pn-text-placeholder` (dark) | `#6d6168` (3,39:1) | `#9a8d95` (≥4,5:1) | Placeholders inputs |
| `--pn-pink-accent` (dark) | — | `#f472b6` | Icônes/liens sur surface sombre |

### Dernier run

- **Light :** 9/9 paires AA texte normal
- **Dark :** 8/9 paires AA texte normal
- **Échec résiduel :** CTA rose `#db2777` sur `#08080b` → 4,35:1 (boutons pleins conservent ce rose ; texte blanc sur bouton = 4,6:1 ✅)

---

## 3. Focus visible

### Web (`style.css`)
- Variable `--fotoce-focus-outline`
- Classe utilitaire `.fotoce-focus-ring`
- Règles globales : `button`, `a`, `[role=button]`, `[role=menuitem]`, `[role=tab]`, `[role=radio]`, `[role=switch]`
- Composants DS : `.pds-btn`, `.app-btn`, inputs (déjà couverts)

### Mobile
- `accessibilityRole` + `accessibilityState` sur chips thème et interrupteur sync OS
- Focus natif OS (TalkBack / VoiceOver)

---

## 4. Libellés accessibles (icônes seules)

| Composant | Attribut | Clés i18n |
|-----------|----------|-----------|
| `FotoGrid.vue` — save | `aria-label` | `foto.a11y.save` / `foto.a11y.saved` |
| `FotoGrid.vue` — menu owner | `aria-label` | `foto.ownerMenu.more` |
| `FotoDetailDesktopModal.vue` | `aria-label` | like, save, share, download |
| `FotoDetailMobileFullscreen.vue` | `aria-label` | idem |
| `FotoCard.tsx` (mobile) | `accessibilityLabel` | `foto.a11y.*` |

---

## 5. Réduction des animations

### Web
- `useReducedMotion.ts` + `initReducedMotionWatcher()` (`main.ts`)
- Règles `@media (prefers-reduced-motion: reduce)` dans `style.css` (animations, transitions, confetti)
- `ConfettiBurst.vue` : désactivé si reduced-motion

### Mobile
- `src/hooks/useReducedMotion.ts` — `AccessibilityInfo.isReduceMotionEnabled` + listener `reduceMotionChanged`
- À brancher sur animations custom lourdes si besoin (Reanimated, Lottie)

---

## 6. Checklist manuelle recommandée

- [ ] Navigation clavier complète : fil → détail foto → retour
- [ ] VoiceOver iOS : réglages apparence 3 options + sync OS
- [ ] TalkBack Android : idem
- [ ] Contraste en conditions réelles (luminosité auto, mode sombre OS)
- [ ] Zoom 200 % : pas de perte de contenu settings

---

## 7. Fichiers modifiés (Prompt 25)

```
scripts/a11y-contrast-audit.mjs
docs/A11Y-AUDIT.md
docs/A11Y-CONTRAST-RESULTS.json
FOTOCE-FRONTEND/src/pages/SettingsPage.vue
FOTOCE-FRONTEND/src/components/FotoGrid.vue
FOTOCE-FRONTEND/src/components/ConfettiBurst.vue
FOTOCE-FRONTEND/src/style.css
FOTOCE-FRONTEND/src/theme/tokens.css
FOTOCE-FRONTEND/src/i18n/locales/fr.ts
FOTOCE-FRONTEND/src/i18n/locales/en.ts
Fotoce-Mobile/src/theme/ThemeProvider.tsx
Fotoce-Mobile/src/theme/tokens.ts
Fotoce-Mobile/src/screens/SettingsScreen.tsx
Fotoce-Mobile/src/hooks/useReducedMotion.ts
Fotoce-Mobile/src/i18n/locales/fr.ts
Fotoce-Mobile/src/i18n/locales/en.ts
```
