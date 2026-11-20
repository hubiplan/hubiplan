"""Dateien mit der Nextcloud: ablegen (mit Frist je Art) und übernehmen (oidc.nc_files)."""

from __future__ import annotations

import datetime
import json
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.mfa import encrypt
from core import safehttp
from core.tenancy import rls_bypass
from oidc import nc_files
from oidc.models import Client, FileItem

from .factories import give_role, make_user
from .test_nextcloud_anmeldung import make_client

DAV_ROOT = "/remote.php/dav/files/hubiplan-dienst/"


class FakeCloud:
    """WebDAV und Freigaben der Nextcloud, so weit HUBIplan sie braucht."""

    def __init__(self):
        self.folders: set[str] = set()
        self.files: dict[str, bytes] = {}
        self.shares: list[dict] = []
        self.calls: list[tuple[str, str]] = []

    def _ocs(self, data, status=200, code=200):
        body = json.dumps({"ocs": {"meta": {"statuscode": code}, "data": data}}).encode()
        return safehttp.Response(status, {}, body)

    def __call__(self, method, url, *, headers=None, body=None, **kwargs):
        assert headers["Authorization"].startswith("Basic ")
        parts = urlsplit(url)
        self.calls.append((method, parts.path))
        if "/ocs/v2.php/" in parts.path:
            return self._share(method, parts.path.split("/ocs/v2.php/")[1], parse_qs(parts.query))
        assert parts.path.startswith(DAV_ROOT), parts.path
        path = unquote(parts.path[len(DAV_ROOT) :]).rstrip("/")
        if method == "MKCOL":
            if path in self.folders:
                return safehttp.Response(405, {}, b"")
            self.folders.add(path)
            return safehttp.Response(201, {}, b"")
        if method == "PUT":
            if headers.get("If-None-Match") == "*" and path in self.files:
                return safehttp.Response(412, {}, b"")
            self.files[path] = body
            return safehttp.Response(201, {}, b"")
        if method == "GET":
            if path not in self.files:
                return safehttp.Response(404, {}, b"")
            return safehttp.Response(200, {}, self.files[path])
        if method == "DELETE":
            return safehttp.Response(204 if self.files.pop(path, None) else 404, {}, b"")
        if method == "PROPFIND":
            if path not in self.folders:
                return safehttp.Response(404, {}, b"")
            return safehttp.Response(207, {}, self._listing(path))
        raise AssertionError(method)

    def _listing(self, folder: str) -> bytes:
        def response(path: str, is_dir: bool, size: int = 0) -> str:
            href = DAV_ROOT + "/".join(p.replace(" ", "%20") for p in path.split("/"))
            kind = "<d:collection/>" if is_dir else ""
            return (
                f"<d:response><d:href>{href}{'/' if is_dir else ''}</d:href><d:propstat><d:prop>"
                f"<d:resourcetype>{kind}</d:resourcetype>"
                f"<d:getcontentlength>{size}</d:getcontentlength>"
                "<d:getcontenttype>image/jpeg</d:getcontenttype>"
                "</d:prop></d:propstat></d:response>"
            )

        items = [response(folder, True)]
        for f in sorted(self.folders):
            if f.rpartition("/")[0] == folder and f != folder:
                items.append(response(f, True))
        for f, data in sorted(self.files.items()):
            if f.rpartition("/")[0] == folder:
                items.append(response(f, False, len(data)))
        return ('<d:multistatus xmlns:d="DAV:">' + "".join(items) + "</d:multistatus>").encode()

    def _share(self, method, path, query):
        if path == "apps/files_sharing/api/v1/shares" and method == "GET":
            return self._ocs([s for s in self.shares if s["path"] == query["path"][0]])
        if path == "apps/files_sharing/api/v1/shares" and method == "POST":
            share = {
                "id": len(self.shares) + 1,
                "path": query["path"][0],
                "share_type": int(query["shareType"][0]),
                "share_with": query["shareWith"][0],
                "permissions": int(query["permissions"][0]),
            }
            self.shares.append(share)
            return self._ocs(share)
        if path.startswith("apps/files_sharing/api/v1/shares/") and method == "DELETE":
            sid = int(path.rsplit("/", 1)[1])
            self.shares = [s for s in self.shares if s["id"] != sid]
            return self._ocs({})
        raise AssertionError((method, path))


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeCloud()
    monkeypatch.setattr(safehttp, "request", fake)
    return fake


def files_client(org, **extra) -> Client:
    client, _ = make_client(
        org,
        service_user="hubiplan-dienst",
        service_password=encrypt("app-passwort", purpose="nextcloud"),
        files_enabled=True,
        **extra,
    )
    return client


def test_fristen_je_art():
    client = Client(files_retention={})
    day = datetime.date(2026, 11, 20)
    assert nc_files.delete_after(client, "records", day) is None
    assert nc_files.delete_after(client, "statistics", day) is None
    assert nc_files.delete_after(client, "finance", day) == datetime.date(2036, 12, 31)
    assert nc_files.delete_after(client, "reports", day) == datetime.date(2032, 12, 31)
    assert nc_files.delete_after(client, "personal", day) == datetime.date(2027, 2, 20)
    assert nc_files.delete_after(client, "other", day) == datetime.date(2028, 11, 20)
    # Eigene Frist geht vor, 0 heißt dauerhaft
    client.files_retention = {"other": 0, "records": 5}
    assert nc_files.delete_after(client, "other", day) is None
    assert nc_files.delete_after(client, "records", day) == datetime.date(2031, 11, 20)


def test_pfade_ohne_ausbruch():
    assert nc_files.clean_segments("/An HUBIplan//Fotos/") == ["An HUBIplan", "Fotos"]
    for bad in ("../x", "a/../b", ".geheim", "a/\x01"):
        with pytest.raises(nc_files.FilesError):
            nc_files.clean_segments(bad)
    assert nc_files.clean_filename("../böse/name.pdf") == "-böse-name.pdf"


def test_ablegen_legt_ordner_an_gibt_frei_und_ueberschreibt_nie(orgs, board_a, cloud):
    client = files_client(orgs["a"])
    with rls_bypass():
        first = nc_files.store(client, board_a, "finance", "finance", "bericht.pdf", b"%PDF-1")
        second = nc_files.store(client, board_a, "finance", "finance", "bericht.pdf", b"%PDF-2")
    assert first.path == "HUBIplan/Kasse/bericht.pdf"
    assert second.path == "HUBIplan/Kasse/bericht (2).pdf"
    assert cloud.files["HUBIplan/Kasse/bericht.pdf"] == b"%PDF-1"
    assert {"HUBIplan", "HUBIplan/Kasse"} <= cloud.folders
    # Nur lesend, einmal, an die Gruppe des Ziels
    assert cloud.shares == [
        {
            "id": 1,
            "path": "/HUBIplan/Kasse",
            "share_type": 1,
            "share_with": "Kassierer",
            "permissions": 1,
        }
    ]
    assert first.delete_after.month == 12 and first.delete_after.day == 31


def test_andere_gruppe_nimmt_alte_freigabe_zurueck(orgs, board_a, cloud):
    client = files_client(orgs["a"])
    with rls_bypass():
        nc_files.store(client, board_a, "board", "records", "a.pdf", b"x")
        Client.objects.filter(pk=client.pk).update(files_board_group="Vorstand Kern")
        client.refresh_from_db()
        nc_files.store(client, board_a, "board", "records", "b.pdf", b"x")
    assert [s["share_with"] for s in cloud.shares] == ["Vorstand Kern"]


def test_personendaten_nie_fuer_alle_mitglieder(orgs, board_a, cloud):
    client = files_client(orgs["a"])
    with pytest.raises(nc_files.FilesError), rls_bypass():
        nc_files.store(client, board_a, "members", "personal", "liste.xlsx", b"x")
    assert cloud.files == {}


def test_frist_loescht_in_den_papierkorb(orgs, board_a, cloud):
    client = files_client(orgs["a"])
    with rls_bypass():
        item = nc_files.store(client, board_a, "board", "personal", "liste.xlsx", b"x")
        keep = nc_files.store(client, board_a, "board", "records", "protokoll.pdf", b"x")
    assert keep.delete_after is None
    assert nc_files.purge_due(item.delete_after) == 0
    assert nc_files.purge_due(item.delete_after + datetime.timedelta(days=1)) == 1
    assert "HUBIplan/Vorstand/liste.xlsx" not in cloud.files
    assert "HUBIplan/Vorstand/protokoll.pdf" in cloud.files
    with rls_bypass():
        assert FileItem.objects.get(pk=item.pk).deleted_at is not None


def test_ablegen_ueber_die_schnittstelle(api, orgs, board_a, cloud):
    files_client(orgs["a"])
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud-dateien/"
    c = api(board_a)
    status = c.get(url).json()
    assert status["store"] and {t["key"] for t in status["targets"]} == {
        "board",
        "finance",
        "members",
    }
    upload = SimpleUploadedFile("liste.xlsx", b"PK\x03\x04")
    # Personendaten nur mit Bestätigung
    resp = c.post(url, {"file": upload, "target": "board", "category": "personal"})
    assert resp.status_code == 400 and "personal" in resp.json()
    upload.seek(0)
    resp = c.post(url, {"file": upload, "target": "board", "category": "personal", "personal": "1"})
    assert resp.status_code == 201, resp.content
    assert resp.json()["path"] == "HUBIplan/Vorstand/liste.xlsx"


def test_ohne_recht_kein_ablegen(api, orgs, cloud):
    files_client(orgs["a"])
    helper = make_user("helfer@example.org")
    give_role(helper, orgs["a"], ["events.manage"], name="Helfer")
    url = f"/api/orgs/{orgs['a'].pk}/nextcloud-dateien/"
    assert api(helper).get(url).json()["store"] is False
    upload = SimpleUploadedFile("a.pdf", b"%PDF", content_type="application/pdf")
    resp = api(helper).post(url, {"file": upload, "target": "finance", "category": "finance"})
    assert resp.status_code == 403


def test_uebernehmen_nur_aus_dem_freigegebenen_ordner(api, orgs, board_a, cloud):
    files_client(orgs["a"], files_source="An HUBIplan")
    cloud.folders |= {"An HUBIplan", "An HUBIplan/Fest 2026", "Privat"}
    cloud.files["An HUBIplan/Fest 2026/bild 1.jpg"] = b"\xff\xd8\xff"
    cloud.files["Privat/geheim.pdf"] = b"%PDF"
    base = f"/api/orgs/{orgs['a'].pk}/nextcloud-dateien/quelle/"
    c = api(board_a)
    top = c.get(base).json()
    assert [(e["name"], e["is_dir"]) for e in top] == [("Fest 2026", True)]
    inner = c.get(base + "?pfad=Fest%202026").json()
    assert inner[0]["path"] == "Fest 2026/bild 1.jpg" and inner[0]["size"] == 3
    resp = c.get(base + "datei/?pfad=Fest%202026/bild%201.jpg")
    assert resp.status_code == 200 and resp.content == b"\xff\xd8\xff"
    assert resp["Content-Type"] == "application/octet-stream"
    # Kein Weg aus dem Ordner heraus
    assert c.get(base + "datei/?pfad=../Privat/geheim.pdf").status_code == 400
    assert c.get(base + "?pfad=..").status_code == 400
