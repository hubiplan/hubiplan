"""Gesamtaudit 11.11.2026, Fachfrage 3 und H-07: kurze Anmeldelinks, höchstens einer offen."""
# ruff: noqa: F811

import datetime

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from core.tenancy import rls_bypass
from portal.models import LoginLink
from portal.tasks import purge_login_links

from .factories import make_member, make_user
from .test_m7_access import JSON, club, link_token  # noqa: F401

pytestmark = pytest.mark.django_db
REQUEST = "/api/public/login-link/"


def request_link(email="erika@example.org"):
    return Client().post(REQUEST, {"email": email}, content_type=JSON)


def test_selbst_angefordert_eine_stunde_und_entwertet_einladung(club, api, board_a):
    m = make_member(club, "Erika", "Muster", "erika@example.org")
    api(board_a).post(f"/api/orgs/{club.pk}/members/{m.pk}/access/")
    with rls_bypass():
        invitation = LoginLink.objects.get()
    assert invitation.expires_at - timezone.now() > datetime.timedelta(days=6)
    old_token = link_token(mail.outbox[-1].body)

    assert request_link().status_code == 200
    assert "eine Stunde" in mail.outbox[-1].body
    new_token = link_token(mail.outbox[-1].body)
    with rls_bypass():
        invitation.refresh_from_db()
        fresh = LoginLink.objects.exclude(pk=invitation.pk).get()
    assert not invitation.is_open
    assert fresh.is_open
    assert fresh.expires_at - timezone.now() <= datetime.timedelta(hours=1)

    # der ältere Link geht nicht mehr, der neue schon
    assert Client().post(f"{REQUEST}{old_token}/").status_code == 404
    assert Client().post(f"{REQUEST}{new_token}/").status_code == 200


def test_hoechstens_drei_links_je_empfaenger_und_stunde(club, api, board_a):
    m = make_member(club, "Erika", "Muster", "erika@example.org")
    api(board_a).post(f"/api/orgs/{club.pk}/members/{m.pk}/access/")
    before = len(mail.outbox)
    answers = [request_link().json() for _ in range(4)]
    assert len(mail.outbox) == before + 3
    # die Antwort verrät nicht, dass die Grenze erreicht ist
    assert all(answer == answers[0] for answer in answers)
    with rls_bypass():
        assert LoginLink.objects.filter(expires_at__gt=timezone.now()).count() == 1


def test_alte_links_werden_aufgeraeumt():
    from portal.services import create_login_link

    user = make_user("alt@example.org")
    now = timezone.now()
    create_login_link(user)
    with rls_bypass():
        current = LoginLink.objects.get()
        LoginLink.objects.create(
            user=user, token_hash="a" * 64, expires_at=now - datetime.timedelta(days=31)
        )
        LoginLink.objects.create(
            user=user,
            token_hash="b" * 64,
            expires_at=now - datetime.timedelta(days=20),
            used_at=now - datetime.timedelta(days=40),
        )
        LoginLink.objects.create(
            user=user, token_hash="c" * 64, expires_at=now - datetime.timedelta(days=2)
        )
    assert purge_login_links() == 2
    with rls_bypass():
        left = set(LoginLink.objects.values_list("token_hash", flat=True))
    assert left == {current.token_hash, "c" * 64}


# --- H-09: Versand im Hintergrund, damit die Antwortzeit nichts verrät ---


@pytest.fixture
def hintergrund(settings):
    settings.MAIL_IN_BACKGROUND = True
    settings.CELERY_TASK_ALWAYS_EAGER = True


def test_anmeldelink_im_hintergrund(
    club, api, board_a, hintergrund, django_capture_on_commit_callbacks
):
    m = make_member(club, "Erika", "Muster", "erika@example.org")
    api(board_a).post(f"/api/orgs/{club.pk}/members/{m.pk}/access/")
    before = len(mail.outbox)
    with django_capture_on_commit_callbacks() as callbacks:
        known = request_link()
        unknown = request_link("niemand@example.org")
    # in der Anfrage selbst geht keine Mail hinaus, die Antworten sind gleich
    assert len(mail.outbox) == before
    assert known.json() == unknown.json()
    assert len(callbacks) == 2
    for callback in callbacks:
        callback()
    assert len(mail.outbox) == before + 1
    assert "eine Stunde" in mail.outbox[-1].body


def test_passwort_vergessen_im_hintergrund(hintergrund, django_capture_on_commit_callbacks):
    from .conftest import csrf_headers

    make_user("anna@example.org")
    client = Client()
    before = len(mail.outbox)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        resp = client.post(
            "/_allauth/browser/v1/auth/password/request",
            {"email": "anna@example.org"},
            content_type=JSON,
            headers=csrf_headers(client),
        )
    assert resp.status_code == 200, resp.content
    assert len(mail.outbox) == before
    for callback in callbacks:
        callback()
    assert len(mail.outbox) == before + 1
    assert "passwort-zuruecksetzen" in mail.outbox[-1].body
