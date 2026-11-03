"""Synthetic local regressions: no provider requests, malware or real persons."""

import io
import json
import uuid
import zipfile
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models

from core import safehttp, virenscan
from datatransfer import dump, load
from datatransfer.permission_schema import policy
from datatransfer.validation import validate_urls
from peering.packet_results import _is_own_starter
from website import social


def test_partner_controlled_names_never_authorize_people():
    coupling = SimpleNamespace(remote_unit_id=42)
    assert not _is_own_starter({"club": "Partner", "unit": None}, coupling, set())
    assert not _is_own_starter({"starter": 7, "unit": 999}, coupling, {7})
    assert _is_own_starter({"starter": 7, "unit": None}, coupling, {7})
    assert _is_own_starter({"unit": 42}, coupling, set())


def test_permission_schema_preserves_old_and_new_meaning():
    old = load.role_codes(["members.view"], schema=1)
    narrow = load.role_codes(["members.view"], schema=2)
    assert set(narrow) < set(old)
    assert narrow == ["members.view"]


def test_unknown_permission_schema_fails_closed():
    data = {"format": "hubiplan-export", "version": 1, "permissions_schema": 999}
    with pytest.raises(load.FileProblem):
        load.open_file(ContentFile(json.dumps(data).encode()))


@pytest.mark.django_db
def test_new_exports_have_explicit_narrow_permission_schema():
    header = dump._header("organization", SimpleNamespace(name="Synthetic", type="club"), False)
    assert header["permissions_schema"] == 2


def test_marked_permission_schema_cannot_be_downgraded_by_request_options():
    doc = {
        "permissions_schema": 2,
        "organization": {
            "type": "club",
            "roles": [{"name": "Narrow", "permissions": ["members.view"]}],
        },
    }
    result = policy(doc, {"permissions_schema": 1, "permissions_confirmed": True})
    assert result["schema"] == 2
    assert not result["errors"]
    assert result["roles"][0]["permissions"] == ["members.view"]


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "data:text/html,test", "ftp://example.org/test"]
)
def test_module_url_policy_rejects_active_or_unsupported_schemes(url):
    field = models.URLField()
    field.set_attributes_from_name("url")
    obj = SimpleNamespace(_meta=SimpleNamespace(concrete_fields=[field]), url=url)
    with pytest.raises(ValidationError):
        validate_urls(obj)


def archive_file():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("files/test.pdf", b"%PDF-synthetic")
    data.seek(0)
    return zipfile.ZipFile(data)


def test_inner_import_file_is_scanned_before_reuse(settings, monkeypatch):
    settings.CLAMD_SOCKET = "/synthetic-scanner"
    seen = []
    monkeypatch.setattr(virenscan, "scan_bytes", lambda data, name: seen.append((data, name)))
    with archive_file() as archive:
        assert load.Files(archive).read("files/test.pdf") == b"%PDF-synthetic"
    assert seen == [(b"%PDF-synthetic", "files/test.pdf")]


@pytest.mark.parametrize("missing", [True, False])
def test_inner_import_file_never_bypasses_required_scan(settings, missing):
    settings.VIRUS_SCAN_REQUIRED = True
    settings.CLAMD_SOCKET = "" if missing else "/synthetic-scanner"
    settings.CLAMD_MAX_BYTES = 1
    with archive_file() as archive, pytest.raises(load.FileProblem):
        load.Files(archive).read("files/test.pdf")


def test_infected_inner_file_is_not_released(settings, monkeypatch):
    settings.CLAMD_SOCKET = "/synthetic-scanner"

    def reject(*args):
        raise virenscan.VirusFound()

    monkeypatch.setattr(virenscan, "scan_bytes", reject)
    with archive_file() as archive, pytest.raises(virenscan.VirusFound):
        load.Files(archive).read("files/test.pdf")


def test_meta_uses_pinned_transport_with_allowlist(monkeypatch):
    seen = []

    def request(method, url, **kwargs):
        seen.append((method, url, kwargs))
        return safehttp.Response(200, {}, b"synthetic-image")

    monkeypatch.setattr(safehttp, "request", request)
    assert social._download("https://media.cdninstagram.com/image.jpg") == b"synthetic-image"
    assert seen[0][2] == {"timeout": social.TIMEOUT, "max_body": social.MAX_IMAGE}
    with pytest.raises(social.MetaError):
        social._download("https://cdninstagram.com.attacker.example/image.jpg")
    assert len(seen) == 1


def test_meta_does_not_fallback_after_safehttp_rejection(monkeypatch):
    def reject(*args, **kwargs):
        raise safehttp.BlockedAddress("synthetic DNS rebinding")

    monkeypatch.setattr(safehttp, "request", reject)
    with pytest.raises(social.MetaError):
        social._download("https://media.cdninstagram.com/image.jpg")


def test_meta_preserves_download_size_and_redirect_rejection(monkeypatch):
    for response in [safehttp.Response(200, {}, b"12345"), safehttp.Response(302, {}, b"")]:
        monkeypatch.setattr(social, "MAX_IMAGE", 4)
        monkeypatch.setattr(
            safehttp, "request", lambda *args, response=response, **kwargs: response
        )
        with pytest.raises(social.MetaError):
            social._download("https://media.cdninstagram.com/image.jpg")


@pytest.mark.django_db
def test_manual_social_fetch_is_coalesced_and_enqueued_after_commit(monkeypatch, orgs):
    from django.db import transaction

    from core.tenancy import rls_bypass
    from website import tasks
    from website.models import SocialFeed, Website
    from website.social_jobs import request_sync

    seen = []
    pending = []
    monkeypatch.setattr(transaction, "on_commit", pending.append)
    monkeypatch.setattr(tasks.sync_social_feed, "delay", lambda *args: seen.append(args))
    with rls_bypass():
        site = Website.objects.create(organization=orgs["a"])
        feed = SocialFeed.objects.create(organization=orgs["a"], website=site, kind="instagram")
        feed.status = SocialFeed.Status.OK
        feed.access_token = "synthetic-not-decrypted"
        feed.save()
        assert request_sync(feed)
        assert not request_sync(feed)
        assert tasks.sync_social_feeds.run() == 0
        # A stale ordinary edit cannot erase the queued request's owner token.
        feed.account_name = "Synthetic renamed feed"
        feed.save()
    assert not seen
    with rls_bypass():
        pending[0]()
        feed.refresh_from_db()
    assert seen == [(feed.pk, str(feed.sync_job_id))]
    assert feed.sync_job_id is not None
    old = str(feed.sync_job_id)
    new = uuid.uuid4()
    with rls_bypass():
        SocialFeed.objects.filter(pk=feed.pk).update(sync_job_id=new)
    assert tasks.sync_social_feed.run(feed.pk, old) == 0
    with rls_bypass():
        feed.refresh_from_db()
    assert feed.sync_job_id == new
