# Remplacée : la 0033 référencée (« offline_sync_foundation » + modèle ProcessedAction)
# n’existe pas dans ce dépôt ; les RenameIndex ci-dessous feraient échouer migrate.
# Graphe linéaire conservé : 0032 → 0034 (no-op) → 0035.


from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0032_ai_recommendation_models'),
    ]

    operations = []
