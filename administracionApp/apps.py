from django.apps import AppConfig


class AdministracionappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'administracionApp'

    def ready(self):
        from . import signals  # noqa: F401

