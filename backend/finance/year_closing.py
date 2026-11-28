"""Prüfungen vor dem Jahresabschluss und für abgeschlossene Jahre, Fehler als API-Fehler."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from . import services
from .models import (
    Booking,
    Receipt,
)


def cash_ok(accounts, since) -> None:
    """Barkasse nie unter null (siehe services.ensure_cash_ok), als API-Fehler."""
    try:
        services.ensure_cash_ok(accounts, since)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(" ".join(exc.messages)) from exc


def _ensure_open(org, year: int) -> None:
    try:
        services.ensure_open(org, year=year)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(" ".join(exc.messages)) from exc


def closing_checks(org, year: int, start, last) -> dict:
    """Zahlen für die Prüfliste vor dem Jahresabschluss (blockieren nie)."""
    from billing.models import DebitRun, Invoice

    bookings = Booking.objects.filter(organization=org, year=year).exclude(
        kind=Booking.Kind.TRANSFER
    )
    checks = {
        "bookings": bookings.count(),
        "without_receipt": bookings.exclude(
            pk__in=Receipt.objects.filter(organization=org, hidden_at__isnull=True).values(
                "booking_id"
            )
        )
        .exclude(
            split_of__in=Receipt.objects.filter(organization=org, hidden_at__isnull=True).values(
                "booking_id"
            )
        )
        .count(),
        "tax_areas_enabled": org.tax_areas_on,
        "categories_without_area": (
            bookings.filter(category__isnull=False, category__tax_area="")
            .values("category")
            .distinct()
            .count()
            if org.tax_areas_on
            else 0
        ),
    }
    if "billing" in (org.enabled_modules or []):
        checks["open_invoices"] = Invoice.objects.filter(
            organization=org,
            status=Invoice.Status.OPEN,
            date__gte=start,
            date__lte=last,
        ).count()
        checks["unbooked_debit_runs"] = DebitRun.objects.filter(
            organization=org,
            status=DebitRun.Status.CREATED,
            collection_date__gte=start,
            collection_date__lte=last,
        ).count()
    return checks
