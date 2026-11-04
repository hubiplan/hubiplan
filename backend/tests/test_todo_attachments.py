import datetime
import io
import json
import zipfile
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.utils import timezone

from access.models import RoleAssignment
from core.tenancy import tenant_context
from documents.services import total_bytes
from todos.models import Todo, TodoAttachment
from todos.tasks import purge_deleted

from .factories import give_role, make_user
from .test_documents import base as docs_base
from .test_documents import folder, upload
from .test_todo_sharing import share
from .test_todos import create, url

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_root(settings, tmp_path):
    settings.PRIVATE_ROOT = tmp_path / "private"


@pytest.fixture
def reader(orgs):
    user = make_user("anhang-lesen@example.org")
    give_role(user, orgs["a"], permissions=["todos.view"], name="Aufgaben lesen")
    return user


def pdf():
    return SimpleUploadedFile("protokoll.pdf", b"%PDF-1.4 erfundener Anhang", "application/pdf")


def endpoint(org, todo):
    return url(org, todo["id"]) + "attachments/"


def add(api, owner, org, todo, **extra):
    return api(owner).post(
        endpoint(org, todo), {"version": todo["version"], "file": pdf(), **extra}
    )


def test_verschluesselt_budget_und_aktuelle_freigabe(api, board_a, orgs, reader):
    org = orgs["a"]
    todo = share(api, board_a, org, create(api, board_a, org), reader)
    response = add(api, board_a, org, todo)
    assert response.status_code == 201, response.content
    attachment = TodoAttachment.objects.get()
    assert attachment.file.storage.is_encrypted(attachment.file.name)
    with tenant_context(org.pk, board_a.pk):
        assert total_bytes(org) == attachment.size
    file_url = endpoint(org, todo) + f"{attachment.pk}/"
    response = api(reader).get(file_url)
    assert response.status_code == 200
    assert b"erfundener Anhang" in b"".join(response.streaming_content)
    assert response["Cache-Control"] == "private, no-store"
    assert add(api, reader, org, todo).status_code == 403
    current = api(board_a).get(url(org, todo["id"])).json()
    api(board_a).patch(
        url(org, todo["id"]),
        {"version": current["version"], "shares": []},
        content_type="application/json",
    )
    assert api(reader).get(file_url).status_code == 404


def test_upload_prueft_typ_groesse_budget_und_version(api, board_a, orgs):
    org = orgs["a"]
    todo = create(api, board_a, org)
    response = api(board_a).post(
        endpoint(org, todo),
        {
            "version": 1,
            "file": SimpleUploadedFile("falsch.pdf", b"keine PDF"),
        },
    )
    assert response.status_code == 400
    with patch("documents.services.MAX_DOCUMENT_BYTES", 3):
        assert add(api, board_a, org, todo).status_code == 400
    with patch("documents.services.budget_bytes", return_value=3):
        assert add(api, board_a, org, todo).status_code == 400
    assert add(api, board_a, org, todo).status_code == 201
    assert add(api, board_a, org, todo).status_code == 409
    assert TodoAttachment.objects.count() == 1


def test_anhang_papierkorb_wiederherstellen_und_endgueltig_loeschen(
    api, board_a, orgs, django_capture_on_commit_callbacks
):
    org = orgs["a"]
    todo = create(api, board_a, org)
    added = add(api, board_a, org, todo).json()
    attachment = TodoAttachment.objects.get()
    file_url = endpoint(org, todo) + f"{attachment.pk}/"
    deleted = api(board_a).patch(
        file_url, {"version": added["version"], "deleted": True}, content_type="application/json"
    )
    assert deleted.status_code == 200
    assert api(board_a).get(file_url).status_code == 404
    assert attachment.file.storage.exists(attachment.file.name)
    restored = api(board_a).patch(
        file_url,
        {"version": deleted.json()["version"], "deleted": False},
        content_type="application/json",
    )
    assert restored.status_code == 200
    response = api(board_a).get(file_url)
    assert b"erfundener Anhang" in b"".join(response.streaming_content)
    with django_capture_on_commit_callbacks(execute=True):
        TodoAttachment.objects.filter(pk=attachment.pk).update(
            deleted_at=timezone.now() - datetime.timedelta(days=31)
        )
        purge_deleted()
    assert not attachment.file.storage.exists(attachment.file.name)


def test_rollback_behaelt_datei(api, board_a, orgs, django_capture_on_commit_callbacks):
    todo = create(api, board_a, orgs["a"])
    add(api, board_a, orgs["a"], todo)
    attachment = TodoAttachment.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(ValueError), transaction.atomic():
            Todo.objects.get(pk=todo["id"]).delete()
            raise ValueError("zurückrollen")
    assert attachment.file.storage.exists(attachment.file.name)


def test_dokumentverweis_oeffnet_keine_ablage_und_verraet_keinen_titel(api, board_a, orgs, reader):
    org = orgs["a"]
    client = api(board_a)
    f = folder(client, docs_base(org))
    doc = upload(client, docs_base(org), f["id"], title="Vertrauliches Sitzungsprotokoll")
    todo = share(api, board_a, org, create(api, board_a, org), reader)
    response = client.post(
        endpoint(org, todo),
        {"version": todo["version"], "document": doc["id"]},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    att = response.json()["attachment"]
    assert att["name"] == doc["title"]
    seen = api(reader).get(endpoint(org, todo)).json()
    assert seen["documents"] == []
    assert seen["items"][0]["name"] == "Dokument ohne Zugriff"
    assert seen["items"][0]["document"] is None
    assert api(reader).get(endpoint(org, todo) + f"{att['id']}/").status_code == 404
    assert (
        api(reader)
        .post(
            endpoint(org, todo),
            {"version": response.json()["version"], "document": doc["id"]},
            content_type="application/json",
        )
        .status_code
        == 403
    )


def test_privater_dateiexport_und_kontoloeschung_nach_rollenverlust(
    api, board_a, orgs, django_capture_on_commit_callbacks
):
    org = orgs["a"]
    todo = create(api, board_a, org)
    add(api, board_a, org, todo)
    attachment = TodoAttachment.objects.get()
    RoleAssignment.objects.filter(user=board_a).delete()
    response = api(board_a).get("/api/me/todos/export/?files=1")
    assert response.status_code == 200, response.content if not response.streaming else ""
    archive = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))
    row = json.loads(archive.read("aufgaben.json"))["tasks"][0]
    assert b"erfundener Anhang" in archive.read(row["attachments"][0]["file"])
    with django_capture_on_commit_callbacks(execute=True):
        assert api(board_a).delete(f"/api/me/todos/{todo['id']}/").status_code == 204
    assert not attachment.file.storage.exists(attachment.file.name)


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL-RLS")
def test_rls_anhaenge_bleiben_privat(api, board_a, orgs, reader):
    from .test_rls import as_app_role

    org = orgs["a"]
    todo = create(api, board_a, org)
    with as_app_role():
        assert add(api, board_a, org, todo).status_code == 201
        with tenant_context(org.pk, reader.pk):
            assert TodoAttachment.objects.count() == 0
        with tenant_context(org.pk, board_a.pk):
            assert TodoAttachment.objects.count() == 1


def test_einheitsexport_und_import_uebernehmen_nur_berechtigte_dateien(api, board_a, orgs, reader):
    from datatransfer.dump import Packer
    from datatransfer.tables import IdMap, dump_tables, load_tables
    from todos.exports import for_actor

    org = orgs["a"]
    private = create(api, board_a, org)
    add(api, board_a, org, private)
    shared = share(api, board_a, org, create(api, board_a, org), reader)
    add(api, board_a, org, shared)
    packer = Packer(True)
    with tenant_context(org.pk), for_actor(reader):
        tables = dump_tables(org, packer)
    assert [r["id"] for r in tables["todos.todo"]] == [shared["id"]]
    assert len(tables["todos.todoattachment"]) == 1
    assert len(packer.files) == 1
    contents = {}
    for path, field in packer.files:
        with field.open("rb") as source:
            contents[path] = source.read()

    class Files:
        def read(self, path):
            return contents[path]

    selected = {key: value for key, value in tables.items() if key.startswith("todos.")}
    with tenant_context(orgs["b"].pk, reader.pk):
        load_tables(selected, orgs["b"], IdMap(), Files(), user=reader)
        imported = Todo.objects.get(organization=orgs["b"], owner=reader)
        assert not imported.shared
        attachment = imported.attachments.get()
        assert attachment.size == len(next(iter(contents.values())))
        assert attachment.file.storage.is_encrypted(attachment.file.name)


def test_virenpruefung_blockiert_upload(api, board_a, orgs, settings):
    from core import virenscan

    todo = create(api, board_a, orgs["a"])
    settings.CLAMD_SOCKET = "/test/clamd"
    with (
        patch("core.virenscan.Stream", side_effect=virenscan.ScanError("nicht erreichbar")),
        patch("core.virenscan._alert"),
    ):
        assert add(api, board_a, orgs["a"], todo).status_code == 503
    assert not TodoAttachment.objects.exists()
