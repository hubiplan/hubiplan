"""Gesamtaudit 05.11.: Anmeldegrenzen je Absender, geheime Links im Postausgang."""

import pytest
from django.test import Client, override_settings

from core.tenancy import rls_bypass
from outbox.models import OutgoingMail

from .factories import PASSWORD, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
LOGIN = "/_allauth/browser/v1/auth/login"


def _login(email: str, password: str, ip: str) -> int:
    # Hinter Caddy steht die Adresse des Aufrufers im letzten X-Forwarded-For-Eintrag,
    # REMOTE_ADDR ist für alle Aufrufer derselbe Proxy.
    return (
        Client(REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR=ip)
        .post(LOGIN, {"email": email, "password": password}, content_type=JSON)
        .status_code
    )


def test_fehlversuche_sperren_nicht_alle_konten():
    """GA-01: Fehlversuche von einer Adresse sperren keine anderen Aufrufer."""
    make_user("opfer@example.org")
    for i in range(12):
        _login(f"raten{i}@example.org", "falsch", "203.0.113.9")
    assert _login("opfer@example.org", PASSWORD, "198.51.100.20") == 200


def test_viele_anmeldungen_von_verschiedenen_adressen():
    """GA-01: Mehr als 30 Anmeldungen je Minute aus verschiedenen Netzen gehen alle durch."""
    for i in range(32):
        make_user(f"mitglied{i}@example.org")
    status = [
        _login(f"mitglied{i}@example.org", PASSWORD, f"198.51.100.{i + 1}") for i in range(32)
    ]
    assert status == [200] * 32


def test_fehlversuche_von_einer_adresse_bleiben_begrenzt():
    make_user("ziel@example.org")
    for i in range(12):
        _login(f"raten{i}@example.org", "falsch", "203.0.113.7")
    # Die Sperre trifft den Absender selbst weiterhin (allauth antwortet mit 400)
    assert _login("ziel@example.org", PASSWORD, "203.0.113.7") != 200


@override_settings(EMAIL_BACKEND="outbox.backend.OutboxBackend")
def test_postausgang_schwaerzt_alle_geheimen_links(settings):
    """GA-04: Foto-, Ausweis-, Bestätigungs- und Abmeldelinks stehen nicht im Postausgang."""
    from outbox import mail

    front = settings.FRONTEND_URL
    body = (
        f"Foto: {front}/foto/GEHEIM1\n"
        f"Ausweis: {front}/ausweis/GEHEIM2\n"
        f"Bestätigen: {front}/rundschreiben/bestaetigen/GEHEIM3\n"
        f"Abbestellen: {front}/rundschreiben/abmelden/GEHEIM4\n"
        f"Rundschreiben: {front}/rundschreiben/17\n"
    )
    mail.send("x@example.org", "Links", body)
    with rls_bypass():
        stored = OutgoingMail.objects.get(subject="Links").body
    assert "GEHEIM" not in stored
    assert f"{front}/rundschreiben/17" in stored


def test_ausweisgrenze_nimmt_adresse_hinter_dem_proxy():
    """Ausweisseite: Grenze je Aufrufer, nicht je frei wählbarem ersten Eintrag."""
    from cards import views

    def scan(ip_header: str) -> int:
        return Client(HTTP_X_FORWARDED_FOR=ip_header).get("/api/public/card/unbekannt/").status_code

    for i in range(views.RATE[0]):
        scan(f"10.0.0.{i}, 203.0.113.50")
    assert scan("10.9.9.9, 203.0.113.50") == 429
    assert scan("203.0.113.51") == 404
