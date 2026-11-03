"""Direkte Passwort-API und nachfolgende Recovery haben eine feste Kontoreihenfolge."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from time import monotonic
from unittest.mock import patch

import pytest
from django.db import connection, connections
from django.db.models.query import QuerySet

from accounts.models import User

from .factories import PASSWORD, give_role
from .test_fachfragen_3110b import _totp

pytestmark = pytest.mark.django_db(transaction=True)


def change(client, password):
    try:
        return client.post(
            "/api/me/password/",
            {"current_password": PASSWORD, "new_password": password},
            content_type="application/json",
        )
    finally:
        connections.close_all()


def test_request_authenticated_before_owner_change_cannot_reuse_old_state(api, user):
    delayed_client, owner_client = api(user), api(user)
    ready, release = Event(), Event()
    select = User.objects.select_for_update

    def select_for_update(*args, **kwargs):
        if current_thread().name.startswith("before-lock"):
            ready.set()
            assert release.wait(15)
        return select(*args, **kwargs)

    with (
        patch.object(User.objects, "select_for_update", select_for_update),
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="before-lock") as pool,
    ):
        delayed = pool.submit(change, delayed_client, "Delayed-New-Password-2026")
        try:
            assert ready.wait(10)
            owner = change(owner_client, "Owner-New-Password-2026")
            assert owner.status_code == 200, owner.content
        finally:
            release.set()
        response = delayed.result(timeout=15)
    assert response.status_code == 403, response.content
    fresh = User.objects.get(pk=user.pk)
    assert fresh.check_password("Owner-New-Password-2026")
    assert not fresh.check_password("Delayed-New-Password-2026")
    assert owner_client.get("/api/me/").status_code == 200
    assert delayed_client.get("/api/me/").status_code == 403


def test_recovery_waits_for_checked_password_change_and_then_revokes_its_session(
    api, user, orgs, board_a
):
    assignment = give_role(user, orgs["a"])
    _totp(user)
    _totp(board_a)
    changing, recovering = api(user), api(User.objects.get(pk=board_a.pk))
    checked, release, updating = Event(), Event(), Event()
    backend_pid = []
    original_check, original_update = User.check_password, QuerySet.update

    def check(instance, raw):
        valid = original_check(instance, raw)
        if instance.pk == user.pk and current_thread().name.startswith("checked-change"):
            assert valid
            checked.set()
            assert release.wait(15)
        return valid

    def update(queryset, **kwargs):
        if (
            queryset.model is User
            and "mfa_required_by" in kwargs
            and current_thread().name.startswith("recover")
        ):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend_pid.append(cursor.fetchone()[0])
            updating.set()
        return original_update(queryset, **kwargs)

    def recover():
        try:
            return recovering.post(
                f"/api/orgs/{orgs['a'].pk}/assignments/{assignment.pk}/reset-mfa/"
            )
        finally:
            connections.close_all()

    with (
        patch.object(User, "check_password", check),
        patch.object(QuerySet, "update", update),
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="checked-change") as changes,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="recover") as recoveries,
    ):
        changing_request = changes.submit(change, changing, "First-New-Password-2026")
        try:
            assert checked.wait(10)
            recovery = recoveries.submit(recover)
            assert updating.wait(10)
            blocked = False
            deadline = monotonic() + 5
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [backend_pid[-1]])
                    blocked = cursor.fetchone()[0] > 0
                if blocked:
                    break
                release.wait(0.02)
            assert blocked and not recovery.done()
        finally:
            release.set()
        assert changing_request.result(timeout=15).status_code == 200
        response = recovery.result(timeout=15)
        assert response.status_code == 200, response.content
    fresh = User.objects.get(pk=user.pk)
    assert fresh.auth_version == 2
    assert fresh.check_password("First-New-Password-2026")
    assert changing.get("/api/me/").status_code == 403
