"""Gesamtaudit 08.11.2026: Regressionstests (Kassenschutz F-07, Linkschlüssel F-04, GA8-05)."""

import datetime

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from core.tenancy import tenant_context
from finance import gobd
from finance.models import Account, Booking, YearClosing
from organizations.models import Organization

from .verbund_netz import app_role

pytestmark = pytest.mark.django_db
DAY = datetime.date(2025, 3, 1)


def _booking(org):
    account = Account.objects.get_or_create(
        organization=org, name="Bank", defaults={"opening_date": "2025-01-01"}
    )[0]
    return Booking.objects.create(
        organization=org,
        account=account,
        year=DAY.year,
        number=1,
        date=DAY,
        kind="income",
        amount="10.00",
        text="Spende",
    )


def _fails(fn, exc=DatabaseError) -> bool:
    try:
        with transaction.atomic():
            fn()
    except exc:
        return True
    return False


def test_sitzungsvariable_hebt_kassenschutz_nicht_mehr_auf(orgs):
    org = orgs["a"]
    with tenant_context(org.pk):
        b = _booking(org)
    Organization.objects.filter(pk=org.pk).update(finance_locked_until=DAY)

    def loeschen():
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.gobd_erasure', 'on', true)")
        Booking.objects.filter(pk=b.pk).delete()

    with app_role(), tenant_context(org.pk):
        assert _fails(loeschen, IntegrityError)
    assert Booking.objects.filter(pk=b.pk).exists()


def test_app_rolle_kann_freigabe_nicht_selbst_eintragen(orgs):
    org = orgs["a"]

    def eintragen():
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO finance_gobd_freigabe (organization_id, art) VALUES (%s, 'einheit')",
                [org.pk],
            )

    def testdatum():
        with connection.cursor() as cur:
            cur.execute("INSERT INTO finance_gobd_testdatum (heute) VALUES ('2099-01-01')")

    with app_role():
        assert _fails(eintragen)
        assert _fails(testdatum)


def test_belege_erst_nach_aufbewahrungsfrist(orgs):
    org = orgs["a"]
    YearClosing.objects.get_or_create(organization=org, year=2025)
    start, end = datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)
    sql = "SELECT finance_gobd_freigeben_belege(%s, %s, %s, %s)"
    with connection.cursor() as cur:
        cur.execute("DELETE FROM finance_gobd_testdatum")
    with app_role():
        # Frist läuft bis Ende 2033 (heutiges Datum der Datenbank)
        assert _fails(lambda: gobd._call(sql, [org.pk, 2025, start, end]), IntegrityError)
        # Ohne Jahresabschluss nie
        old = [datetime.date(2015, 1, 1), datetime.date(2015, 12, 31)]
        assert _fails(lambda: gobd._call(sql, [org.pk, 2015, *old]), IntegrityError)


def test_plattform_nicht_als_einheit_loeschbar(orgs):
    platform = Organization.platform()
    with app_role():
        assert _fails(lambda: gobd.release_unit(platform.pk), IntegrityError)


def test_ausweis_schluessel_verschluesselt_und_ueber_hash_gefunden(orgs, settings, tmp_path):
    from cards import services as cards
    from cards.models import MemberCard

    from .factories import make_member

    settings.PRIVATE_ROOT = tmp_path / "private"
    club = orgs["a"]
    club.enabled_modules = sorted({*club.enabled_modules, "cards"})
    club.save()
    m = make_member(club, "Erika", "Muster")
    with tenant_context(club.pk):
        card = MemberCard.objects.create(organization=club, membership=m)
        token = card.token
        with connection.cursor() as cur:
            cur.execute("SELECT token, token_hash FROM cards_membercard WHERE id = %s", [card.pk])
            raw, stored_hash = cur.fetchone()
        assert raw.startswith("enc1:") and token not in raw
        assert stored_hash and token not in stored_hash
        assert MemberCard.objects.get(pk=card.pk).token == token
    assert cards.find_valid(token).pk == card.pk
    with tenant_context(club.pk):
        cards.renew(card)
    assert cards.find_valid(token) is None
    assert cards.find_valid(card.token).pk == card.pk


@pytest.mark.parametrize("modul_an", [True, False])
def test_helferdienste_fremder_verein_immer_404(orgs, board_a, api, modul_an):
    fremd = orgs["b"]
    mods = {*fremd.enabled_modules} - {"helpers"}
    fremd.enabled_modules = sorted(mods | ({"helpers"} if modul_an else set()))
    fremd.save()
    assert api(board_a).get(f"/api/orgs/{fremd.pk}/helpers/").status_code == 404


def test_ansicht_als_rolle_fremder_verein_404(orgs, board_a, api):
    assert api(board_a).delete(f"/api/orgs/{orgs['b'].pk}/ansicht/").status_code == 404


@pytest.fixture
def platform_admin(db):
    from .factories import give_role, make_user

    user = make_user("plattform-0811@example.org")
    give_role(user, Organization.platform())
    return user


QUARANTAENE_LEER = {"pending": 0, "infected": 0}


@pytest.mark.parametrize(
    ("socket", "required", "erwartet"),
    [
        ("", False, {"enabled": False, "required": False, "quarantine": QUARANTAENE_LEER}),
        (
            "/run/clamd.ctl",
            True,
            {"enabled": True, "required": True, "quarantine": QUARANTAENE_LEER},
        ),
    ],
)
def test_plattform_sieht_stand_der_virenpruefung(
    api, platform_admin, settings, socket, required, erwartet
):
    settings.CLAMD_SOCKET = socket
    settings.VIRUS_SCAN_REQUIRED = required
    data = api(platform_admin).get("/api/platform/update/").json()
    assert data["virus_scan"] == erwartet
