"""Recovery widerruft ältere Browser-/OIDC-/Peer-Authentifizierung kontoweit."""
# ruff: noqa: F811

import time
import uuid
from unittest.mock import patch

import pytest
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.mfa import signals as mfa_signals
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory

from accounts.models import User
from accounts.security import secure_account
from peering import sso
from peering.models import LoginLink, Peer

from .factories import PASSWORD, give_role, make_user
from .test_fachfragen_3110b import _totp
from .test_nextcloud_anmeldung import (
    _key,  # noqa: F401
    code_of,
    make_client,
    redeem,
    start,
)

pytestmark = pytest.mark.django_db


def _peer():
    return Peer.objects.create(
        instance_id=uuid.uuid4(),
        base_url="https://peer.example.invalid",
        public_key="synthetic",
        enc_public_key="synthetic",
        fingerprint="synthetic",
    )


def test_version_zero_preserves_existing_session_hash_and_secret_fallback(user):
    assert user.auth_version == 0
    assert user.get_session_auth_hash() == AbstractBaseUser._get_session_auth_hash(user)
    secure_account(user, devices=False)
    assert user.get_session_auth_hash() != AbstractBaseUser._get_session_auth_hash(user)
    assert user._get_session_auth_hash(secret="synthetic-fallback") != user.get_session_auth_hash()


@pytest.mark.parametrize("explicit", [False, True])
def test_stale_user_save_cannot_restore_revoked_authentication_version(api, user, explicit):
    browser = api(user)
    stale = User.objects.get(pk=user.pk)
    old_hash = stale.get_session_auth_hash()
    secure_account(user, devices=False, recovery=True)
    stale.first_name = "Updated profile"
    if explicit:
        stale.save(update_fields=["first_name", "auth_version"])
    else:
        stale.save()
    fresh = User.objects.get(pk=user.pk)
    assert fresh.first_name == "Updated profile"
    assert fresh.auth_version == user.auth_version == 1
    assert fresh.get_session_auth_hash() != old_hash
    assert browser.get("/api/me/").status_code == 403


def test_recovery_endpoint_revokes_two_browsers_code_token_and_peer_links(api, orgs, board_a):
    target = make_user("recovery@example.invalid")
    assignment = give_role(target, orgs["a"])
    _totp(target)
    _totp(board_a)
    browsers = [api(target), api(target)]
    for browser in browsers:
        session = browser.session
        session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "mfa", "at": time.time()}]
        session.save()
        assert browser.get("/api/me/").status_code == 200
    oidc, secret = make_client(orgs["a"])
    issued_code = code_of(start(browsers[0], oidc))
    access = redeem(oidc, secret, code_of(start(browsers[1], oidc))).json()["access_token"]
    peer = _peer()
    LoginLink.objects.create(user=target, peer=peer, subject="synthetic-remote")
    other = make_user("unaffected@example.invalid")
    untouched = api(other)
    LoginLink.objects.create(user=other, peer=peer, subject="other-remote")
    response = api(User.objects.get(pk=board_a.pk)).post(
        f"/api/orgs/{orgs['a'].pk}/assignments/{assignment.pk}/reset-mfa/"
    )
    assert response.status_code == 200, response.content
    for browser in browsers:
        assert browser.get("/api/me/").status_code == 403
        assert AUTHENTICATION_METHODS_SESSION_KEY not in browser.session
    assert redeem(oidc, secret, issued_code).json()["error"] == "invalid_grant"
    assert (
        Client().get("/api/oidc/userinfo", HTTP_AUTHORIZATION=f"Bearer {access}").status_code == 401
    )
    assert not LoginLink.objects.filter(user=target).exists()
    with pytest.raises(ValidationError):
        sso.complete_login(
            {"peer": peer, "data": {"sub": "synthetic-remote", "amr": ["pwd", "mfa"]}}
        )
    assert untouched.get("/api/me/").status_code == 200
    assert LoginLink.objects.filter(user=other).exists()


def test_password_change_preserves_own_session_and_revokes_other_browser(api, user):
    own, other = api(user), api(user)
    response = own.post(
        "/api/me/password/",
        {"current_password": PASSWORD, "new_password": "Eigenes-Neues-Passwort-2026"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert own.get("/api/me/").status_code == 200
    assert other.get("/api/me/").status_code == 403


def test_mfa_removal_clears_historical_amr_in_retained_own_session(api, user):
    browser = api(user)
    session = browser.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [
        {"method": "password", "at": time.time()},
        {"method": "mfa", "at": time.time()},
    ]
    session.save()
    request = RequestFactory().post("/")
    request.user, request.session = user, session
    mfa_signals.authenticator_removed.send(sender=User, request=request, user=user)
    assert sso.session_auth(request)["amr"] == ["pwd"]
    assert sso.session_auth(request)["mfa_time"] == 0
    assert request.session.get("_auth_user_hash") == user.get_session_auth_hash()


def test_old_peer_stepup_rejected_even_if_link_recreated_after_recovery(user):
    peer = _peer()
    _totp(user)
    request = RequestFactory().post("/")
    request.user, request.session = user, {}
    sso.begin_stepup(request, user, peer, "/")
    secure_account(user, devices=False, recovery=True)
    LoginLink.objects.create(user=user, peer=peer, subject="new-link")
    with (
        patch.object(sso, "coupled_peers", return_value=Peer.objects.all()),
        patch.object(sso, "login_enabled", return_value=True),
        patch.object(sso, "check_second_factor", return_value=True) as check,
    ):
        with pytest.raises(PermissionDenied):
            sso.finish_stepup(request, "synthetic")
        check.assert_not_called()
