"""Two real DB connections compete for the last synthetic mail reservation."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection, connections

from circulars import services
from circulars.models import Circular, CircularRecipient
from core.tenancy import rls_bypass, tenant_context
from outbox.models import OutgoingMail


@pytest.mark.django_db(transaction=True)
def test_global_mail_budget_last_slot_is_claimed_once(orgs, settings):
    settings.MAIL_RATE_PER_HOUR = 10  # Nine circular slots after the system reserve.
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    targets = []
    for name in ("a", "b"):
        org = orgs[name]
        with tenant_context(org.pk):
            circular = Circular.objects.create(
                organization=org,
                subject="Synthetic mail race",
                kind=Circular.Kind.INFO,
                audience=Circular.Audience.MEMBERS,
            )
            recipient = CircularRecipient.objects.create(
                organization=org,
                club=org,
                circular=circular,
                channel="mail",
                email=f"synthetic-{name}@example.org",
            )
            targets.append((org.pk, recipient.pk))
    with rls_bypass():
        for number in range(8):
            OutgoingMail.objects.create(
                to="synthetic@example.org", subject=f"Existing {number}", body=""
            )
        assert services.mail_budget() == 1
    barrier = Barrier(2)

    def claim(target):
        try:
            with tenant_context(target[0]):
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pid = cursor.fetchone()[0]
                barrier.wait(timeout=10)
                return pid, services.claim(target[1])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim, target) for target in targets]
        result = [future.result(timeout=20) for future in futures]
    assert len({pid for pid, _ in result}) == 2
    assert sum(outcome is True for _, outcome in result) == 1
    assert sum(outcome is None for _, outcome in result) == 1
    with rls_bypass():
        assert (
            CircularRecipient.objects.filter(status=CircularRecipient.Status.SENDING).count() == 1
        )
        assert (
            CircularRecipient.objects.filter(status=CircularRecipient.Status.PENDING).count() == 1
        )
        assert services.mail_budget() == 0
