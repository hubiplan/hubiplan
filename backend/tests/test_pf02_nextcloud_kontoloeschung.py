"""Kontolöschung deaktiviert das Nextcloud-Konto, wo der Dienst Konten verwaltet (PF-02).

Gesamtaudit 15.11.: Beim Löschen eines HUBIplan-Kontos blieb das verknüpfte Nextcloud-Konto
aktiv. Bei Diensten mit „Konten automatisch deaktivieren“ wird es jetzt deaktiviert (nicht
gelöscht). Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

from __future__ import annotations

import pytest

from accounts import deletion
from core.tenancy import rls_bypass

from .factories import make_user
from .test_nextcloud_anmeldung import make_client  # noqa: F401
from .test_nextcloud_konten import cloud, login, managed  # noqa: F401

pytestmark = pytest.mark.django_db


def test_konto_loeschen_deaktiviert_nextcloud(
    api, orgs, board_a, cloud, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    client, secret = managed(orgs["a"], usernames="vorstand-a@example.org = vbisher")
    login(api, client, secret, board_a)
    with django_capture_on_commit_callbacks(execute=True):
        deletion.delete_account(board_a, reason="Test")
    assert ("PUT", "cloud/users/vbisher/disable") in cloud.calls


def test_ohne_kontoverwaltung_passiert_in_nextcloud_nichts(
    api, orgs, cloud, settings, django_capture_on_commit_callbacks
):
    from .factories import give_role
    from .test_nextcloud_anmeldung import make_client

    settings.CELERY_TASK_ALWAYS_EAGER = True
    user = make_user("nur-anmeldung@example.org")
    give_role(user, orgs["a"])
    client, secret = make_client(orgs["a"])
    login(api, client, secret, user)
    with django_capture_on_commit_callbacks(execute=True):
        deletion.delete_account(user, reason="Test")
    assert cloud.calls == []
    with rls_bypass():
        from oidc.models import Account

        assert not Account.objects.filter(user_id=user.pk).exists()
