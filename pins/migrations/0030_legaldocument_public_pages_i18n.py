# Generated manually

from django.db import migrations, models


def seed_public_pages(apps, schema_editor):
    LegalDocument = apps.get_model('pins', 'LegalDocument')
    from pins.legal_defaults import (
        CONTACT_EN,
        CONTACT_FR,
        PRIVACY_EN,
        PRIVACY_FR,
        TERMS_EN,
        TERMS_FR,
        default_title,
    )

    LegalDocument.objects.update_or_create(
        slug='privacy',
        defaults={
            'title_fr': default_title('privacy', 'fr'),
            'title_en': default_title('privacy', 'en'),
            'body_fr': PRIVACY_FR,
            'body_en': PRIVACY_EN,
            'contact_email': '',
            'translations_cache': {},
        },
    )
    LegalDocument.objects.update_or_create(
        slug='terms',
        defaults={
            'title_fr': default_title('terms', 'fr'),
            'title_en': default_title('terms', 'en'),
            'body_fr': TERMS_FR,
            'body_en': TERMS_EN,
            'contact_email': '',
            'translations_cache': {},
        },
    )
    LegalDocument.objects.update_or_create(
        slug='contact',
        defaults={
            'title_fr': default_title('contact', 'fr'),
            'title_en': default_title('contact', 'en'),
            'body_fr': CONTACT_FR,
            'body_en': CONTACT_EN,
            'contact_email': 'support@pinova.app',
            'translations_cache': {},
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0029_contentreport_unique_pin_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='legaldocument',
            name='title_fr',
            field=models.CharField(blank=True, default='', max_length=500, verbose_name='Titre (FR)'),
        ),
        migrations.AddField(
            model_name='legaldocument',
            name='title_en',
            field=models.CharField(blank=True, default='', max_length=500, verbose_name='Titre (EN)'),
        ),
        migrations.AddField(
            model_name='legaldocument',
            name='contact_email',
            field=models.EmailField(
                blank=True,
                default='',
                help_text='Utilisé pour la page « contact » (mailto).',
                max_length=254,
                verbose_name='E-mail de contact',
            ),
        ),
        migrations.AddField(
            model_name='legaldocument',
            name='translations_cache',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Rempli automatiquement (googletrans), ex. {"es": {"title": "…", "body": "…"}}.',
                verbose_name='Cache traductions',
            ),
        ),
        migrations.AlterField(
            model_name='legaldocument',
            name='slug',
            field=models.CharField(
                choices=[
                    ('privacy', 'Politique de confidentialité'),
                    ('terms', "Conditions d'utilisation"),
                    ('contact', 'Contact'),
                ],
                max_length=40,
                unique=True,
            ),
        ),
        migrations.AlterModelOptions(
            name='legaldocument',
            options={
                'ordering': ['slug'],
                'verbose_name': 'Page publique (légal / contact)',
                'verbose_name_plural': 'Pages publiques (légal / contact)',
            },
        ),
        migrations.RunPython(seed_public_pages, migrations.RunPython.noop),
    ]
