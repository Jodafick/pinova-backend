from django.apps import AppConfig


class PinsConfig(AppConfig):
    name = 'pins'

    def ready(self):
        from . import signals_media  # noqa: F401
