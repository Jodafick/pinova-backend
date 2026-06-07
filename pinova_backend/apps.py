from django.apps import AppConfig


class PinovaBackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pinova_backend'
    verbose_name = 'Pinova backend core'

    def ready(self):
        from django.conf import settings

        from pinova_backend.core import checks  # noqa: F401
        from pinova_backend.config.cache import redis_url_from_env, warn_if_locmem_in_production

        warn_if_locmem_in_production(redis_url=redis_url_from_env(), debug=settings.DEBUG)

        from pinova_backend.observability.sentry import init_sentry

        init_sentry()

        from pinova_backend.observability.otel import init_opentelemetry

        init_opentelemetry()
