from allauth.account.adapter import DefaultAccountAdapter
from allauth.headless.adapter import DefaultHeadlessAdapter
from django.utils.translation import gettext_lazy


class AccountAdapter(DefaultAccountAdapter):
    error_messages = {
        **DefaultAccountAdapter.error_messages,
        "too_many_login_attempts": gettext_lazy(
            "Zu viele gescheiterte Anmeldeversuche. Bitte später erneut versuchen. Auf einem "
            "Gerät, mit dem du dich schon einmal angemeldet hast, oder mit einem Passkey "
            "geht die Anmeldung weiter."
        ),
    }

    def is_open_for_signup(self, request) -> bool:
        # Konten werden von Verwaltenden angelegt, nicht selbst registriert.
        return False

    def get_client_ip(self, request) -> str:
        """Adresse des Aufrufers wie bei allen eigenen Grenzen (``core.ratelimit``).

        allauth nähme sonst ``REMOTE_ADDR``. Hinter Caddy ist das für alle Aufrufer
        dieselbe Adresse, und die Grenzen für Anmeldungen würden für alle zugleich
        greifen (Gesamtaudit 05.11. GA-01).
        """
        from core.ratelimit import client_ip

        return client_ip(request) or super().get_client_ip(request)

    def _get_login_attempts_cache_key(self, request, **credentials) -> str:
        """Fehlversuche je Konto, auf bekannten Geräten in einem eigenen Zähler je Gerät.

        Sonst kann jeder, der die E-Mail-Adresse kennt, den Inhaber mit fünf falschen
        Passwörtern aussperren (Gesamtaudit 11.11. S-03, ``known_device``).
        """
        from . import known_device

        key = super()._get_login_attempts_cache_key(request, **credentials)
        device = known_device.device_for(request, credentials.get("email", ""))
        return f"{key}:geraet:{device}" if device else key

    def pre_authenticate(self, request, **credentials) -> None:
        from django.core.exceptions import ValidationError

        from . import known_device

        try:
            super().pre_authenticate(request, **credentials)
        except ValidationError:
            known_device.notify_locked(credentials.get("email", ""))
            raise

    def send_mail(self, template_prefix, email, context):
        """Mails von allauth (z. B. „Passwort vergessen“) in der Sprache des Kontos.

        Versand im Hintergrund (Gesamtaudit 11.11., H-09): Die Antwortzeit verrät dann nicht,
        ob es zu der Adresse ein Konto gibt."""
        from allauth.core import context as allauth_context
        from django.contrib.sites.shortcuts import get_current_site
        from django.utils import translation

        from core.i18n import user_language
        from outbox.tasks import deliver

        user = context.get("user")
        if user is None:
            from .models import User

            user = User.objects.filter(email__iexact=email).first()
        request = allauth_context.request
        ctx = {"request": request, "email": email, "current_site": get_current_site(request)}
        ctx.update(context)
        language = user_language(user) if user is not None else translation.get_language()
        with translation.override(language):
            msg = self.render_mail(template_prefix, email, ctx)
        deliver(msg)


class HeadlessAdapter(DefaultHeadlessAdapter):
    def get_frontend_url(self, urlname: str, **kwargs) -> str | None:
        """Links (Passwort vergessen) auf der Adresse, auf der sie angefordert wurden (W7b)."""
        from organizations.addresses import base_url, rebase

        url = super().get_frontend_url(urlname, **kwargs)
        request = getattr(self, "request", None)
        if url and request is not None:
            url = rebase(url, base_url(request=request))
        return url

    def serialize_user(self, user) -> dict:
        data = super().serialize_user(user)
        # Mit Startpasswort angemeldet: die Oberfläche verlangt zuerst ein eigenes Passwort
        data["must_change_password"] = bool(getattr(user, "must_change_password", False))
        if getattr(user, "pk", None):
            from core.i18n import user_language

            from .mfa_policy import status

            # Sprache des Kontos: die Oberfläche lädt neu, wenn sie anders angezeigt wird
            data["language"] = user_language(user)

            data.update(status(user))
        return data
