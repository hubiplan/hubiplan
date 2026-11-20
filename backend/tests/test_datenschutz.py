"""Datenschutz-Werkzeuge: Verzeichnis der Verarbeitungstätigkeiten, Auftragsverarbeiter,
Datenpannen mit 72-Stunden-Frist. Alles erfunden."""

import datetime

import pytest
from django.utils import timezone

from billing.models import BusinessPartner, PartnerAgreement
from core.tenancy import tenant_context

from .factories import give_role, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


@pytest.fixture
def setup(orgs, api):
    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "members", "finance", "circulars"})
    org.save()
    chef = make_user("vorsitz@example.org", first_name="Erika")
    give_role(chef, org, permissions=["privacy.edit", "partners.view"], name="Vorsitz")
    kasse = make_user("kasse@example.org", first_name="Karl")
    give_role(kasse, org, permissions=["privacy.view"], name="Kassierer")
    fremd = make_user("fremd@example.org")
    give_role(fremd, org, permissions=["members.view"], name="Schriftführer")
    return {
        "org": org,
        "chef": api(chef),
        "kasse": api(kasse),
        "fremd": api(fremd),
        "base": f"/api/orgs/{org.pk}/privacy/",
    }


def test_verzeichnis_aus_modulen(setup):
    s = setup
    data = ok(s["chef"].get(s["base"]))
    keys = [a["key"] for a in data["activities"]]
    assert "members" in keys and "finance" in keys and "circulars" in keys and "accounts" in keys
    # Nicht eingeschaltete Module fehlen
    assert "competitions" not in keys
    assert data["can_edit"] is True and data["settings"]["toms"]
    # Vorschlag ausblenden: für Leser verschwunden, für Bearbeiter als ausgeblendet markiert
    ok(s["chef"].post(f"{s['base']}hide/", {"key": "circulars", "hidden": True}, content_type=JSON))
    rows = {a["key"]: a for a in ok(s["chef"].get(s["base"]))["activities"]}
    assert rows["circulars"]["hidden"] is True
    reader = ok(s["kasse"].get(s["base"]))
    assert reader["can_edit"] is False
    assert "circulars" not in [a["key"] for a in reader["activities"]]
    assert (
        s["chef"]
        .post(f"{s['base']}hide/", {"key": "gibtsnicht", "hidden": True}, content_type=JSON)
        .status_code
        == 400
    )


def test_eigene_taetigkeit_und_angaben(setup):
    s = setup
    a = ok(
        s["chef"].post(
            f"{s['base']}activities/",
            {"title": "Fahrgemeinschaften", "purpose": "Mitfahrten zu Turnieren"},
            content_type=JSON,
        ),
        201,
    )
    assert (
        s["chef"].post(f"{s['base']}activities/", {"title": " "}, content_type=JSON).status_code
        == 400
    )
    a = ok(
        s["chef"].patch(
            f"{s['base']}activities/{a['id']}/",
            {"legal_basis": "Art. 6 Abs. 1 lit. a DSGVO", "version": a["version"]},
            content_type=JSON,
        )
    )
    # Veraltete Fassung
    assert (
        s["chef"]
        .patch(f"{s['base']}activities/{a['id']}/", {"title": "X", "version": 1}, content_type=JSON)
        .status_code
        == 409
    )
    saved = ok(
        s["chef"].put(
            f"{s['base']}settings/",
            {"dpo_name": "Dora Datenschutz", "hoster": "Muster-Hosting GmbH"},
            content_type=JSON,
        )
    )
    assert saved["dpo_name"] == "Dora Datenschutz"
    data = ok(s["chef"].get(s["base"]))
    assert data["settings"]["hoster"] == "Muster-Hosting GmbH"
    assert "Fahrgemeinschaften" in [x["title"] for x in data["activities"]]
    # PDF für jeden, der lesen darf
    pdf = s["kasse"].get(f"{s['base']}?als=pdf")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    # Lesen darf nicht schreiben, ohne Recht kein Zugriff
    assert (
        s["kasse"].put(f"{s['base']}settings/", {"toms": "x"}, content_type=JSON).status_code == 403
    )
    assert s["fremd"].get(s["base"]).status_code == 403
    ok(s["chef"].delete(f"{s['base']}activities/{a['id']}/"), 204)


def test_auftragsverarbeiter(setup):
    s = setup
    org = s["org"]
    with tenant_context(org.pk):
        mit = BusinessPartner.objects.create(
            organization=org, name="Muster Mailversand", roles=["processor", "service"]
        )
        BusinessPartner.objects.create(
            organization=org, name="Ohne Vertrag Cloud", roles=["processor"]
        )
        BusinessPartner.objects.create(organization=org, name="Bäckerei", roles=["supplier"])
        PartnerAgreement.objects.create(
            organization=org,
            partner=mit,
            kind=PartnerAgreement.Kind.DPA,
            title="AV-Vertrag",
            start=datetime.date(2026, 1, 1),
        )
    procs = ok(s["chef"].get(s["base"]))["processors"]
    assert [p["name"] for p in procs] == ["Muster Mailversand", "Ohne Vertrag Cloud"]
    assert procs[0]["agreement"]["title"] == "AV-Vertrag" and procs[1]["agreement"] is None


def test_datenpanne_frist_und_abschluss(setup, api):
    s = setup
    base = f"{s['base']}breaches/"
    found = timezone.now() - datetime.timedelta(hours=80)
    b = ok(
        s["chef"].post(
            base,
            {
                "title": "Mitgliederliste falsch verschickt",
                "discovered_at": found.isoformat(),
                "description": "Liste ging an einen falschen Verteiler.",
                "risk": "risk",
            },
            content_type=JSON,
        ),
        201,
    )
    assert b["status"] == "overdue" and b["created_by"]
    # Verschlüsselt gespeichert, im Klartext zurück
    assert ok(s["kasse"].get(f"{base}{b['id']}/"))["description"].startswith("Liste ging")
    # Zukunft und Meldung vor dem Bekanntwerden gehen nicht
    future = (timezone.now() + datetime.timedelta(days=1)).isoformat()
    assert (
        s["chef"].post(base, {"title": "x", "discovered_at": future}, content_type=JSON).status_code
        == 400
    )
    assert (
        s["chef"]
        .patch(
            f"{base}{b['id']}/",
            {"reported_at": (found - datetime.timedelta(hours=1)).isoformat()},
            content_type=JSON,
        )
        .status_code
        == 400
    )
    # Abschließen braucht Meldung oder Begründung
    assert (
        s["chef"].patch(f"{base}{b['id']}/", {"closed": True}, content_type=JSON).status_code == 400
    )
    # Offene Panne steht unter „Zu erledigen“
    tasks = ok(s["chef"].get(f"/api/orgs/{s['org'].pk}/open-tasks/"))["items"]
    assert any(t["kind"] == "breach" and t["highlight"] for t in tasks)
    b = ok(
        s["chef"].patch(
            f"{base}{b['id']}/",
            {"reported_at": timezone.now().isoformat(), "report_reference": "LDI-123"},
            content_type=JSON,
        )
    )
    assert b["status"] == "open"
    b = ok(
        s["chef"].patch(
            f"{base}{b['id']}/", {"closed": True, "version": b["version"]}, content_type=JSON
        )
    )
    assert b["status"] == "closed" and b["closed_at"]
    pdf = s["chef"].get(f"{base}{b['id']}/?als=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    tasks = ok(s["chef"].get(f"/api/orgs/{s['org'].pk}/open-tasks/"))["items"]
    assert not any(t["kind"] == "breach" for t in tasks)
    # Ohne Risiko: Abschluss ohne Meldung möglich
    low = ok(
        s["chef"].post(
            base,
            {
                "title": "USB-Stick kurz verlegt",
                "discovered_at": timezone.now().isoformat(),
                "risk": "unlikely",
                "closed": True,
            },
            content_type=JSON,
        ),
        201,
    )
    assert low["status"] == "closed"
    # Lesen ja, anlegen nein
    assert s["kasse"].post(base, {"title": "x"}, content_type=JSON).status_code == 403
    assert len(ok(s["kasse"].get(base))["items"]) == 2
    ok(s["chef"].delete(f"{base}{low['id']}/"), 204)
