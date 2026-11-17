from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Benutzerkonten"

    def ready(self):
        from . import email_verified, known_device, security

        email_verified.connect()
        security.connect()
        known_device.connect()
