from django.apps import AppConfig


class TodosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "todos"
    verbose_name = "Aufgaben"

    def ready(self):
        from . import signals

        signals.connect()
