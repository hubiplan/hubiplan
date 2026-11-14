"""Dokumente der Ablage an Termine knüpfen."""
# ruff: noqa: F811  (Fixtures aus test_m12_events)

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditEntry
from events.models import EventAttachment

from .factories import make_user
from .test_m12_events import cal, create, member_with_access, org_base, private_root, zug  # noqa: F401

JSON = "application/json"


def pdf(name="Plan.pdf", body=b"%PDF-1.4 erfundener Plan"):
    return SimpleUploadedFile(name, body, content_type="application/pdf")


def ablage(client, org, title="Ablaufplan", visibility="board", file=None):
    b = f"/api/orgs/{org.pk}/documents/"
    resp = client.post(
        f"{b}folders/", {"name": "Planung", "visibility": visibility}, content_type=JSON
    )
    assert resp.status_code == 201, resp.json()
    resp = client.post(
        f"{b}folders/{resp.json()['id']}/documents/", {"title": title, "file": file or pdf()}
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def body(resp) -> bytes:
    return b"".join(resp.streaming_content)


class TestVerknuepfen:
    def test_verknuepfen_und_fuer_mitglieder_sichtbar(self, cal, board_a, api):
        c = api(board_a)
        base = org_base(cal["a"])
        doc = ablage(c, cal["a"])
        ev = create(c, base, title="Schützenfest")
        url = f"{base}events/{ev['id']}/attachments/"
        choices = c.get(url).json()["documents"]
        assert [d["title"] for d in choices] == ["Ablaufplan"]
        # Vorstandsordner, Termin für Mitglieder: Hinweis im Dialog
        assert choices[0]["narrower"] is True
        resp = c.post(url, {"document": doc["id"]}, content_type=JSON)
        assert resp.status_code == 201, resp.json()
        att = resp.json()["attachments"][0]
        assert att["kind"] == "document" and att["name"] == "Ablaufplan"
        assert att["file_name"] == "Plan.pdf" and att["available"] is True
        assert body(c.get(att["url"])).startswith(b"%PDF")
        # Nicht doppelt, und schon verknüpfte stehen nicht mehr zur Wahl
        assert c.post(url, {"document": doc["id"]}, content_type=JSON).status_code == 400
        assert c.get(url).json()["documents"] == []
        assert any("Dokument verknüpft" in (e.changes or {}) for e in AuditEntry.objects.all())
        # Mitglied sieht das Dokument über den Termin, obwohl der Ordner nur für den Vorstand ist
        _, user, access = member_with_access(cal["a"], "Erika")
        detail = api(user).get(f"/api/portal/{access.pk}/events/{ev['id']}/").json()
        portal_att = detail["attachments"][0]
        assert portal_att["name"] == "Ablaufplan"
        assert body(api(user).get(portal_att["url"])).startswith(b"%PDF")
        # Neue Fassung in der Ablage: der Termin zeigt sie sofort
        db = f"/api/orgs/{cal['a'].pk}/documents/"
        resp = c.post(f"{db}{doc['id']}/versions/", {"file": pdf("Plan2.pdf", b"%PDF-1.7 neu")})
        assert resp.status_code == 201
        assert body(api(user).get(portal_att["url"])) == b"%PDF-1.7 neu"
        # Entfernen löst nur die Verknüpfung, das Dokument bleibt in der Ablage
        assert c.delete(att["url"]).status_code == 204
        from documents.models import Document

        assert Document.objects.filter(pk=doc["id"], deleted_at__isnull=True).exists()

    def test_papierkorb_blendet_aus(self, cal, board_a, api):
        c = api(board_a)
        base = org_base(cal["a"])
        doc = ablage(c, cal["a"], visibility="members")
        ev = create(c, base)
        url = f"{base}events/{ev['id']}/attachments/"
        att = c.post(url, {"document": doc["id"]}, content_type=JSON).json()["attachments"][0]
        db = f"/api/orgs/{cal['a'].pk}/documents/"
        assert c.delete(f"{db}{doc['id']}/").status_code == 204
        # Bearbeitende sehen einen Platzhalter, Mitglieder nichts
        mine = c.get(f"{base}events/{ev['id']}/").json()["attachments"]
        assert mine[0]["available"] is False
        assert c.get(att["url"]).status_code == 404
        _, user, access = member_with_access(cal["a"], "Erika")
        detail = api(user).get(f"/api/portal/{access.pk}/events/{ev['id']}/").json()
        assert detail["attachments"] == []
        # Wiederhergestellt gilt die Verknüpfung wieder
        assert c.post(f"{db}{doc['id']}/restore/").status_code == 200
        detail = api(user).get(f"/api/portal/{access.pk}/events/{ev['id']}/").json()
        assert [a["name"] for a in detail["attachments"]] == ["Ablaufplan"]

    def test_nur_eigene_ablage_und_mit_leserecht(self, cal, board_a, board_b, api):
        doc_b = ablage(api(board_b), cal["b"], title="Fremd")
        c = api(board_a)
        base = org_base(cal["a"])
        ev = create(c, base)
        url = f"{base}events/{ev['id']}/attachments/"
        assert c.post(url, {"document": doc_b["id"]}, content_type=JSON).status_code == 400
        assert not EventAttachment.objects.exists()
        # Termine verwalten ohne Ablage-Recht: keine Auswahl
        from .factories import give_role

        user = make_user("termine@example.org")
        give_role(user, cal["a"], permissions=["events.view", "events.manage"], name="Termine")
        doc_a = ablage(c, cal["a"])
        assert api(user).get(url).json()["documents"] == []
        resp = api(user).post(url, {"document": doc_a["id"]}, content_type=JSON)
        assert resp.status_code == 400

    def test_mitglied_kann_nicht_verknuepfen(self, cal, board_a, api):
        c = api(board_a)
        base = org_base(cal["a"])
        doc = ablage(c, cal["a"], visibility="members")
        ev = create(c, base)
        _, user, access = member_with_access(cal["a"], "Erika")
        resp = api(user).post(
            f"/api/portal/{access.pk}/events/{ev['id']}/attachments/",
            {"document": doc["id"]},
            content_type=JSON,
        )
        assert resp.status_code in (403, 404, 405)

    def test_einladung_nimmt_dokument_mit(self, cal, board_a, api):
        from events import rsvp_link

        c = api(board_a)
        base = org_base(cal["a"])
        doc = ablage(c, cal["a"])
        ev = create(c, base)
        url = f"{base}events/{ev['id']}/attachments/"
        c.post(url, {"document": doc["id"]}, content_type=JSON)
        c.post(url, {"file": pdf("Anfahrt.pdf")})
        from events.models import Event

        chosen, skipped = rsvp_link.mail_attachments(Event.objects.get(pk=ev["id"]))
        assert sorted(a["name"] for a in chosen) == ["Anfahrt.pdf", "Plan.pdf"]
        assert skipped == []


@pytest.mark.parametrize("visibility,expected", [("board", False), ("members", True)])
def test_hinweis_nach_sichtbarkeit(cal, board_a, api, visibility, expected):
    c = api(board_a)
    base = org_base(cal["a"])
    ablage(c, cal["a"], visibility="members")
    ev = create(c, base, visibility=visibility)
    choices = c.get(f"{base}events/{ev['id']}/attachments/").json()["documents"]
    # Mitgliederordner ist nur bei öffentlichen Terminen enger
    assert choices[0]["narrower"] is False
    ablage(c, cal["a"], title="Intern")
    choices = {
        d["title"]: d["narrower"]
        for d in c.get(f"{base}events/{ev['id']}/attachments/").json()["documents"]
    }
    assert choices["Intern"] is expected


def test_rundschreiben_zum_termin_nimmt_dokument_mit(cal, board_a, api):
    c = api(board_a)
    base = org_base(cal["a"])
    doc = ablage(c, cal["a"])
    gone = ablage(c, cal["a"], title="Alt")
    ev = create(c, base, rsvp_enabled=True)
    url = f"{base}events/{ev['id']}/attachments/"
    for d in (doc, gone):
        assert c.post(url, {"document": d["id"]}, content_type=JSON).status_code == 201
    assert c.delete(f"/api/orgs/{cal['a'].pk}/documents/{gone['id']}/").status_code == 204
    resp = c.post(f"/api/orgs/{cal['a'].pk}/circulars/from-event/{ev['id']}/", content_type=JSON)
    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert [a["name"] for a in data["attachments"]] == ["Plan.pdf"]
    assert data["skipped_attachments"] == []
