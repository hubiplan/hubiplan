"""Pinnwand: kurze Beiträge an die Mitglieder (Lückenliste 20.11.2026, A3)."""

import datetime
import io
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from pinboard.models import Notice, NoticePhoto

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"
KEY = "6f1c2a3e-2b7d-4c55-9a1e-0b6f4b7c9d21"


def ok(resp, code=(200, 201)):
    assert resp.status_code in ((code,) if isinstance(code, int) else code), resp.content
    return resp.json() if resp.content else None


def jpeg(name="fest.jpg"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "green").save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def setup(orgs, api):
    from organizations.models import Department
    from portal.models import PortalAccess

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "pinboard", "portal"})
    org.member_portal_enabled = True
    org.department_access_enabled = True
    org.save()
    zug = Department.objects.create(
        self_managed=True, organization=org, name="Jägerzug", short_name="Jäger"
    )
    andere = Department.objects.create(
        self_managed=True, organization=org, name="Grenadiere", short_name="Gren"
    )
    chef = make_user("schreiber@example.org")
    give_role(chef, org, permissions=["pinboard.edit", "pinboard.view"], name="Pinnwand-Team")
    leser = make_user("leser@example.org")
    give_role(leser, org, permissions=["pinboard.view"], name="Pinnwand-Leser")
    people, portals = {}, {}
    for first, depts in (("Anna", [zug]), ("Bernd", [andere]), ("Carla", [])):
        m = make_member(org, first, "Muster", departments=depts)
        user = make_user(f"{first.lower()}-konto@example.org")
        access = PortalAccess.objects.create(organization=org, membership=m, user=user)
        people[first] = m
        portals[first] = (api(user), f"/api/portal/{access.pk}/pinboard/", access, user)
    return {
        "org": org,
        "zug": zug,
        "andere": andere,
        "chef": api(chef),
        "chef_user": chef,
        "leser": api(leser),
        "url": f"/api/orgs/{org.pk}/pinboard/",
        "people": people,
        "portals": portals,
    }


def post(s, **data):
    data.setdefault("text", "Der Bus fährt heute 10 Minuten später ab.")
    return ok(s["chef"].post(s["url"], data, content_type=JSON))


def test_anlegen_sehen_und_neu_zaehler(setup):
    s = setup
    first = post(s)
    assert first["from"] == s["org"].name and first["can_edit"]
    client, url, access, _user = s["portals"]["Carla"]
    data = ok(client.get(f"{url}?seen=0"))
    assert [n["id"] for n in data["notices"]] == [first["id"]]
    assert data["notices"][0]["new"] is True
    assert data["targets"] == []
    # Zähler in der Übersicht, nach dem Lesen null
    from portal.views import portal_summary

    summary = portal_summary(access)
    assert summary["pinboard_enabled"] is True and summary["pinboard_new"] == 1
    ok(client.get(url))
    assert portal_summary(access)["pinboard_new"] == 0
    second = post(s, text="Bilder vom Fest folgen.", pinned=True)
    data = ok(client.get(url))
    # Angeheftet oben, nur der neue ist „neu“
    assert [n["id"] for n in data["notices"]] == [second["id"], first["id"]]
    assert [n["new"] for n in data["notices"]] == [True, False]


def test_nur_lesen_ohne_recht_und_leere_texte(setup):
    s = setup
    assert s["leser"].post(s["url"], {"text": "x"}, content_type=JSON).status_code == 403
    assert ok(s["leser"].get(s["url"]))["can_edit"] is False
    resp = s["chef"].post(s["url"], {"text": "  "}, content_type=JSON)
    assert resp.status_code == 400
    resp = s["chef"].post(s["url"], {"text": "x" * 2001}, content_type=JSON)
    assert resp.status_code == 400
    yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
    resp = s["chef"].post(s["url"], {"text": "x", "visible_until": yesterday}, content_type=JSON)
    assert resp.status_code == 400


def test_modul_aus_und_fremder_verein(setup, orgs, api):
    s = setup
    fremd = make_user("fremd-pinnwand@example.org")
    give_role(fremd, orgs["b"], permissions=["pinboard.edit", "pinboard.view"], name="Fremd")
    assert api(fremd).get(s["url"]).status_code == 404
    s["org"].enabled_modules = sorted(set(s["org"].enabled_modules) - {"pinboard"})
    s["org"].save()
    assert s["chef"].get(s["url"]).status_code == 404
    client, url, _access, _user = s["portals"]["Anna"]
    assert client.get(url).status_code == 404


def test_untereinheit_nur_eigene_mitglieder(setup, api):
    from members.models import DepartmentRoleHolder
    from organizations.models import DepartmentRole

    s = setup
    anna = s["people"]["Anna"]
    role = DepartmentRole.objects.create(
        department=s["zug"], name="Zugführer", permissions=["pinboard.edit"]
    )
    DepartmentRoleHolder.objects.create(
        organization=s["org"], membership=anna, role=role, valid_from=datetime.date(2020, 1, 1)
    )
    client, url, _access, user = s["portals"]["Anna"]
    dept_client = api(user)
    dept_url = f"/api/depts/{s['zug'].pk}/pinboard/"
    notice = ok(dept_client.post(dept_url, {"text": "Zugabend fällt aus."}, content_type=JSON))
    assert Notice.objects.get(pk=notice["id"]).department_id == s["zug"].pk
    assert notice["from"] == "Jägerzug"
    # Verein sieht ihn in der Verwaltung nicht, Anna im Mitgliederbereich schon, Bernd nicht
    assert ok(s["chef"].get(s["url"]))["notices"] == []
    assert [n["id"] for n in ok(client.get(url))["notices"]] == [notice["id"]]
    bernd, bernd_url, _a, _u = s["portals"]["Bernd"]
    assert ok(bernd.get(bernd_url))["notices"] == []
    assert bernd.get(f"{bernd_url}{notice['id']}/").status_code == 404
    assert dept_client.get(f"/api/depts/{s['andere'].pk}/pinboard/").status_code == 404


def test_aus_der_app_schreiben_und_loeschen(setup, api, django_capture_on_commit_callbacks):
    from members.models import DepartmentRoleHolder
    from organizations.models import DepartmentRole

    s = setup
    anna = s["people"]["Anna"]
    role = DepartmentRole.objects.create(
        department=s["zug"], name="Zugführer", permissions=["pinboard.edit"]
    )
    DepartmentRoleHolder.objects.create(
        organization=s["org"], membership=anna, role=role, valid_from=datetime.date(2020, 1, 1)
    )
    client, url, _access, _user = s["portals"]["Anna"]
    data = ok(client.get(url))
    assert data["targets"] == [{"department": s["zug"].pk, "name": "Jägerzug"}]
    # Verein: kein Recht
    resp = client.post(url, {"text": "An alle"}, content_type=JSON)
    assert resp.status_code == 403
    with (
        mock.patch("pinboard.tasks.notify.delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        notice = ok(
            client.post(
                url,
                {"text": "Treffpunkt Kirche", "department": s["zug"].pk, "push": "1"},
                HTTP_IDEMPOTENCY_KEY=KEY,
            )
        )
    assert notice["can_edit"] and notice["author"] == "Anna Muster"
    delay.assert_called_once_with(notice["id"])
    # Derselbe Schlüssel nach Verbindungsabbruch: nichts doppelt
    again = ok(
        client.post(
            url,
            {"text": "Treffpunkt Kirche", "department": s["zug"].pk, "push": "1"},
            HTTP_IDEMPOTENCY_KEY=KEY,
        )
    )
    assert again["id"] == notice["id"] and Notice.objects.count() == 1
    # Bernd (andere Untereinheit) darf nicht löschen, Anna schon
    bernd, bernd_url, _a, _u = s["portals"]["Bernd"]
    assert bernd.delete(f"{bernd_url}{notice['id']}/").status_code == 404
    carla, carla_url, _a, _u = s["portals"]["Carla"]
    ok(client.delete(f"{url}{notice['id']}/"), 204)
    assert not Notice.objects.filter(pk=notice["id"]).exists()
    # Schreiber des Vereins auch aus dem Mitgliederbereich: Ziel Verein
    chef_member = make_member(s["org"], "Chef", "Muster")
    from portal.models import PortalAccess

    acc = PortalAccess.objects.create(
        organization=s["org"], membership=chef_member, user=s["chef_user"]
    )
    data = ok(s["chef"].get(f"/api/portal/{acc.pk}/pinboard/"))
    assert {"department": None, "name": s["org"].name} in data["targets"]
    assert carla.get(carla_url).status_code == 200


def test_fotos_hochladen_zeigen_loeschen(setup):
    s = setup
    resp = s["chef"].post(s["url"], {"text": "Bilder vom Fest", "photos": [jpeg(), jpeg("b.jpg")]})
    notice = ok(resp)
    assert len(notice["photos"]) == 2
    photo = notice["photos"][0]
    assert photo["url"] == f"{s['url']}{notice['id']}/photos/{photo['id']}/"
    image = s["chef"].get(photo["url"])
    assert image.status_code == 200 and image["Content-Type"] == "image/jpeg"
    client, url, _access, _user = s["portals"]["Carla"]
    seen = ok(client.get(url))["notices"][0]["photos"][0]
    assert seen["url"] == f"{url}{notice['id']}/photos/{photo['id']}/"
    assert client.get(seen["url"]).status_code == 200
    # Kein Bild: abgelehnt; mehr als sechs: abgelehnt
    bad = SimpleUploadedFile("x.jpg", b"kein bild", content_type="image/jpeg")
    assert s["chef"].post(f"{s['url']}{notice['id']}/photos/", {"photos": [bad]}).status_code == 400
    many = [jpeg(f"{i}.jpg") for i in range(5)]
    resp = s["chef"].post(f"{s['url']}{notice['id']}/photos/", {"photos": many})
    assert resp.status_code == 400
    data = ok(s["chef"].delete(photo["url"]))
    assert len(data["photos"]) == 1
    ok(s["chef"].delete(f"{s['url']}{notice['id']}/"), 204)
    assert not NoticePhoto.objects.exists()


def test_aendern_mit_version_und_ablauf(setup):
    s = setup
    notice = post(s)
    url = f"{s['url']}{notice['id']}/"
    changed = ok(
        s["chef"].patch(
            url, {"text": "Neu", "version": notice["version"], "pinned": True}, content_type=JSON
        )
    )
    assert changed["text"] == "Neu" and changed["pinned"] and changed["edited_at"]
    resp = s["chef"].patch(url, {"text": "Alt", "version": notice["version"]}, content_type=JSON)
    assert resp.status_code == 409
    # Abgelaufen: Mitglieder sehen ihn nicht mehr, die Verwaltung schon
    Notice.objects.filter(pk=notice["id"]).update(
        visible_until=timezone.localdate() - datetime.timedelta(days=1)
    )
    client, purl, _access, _user = s["portals"]["Carla"]
    assert ok(client.get(purl))["notices"] == []
    assert ok(s["chef"].get(s["url"]))["notices"][0]["expired"] is True


def test_aufraeumen(setup):
    from pinboard.services import purge_due

    s = setup
    alt = post(s)
    fest = post(s, pinned=True)
    abgelaufen = post(s)
    frisch = post(s)
    old = timezone.now() - datetime.timedelta(days=400)
    Notice.objects.filter(pk__in=[alt["id"], fest["id"]]).update(created_at=old)
    Notice.objects.filter(pk=abgelaufen["id"]).update(
        visible_until=timezone.localdate() - datetime.timedelta(days=31)
    )
    assert purge_due() == 2
    assert set(Notice.objects.values_list("pk", flat=True)) == {fest["id"], frisch["id"]}


def test_push_an_app_mitglieder(setup):
    from pinboard import notify

    s = setup
    notice = post(s, push=True)
    accesses = {
        s["people"]["Anna"].pk: s["portals"]["Anna"][2].pk,
        s["people"]["Bernd"].pk: s["portals"]["Bernd"][2].pk,
    }
    with (
        mock.patch("devices.push.app_accesses", return_value=accesses) as app,
        mock.patch("devices.push.send_to_user", return_value=1) as send,
    ):
        assert notify.send(notice["id"]) == 2
        # Nur einmal
        assert notify.send(notice["id"]) == 0
    ids = set(app.call_args.args[0])
    assert {m.pk for m in s["people"].values()} <= ids
    payload = send.call_args.args[1]
    assert payload["t"] == "pinboard" and payload["id"] == notice["id"]
    assert payload["text"].startswith("Der Bus")
    # Ohne Push-Wunsch geht nichts raus
    plain = post(s)
    with mock.patch("devices.push.send_to_user") as send:
        assert notify.send(plain["id"]) == 0
        assert not send.called


def test_rechte_migration_fuer_bestehende_rollen():
    from importlib import import_module

    mod = import_module("pinboard.migrations.0002_rls_rechte")
    assert mod.EDITORS == {"circulars.edit", "events.edit"}
