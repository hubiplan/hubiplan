"""Härtung Stufe 1 (22.11.2026): Argon2id und security.txt.

Kopfzeilen und der Weg von security.txt durch Caddy: scripts/pruefe-caddy.sh.
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.contrib.auth.hashers import check_password, get_hasher, identify_hasher, make_password
from django.test import Client
from django.utils import timezone

BACKEND = Path(__file__).resolve().parents[1]
ARGON2 = "accounts.hashers.Argon2idHasher"
PBKDF2 = "django.contrib.auth.hashers.PBKDF2PasswordHasher"


class TestArgon2id:
    def test_werte_nach_rfc_9106(self, settings):
        settings.PASSWORD_HASHERS = [ARGON2, PBKDF2]
        wert = make_password("Sommerfest-2026!")
        assert wert.startswith("argon2$argon2id$")
        assert "m=65536,t=3,p=4" in wert
        assert check_password("Sommerfest-2026!", wert)
        assert not check_password("sommerfest-2026!", wert)

    def test_ausgeschaltet_wird_argon2id_trotzdem_geprueft(self, settings):
        """Rückweg: Nach dem Ausschalten bleiben umgestellte Konten anmeldbar und wandern zurück."""
        settings.PASSWORD_HASHERS = [ARGON2, PBKDF2]
        wert = make_password("Sommerfest-2026!")
        settings.PASSWORD_HASHERS = [PBKDF2, ARGON2]
        neu = []
        assert check_password("Sommerfest-2026!", wert, setter=neu.append)
        assert neu == ["Sommerfest-2026!"]  # Django speichert neu, jetzt mit PBKDF2
        assert make_password("x").startswith("pbkdf2_sha256$")

    def test_eingeschaltet_stellt_pbkdf2_bei_der_anmeldung_um(self, settings):
        settings.PASSWORD_HASHERS = [PBKDF2, ARGON2]
        alt = make_password("Sommerfest-2026!")
        settings.PASSWORD_HASHERS = [ARGON2, PBKDF2]
        neu = []
        assert check_password("Sommerfest-2026!", alt, setter=neu.append)
        assert neu == ["Sommerfest-2026!"]
        assert identify_hasher(make_password("x")).algorithm == "argon2"

    def test_schalter_in_den_einstellungen(self):
        """Diese Fassung prüft Argon2id immer und speichert damit nur auf Wunsch."""
        text = (BACKEND / "config/settings.py").read_text(encoding="utf-8")
        assert 'PASSWORD_ARGON2 = env_bool("HUBIPLAN_ARGON2", False)' in text
        assert "[_ARGON2, _PBKDF2] if PASSWORD_ARGON2 else [_PBKDF2, _ARGON2]" in text
        assert get_hasher("default") is not None


@pytest.mark.django_db
class TestSecurityTxt:
    URL = "/.well-known/security.txt"

    def test_ohne_anmeldung_mit_meldestelle_des_projekts(self, settings):
        settings.SECURITY_CONTACT = []
        resp = Client().get(self.URL)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/plain; charset=utf-8"
        text = resp.content.decode()
        assert text.count("Contact: ") == 1
        assert "Contact: https://github.com/hubiplan/hubiplan/security/advisories/new" in text
        assert "Preferred-Languages: de, en" in text
        assert "Canonical: http://testserver/.well-known/security.txt" in text

    def test_ablauf_liegt_in_der_zukunft_und_unter_einem_jahr(self, settings):
        settings.SECURITY_CONTACT = []
        text = Client().get(self.URL).content.decode()
        wert = re.search(r"^Expires: (\S+)$", text, re.M).group(1)
        ablauf = datetime.strptime(wert, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        assert timedelta(days=30) < ablauf - timezone.now() < timedelta(days=365)

    def test_kontakt_des_betreibers_steht_vorn(self, settings):
        settings.SECURITY_CONTACT = ["sicherheit@example.org", "https://example.org/melden"]
        zeilen = Client().get(self.URL).content.decode().splitlines()
        assert zeilen[:3] == [
            "Contact: mailto:sicherheit@example.org",
            "Contact: https://example.org/melden",
            "Contact: https://github.com/hubiplan/hubiplan/security/advisories/new",
        ]

    def test_kein_zeilenumbruch_aus_der_einstellung(self, settings):
        settings.SECURITY_CONTACT = ["a@example.org\nContact: https://boese.example"]
        text = Client().get(self.URL).content.decode()
        assert "\nContact: https://boese.example" not in text

    def test_nur_lesen(self):
        assert Client().post(self.URL).status_code == 405

    def test_verraet_keine_fassung_und_keine_person(self, settings):
        settings.SECURITY_CONTACT = []
        text = Client().get(self.URL).content.decode()
        assert set(re.findall(r"^([A-Za-z-]+):", text, re.M)) == {
            "Contact",
            "Expires",
            "Preferred-Languages",
            "Policy",
            "Canonical",
        }
