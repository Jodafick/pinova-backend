from django.apps import AppConfig


class AdsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ads'
    verbose_name = 'Publicité Pinova'

    def ready(self):
        # Enregistre ``record_user_content_signal`` pour hooks externes (pins, etc.).
        import ads.signals  # noqa: F401
