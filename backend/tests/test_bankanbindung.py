"""Bankanbindung (FT1): Bankzugang einrichten und Umsätze direkt bei der Bank abrufen.

Die Bank ist der nachgebaute FinTS-Server aus ``tests/fints_server.py``.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import base64
import datetime
import json
import logging
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from audit.models import AuditEntry
from core.tenancy import tenant_context
from finance import bank_fetch, bankweg, camt, mt940
from finance.models import Account, BankAccess, BankLine, BankStatement, BankTask

from . import fints_server
from .test_kontoauszug import camt_xml, entry
from .test_m9_billing import JSON, base, c, club, setup, zug  # noqa: F401

pytestmark = pytest.mark.django_db

PIN = "Zq7Wal82x"  # kommt in keiner IBAN und keiner Kennung vor
IBAN = fints_server.IBAN


@pytest.fixture(autouse=True)
def _bankweg(settings):
    settings.FINTS_ENABLED = True
    settings.FINTS_PRODUCT_ID = "TESTPRODUKT0000000000"
    settings.FINTS_ALLOW_INTERNAL = True
    cache.clear()


@pytest.fixture
def bank():
    """Startet die nachgebaute Bank; ``bank(tan=True)`` verlangt eine TAN für Umsätze."""
    stops = []

    def _start(**options):
        url, state, stop = fints_server.start({"pin": PIN, **options})
        stops.append(stop)
        return url, state

    yield _start
    for stop in stops:
        stop()


@pytest.fixture
def fin(club):
    return f"/api/orgs/{club.pk}/finance"


@pytest.fixture
def konto(club, setup):
    """Das Girokonto aus ``setup`` bekommt die IBAN der nachgebauten Bank."""
    with tenant_context(club.pk):
        Account.objects.filter(pk=setup["bank"]).update(iban=IBAN)
        club.bank_access_enabled = True
        club.save(update_fields=["bank_access_enabled"])
    return setup["bank"]


def anlegen(c, fin, url, **extra):
    resp = c.post(
        f"{fin}/bank-access/",
        {"name": "Testbank", "bank_code": "12345678", "url": url, "login": "test1", **extra},
        content_type=JSON,
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["id"]


def schritt(c, fin, access, what, pin=PIN, **extra):
    return c.post(f"{fin}/bank-access/{access}/{what}/", {"pin": pin, **extra}, content_type=JSON)


def eingerichtet(c, fin, url):
    access = anlegen(c, fin, url)
    resp = schritt(c, fin, access, "setup")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "done", resp.json()
    return access


def weiter(c, fin, task, tan="", pin=PIN):
    return c.post(f"{fin}/bank-tasks/{task}/continue/", {"pin": pin, "tan": tan}, content_type=JSON)


# --- Schalter und Rechte ---


def test_ohne_servereinstellung_nicht_verfuegbar(c, fin, konto, settings):
    settings.FINTS_PRODUCT_ID = ""
    data = c.get(f"{fin}/bank-access/").json()
    assert data == {"available": False, "enabled": False, "accesses": []}
    resp = c.post(
        f"{fin}/bank-access/",
        {"name": "x", "bank_code": "12345678", "url": "https://bank.example/fints", "login": "a"},
        content_type=JSON,
    )
    assert resp.status_code == 400
    assert bankweg.available_ways() == []


def test_schalter_je_verein(c, fin, club, setup):
    data = c.get(f"{fin}/bank-access/").json()
    assert data["available"] is True and data["enabled"] is False
    resp = c.post(
        f"{fin}/bank-access/",
        {"name": "x", "bank_code": "12345678", "url": "https://bank.example/fints", "login": "a"},
        content_type=JSON,
    )
    assert resp.status_code == 400


def test_eingaben_geprueft(c, fin, konto, settings):
    settings.FINTS_ALLOW_INTERNAL = False
    for change in (
        {"bank_code": "1234"},
        {"url": "http://bank.example/fints"},
        {"url": "ftp://bank.example/"},
    ):
        body = {
            "name": "x",
            "bank_code": "12345678",
            "url": "https://bank.example/fints",
            "login": "a",
            **change,
        }
        resp = c.post(f"{fin}/bank-access/", body, content_type=JSON)
        assert resp.status_code == 400, change


def test_zweiter_faktor_noetig(c, fin, konto, settings):
    settings.MFA_STEP_UP = True
    resp = c.post(
        f"{fin}/bank-access/",
        {"name": "x", "bank_code": "12345678", "url": "https://bank.example/fints", "login": "a"},
        content_type=JSON,
    )
    assert resp.status_code == 403
    assert not BankAccess.objects.filter(organization_id=konto).exists()


def test_anderer_verein_sieht_nichts(c, fin, konto, bank, api, board_b):
    url, _ = bank()
    access = eingerichtet(c, fin, url)
    other = api(board_b)
    assert other.get(f"{fin}/bank-access/").status_code in (403, 404)
    assert schritt(other, fin, access, "fetch").status_code in (403, 404)


def test_anmeldename_wird_nie_ausgegeben(c, fin, konto, bank, club):
    url, _ = bank()
    access = anlegen(c, fin, url, login="geheimer-name-77")
    text = c.get(f"{fin}/bank-access/").content.decode()
    assert "geheimer-name" not in text
    assert "…77" in text
    with connection.cursor() as cur:
        cur.execute("SELECT login FROM finance_bankaccess WHERE id = %s", [access])
        assert "geheimer-name" not in cur.fetchone()[0]


# --- Einrichten ---


def test_einrichten_verbindet_konten(c, fin, konto, bank, club):
    url, _ = bank()
    access = anlegen(c, fin, url)
    resp = schritt(c, fin, access, "setup")
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    assert data["status"] == "done" and data["kind"] == "setup"
    assert data["linked"] == [IBAN]
    with tenant_context(club.pk):
        obj = BankAccess.objects.get(pk=access)
        assert obj.ready and IBAN in obj.ibans
        assert obj.tan_mechanism
        assert Account.objects.get(pk=konto).bank_access_id == access
        assert AuditEntry.objects.filter(organization=club, object_type="bankaccess").exists()
    listed = c.get(f"{fin}/bank-access/").json()["accesses"][0]
    assert listed["ready"] is True
    assert [a["iban"] for a in listed["accounts"]] == [IBAN]


def test_abruf_erst_nach_einrichten(c, fin, konto, bank):
    url, _ = bank()
    access = anlegen(c, fin, url)
    resp = schritt(c, fin, access, "fetch")
    assert resp.status_code == 409
    assert resp.json()["code"] == "unsupported"


def test_aenderung_der_zugangsdaten_setzt_zurueck(c, fin, konto, bank, club):
    url, _ = bank()
    access = eingerichtet(c, fin, url)
    resp = c.patch(f"{fin}/bank-access/{access}/", {"name": "Hausbank"}, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["ready"] is True
    resp = c.patch(f"{fin}/bank-access/{access}/", {"login": "test2"}, content_type=JSON)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["ready"] is False and resp.json()["accounts"] == []
    with tenant_context(club.pk):
        assert Account.objects.get(pk=konto).bank_access_id is None


def test_loeschen_laesst_konto_und_umsaetze(c, fin, konto, bank, club):
    url, _ = bank()
    access = eingerichtet(c, fin, url)
    assert schritt(c, fin, access, "fetch").status_code == 200
    assert c.delete(f"{fin}/bank-access/{access}/").status_code == 204
    with tenant_context(club.pk):
        assert Account.objects.get(pk=konto).bank_access_id is None
        assert BankLine.objects.filter(account_id=konto).count() == 3


# --- Abrufen ---


def test_abruf_liest_umsaetze_ein(c, fin, konto, bank, club):
    url, _ = bank()
    access = eingerichtet(c, fin, url)
    resp = schritt(c, fin, access, "fetch")
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    assert data["status"] == "done" and data["lines"] == 3 and data["duplicates"] == 0
    with tenant_context(club.pk):
        st = BankStatement.objects.get(pk=data["statements"][0])
        assert st.channel == "fints"
        assert st.account_id == konto
        assert st.opening_balance == Decimal("1041.23")
        assert st.closing_balance == Decimal("1273.60")
        assert st.source  # Rohdaten der Bank liegen als Original bei
        lines = list(BankLine.objects.filter(statement=st).order_by("date", "pk"))
        assert [(line.amount, line.credit) for line in lines] == [
            (Decimal("182.34"), True),
            (Decimal("100.03"), True),
            (Decimal("50.00"), False),
        ]
        assert lines[0].name == "Erika Muster"
        assert lines[0].end_to_end == "R2015-0001"
        assert "Beitrag 2015" in lines[0].purpose
        assert Account.objects.get(pk=konto).bank_fetched_until == timezone.localdate()
        task = BankTask.objects.filter(access_id=access, kind="fetch").latest("pk")
        assert task.status == "done" and task.dialog == {}
    listed = c.get(f"{fin}/bank-statements/").json()
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert rows[0]["channel"] == "fints"
    tasks = c.get(f"{fin}/bank-tasks/").json()
    assert {t["kind"] for t in tasks} == {"setup", "fetch"}


def test_zweiter_abruf_bringt_nichts_doppelt(c, fin, konto, bank, club):
    url, _ = bank()
    access = eingerichtet(c, fin, url)
    assert schritt(c, fin, access, "fetch").json()["lines"] == 3
    resp = schritt(c, fin, access, "fetch")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["lines"] == 0 and resp.json()["duplicates"] == 3
    with tenant_context(club.pk):
        assert BankLine.objects.filter(account_id=konto).count() == 3


def test_zeitraum_des_abrufs(club, konto):
    today = datetime.date(2026, 5, 20)
    with tenant_context(club.pk):
        access = BankAccess.objects.create(
            organization=club, name="x", bank_code="12345678", url="https://bank.example/"
        )
        account = Account.objects.get(pk=konto)
        account.bank_access = access
        account.save()
        job = bank_fetch.fetch_job(access, today)
        assert job["accounts"] == [{"iban": IBAN, "from": "2026-02-19", "to": "2026-05-20"}]
        account.bank_fetched_until = datetime.date(2026, 5, 10)
        account.save()
        assert bank_fetch.fetch_job(access, today)["accounts"][0]["from"] == "2026-05-03"
        account.bank_access = None
        account.save()
        with pytest.raises(bankweg.BankError):
            bank_fetch.fetch_job(access, today)


# --- Freigabe (TAN) ---


def test_abruf_mit_tan(c, fin, konto, bank, club, api, board_b, caplog):
    caplog.set_level(logging.DEBUG)
    url, state = bank(tan=True)
    access = eingerichtet(c, fin, url)
    resp = schritt(c, fin, access, "fetch")
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    assert data["status"] == "tan" and data["decoupled"] is False
    assert "TAN" in data["challenge"]
    task = data["task"]
    with tenant_context(club.pk):
        obj = BankTask.objects.get(pk=task)
        assert obj.status == "tan"
        # Die PIN steht weder im angehaltenen Dialog noch im Sitzungsstand noch roh in der DB
        assert PIN not in json.dumps(obj.dialog)
        for value in _texts(obj.dialog):
            assert PIN.encode() not in _decoded(value)
        assert PIN.encode() not in _decoded(obj.access.state)
        with connection.cursor() as cur:
            cur.execute("SELECT dialog::text FROM finance_banktask WHERE id = %s", [task])
            raw = cur.fetchone()[0]
        assert PIN not in raw and "dialog" not in raw  # verschlüsselt abgelegt
    # eine andere Person darf den Vorgang nicht fortsetzen
    assert weiter(api(board_b), fin, task, fints_server.TAN).status_code in (400, 403, 404)
    resp = weiter(c, fin, task, fints_server.TAN)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "done" and resp.json()["lines"] == 3
    with tenant_context(club.pk):
        obj = BankTask.objects.get(pk=task)
        assert obj.status == "done" and obj.dialog == {}
    assert PIN not in caplog.text
    assert PIN not in resp.content.decode()
    # an die Bank ging die PIN natürlich schon
    assert any(PIN.encode() in message for message in state["messages"])


def _texts(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _texts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _texts(item)
    elif isinstance(value, str):
        yield value


def _decoded(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except ValueError:  # kein Base64 (binascii.Error ist ein ValueError)
        return value.encode()


def test_falsche_tan_beendet_den_vorgang(c, fin, konto, bank, club):
    url, _ = bank(tan=True)
    access = eingerichtet(c, fin, url)
    task = schritt(c, fin, access, "fetch").json()["task"]
    resp = weiter(c, fin, task, "000000")
    assert resp.status_code == 409 and resp.json()["code"] == "tan"
    # kein zweiter Versuch im selben Dialog
    resp = weiter(c, fin, task, fints_server.TAN)
    assert resp.status_code == 409 and resp.json()["code"] == "expired"
    with tenant_context(club.pk):
        assert BankLine.objects.filter(account_id=konto).count() == 0
        # eine falsche TAN zählt nicht als abgelehnte PIN
        assert BankAccess.objects.get(pk=access).failures == 0
    data = schritt(c, fin, access, "fetch").json()
    assert weiter(c, fin, data["task"], fints_server.TAN).json()["lines"] == 3


def test_freigabe_verfaellt(c, fin, konto, bank, club):
    url, _ = bank(tan=True)
    access = eingerichtet(c, fin, url)
    task = schritt(c, fin, access, "fetch").json()["task"]
    with tenant_context(club.pk):
        BankTask.objects.filter(pk=task).update(
            expires_at=timezone.now() - datetime.timedelta(seconds=1)
        )
    resp = weiter(c, fin, task, fints_server.TAN)
    assert resp.status_code == 409 and resp.json()["code"] == "expired"
    with tenant_context(club.pk):
        obj = BankTask.objects.get(pk=task)
        assert obj.status == "expired" and obj.dialog == {}


def test_abbrechen_leert_den_dialog(c, fin, konto, bank, club):
    url, _ = bank(tan=True)
    access = eingerichtet(c, fin, url)
    task = schritt(c, fin, access, "fetch").json()["task"]
    assert c.post(f"{fin}/bank-tasks/{task}/cancel/").status_code == 204
    with tenant_context(club.pk):
        obj = BankTask.objects.get(pk=task)
        assert obj.status == "failed" and obj.dialog == {}
    assert weiter(c, fin, task, fints_server.TAN).json()["code"] == "expired"


def test_freigabe_in_der_app(c, fin, konto, bank, club, monkeypatch):
    """Freigabe ohne Eintippen: solange die Bank wartet, bleibt der Vorgang offen."""
    from fints.client import FinTS3PinTanClient

    url, _ = bank(tan=True)
    access = eingerichtet(c, fin, url)
    task = schritt(c, fin, access, "fetch").json()["task"]
    with tenant_context(club.pk):
        obj = BankTask.objects.get(pk=task)
        obj.dialog = {**obj.dialog, "decoupled": True}
        obj.decoupled = True
        obj.save()
    seen = []
    real = FinTS3PinTanClient.send_tan

    def send_tan(self, challenge, tan):
        seen.append((challenge.decoupled, tan))
        if len(seen) == 1:
            return challenge  # die Bank wartet noch auf die Freigabe
        challenge.decoupled = False
        return real(self, challenge, fints_server.TAN)

    monkeypatch.setattr(FinTS3PinTanClient, "send_tan", send_tan)
    resp = weiter(c, fin, task)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "tan" and resp.json()["decoupled"] is True
    resp = weiter(c, fin, task)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "done" and resp.json()["lines"] == 3
    assert seen[0] == (True, "")


# --- Schutz vor einer Sperre bei der Bank ---


def test_falsche_pin_zweimal_dann_ruht_der_zugang(c, fin, konto, bank, club):
    url, state = bank()
    access = eingerichtet(c, fin, url)
    resp = schritt(c, fin, access, "fetch", pin="falsch-1")
    assert resp.status_code == 409 and resp.json()["code"] == "pin"
    listed = c.get(f"{fin}/bank-access/").json()["accesses"][0]
    assert listed["retry_needs_confirm"] is True and listed["paused_until"] is None
    # ohne ausdrückliche Bestätigung geht nichts an die Bank
    sent = len(state["messages"])
    resp = schritt(c, fin, access, "fetch", pin="falsch-2")
    assert resp.status_code == 409 and resp.json()["code"] == "pin_retry"
    assert len(state["messages"]) == sent
    resp = schritt(c, fin, access, "fetch", pin="falsch-2", confirm_retry=True)
    assert resp.status_code == 409 and resp.json()["code"] == "pin"
    sent = len(state["messages"])
    resp = schritt(c, fin, access, "fetch", confirm_retry=True)
    assert resp.status_code == 409 and resp.json()["code"] == "paused"
    assert len(state["messages"]) == sent
    assert c.get(f"{fin}/bank-access/").json()["accesses"][0]["paused_until"]
    with tenant_context(club.pk):
        tasks = BankTask.objects.filter(access_id=access, status="failed")
        assert tasks.count() == 2
        assert all("falsch" not in t.message for t in tasks)
        # nach der Pause geht es mit Bestätigung weiter, ein Erfolg setzt den Zähler zurück
        BankAccess.objects.filter(pk=access).update(locked_until=timezone.now())
    resp = schritt(c, fin, access, "fetch", confirm_retry=True)
    assert resp.status_code == 200, resp.json()
    with tenant_context(club.pk):
        assert BankAccess.objects.get(pk=access).failures == 0


def test_gesperrter_zugang_wird_gemeldet(c, fin, konto, bank):
    url, _ = bank()
    access = anlegen(c, fin, url)
    resp = schritt(c, fin, access, "setup", pin="3938")
    assert resp.status_code == 409
    assert resp.json()["code"] == "locked"


def test_nur_ein_vorgang_gleichzeitig(c, fin, konto, bank):
    url, state = bank()
    access = eingerichtet(c, fin, url)
    cache.add(f"bankweg:{access}", 1, 60)
    sent = len(state["messages"])
    resp = schritt(c, fin, access, "fetch")
    assert resp.status_code == 409 and resp.json()["code"] == "busy"
    assert len(state["messages"]) == sent


def test_bank_nicht_erreichbar(c, fin, konto, bank, club):
    url, _ = bank()
    access = eingerichtet(c, fin, url)
    with tenant_context(club.pk):
        BankAccess.objects.filter(pk=access).update(url="http://127.0.0.1:9/")
    resp = schritt(c, fin, access, "fetch")
    assert resp.status_code == 409 and resp.json()["code"] == "connection"
    with tenant_context(club.pk):
        assert BankAccess.objects.get(pk=access).failures == 0


# --- Formate ---

MT = b"""
:20:STARTUMS
:25:12345678/0000000001
:28C:5/1
:60F:C250301EUR100,00
:61:2503030303C60,00NMSCNONREF//B123
:86:166?00GUTSCHRIFT?109310?20EREF+R2025-0007?21SVWZ+Beitrag 2025 R2025-0
?22007?30GENODE11XXX?31DE02120300000000202051?32Erika?33 Muster
:61:2503040304D25,50NDDTNONREF
:86:109?00RUECKLASTSCHRIFT?109310?20SVWZ+Ruecklastschrift?21MREF+M-1?34914?32Max Beispiel
:61:2503050305RC10,00NMSCNONREF
:86:Storno einer Gutschrift
:62F:C250305EUR124,50
-
"""


def test_mt940_lesen():
    st = mt940.parse(MT, IBAN)
    assert st.iban == IBAN
    assert st.opening == Decimal("100.00") and st.closing == Decimal("124.50")
    assert st.date_from == datetime.date(2025, 3, 1) and st.date_to == datetime.date(2025, 3, 5)
    first, second, third = st.lines
    assert (first.amount, first.credit, first.date) == (
        Decimal("60.00"),
        True,
        datetime.date(2025, 3, 3),
    )
    assert first.name == "Erika Muster"
    assert first.iban == "DE02120300000000202051"
    assert first.end_to_end == "R2025-0007"
    assert first.purpose == "Beitrag 2025 R2025-0007"
    assert first.bank_ref == "B123"
    assert (second.amount, second.credit) == (Decimal("25.50"), False)
    assert second.return_code  # Rücklastschrift erkannt
    assert (third.amount, third.credit) == (Decimal("10.00"), False)  # Storno einer Gutschrift
    assert third.purpose == "Storno einer Gutschrift"


@pytest.mark.parametrize("data", [b"", b"kein mt940", b":20:X\n:61:kaputt\n-"])
def test_mt940_unlesbar(data):
    try:
        st = mt940.parse(data, IBAN)
    except camt.CamtError:
        return
    assert st.lines == []


def test_camt052_aus_dem_abruf():
    xml = (
        camt_xml([entry("12.00", purpose="Spende")], iban=IBAN)
        .decode()
        .replace("camt.053.001.08", "camt.052.001.08")
        .replace("BkToCstmrStmt", "BkToCstmrAcctRpt")
        .replace("<Stmt>", "<Rpt>")
        .replace("</Stmt>", "</Rpt>")
        .encode()
    )
    (st,) = camt.parse_fetched(xml)
    assert st.iban == IBAN and len(st.lines) == 1
    # als hochgeladene Datei bleibt ein Umsatzbericht abgelehnt (kein Kontoauszug)
    with pytest.raises(camt.CamtError):
        camt.parse(xml)


def test_abruf_erkennt_umsaetze_aus_hochgeladener_datei(c, fin, konto, bank, club):
    """Derselbe Umsatz kam schon als CAMT-Datei: der Abruf (MT940) legt ihn nicht doppelt an."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    xml = (
        camt_xml(
            [
                entry(
                    "182.34",
                    date="2015-01-01",
                    e2e="R2015-0001",
                    purpose="Beitrag 2015 R2015-0001",
                    ref="BANKREF-1",
                ),
                entry("100.03", date="2015-03-01", purpose="Spende  Fahne", ref="BANKREF-2"),
            ],
            iban=IBAN,
        )
        .replace(b"2025-03-01T", b"2015-01-01T")
        .replace(b"2025-03-31T", b"2015-03-31T")
    )
    resp = c.post(
        f"{fin}/bank-statements/",
        {"file": SimpleUploadedFile("auszug.xml", xml, content_type="application/xml")},
    )
    assert resp.status_code in (200, 201), resp.content
    url, _ = bank()
    access = eingerichtet(c, fin, url)
    data = schritt(c, fin, access, "fetch").json()
    assert data["lines"] == 1 and data["duplicates"] == 2
    with tenant_context(club.pk):
        assert BankLine.objects.filter(account_id=konto).count() == 3


def test_abbrechen_nur_durch_die_person_die_begonnen_hat(c, fin, konto, bank, club, api):
    """Sicherheitsprüfung 26.11.2026, B-M06."""
    from .factories import give_role, make_user

    url, _ = bank(tan=True)
    access = eingerichtet(c, fin, url)
    task = schritt(c, fin, access, "fetch").json()["task"]
    other = make_user("zweite-kasse@example.org")
    give_role(other, club, ["finance.view", "finance.edit"], name="Zweite Kasse")
    assert api(other).post(f"{fin}/bank-tasks/{task}/cancel/").status_code == 400
    with tenant_context(club.pk):
        assert BankTask.objects.get(pk=task).status == "tan"
    assert c.post(f"{fin}/bank-tasks/{task}/cancel/").status_code == 204
