# ruff: noqa: F401, F811  (Fixtures aus test_datatransfer)
"""Import absichern (Gesamtaudit 15.11., AZ-05, AZ-10, AZ-11). Erfundene Daten.

- AZ-05: Eine Abteilungsdatei legt nur Daten der neuen Abteilung an. Zeilen ohne Abteilung
  werden abgewiesen, die Satzung bleibt draußen, und jeder Bereich der Datei braucht sein
  Bearbeitungsrecht. Bestehende Daten anderer Abteilungen bleiben unberührt.
- AZ-10: Ein Dachverband legt keine „fernen“ Vereine und nur Vereine an.
- AZ-11: Import, Abteilungsexport und Kopplungsaktionen verlangen eine frische Bestätigung.
"""

import json
import uuid

import pytest

from core.tenancy import rls_bypass, tenant_context
from documents.models import Folder
from members.models import DepartmentMembership
from organizations.models import Department, Organization

from .factories import give_role, make_member, make_user
from .test_datatransfer import _eager, _on_commit_now, as_doc, club_c, export, types, upload

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _ordner(club, dept, name):
    with tenant_context(club.pk):
        return Folder.objects.create(
            organization=club, department=dept, name=name, public_key=uuid.uuid4().hex
        )


@pytest.fixture
def abteilungsdatei(api, club_c, board_c):
    _ordner(club_c["club"], club_c["dept"], "Zugakten")
    content, _ = export(
        api(board_c),
        f"/api/orgs/{club_c['club'].pk}",
        kind="department",
        department=club_c["dept"].pk,
    )
    doc = as_doc(content)
    assert doc["tables"]["documents.folder"]
    return doc


def _upload(c, org, doc):
    return upload(c, f"/api/orgs/{org.pk}", json.dumps(doc).encode(), name="Neuzug")


def _run(c, org, job):
    base = f"/api/orgs/{org.pk}"
    c.post(f"{base}/datatransfer/imports/{job['id']}/run/")
    return c.get(f"{base}/datatransfer/imports/{job['id']}/").json()


def test_zeile_ohne_abteilung_wird_abgewiesen(api, orgs, board_a, abteilungsdatei):
    for row in abteilungsdatei["tables"]["documents.folder"]:
        row["department"] = None
    job = _upload(api(board_a), orgs["a"], abteilungsdatei)
    assert job["preview"]["error_count"] >= 1
    assert any("keiner Abteilung" in e for e in job["preview"]["errors"])


def test_nur_einstellungen_reicht_nicht(api, orgs, abteilungsdatei):
    user = make_user("einstellungen-az05@example.org")
    give_role(user, orgs["a"], permissions=["org.edit"], name="Einstellungen")
    c = api(user)
    job = _upload(c, orgs["a"], abteilungsdatei)
    errors = " ".join(job["preview"]["errors"])
    assert "members.edit" in errors and "docs.edit" in errors
    # Nur Rechtenamen, keine Inhalte der Datei
    assert "Zugakten" not in errors and "Muster" not in errors
    job = _run(c, orgs["a"], job)
    assert job["status"] != "done"
    with rls_bypass():
        assert not Department.objects.filter(organization=orgs["a"], name="Neuzug").exists()
        assert not Folder.objects.filter(organization=orgs["a"]).exists()


def test_andere_abteilungen_bleiben_unberuehrt(api, orgs, types, board_a, abteilungsdatei):
    club = orgs["a"]
    with tenant_context(club.pk):
        alt = Department.objects.create(
            self_managed=True, organization=club, name="Altzug", founding_year=1960
        )
    _ordner(club, alt, "Altakten")
    make_member(club, "Ida", "Beispiel", member_type=types["a"]["aktiv"], departments=[alt])
    with rls_bypass():
        before_folders = list(Folder.objects.filter(department=alt).values("pk", "name"))
        before_links = list(
            DepartmentMembership.objects.filter(department=alt).values("pk", "membership_id")
        )
    c = api(board_a)
    job = _upload(c, club, abteilungsdatei)
    assert job["preview"]["error_count"] == 0, job["preview"]["errors"]
    job = _run(c, club, job)
    assert job["status"] == "done", job
    with rls_bypass():
        neu = Department.objects.get(organization=club, name="Neuzug")
        assert set(
            Folder.objects.filter(organization=club)
            .exclude(department=alt)
            .values_list("department_id", flat=True)
        ) == {neu.pk}
        assert list(Folder.objects.filter(department=alt).values("pk", "name")) == before_folders
        assert (
            list(DepartmentMembership.objects.filter(department=alt).values("pk", "membership_id"))
            == before_links
        )


def test_dachverband_legt_keine_fernen_vereine_an(api, orgs, club_c, board_c):
    content, _ = export(api(board_c), f"/api/orgs/{club_c['club'].pk}")
    doc = as_doc(content)
    doc["organization"]["is_remote"] = True
    board_fed = make_user("verband-az10@example.org")
    give_role(board_fed, orgs["federation"])
    c = api(board_fed)
    base = f"/api/orgs/{orgs['federation'].pk}"
    job = upload(c, base, json.dumps(doc).encode(), name="Eingelesen AZ10")
    c.post(f"{base}/datatransfer/imports/{job['id']}/run/")
    job = c.get(f"{base}/datatransfer/imports/{job['id']}/").json()
    assert job["status"] == "done", job
    with rls_bypass():
        new = Organization.objects.get(pk=job["result_organization"]["id"])
        assert new.is_remote is False


def test_nur_vereine_unter_einer_einheit(api, orgs, club_c, board_c):
    content, _ = export(api(board_c), f"/api/orgs/{club_c['club'].pk}")
    doc = as_doc(content)
    unter = json.loads(json.dumps(doc["organization"]))
    unter["type"] = "federation"
    unter["clubs"] = []
    doc["organization"]["clubs"] = [unter]
    board_fed = make_user("verband-az10b@example.org")
    give_role(board_fed, orgs["federation"])
    job = upload(api(board_fed), f"/api/orgs/{orgs['federation'].pk}", json.dumps(doc).encode())
    assert any("nur Vereine" in e for e in job["preview"]["errors"]), job["preview"]


class TestFrischeBestaetigung:
    @pytest.fixture(autouse=True)
    def streng(self, settings):
        settings.MFA_STEP_UP = True

    @pytest.mark.parametrize(
        "pfad",
        [
            "/api/orgs/{a}/datatransfer/imports/",
            "/api/orgs/{a}/peering/codes/",
            "/api/orgs/{a}/peering/couplings/",
            "/api/platform/datatransfer/imports/",
        ],
    )
    def test_verlangt(self, api, orgs, board_a, pfad):
        user = board_a
        if pfad.startswith("/api/platform"):
            user = make_user("plattform-az11@example.org")
            give_role(user, Organization.platform())
        resp = api(user).post(pfad.format(a=orgs["a"].pk), {}, content_type=JSON)
        assert resp.status_code == 403, resp.content
        assert resp.json().get("step_up"), resp.json()

    def test_abteilungsexport(self, api, club_c, board_c):
        resp = api(board_c).post(
            f"/api/depts/{club_c['dept'].pk}/datatransfer/exports/", {}, content_type=JSON
        )
        assert resp.status_code == 403 and resp.json().get("step_up"), resp.content
