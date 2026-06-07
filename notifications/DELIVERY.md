# Livraison des notifications Pinova

## Canaux

| Canal | Rôle | Quand |
|-------|------|--------|
| **WebSocket** | Sync temps réel (badge, liste, payload complet) | Toujours à la création |
| **Toast in-app** | Bannière légère si l’utilisateur a l’app ouverte | Événements **nouveaux** après connexion ; regroupés par rafale (~900 ms) ; respecte `in_app_toast` |
| **Push Web / Expo** | Alerte OS quand l’app est fermée ou WS indisponible | Selon `delivery_mode` + anti-spam par groupe |

## Modes (`metadata.delivery_mode`)

- **`ws_fallback_push`** (défaut social : like, save, comment, follow)  
  WS + toast in-app si connecté. Push **uniquement** si WS indisponible (hors ligne / dégradé).

- **`ws_and_push`** (critique : paiement, plan, invite tableau, campagnes, concours)  
  WS + toast + push systématique.

- **`ws_only`** (discret : digest, changement de rang concours affiché)  
  Centre de notifications + badge ; **pas** de push ni toast.

## Regroupement push (backend)

Types sociaux : une seule push par **fenêtre 120 s** et par **clé de groupe**  
(ex. `like:pin:42`, `follow:user:7`). Les notifications restent toutes en base + WS.

## Overrides création

```python
create_localized_notification(
    ...,
    metadata={
        'delivery_mode': 'ws_only',      # optionnel
        'in_app_toast': False,           # optionnel
        'kind': 'contest_display_rank_change',
    },
)
```

## Client (PWA)

- Curseur `sessionStorage` : pas de toast pour l’historique au login/reconnexion.
- Rafales : un toast résumé « N nouvelles notifications ».
- Style : surface `notification`, haut mobile / bas-droite desktop, glass blur, coins ~18px.
