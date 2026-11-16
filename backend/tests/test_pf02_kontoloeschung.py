"""Benutzerkonten löschen: selbst und nach 90 Tagen ohne Zugang (Gesamtaudit 15.11., PF-02).

Vorher gab es keinen Weg, ein Konto zu löschen; Passkeys, Geräte mit Push-Adresse, Nextcloud-
und KI-Freigaben und persönliche Aufgaben blieben unbegrenzt. Erfundene Daten.
"""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.utils import timezone

from accounts import deletion
from accounts.models import StoredSignature, User
from core.tenancy import tenant_context
from devices.models import Device
from mcpserver.models import McpClient, McpGrant
from portal.models import PortalAccess
from todos.models import Todo

from .factories import give_role, make_member, make_org, make_user

pytestmark = pytest.mark.django_db
JSON = "application/json"


def _equip(user, org):
    """Konto mit Passkey, Gerät, KI-Freigabe, Unterschrift und Aufgaben (erfunden)."""
    Authenticator.objects.create(user=user, type=Authenticator.Type.WEBAUTHN, data={"name": "S"})
    StoredSignature.objects.create(user=user, strokes=[[[0, 0], [1, 1]]])
    Device.objects.create(
        user=user, name="Telefon", token_hash=f"{user.pk:064d}", push_endpoint="https://p.test/x"
    )
    now = timezone.now()
    McpGrant.objects.create(
        user=user,
        organization=org,
        client=McpClient.objects.create(name="Assistent", redirect_uris=[]),
        access_hash=f"a{user.pk:063d}",
        access_expires_at=now + datetime.timedelta(hours=1),
        refresh_hash=f"r{user.pk:063d}",
        expires_at=now + datetime.timedelta(days=30),
    )
    with tenant_context(org.pk):
        private = Todo.objects.create(organization=org, title="Privat", owner=user)
        shared = Todo.objects.create(organization=org, title="Verein", owner=user, shared=True)
    return private, shared


def _gone(user, private, shared) -> None:
    assert not User.objects.filter(pk=user.pk).exists()
    assert not Authenticator.objects.filter(user_id=user.pk).exists()
    assert not StoredSignature.objects.filter(user_id=user.pk).exists()
    assert not Device.objects.filter(user_id=user.pk).exists()
    assert not McpGrant.objects.filter(user_id=user.pk).exists()
    with tenant_context(shared.organization_id):
        assert not Todo.objects.filter(pk=private.pk).exists()
        shared.refresh_from_db()
    assert shared.owner_id is None  # geteilte Aufgabe gehört dem Verein


def test_selbst_loeschen(api):
    club = make_org("Verein Konto")
    member = make_member(club, "Erika", "Muster")
    user = make_user("erika.selbst@example.org")
    PortalAccess.objects.create(organization=club, membership=member, user=user)
    private, shared = _equip(user, club)
    c = api(user)
    data = c.get("/api/me/account/").json()
    assert data["delete_blockers"] == []

    wrong = c.post("/api/me/account/delete/", {"email": "jemand@example.org"}, content_type=JSON)
    assert wrong.status_code == 400
    assert User.objects.filter(pk=user.pk).exists()

    resp = c.post(
        "/api/me/account/delete/", {"email": "Erika.Selbst@example.org"}, content_type=JSON
    )
    assert resp.status_code == 204, resp.content
    _gone(user, private, shared)
    # Die Mitgliedsakte gehört dem Verein und bleibt
    with tenant_context(club.pk):
        member.refresh_from_db()
    assert member.purged_at is None


def test_mit_laufendem_amt_nicht(api):
    club = make_org("Verein Amt")
    user = make_user("kassenwart@example.org")
    give_role(user, club)
    c = api(user)
    assert c.get("/api/me/account/").json()["delete_blockers"] == ["Verein Amt"]
    resp = c.post("/api/me/account/delete/", {"email": user.email}, content_type=JSON)
    assert resp.status_code == 403
    assert User.objects.filter(pk=user.pk).exists()


def test_bestaetigung_mit_frischem_code(api, settings):
    settings.MFA_STEP_UP = True
    user = make_user("erika.code@example.org")
    user.set_password("ein-langes-Passwort-42")
    user.save()
    resp = api(user).post("/api/me/account/delete/", {"email": user.email}, content_type=JSON)
    assert resp.status_code == 403 and resp.json()["step_up"] == "password"
    assert User.objects.filter(pk=user.pk).exists()


def test_verwaiste_konten_nach_90_tagen(mailoutbox):
    club = make_org("Verein Frist")
    start = timezone.now()
    orphan = make_user("ehemals@example.org")
    private, shared = _equip(orphan, club)
    former = make_user("ehemaliger.vorstand@example.org")
    give_role(former, club, valid_until=datetime.date(2025, 12, 31))
    board = make_user("vorstand@example.org")
    give_role(board, club)
    future = make_user("kuenftig@example.org")
    give_role(future, club, valid_from=datetime.date(2099, 1, 1))
    admin = make_user("plattform@example.org", is_superuser=True)
    member = make_member(club, "Max", "Muster")
    with_access = make_user("mitglied@example.org")
    PortalAccess.objects.create(organization=club, membership=member, user=with_access)

    ours = [orphan, former, board, future, admin, with_access]
    deletion.orphan_run(start)
    marked = set(
        User.objects.filter(orphaned_since__isnull=False, pk__in=[u.pk for u in ours]).values_list(
            "pk", flat=True
        )
    )
    assert marked == {orphan.pk, former.pk}  # ohne Zugang; ein beendetes Amt zählt nicht

    # Nach 75 Tagen noch nichts, nach 76 Tagen die Hinweismail, nichts gelöscht
    deletion.orphan_run(start + datetime.timedelta(days=75))
    assert mailoutbox == []
    deletion.orphan_run(start + datetime.timedelta(days=76))
    assert {m.to[0] for m in mailoutbox} == {
        "ehemals@example.org",
        "ehemaliger.vorstand@example.org",
    }
    assert "gelöscht" in mailoutbox[0].subject
    assert User.objects.filter(pk=orphan.pk).exists()

    # Der ehemalige Vorstand bekommt wieder ein Amt: Frist endet
    give_role(former, club, name="Beisitz")
    deletion.orphan_run(start + datetime.timedelta(days=90))
    _gone(orphan, private, shared)
    for user in (former, board, future, admin, with_access):
        user.refresh_from_db()
    assert former.orphaned_since is None and former.deletion_notice_at is None


def test_ohne_hinweis_keine_loeschung():
    """Fällt der Hinweis aus (etwa Mailfehler), wird nicht gelöscht."""
    start = timezone.now()
    user = make_user("ohne.hinweis@example.org")
    User.objects.filter(pk=user.pk).update(orphaned_since=start - datetime.timedelta(days=200))
    counts = deletion.orphan_run(start)
    assert counts["geloescht"] == 0 and counts["benachrichtigt"] == 1
    assert User.objects.filter(pk=user.pk).exists()
    assert deletion.orphan_run(start + datetime.timedelta(days=13))["geloescht"] == 0
    assert deletion.orphan_run(start + datetime.timedelta(days=14))["geloescht"] == 1


def test_geraete_nach_180_tagen_abgemeldet():
    user = make_user("geraete@example.org")
    old = Device.objects.create(
        user=user,
        name="Altes Telefon",
        token_hash="1" * 64,
        push_kind=Device.Push.UNIFIEDPUSH,
        push_endpoint="https://push.test/alt",
    )
    Device.objects.filter(pk=old.pk).update(
        last_seen_at=timezone.now() - datetime.timedelta(days=181)
    )
    fresh = Device.objects.create(user=user, name="Neues Telefon", token_hash="2" * 64)
    assert deletion.retire_idle_devices() == 1
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.revoked_at is not None and old.push_endpoint == ""
    assert fresh.revoked_at is None
