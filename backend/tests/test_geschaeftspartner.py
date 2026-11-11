"""Geschäftspartner (Konzept geschaeftspartner.md, P1): Rechte, Felder, Ansprechpartner,
Zusammenführen, Löschen, Excel und Mandantentrennung."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook

from access.catalog import codes_for
from billing.models import BusinessPartner, Invoice, PartnerContact
from core.tenancy import tenant_context

from .factories import give_role, make_member, make_user
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db
JSON = "application/json"


@pytest.fixture
def club(orgs):
    return orgs["a"]


@pytest.fixture
def base(club):
    return f"/api/orgs/{club.pk}/billing/partners/"


@pytest.fixture
def c(api, board_a):
    return api(board_a)


def create(c, base, name="Getränke Beispiel GmbH", **extra):
    response = c.post(base, {"details": {"name": name}, **extra}, content_type=JSON)
    assert response.status_code == 201, response.content
    return response.json()


def test_nur_name_pflicht_nummer_und_rollen(c, base):
    first = create(c, base, roles=["supplier", "sponsor"], kind="company")
    assert first["number"] == "GP-0001"
    assert first["roles"] == ["sponsor", "supplier"]
    assert first["is_supplier"] is True and first["is_customer"] is False
    second = create(c, base, name="Ordnungsamt Musterstadt", kind="authority")
    assert second["number"] == "GP-0002"
    # Ohne Rollen bleibt es beim bisherigen Standard „Kunde“ (Ausgangsrechnungen)
    assert second["is_customer"] is True
    bad = c.post(base, {"details": {"name": "X"}, "roles": ["chef"]}, content_type=JSON)
    assert bad.status_code == 400


def test_recht_im_katalog_und_neue_vorstandsrolle():
    assert {"partners.view", "partners.edit"} <= set(codes_for("club"))
    assert {"partners.view", "partners.edit"} <= set(codes_for("unit"))


def test_eigenes_recht_ohne_kasse_sieht_keine_bankdaten(api, club, c, base):
    partner = create(
        c,
        base,
        bank={"iban": "DE89 3704 0044 0532 0130 00", "bic": "cobadeffxxx", "holder": "Beispiel"},
    )
    assert partner["bank"]["iban"] == "DE89370400440532013000"
    assert partner["bank"]["bic"] == "COBADEFFXXX"
    assert partner["bank"]["changed_by"]
    user = make_user("fest@example.org")
    give_role(user, club, ["partners.view", "partners.edit"], name="Festausschuss")
    other = api(user)
    seen = other.get(f"{base}{partner['id']}/").json()
    assert "bank" not in seen and "default_category" not in seen
    # Bankdaten lassen sich ohne Kassenrecht auch nicht ändern
    response = other.patch(
        f"{base}{partner['id']}/",
        {"bank": {"iban": "DE02120300000000202051"}, "notes": "Liefert Fassbier"},
        content_type=JSON,
    )
    assert response.status_code == 200, response.content
    assert c.get(f"{base}{partner['id']}/").json()["bank"]["iban"] == "DE89370400440532013000"
    assert response.json()["notes"] == "Liefert Fassbier"


def test_ohne_recht_kein_zugriff(api, club, base):
    user = make_user("mitglied@example.org")
    give_role(user, club, ["events.view"], name="Mitglied")
    assert api(user).get(base).status_code == 403


def test_ungueltige_iban(c, base):
    response = c.post(
        base, {"details": {"name": "Bank"}, "bank": {"iban": "DE00123"}}, content_type=JSON
    )
    assert response.status_code == 400


def test_ansprechpartner_und_hauptansprechpartner(c, base):
    partner = create(c, base)
    contacts = f"{base}{partner['id']}/contacts/"
    a = c.post(contacts, {"last_name": "Muster", "is_primary": True}, content_type=JSON)
    assert a.status_code == 201, a.content
    b = c.post(
        contacts,
        {"last_name": "Beispiel", "first_name": "Alex", "is_primary": True},
        content_type=JSON,
    )
    assert b.status_code == 201
    listed = c.get(f"{base}{partner['id']}/").json()["contacts"]
    assert [x["last_name"] for x in listed] == ["Beispiel", "Muster"]
    assert [x["is_primary"] for x in listed] == [True, False]
    assert c.delete(f"{contacts}{a.json()['id']}/").status_code == 204


def test_kontaktperson_aus_angaben_wird_ansprechpartner(c, base):
    created = c.post(
        base, {"details": {"name": "Zeltverleih", "contact": "Kim Muster"}}, content_type=JSON
    ).json()
    assert created["contacts"][0]["first_name"] == "Kim"
    assert created["contacts"][0]["last_name"] == "Muster"


def test_zusammenfuehren_nimmt_verweise_mit(c, base, club):
    keep = create(c, base, roles=["supplier"])
    other = create(c, base, name="Getränke Beispiel", roles=["sponsor"])
    c.post(f"{base}{other['id']}/contacts/", {"last_name": "Muster"}, content_type=JSON)
    with tenant_context(club.pk):
        Invoice.objects.create(
            organization=club,
            recipient_kind="partner",
            partner_id=other["id"],
            recipient_name="Getränke Beispiel",
            date="2026-11-01",
            due_date="2026-11-15",
        )
    response = c.post(f"{base}{keep['id']}/merge/", {"other": other["id"]}, content_type=JSON)
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["roles"] == ["sponsor", "supplier"]
    assert [x["last_name"] for x in data["contacts"]] == ["Muster"]
    with tenant_context(club.pk):
        assert not BusinessPartner.objects.filter(pk=other["id"]).exists()
        assert Invoice.objects.filter(partner_id=keep["id"]).count() == 1


def test_loeschen_nur_ohne_verwendung(c, base, club):
    used = create(c, base)
    free = create(c, base, name="Frei")
    with tenant_context(club.pk):
        Invoice.objects.create(
            organization=club,
            recipient_kind="partner",
            partner_id=used["id"],
            recipient_name="Getränke Beispiel",
            date="2026-11-01",
            due_date="2026-11-15",
        )
    assert c.delete(f"{base}{used['id']}/").status_code == 400
    assert c.delete(f"{base}{free['id']}/").status_code == 204


def test_excel_export_und_import(c, base):
    create(c, base, roles=["supplier"])
    exported = c.get(f"{base}export/")
    assert exported.status_code == 200
    sheet = load_workbook(io.BytesIO(exported.content)).active
    assert sheet.cell(2, 2).value == "Getränke Beispiel GmbH"
    book = Workbook()
    ws = book.active
    ws.append(["Name", "Ort", "Rollen", "Art", "Ansprechpartner", "E-Mail"])
    ws.append(["Getränke Beispiel GmbH", "Musterstadt", "", "", "", ""])
    ws.append(["Musterdruck", "Musterstadt", "Lieferant, Sponsor", "Firma", "Kim Muster", ""])
    ws.append(["Kaputt", "", "", "", "", "keine-mail"])
    out = io.BytesIO()
    book.save(out)

    def upload(probe):
        f = SimpleUploadedFile("partner.xlsx", out.getvalue())
        return c.post(f"{base}import/{'?probe=1' if probe else ''}", {"file": f})

    probe = upload(True).json()
    assert probe["created"] == 1 and probe["skipped"] == 1 and len(probe["errors"]) == 1
    assert len(c.get(base).json()) == 1
    result = upload(False).json()
    assert result["created"] == 1
    names = {p["name"]: p for p in c.get(base).json()}
    assert names["Musterdruck"]["roles"] == ["sponsor", "supplier"]
    assert names["Musterdruck"]["contacts"][0]["last_name"] == "Muster"


def _xlsx(book) -> SimpleUploadedFile:
    out = io.BytesIO()
    book.save(out)
    return SimpleUploadedFile("partner.xlsx", out.getvalue())


def test_erstkontakt_und_betreut_von(c, base, club, orgs):
    otto = make_member(club, "Otto", "Muster")
    stranger = make_member(orgs["b"], "Fremd", "Person")
    partner = create(
        c,
        base,
        liaison=otto.pk,
        first_contact_on="2026-03-01",
        first_contact_note="Schützenfest, Stand am Markt",
    )
    assert partner["liaison_name"] == "Otto Muster"
    assert partner["first_contact_on"] == "2026-03-01"
    bad = c.patch(f"{base}{partner['id']}/", {"liaison": stranger.pk}, content_type=JSON)
    assert bad.status_code == 400


def test_export_alle_felder_und_import_aktualisiert(c, base, club):
    otto = make_member(club, "Otto", "Muster")
    with tenant_context(club.pk):
        otto.club_number = "117"
        otto.save()
    partner = create(
        c,
        base,
        roles=["sponsor"],
        notes="Seit Jahren treu",
        liaison=otto.pk,
        first_contact_on="2026-03-01",
        bank={"iban": "DE89370400440532013000"},
    )
    path = f"{base}{partner['id']}/contacts/"
    kim = {"last_name": "Beispiel", "first_name": "Kim", "is_primary": True}
    assert c.post(path, kim, content_type=JSON).status_code == 201
    book = load_workbook(io.BytesIO(c.get(f"{base}export/").content))
    main, contacts = book.worksheets
    head = [cell.value for cell in main[1]]
    row = {h: cell.value for h, cell in zip(head, main[2], strict=True)}
    assert row["Notizen"] == "Seit Jahren treu"
    assert row["Betreut von"] == "Otto Muster" and row["Betreut von (Mitgliedsnummer)"] == "117"
    assert row["IBAN"] == "DE89370400440532013000"
    assert row["Erstkontakt am"].date().isoformat() == "2026-03-01"
    first = [cell.value for cell in contacts[2]]
    assert first[:4] == ["GP-0001", partner["name"], "Beispiel", "Kim"]

    # Datei ändern: Nummer bleibt, Ort und Erstkontakt neu, Ansprechpartner ergänzen
    main.cell(2, head.index("Ort") + 1, "Neustadt")
    main.cell(2, head.index("Erstkontakt") + 1, "Messe")
    main.cell(2, head.index("Rollen") + 1, "Sponsor, Lieferant")
    contacts.cell(2, 5, "Marketing")
    contacts.cell(2, 8, "Nein")
    contacts.append(["GP-0001", "", "Muster", "Alex", "", "alex@example.org", "", "Ja"])
    contacts.append(["GP-9999", "", "Niemand"])
    data = _xlsx(book).read()

    def upload(probe):
        f = SimpleUploadedFile("partner.xlsx", data)
        return c.post(f"{base}import/{'?probe=1' if probe else ''}", {"file": f}).json()

    probe = upload(True)
    assert probe["created"] == 0 and probe["updated"] == 1, probe
    assert probe["contacts_created"] == 1 and probe["contacts_updated"] == 1
    assert len(probe["errors"]) == 1 and "GP-9999" in probe["errors"][0]
    assert c.get(f"{base}{partner['id']}/").json()["details"]["city"] == ""
    result = upload(False)
    assert result["updated"] == 1
    after = c.get(f"{base}{partner['id']}/").json()
    assert after["details"]["city"] == "Neustadt"
    assert after["first_contact_note"] == "Messe"
    assert after["roles"] == ["sponsor", "supplier"]
    assert after["notes"] == "Seit Jahren treu" and after["liaison"] == otto.pk
    people = {p["first_name"]: p for p in after["contacts"]}
    assert people["Kim"]["function"] == "Marketing" and people["Kim"]["is_primary"] is False
    assert people["Alex"]["is_primary"] is True
    # Zweiter Lauf ändert nichts mehr
    again = upload(False)
    assert again["updated"] == 0 and again["contacts_created"] == 0
    assert again["contacts_updated"] == 0


def test_import_bank_nur_mit_kassenrecht(api, club, base):
    user = make_user("fest@example.org")
    give_role(user, club, ["partners.view", "partners.edit"], name="Festausschuss")
    other = api(user)
    book = Workbook()
    book.active.append(["Name", "IBAN", "Betreut von"])
    book.active.append(["Musterdruck", "DE89370400440532013000", ""])
    book.active.append(["Zweitdruck", "", "Unbekannt Niemand"])
    result = other.post(f"{base}import/", {"file": _xlsx(book)}).json()
    assert result["created"] == 1 and len(result["errors"]) == 1
    with tenant_context(club.pk):
        made = [p for p in BusinessPartner.objects.all() if p.name == "Musterdruck"]
        assert len(made) == 1 and made[0].bank == {}
    exported = load_workbook(io.BytesIO(other.get(f"{base}export/").content)).active
    assert "IBAN" not in [cell.value for cell in exported[1]]


def test_fremder_verein_sieht_nichts(c, base, orgs):
    partner = create(c, base)
    with tenant_context(orgs["a"].pk):
        assert PartnerContact.objects.count() == 0
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not BusinessPartner.objects.filter(pk=partner["id"]).exists()
    foreign = f"/api/orgs/{orgs['b'].pk}/billing/partners/{partner['id']}/"
    assert c.get(foreign).status_code == 404


def test_einheit_und_mitgliedschaft_aus_fremdem_verein_abgelehnt(c, base, orgs):
    response = c.post(base, {"details": {"name": "X"}, "unit": orgs["b"].pk}, content_type=JSON)
    assert response.status_code == 400


def test_schalter_hauptmenue(api, club, c, base):
    def summary(client):
        rows = client.get("/api/me/organizations/").json()
        return next(o for o in rows if o["id"] == club.pk)

    assert summary(c)["partners_in_menu"] is False
    response = c.post(f"{base}menu/", {"partners_in_menu": True}, content_type=JSON)
    assert response.status_code == 200, response.content
    assert response.json() == {"partners_in_menu": True}
    assert summary(c)["partners_in_menu"] is True
    assert c.post(f"{base}menu/", {}, content_type=JSON).status_code == 400
    # Nur lesen reicht nicht zum Umschalten
    user = make_user("lesen@example.org")
    give_role(user, club, ["partners.view"], name="Nur lesen")
    reader = api(user)
    assert (
        reader.post(f"{base}menu/", {"partners_in_menu": False}, content_type=JSON).status_code
        == 403
    )
