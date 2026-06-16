# Preuve — suppression compte 30 j (staging local)

**Date** : 6 juin 2026  
**Spec** : `FOTOCE-FRONTEND/e2e/gdpr-account.spec.ts` — test « suppression compte »

## Étapes validées

1. Paramètres → « Programmer la suppression ».
2. Modale avertissement → OK.
3. Modale export optionnel → Confirmer (`request_export: true` côté API si confirmé).
4. Saisie `SUPPRIMER` → `POST /api/me/account-deletion/request/` **200**.
5. `scheduled_at` ≈ J+30 (29–31 jours de grâce).
6. E-mail confirmation via `send_fotoce_mail` (locmem en e2e ; assert backend dans `tests_gdpr.py`).
7. Nettoyage test : `POST me/account-deletion/cancel/`.

## Capture UI (placeholder)

> `docs/evidence/rgpd/screenshots/deletion-scheduled-success.png`

## Backend corrélé

- `accounts/tests_gdpr.py::AccountDeletionGdprTests`
- `accounts/views.py::AccountDeletionRequestView` — purge Celery `purge_scheduled_account_deletions`
