"""Termine nach oben unter dem Zeilenschutz (Gesamtaudit 15.11., AZ-04).

Die Regel für ``events_event`` band ``organization_id`` in der Unterabfrage über die Einheiten
an die Einheit selbst (``o.id = o.organization_id``). Im Betrieb sah der Vorstand eines
Dachverbands deshalb keinen nach oben freigegebenen Termin seiner Vereine. Die Anfragen laufen
hier wie im Betrieb unter der Rolle der Anwendung. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest

from core.tenancy import tenant_context
from events.models import Event

from .factories import make_org
from .test_m12_events import create, org_base, titles
from .test_termine_weitergabe import board_fed, cal  # noqa: F401
from .verbund_netz import app_role

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anfragen_unter_app_rolle")]


@pytest.fixture
def fremder_verein(cal):
    """Verein eines anderen Dachverbands, der seine Termine nach oben freigibt."""
    bund = make_org("Zweiter Bund", "federation")
    verein = make_org("Verein X", parent=bund)
    for org in (bund, verein):
        org.enabled_modules = ["members", "events"]
        org.save()
    verein.events_share_up = True
    verein.save()
    Event.objects.create(
        organization=verein,
        title="Fremdes Fest",
        share_up=True,
        starts_at="2026-06-20T14:00:00+02:00",
        ends_at="2026-06-20T18:00:00+02:00",
    )
    return verein


def _unter_zeilenschutz(org) -> set[str]:
    """Titel, die der Zeilenschutz im Kontext der Einheit freigibt (ohne Filter der Sicht)."""
    with tenant_context(org.pk), app_role():
        return set(Event.objects.values_list("title", flat=True))


def test_verein_gibt_alle_termine_nach_oben(cal, board_a, board_fed, fremder_verein, api):
    cal["a"].events_share_up = True
    cal["a"].save()
    c = api(board_a)
    create(c, org_base(cal["a"]), title="Schützenfest")
    create(c, org_base(cal["a"]), title="Nicht nach oben", share_up=False)
    create(c, org_base(cal["a"]), title="Intern", visibility="board")
    got = titles(api(board_fed), org_base(cal["federation"]))
    assert got == ["Schützenfest"]
    assert _unter_zeilenschutz(cal["federation"]) == {"Schützenfest"}


def test_einzelner_termin_nach_oben(cal, board_a, board_fed, fremder_verein, api):
    assert not cal["a"].events_share_up
    c = api(board_a)
    create(c, org_base(cal["a"]), title="Nur dieser", share_up=True)
    create(c, org_base(cal["a"]), title="Standard")
    create(c, org_base(cal["a"]), title="Intern", visibility="board", share_up=True)
    got = titles(api(board_fed), org_base(cal["federation"]))
    assert got == ["Nur dieser"]
    assert _unter_zeilenschutz(cal["federation"]) == {"Nur dieser"}


def test_kein_termin_aus_fremdem_dachverband(cal, board_a, fremder_verein, api):
    cal["a"].events_share_up = True
    cal["a"].save()
    create(api(board_a), org_base(cal["a"]), title="Schützenfest")
    assert _unter_zeilenschutz(fremder_verein.parent) == {"Fremdes Fest"}
    assert "Fremdes Fest" not in _unter_zeilenschutz(cal["federation"])
