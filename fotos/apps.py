from django.apps import AppConfig


class FotosConfig(AppConfig):
    name = 'fotos'
    label = 'fotos'

    def ready(self):
        from . import signals_media  # noqa: F401
        from . import signals_cache  # noqa: F401
        from . import signals_search  # noqa: F401
        from . import signals_variants  # noqa: F401
