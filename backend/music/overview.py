"""Readiness is derived from live data and never widens calendar or finance access."""

import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import F, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination

from .availability import Availability, performance_interval
from .models import MusicianClaim, PerformanceAccount, ScoreLoan
from .scores import program_data


class OverviewRange(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if (
            attrs["end"] == datetime.date.max
            or not 0 <= (attrs["end"] - attrs["start"]).days <= 365
        ):
            raise serializers.ValidationError(
                gettext("Bitte einen Zeitraum bis zu einem Jahr wählen.")
            )
        return attrs


class OverviewPagination(PageNumberPagination):
    page_size = 12


def result(view, request):
    today = timezone.localdate()
    form = OverviewRange(
        data={
            "start": request.query_params.get("start", today - datetime.timedelta(days=90)),
            "end": request.query_params.get("end", today + datetime.timedelta(days=180)),
        }
    )
    form.is_valid(raise_exception=True)
    dates = form.validated_data
    start = timezone.make_aware(datetime.datetime.combine(dates["start"], datetime.time.min))
    end = timezone.make_aware(
        datetime.datetime.combine(dates["end"] + datetime.timedelta(days=1), datetime.time.min)
    )
    query = (
        view.get_queryset()
        .filter(event__starts_at__gte=start, event__starts_at__lt=end)
        .select_related("event", "organization")
        .prefetch_related(
            "positions",
            "assignments__musician",
            "assignments__position",
            "program_entries__arrangement__piece",
            "program_entries__arrangement__parts",
        )
        .order_by("event__starts_at", "pk")
    )
    pager = OverviewPagination()
    performances = pager.paginate_queryset(query, request, view=view)
    identifiers = [row.pk for row in performances]
    arrangements = {
        entry.arrangement_id
        for row in performances
        for entry in row.program_entries.all()
        if entry.arrangement_id
    }
    loans = defaultdict(dict)
    for row in (
        ScoreLoan.objects.filter(organization=view.org, part__arrangement_id__in=arrangements)
        .values("part_id", "musician_id")
        .annotate(open=Sum(F("quantity") - F("returned")))
    ):
        loans[row["part_id"]][row["musician_id"]] = row["open"]
    finance = "finance" in view.org.enabled_modules and "finance.view" in view.org_permissions
    accounts, claims = {}, defaultdict(list)
    if finance:
        accounts = {
            row.performance_id: row
            for row in PerformanceAccount.objects.filter(
                organization=view.org, performance_id__in=identifiers
            ).select_related("invoice")
        }
        for row in (
            MusicianClaim.objects.filter(
                organization=view.org, assignment__performance_id__in=identifiers
            )
            .select_related("assignment")
            .annotate(
                paid_sum=Sum(
                    "payments__booking__amount",
                    filter=Q(payments__booking__cancellation__isnull=True),
                )
            )
        ):
            claims[row.assignment.performance_id].append(row)
    rows = [
        readiness(row, loans, accounts.get(row.pk), claims[row.pk], finance, today)
        for row in performances
    ]
    response = pager.get_paginated_response(rows)
    response.data.update(
        range={key: value.isoformat() for key, value in dates.items()}, finance_visible=finance
    )
    return response


def readiness(performance, loans, account, claims, finance, today):
    assignments = list(performance.assignments.all())
    active = [row for row in assignments if row.status in ["pending", "accepted"]]
    musicians = [row.musician for row in active]
    availability = Availability(
        performance.organization, musicians, performance.event, *performance_interval(performance)
    )
    conflicts = sum(
        bool(availability.reasons(row.musician)) or not row.musician.active for row in active
    )
    confirmed = defaultdict(int)
    for row in active:
        if row.status == "accepted" and row.musician.active:
            confirmed[row.position_id] += 1
    positions = list(performance.positions.all())
    missing = sum(max(0, row.required - confirmed[row.pk]) for row in positions)
    pending = sum(row.status == "pending" for row in active)
    program = program_data(performance, loan_balances=loans)
    missing_scores = sum(
        voice["missing_copies"] for row in program["preparation"] for voice in row["voices"]
    )
    missing_spec = sum(
        row["missing_specification"] or not row["active"] for row in program["preparation"]
    )
    program_open = not program["preparation"] or bool(missing_spec)
    score_players = sum(
        voice["missing_players"] for row in program["preparation"] for voice in row["voices"]
    )
    closed = performance.event.ends_at < timezone.now()
    notes = []

    def add(code, count, area, level="attention"):
        if count:
            notes.append({"code": code, "count": count, "area": area, "level": level})

    if not performance.event.is_cancelled:
        add("positions", int(not positions), "staffing")
        add("missing_players", missing, "staffing", "critical")
        add("pending", pending, "staffing")
        add("conflicts", conflicts, "staffing", "critical")
        add("program", int(program_open), "program")
        add("missing_scores", missing_scores, "program", "critical")
        add("score_players", score_players, "staffing", "critical")
        if finance:
            invoice = account.invoice if account else None
            add("agreement", int(closed and account is None), "settlement")
            add(
                "invoice",
                int(
                    closed
                    and account is not None
                    and (invoice is None or invoice.status in ["draft", "cancelled"])
                ),
                "settlement",
            )
            add(
                "overdue",
                int(
                    invoice is not None
                    and invoice.status == "open"
                    and invoice.due_date < today
                    and invoice.outstanding > 0
                ),
                "settlement",
                "critical",
            )
            add(
                "claim_drafts",
                sum(row.status == "draft" for row in claims) if closed else 0,
                "settlement",
            )
            add(
                "payouts",
                sum(
                    row.status == "approved"
                    and row.fee + row.allowance + row.expenses > (row.paid_sum or Decimal(0))
                    for row in claims
                ),
                "settlement",
            )
    status = (
        "cancelled"
        if performance.event.is_cancelled
        else "critical"
        if any(row["level"] == "critical" for row in notes)
        else "attention"
        if notes
        else "ready"
    )
    return {
        "id": performance.pk,
        "title": performance.event.title,
        "starts_at": performance.event.starts_at,
        "ends_at": performance.event.ends_at,
        "location": performance.event.location,
        "status": status,
        "issues": notes,
        "required": sum(row.required for row in positions),
        "accepted": sum(confirmed.values()),
        "pending": pending,
    }
