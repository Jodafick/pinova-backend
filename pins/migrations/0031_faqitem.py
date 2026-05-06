# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0030_legaldocument_public_pages_i18n'),
    ]

    operations = [
        migrations.CreateModel(
            name='FaqItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question_fr', models.CharField(max_length=500, verbose_name='Question (FR)')),
                ('question_en', models.CharField(blank=True, default='', max_length=500, verbose_name='Question (EN)')),
                ('answer_fr', models.TextField(verbose_name='Réponse (FR)')),
                ('answer_en', models.TextField(blank=True, default='', verbose_name='Réponse (EN)')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='Ordre')),
                ('is_published', models.BooleanField(db_index=True, default=True, verbose_name='Publié')),
                (
                    'related_legal_slug',
                    models.CharField(
                        blank=True,
                        choices=[
                            ('', 'Aucun lien'),
                            ('privacy', 'Confidentialité'),
                            ('terms', "Conditions d'utilisation"),
                            ('contact', 'Contact'),
                        ],
                        default='',
                        max_length=40,
                        verbose_name='Lien « en savoir plus »',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Entrée FAQ',
                'verbose_name_plural': 'FAQ',
                'ordering': ['sort_order', 'id'],
            },
        ),
    ]
