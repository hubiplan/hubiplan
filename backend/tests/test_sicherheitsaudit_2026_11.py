"""Regressionstests für die Sicherheitsprüfung 2026-11 (AP1–AP6)."""

from __future__ import annotations

import datetime
import io

import pytest
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from access.models import Role
from core import safehttp, virenscan
from devices import devicekey
from feeproofs import precheck
from finance import datev
from meetings.models import Meeting
from members.models import DepartmentRoleHolder
from organizations.addresses import TlsAskView
from organizations.models import Department, DepartmentRole
from peering import crypto, keys
from peering.models import Peer

from .factories import give_role, make_member, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def test_safehttp_blocks_rfc8215_and_multicast():
    assert not safehttp.is_public("64:ff9b:1::192.0.2.1")
    assert not safehttp.is_public("224.0.0.1")
    assert not safehttp.is_public("ff02::1")
    assert safehttp.is_public("93.184.216.34")


def test_datev_neutralises_csv_formula_prefixes():
    assert datev._q("=CMD|' /C calc'!A0") == '"\'=CMD|\' /C calc\'!A0"'
    assert datev._q("+1+1") == '"\'+1+1"'
    assert datev._q("-100") == '"\'-100"'
    assert datev._q("@SUM(A1:A2)") == '"\'@SUM(A1:A2)"'
    assert datev._q("Beitrag 2026") == '"Beitrag 2026"'


def test_devicekey_request_body_rejects_invalid_and_oversized_content_length():
    rf = RequestFactory()
    req = rf.post("/api/app/v1/admin/u/1/", data=b"abc", content_type="application/octet-stream")
    req.META["CONTENT_LENGTH"] = "not-a-number"
    with pytest.raises(devicekey.BodyTooLarge):
        devicekey.request_body(req)

    req2 = rf.post("/api/app/v1/admin/u/1/", data=b"x" * 10, content_type="application/octet-stream")
    req2.META["CONTENT_LENGTH"] = str(devicekey.MAX_SIGNED_BODY + 1)
    with pytest.raises(devicekey.BodyTooLarge):
        devicekey.request_body(req2)

    req3 = rf.post("/api/app/v1/admin/u/1/", data=b"", content_type="application/octet-stream")
    req3._stream = io.BytesIO(b"a" * (devicekey.MAX_SIGNED_BODY + 5))
    req3.META["CONTENT_LENGTH"] = "0"
    with pytest.raises(devicekey.BodyTooLarge):
        devicekey.request_body(req3)


def test_feeproof_signature_rejects_trailing_bytes_and_never_claims_verified():
    body = b"%PDF-1.4\n/ByteRange [0 20 30 10]\n<00000000>0123456789EXTRA"
    sig = precheck.signature_info(body)
    assert sig is not None
    assert sig["intact"] is False
    assert sig["verified"] is False
    assert sig["digest_match"] is False


def test_feeproof_check_requires_birth_date_for_green(monkeypatch):
    monkeypatch.setattr(
        precheck,
        "pdf_text",
        lambda _data: "Immatrikulationsbescheinigung Anna Muster Wintersemester 2026/27",
    )
    res = precheck.check(
        b"%PDF-1.4 dummy",
        "application/pdf",
        first_name="Anna",
        last_name="Muster",
        birth_date=datetime.date(2000, 5, 17),
        needed_until=datetime.date(2026, 1, 1),
    )
    assert res["level"] == precheck.YELLOW
    assert "birth_missing" in res["reasons"]


def test_tls_ask_rejects_forwarded_requests(settings, orgs):
    from organizations.models import InstanceAddress

    settings.ADDRESSES_FROM_LIST = True
    settings.PROXY_HOSTS = ["127.0.0.1"]
    InstanceAddress.objects.create(organization=orgs["a"], hostname="verein.example.org")
    rf = RequestFactory()
    req = rf.get(
        "/api/intern/tls/?domain=verein.example.org",
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_FORWARDED_FOR="203.0.113.9",
    )
    resp = TlsAskView.as_view()(req)
    assert resp.status_code == 404


def test_virenscan_scan_bytes_fails_closed_when_too_big(settings):
    settings.CLAMD_SOCKET = "/tmp/fake-clamd.sock"
    settings.CLAMD_REQUIRED = True
    settings.CLAMD_MAX_BYTES = 10
    with pytest.raises(virenscan.NotScanned):
        virenscan.scan_bytes(b"x" * 20, "gross.pdf")
    assert virenscan.inbound_ok(b"x" * 20, "gross.pdf", "test") is False


def test_oidc_department_role_pk_does_not_collide_with_club_role_pk(orgs):
    from oidc.claims import groups_for
    from oidc.models import Client

    org = orgs["a"]
    dept = Department.objects.create(organization=org, name="Jugend")
    club_role = Role.objects.create(organization=org, name="Vorstand", permissions=[])
    dept_role = DepartmentRole.objects.create(
        id=club_role.pk, organization=org, name="Jugendwart"
    )
    user = make_user("jugend@example.org")
    member = make_member(org, first_name="Max", last_name="Jugend", email="jugend@example.org")
    DepartmentRoleHolder.objects.create(
        organization=org,
        department=dept,
        role=dept_role,
        membership=member,
        valid_from=datetime.date(2025, 1, 1),
    )
    client = Client.objects.create(
        organization=org,
        name="Nextcloud",
        client_id="nc-test",
        redirect_uris=["https://nc.example.org/cb"],
        groups_roles={str(club_role.pk): "vorstand-gruppe"},
    )
    groups = groups_for(client, user)
    assert "vorstand-gruppe" not in groups


def test_peering_key_rotation_requires_current_key_and_monotonic_timestamp():
    _, pub_cur = crypto.generate_keypair()
    _, pub_old = crypto.generate_keypair()
    _, pub_new = crypto.generate_keypair()
    now = timezone.now()
    peer = Peer.objects.create(
        url="https://peer.example.org",
        public_key=pub_cur,
        previous_public_key=pub_old,
        previous_until=now + datetime.timedelta(days=5),
        keys_changed_at=now,
    )
    # Geplante Rotation mit altem (previous) Schlüssel muss scheitern
    payload_planned = {
        "new": pub_new,
        "old": pub_cur,
        "until": (now + datetime.timedelta(days=7)).isoformat(),
        "changed_at": (now + datetime.timedelta(minutes=5)).isoformat(),
    }
    with pytest.raises(PermissionDenied):
        keys.receive(peer, payload_planned, signed_with=pub_old)

    # Rückdatierter Zeitstempel (Replay) muss scheitern
    payload_replay = {
        "new": pub_new,
        "old": pub_cur,
        "until": (now + datetime.timedelta(days=7)).isoformat(),
        "changed_at": now.isoformat(),
    }
    with pytest.raises(PermissionDenied):
        keys.receive(peer, payload_replay, signed_with=pub_cur)


def test_outbox_redacts_secret_links_and_reply_to_plus_tags():
    from outbox.backend import redact_links, redact_reply_to

    text = (
        "Bitte bestätigen: https://verein.example.org/anmeldung/bestaetigen/abc123SECRETtoken "
        "und https://verein.example.org/umfrage/xyz987SECRETtoken"
    )
    cleaned = redact_links(text)
    assert "abc123SECRETtoken" not in cleaned
    assert "xyz987SECRETtoken" not in cleaned
    assert redact_reply_to("rechnung+nw12345678@example.org") == "rechnung+[geschützt]@example.org"
    assert redact_reply_to("vorstand@example.org") == "vorstand@example.org"


def test_meetings_draft_hidden_from_portal_live(orgs, api):
    from events.models import Event
    from meetings.models import MeetingKind
    from portal.models import PortalAccess

    org = orgs["a"]
    org.enabled_modules = sorted({*org.enabled_modules, "meetings", "events"})
    org.save()
    user = make_user("mitglied@example.org")
    member = make_member(org, first_name="Mia", last_name="Mitglied", email="mitglied@example.org")
    access = PortalAccess.objects.create(organization=org, membership=member, user=user)
    kind = MeetingKind.objects.create(organization=org, name="JHV", base_type="general")
    now = timezone.now()
    event = Event.objects.create(
        organization=org,
        title="Entwurf-JHV",
        starts_at=now + datetime.timedelta(days=7),
        ends_at=now + datetime.timedelta(days=7, hours=2),
    )
    meeting = Meeting.objects.create(
        organization=org,
        kind=kind,
        event=event,
        status=Meeting.Status.DRAFT,
        checkin_open=True,
    )
    resp = api(user).get(f"/api/portal/{access.pk}/meetings/{meeting.pk}/live/")
    assert resp.status_code == 404


def test_app_send_rejects_portal_device_token(orgs, api):
    from devices.models import Device, hash_token

    org = orgs["a"]
    user = make_user("vorstand-app@example.org")
    give_role(user, org, permissions=["circulars.send"], name="Vorstand")
    token = Device.new_token()
    Device.objects.create(user=user, name="Telefon", token_hash=hash_token(token))
    client = api(None)
    resp = client.get("/api/app/v1/send/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code in (401, 403)
    resp2 = client.get("/api/app/v1/admin/send/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp2.status_code in (401, 403)
