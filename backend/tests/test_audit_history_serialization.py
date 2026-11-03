"""Chronikwiderspruch wartet auf eine gleichzeitig verknüpfte Mitgliedschaft."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest
from django.db import connections, transaction

from core.tenancy import tenant_context
from members import services, workflows
from members.models import Membership

from .factories import make_member, make_org


@pytest.mark.django_db(transaction=True)
def test_history_erasure_sees_other_membership_after_person_lock():
    federation = make_org("Testverband", type_="federation")
    first = make_org("Chronikverein", parent=federation)
    second = make_org("Zweiter Verein", parent=federation)
    membership = make_member(first, "Erika", "Muster")
    person = membership.person
    linked, release, erasing = Event(), Event(), Event()
    lock_person = services.lock_person

    def lock(person_id):
        if linked.is_set():
            erasing.set()
        lock_person(person_id)

    def link_elsewhere():
        try:
            with transaction.atomic(), tenant_context(second.pk):
                services.lock_person(person.pk)
                Membership.objects.create(organization=second, scope=federation, person=person)
                linked.set()
                assert release.wait(10)
        finally:
            connections.close_all()

    def erase():
        try:
            with tenant_context(first.pk):
                return workflows.erase_history(membership, listed=True)
        finally:
            connections.close_all()

    with patch.object(services, "lock_person", lock), ThreadPoolExecutor(max_workers=2) as pool:
        linking = pool.submit(link_elsewhere)
        assert linked.wait(10)
        erasure = pool.submit(erase)
        try:
            assert erasing.wait(10)
            assert not erasure.done()
        finally:
            release.set()
        linking.result(timeout=10)
        result = erasure.result(timeout=10)
    person.refresh_from_db()
    assert person.first_name == "Erika" and person.last_name == "Muster"
    assert "Name" not in result
