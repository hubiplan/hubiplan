"""Guest bearer access is scoped, revocable and independent of member sessions."""
# ruff: noqa: F811

import datetime
import uuid
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone

from changes.models import RequestKey
from core.tenancy import tenant_context
from music.guest import access_token, token_hash
from music.models import Assignment, GuestAccess, Musician, MusicianAbsence, Performance, Position
from music.performance_tasks import assignment_notice
from outbox.backend import redact

from .factories import give_role, make_member, make_user
from .test_music import JSON, c, club, music  # noqa: F401
from .test_rls import as_app_role

pytestmark = pytest.mark.django_db


@pytest.fixture
def guest(club, music):
    cache.clear()
    base, event = music
    with tenant_context(club.pk):
        event.starts_at = timezone.now() + datetime.timedelta(days=10)
        event.ends_at = event.starts_at + datetime.timedelta(hours=2)
        event.save()
        musician = Musician.objects.create(
            organization=club, name="Muster Gast", guest_email="gast@example.org"
        )
        performance = Performance.objects.create(
            organization=club, event=event, uniform="Vereinshemd"
        )
        position = Position.objects.create(
            organization=club, performance=performance, instrument="Tuba"
        )
        row = Assignment.objects.create(
            organization=club, performance=performance, position=position, musician=musician
        )
    return SimpleNamespace(
        org=club,
        base=base,
        event=event,
        musician=musician,
        performance=performance,
        row=row,
        url=f"{base}/assignments/{row.pk}/guest-access/",
        client=Client(),
    )


def manage(c, g, action="create", key=None):
    return c.post(
        g.url, {"action": action}, content_type=JSON, HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4())
    )


def invited(c, g):
    response = manage(c, g)
    assert response.status_code == 200, response.content
    return response.json()["url"].split("#")[1]


def public(g, token, status=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    if status:
        return g.client.post("/api/music/guest/", {"status": status}, content_type=JSON, **headers)
    return g.client.get("/api/music/guest/", **headers)


def test_scoped_view_response_and_secret_storage(c, guest):
    g = guest
    token = invited(c, g)
    response = public(g, token)
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["Referrer-Policy"] == "no-referrer"
    assert response.json()["uniform"] == "Vereinshemd"
    assert (
        not {"musicians", "assignments", "customer", "fee", "guest_email", "contact"}
        & response.json().keys()
    )
    with tenant_context(g.org.pk):
        access = GuestAccess.objects.get(assignment=g.row)
        assert access.token_hash == token_hash(token) and str(access.nonce) != token
        assert token not in str(list(RequestKey.objects.values_list("result", flat=True)))
    assert token not in redact(f"Persönlich: https://example.org/musik-gast#{token}\nEnde")
    for status in ["accepted", "accepted", "declined"]:
        assert public(g, token, status).json() == {"status": status}
    assert public(g, token, "paid").status_code == 400


def test_rotate_revoke_and_idempotent_create(c, guest):
    g = guest
    key = str(uuid.uuid4())
    one = manage(c, g, key=key).json()["url"].split("#")[1]
    assert manage(c, g, key=key).json()["url"].endswith(one)
    two = manage(c, g, "rotate").json()["url"].split("#")[1]
    assert one != two and public(g, one).status_code == 404
    assert public(g, one, "accepted").status_code == 404
    assert public(g, two).status_code == 200
    assert manage(c, g, "revoke").json()["active"] is False
    assert public(g, two).status_code == 404
    assert public(g, two, "declined").status_code == 404


@pytest.mark.parametrize("change", ["expired", "inactive", "member", "disabled"])
def test_live_access_boundaries(c, guest, change):
    g = guest
    token = invited(c, g)
    with tenant_context(g.org.pk):
        if change == "expired":
            GuestAccess.objects.filter(assignment=g.row).update(expires_at=timezone.now())
        elif change == "inactive":
            g.musician.active = False
            g.musician.save()
        elif change == "member":
            g.musician.membership = make_member(g.org, "Muster", "Mitglied")
            g.musician.save()
        else:
            g.org.enabled_modules.remove("music")
            g.org.save()
    assert public(g, token).status_code == 404
    assert public(g, token, "accepted").status_code == 404


def test_conflicts_cancelled_and_past_are_rechecked(c, guest):
    g = guest
    token = invited(c, g)
    with tenant_context(g.org.pk):
        MusicianAbsence.objects.create(
            organization=g.org,
            musician=g.musician,
            starts_at=g.event.starts_at,
            ends_at=g.event.ends_at,
        )
    assert public(g, token).json()["availability"] == ["absence"]
    assert public(g, token, "accepted").status_code == 400
    assert public(g, token, "declined").status_code == 200
    with tenant_context(g.org.pk):
        g.event.is_cancelled = True
        g.event.save()
    assert public(g, token).json()["can_respond"] is False
    assert public(g, token, "declined").status_code == 400
    assert manage(c, g, "send").status_code == 400
    with tenant_context(g.org.pk):
        g.event.is_cancelled = False
        g.event.starts_at = timezone.now() - datetime.timedelta(hours=2)
        g.event.ends_at = timezone.now() - datetime.timedelta(hours=1)
        g.event.save()
    assert public(g, token, "accepted").status_code == 400


def test_admin_permissions_and_rls(c, api, guest, orgs):
    g = guest
    invited(c, g)
    user = make_user("musik-leser@example.org")
    give_role(user, g.org, permissions=["music.view", "events.view"])
    assert api(user).get(g.url).status_code == 403
    editor = make_user("musik-ohne-kalender@example.org")
    give_role(editor, g.org, permissions=["music.view", "music.edit"], name="Ohne Kalender")
    assert api(editor).get(g.url).status_code == 404
    assert g.client.get(g.url).status_code in [401, 403]
    assert g.client.get("/api/music/guest/").status_code == 404
    with as_app_role(), tenant_context(orgs["b"].pk):
        assert not GuestAccess.objects.filter(assignment_id=g.row.pk).exists()


def test_email_change_revokes_and_validation(c, guest):
    g = guest
    token = invited(c, g)
    url = f"{g.base}/musicians/{g.musician.pk}/"
    assert c.patch(url, {"guest_email": "keine-adresse"}, content_type=JSON).status_code == 400
    assert public(g, token).status_code == 200
    assert c.patch(url, {"guest_email": "neu@example.org"}, content_type=JSON).status_code == 200
    assert public(g, token).status_code == 404
    with tenant_context(g.org.pk):
        assert GuestAccess.objects.get(assignment=g.row).revoked_at


def test_guest_notices_only_after_explicit_send_and_no_duplicates(c, guest, monkeypatch):
    g = guest
    token = invited(c, g)
    sent = []
    monkeypatch.setattr("music.guest.mail.send", lambda *args, **kw: sent.append(args) or True)
    assert assignment_notice.run(g.row.pk) == 0
    key = str(uuid.uuid4())
    assert manage(c, g, "send", key).json()["sent"] is True
    assert manage(c, g, "send", key).json()["sent"] is True
    assert len(sent) == 1 and token in sent[0][2]
    assert assignment_notice.run(g.row.pk) == 0
    with tenant_context(g.org.pk):
        g.event.location = "Musterhalle"
        g.event.save()
        from music.models import PerformanceNotice

        PerformanceNotice.objects.filter(assignment=g.row).update(
            attempted_at=timezone.now() - datetime.timedelta(minutes=6)
        )
    assert assignment_notice.run(g.row.pk) == 1
    assert len(sent) == 2 and "Musterhalle" not in sent[-1][2]
    manage(c, g, "revoke")
    assert assignment_notice.run(g.row.pk) == 0


def test_rotation_between_lookup_and_lock_invalidates_old_bearer(c, guest, monkeypatch):
    from music.guest import GuestPerformanceView

    g = guest
    token = invited(c, g)
    original = GuestPerformanceView.access
    calls = 0

    def access(view, pk, request):
        nonlocal calls
        calls += 1
        if calls == 2:
            GuestAccess.objects.filter(pk=pk).update(token_hash=token_hash("0" * 64))
        return original(view, pk, request)

    monkeypatch.setattr(GuestPerformanceView, "access", access)
    assert public(g, token, "accepted").status_code == 404
    with tenant_context(g.org.pk):
        assert Assignment.objects.get(pk=g.row.pk).status == "pending"


def test_fallback_key_can_recover_existing_link(c, guest, settings):
    g = guest
    token = invited(c, g)
    with override_settings(
        SECRET_KEY="changed-only-for-this-test", SECRET_KEY_FALLBACKS=[settings.SECRET_KEY]
    ):
        with tenant_context(g.org.pk):
            assert access_token(GuestAccess.objects.get(assignment=g.row)) == token


@override_settings(EMAIL_BACKEND="outbox.backend.OutboxBackend", EMAIL_HOST="")
def test_outbox_stores_no_usable_guest_credential(c, guest):
    from outbox.models import OutgoingMail

    g = guest
    token = invited(c, g)
    assert manage(c, g, "send").json()["sent"] is True
    with tenant_context(g.org.pk):
        message = OutgoingMail.objects.get(organization=g.org)
        assert token not in message.body
        assert "musik-gast#" in message.body
        assert not message.attachments
