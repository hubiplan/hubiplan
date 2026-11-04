"""Synthetic app-field fixture/fingerprint for scripts/test.sh, never installed."""

import datetime
import hashlib
import json
import os
import sys


def main():
    # This test is mounted under /tmp; import the application from the image's
    # working directory just as manage.py does from /app.
    sys.path.insert(0, os.getcwd())
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django

    django.setup()
    from billing.models import Invoice
    from circulars.models import Circular, CircularRecipient
    from core.tenancy import rls_bypass
    from django.db import connection
    from members.models import Membership, Person

    label = "Synthetic restore probe"
    address = "Testweg 1\n12345 Musterstadt"
    email = "restore-probe@example.org"
    values = {"Vorname": "Audit", "Nachname": "Beispiel"}
    with rls_bypass():
        if sys.argv[1] == "seed":
            member = Membership.objects.order_by("pk").first()
            Invoice.objects.create(
                organization=member.organization,
                membership=member,
                recipient_kind="member",
                recipient_name=label,
                recipient_address=address,
                recipient_email=email,
                subject=label,
                date=datetime.date(2026, 11, 3),
                due_date=datetime.date(2026, 11, 17),
            )
            circular = Circular.objects.create(
                organization=member.organization, subject=label, body="Hallo {Vorname}"
            )
            CircularRecipient.objects.create(
                organization=member.organization,
                circular=circular,
                club=member.organization,
                membership=member,
                first_name="Audit",
                last_name="Beispiel",
                email=email,
                address=address,
                values=values,
                channel="mail",
            )
            return
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM members_person WHERE birth_date LIKE %s",
                ["enc1:%"],
            )
            assert cursor.fetchone()[0] > 0
            cursor.execute(
                "SELECT recipient_name, recipient_email FROM billing_invoice WHERE subject = %s",
                [label],
            )
            invoice_rows = cursor.fetchall()
            assert len(invoice_rows) == 1
            assert all(value.startswith("enc1:") for value in invoice_rows[0])
            cursor.execute(
                "SELECT r.first_name, r.last_name, r.email "
                "FROM circulars_circularrecipient r "
                "JOIN circulars_circular c ON c.id = r.circular_id WHERE c.subject = %s",
                [label],
            )
            recipient_rows = cursor.fetchall()
            assert len(recipient_rows) == 1
            assert all(value.startswith("enc1:") for value in recipient_rows[0])
        dates = list(Person.objects.order_by("pk").values_list("birth_date", flat=True))
        invoices = list(
            Invoice.objects.filter(subject=label).values_list(
                "recipient_name", "recipient_email", "recipient_address"
            )
        )
        recipients = list(
            CircularRecipient.objects.filter(circular__subject=label).values_list(
                "first_name", "last_name", "email", "address", "values"
            )
        )
        assert dates and invoices == [(label, email, address)]
        assert recipients == [("Audit", "Beispiel", email, address, values)]
        payload = [
            [value.isoformat() if value else "" for value in dates],
            invoices,
            recipients,
        ]
        print(hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())


if __name__ == "__main__":
    main()
