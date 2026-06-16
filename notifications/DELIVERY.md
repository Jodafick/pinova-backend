# Livraison des notifications Fotoce

## Canaux

| Canal | Rôle | Quand |
|-------|------|--------|
| **WebSocket** | Sync temps réel (badge, liste, payload complet) | Toujours à la création |
| **Toast in-app** | Bannière si l’app est ouverte | Événements **nouveaux** ; `in_app_toast: true` |
| **Push Web / Expo** | Alerte OS (app fermée / WS down) | Selon `delivery_mode` |

## Modes (`metadata.delivery_mode`)

| Mode | Push | Usage |
|------|------|--------|
| `ws_fallback_push` | Si WS indisponible | Social (like, save, comment, follow) — défaut |
| `ws_and_push` | Toujours | Concours, parrainage, paiement, rétention, campagnes |
| `ws_only` | Jamais | Micro-mouvements de rang concours, digest |

`create_localized_notification` appelle `enrich_notification_metadata()` si `delivery_mode` / `in_app_toast` sont absents.

## Concours & engagement (push systématique)

- Nouveau mois concours / parrainage
- Jalons : top 100, top 10, 1ère place (pins + parrainage)
- Changement de rang **prioritaire** (podium, entrée/sortie top 10 affiché)
- Fin de mois : podium + classement final participants
- Stories des abonnés, streak découverte, campagnes promo

Micro-changements de rang concours → `ws_only`, pas de toast (badge uniquement).

## Regroupement push social

Types `like`, `save`, `comment`, `follow` : 1 push / 120 s / groupe (ex. `like:pin:42`).

## Audit couverture (backend)

| Domaine | Statut |
|---------|--------|
| Like / save / comment / follow | OK |
| Comment like, mentions | OK |
| Board invite + acceptation invitant | OK (accept ajouté) |
| Siège abonnement famille/équipe | OK + push |
| Paiement / plan / essai Plus | OK + push |
| Publication planifiée | OK + push |
| Campagnes / boost créateur | OK |
| Stories abonnés | OK + push |
| Streak découverte | OK + push |
| Concours fotos (rang, jalons, clôture) | OK (jalons + finalize ajoutés) |
| Concours parrainage | OK + push explicite |
| Bienvenue / OTP | in-app, push si hors ligne |
| Digest hebdo PRO | email + notif `ws_only` |
| Emails réactivation J+7/J+30 | email seul (volontaire) |
| Signalement contenu / modération | pas de notif utilisateur (volontaire) |

## Overrides création

```python
create_localized_notification(
    ...,
    metadata={
        'kind': 'contest_milestone_top10',
        'delivery_mode': 'ws_and_push',
        'in_app_toast': True,
    },
)
```
