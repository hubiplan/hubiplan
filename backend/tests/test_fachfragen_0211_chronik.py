"""Fachfrage FQ12 (Audit 02.11.): Namen auf Wunsch auch aus Chronik und Ehrungen entfernen
(erfundene Daten)."""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest
from django.db import connection

from core.tenancy import rls_bypass
from honors.models import Companion, Dignity, Reign
from members import loeschliste
from members.models import Membership
from members.workflows import NAME_REMOVED

from .test_m3_workflows import JSON, member, types, url  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _liste(settings, tmp_path):
    settings.LOESCHLISTE_PATH = str(tmp_path / "loeschliste" / "loeschliste.jsonl")


def _former(c, orgs, member, capture):
    c.post(
        url(orgs, member, "exit/"),
        {"exit_date": "2020-06-30", "exit_reason": "exit"},
        content_type=JSON,
    )
    with capture(execute=True):
        assert c.post(url(orgs, member, "erase/")).status_code == 200


def test_erst_loeschen_dann_chronik(api, orgs, member, board_a):
    resp = api(board_a).post(url(orgs, member, "erase-history/"))
    assert resp.status_code == 400


def test_namen_entfernt_jahre_bleiben(
    api, orgs, member, board_a, django_capture_on_commit_callbacks
):
    c = api(board_a)
    org = orgs["a"]
    membership = Membership.objects.get(organization=org)
    person = membership.person
    with rls_bypass():
        koenig = Dignity.objects.create(organization=org, name="König")
        reign = Reign.objects.create(
            organization=org, dignity=koenig, year=2015, person=person, name="Erika Muster"
        )
        Companion.objects.create(
            organization=org, reign=reign, label="Königin", person=person, name="Erika Muster"
        )
        other = Reign.objects.create(organization=org, dignity=koenig, year=2016, name="Otto Alt")
    _former(c, orgs, member, django_capture_on_commit_callbacks)
    # Nach dem Löschen bleibt der Name für die Chronik
    reign.refresh_from_db()
    assert reign.person_id == person.pk

    with django_capture_on_commit_callbacks(execute=True):
        resp = c.post(url(orgs, member, "erase-history/"))
    assert resp.status_code == 200, resp.json()
    assert resp.json()["erased"]["Würden"] == 1
    reign.refresh_from_db()
    assert (reign.person_id, reign.name, reign.year) == (None, NAME_REMOVED, 2015)
    with rls_bypass():
        assert Companion.objects.get().name == NAME_REMOVED
    other.refresh_from_db()
    assert other.name == "Otto Alt"
    person.refresh_from_db()
    assert person.last_name == NAME_REMOVED and person.first_name == ""
    assert loeschliste.entries()[-1].get("h") is True

    # Älteres Backup eingespielt: Liste entfernt den Namen erneut
    with rls_bypass():
        # Das alte Backup enthält noch Klartext; bewusst direkt einspielen statt
        # den neuen, nur verschlüsselt schreibenden Anwendungspfad zu verwenden.
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE honors_reign SET person_id = %s, name = %s WHERE id = %s",
                [person.pk, "Erika Muster", reign.pk],
            )
    assert loeschliste.apply() == 1
    reign.refresh_from_db()
    assert reign.name == NAME_REMOVED
    assert loeschliste.apply() == 0
