"""Kassenprüfung als Ablauf (Konzept vereinskasse-steuern, S6).

Prüfauftrag je Geschäftsjahr, Stichproben (die größten Ausgaben und zufällig gezogene
weitere Buchungen), Kontenabgleich zum Jahresende, Prüfpunkte, Feststellungen und
Empfehlung zur Entlastung. Prüfen dürfen nur Konten, die die Kasse lesen, aber nicht
führen (Kassenprüfer); angelegt wird der Auftrag von der Kasse.
"""

from __future__ import annotations

import datetime
import random
from decimal import Decimal

from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.translation import gettext, gettext_noop

from access.catalog import FINANCE_EDIT, FINANCE_VIEW, effective

from . import services
from .models import (
    Account,
    Booking,
    CashAudit,
    CashAuditAccount,
    CashAuditSample,
    CashCount,
    Receipt,
    YearClosing,
)

LARGEST = 5
RESULTS = ("", "ok", "issue", "na")
# Prüfpunkte in der Reihenfolge des Berichts
CHECKS = (
    ("receipts", gettext_noop("Belege vollständig und geordnet")),
    ("numbering", gettext_noop("Buchungen lückenlos nummeriert")),
    ("accounts", gettext_noop("Kontenstände stimmen mit den Kontoauszügen überein")),
    ("cash", gettext_noop("Barkasse gezählt, Bestand stimmt mit dem Kassenbuch überein")),
    ("reserves", gettext_noop("Rücklagen nachvollziehbar gebildet und verwendet")),
    ("donations", gettext_noop("Zuwendungsbestätigungen passen zu den Spenden")),
    ("allowances", gettext_noop("Aufwandsvergütungen innerhalb der Freibeträge")),
    ("purpose", gettext_noop("Ausgaben im Rahmen der Satzungszwecke")),
)
CHECK_KEYS = {key for key, _ in CHECKS}


def is_auditor(perms: set[str]) -> bool:
    """Kassenprüfer: Kasse lesen, aber nicht führen (unabhängig von der Kassenführung)."""
    return FINANCE_VIEW in perms and FINANCE_EDIT not in perms


def _year_bookings(org, year: int):
    return Booking.objects.filter(organization=org, year=year)


def _plain(qs):
    """Ohne Stornos, stornierte Buchungen und Teile einer Splitbuchung (die hängen am Kopf)."""
    return qs.filter(cancels__isnull=True, cancellation__isnull=True, split_of__isnull=True)


def facts(org, year: int) -> dict:
    """Zahlen, die die Prüfer vorab sehen: Buchungen, fehlende Belege, Nummernlücken."""
    bookings = _year_bookings(org, year)
    numbers = sorted(bookings.values_list("number", flat=True))
    gaps = sorted(set(range(1, numbers[-1] + 1)) - set(numbers)) if numbers else []
    visible = Receipt.objects.filter(booking=OuterRef("pk"), hidden_at__isnull=True)
    without = (
        _plain(bookings)
        .exclude(kind=Booking.Kind.TRANSFER)
        .annotate(has=Exists(visible))
        .filter(has=False)
    )
    start, last = org.fiscal_range(year)
    return {
        "bookings": len(numbers),
        "without_receipt": without.count(),
        "gaps": [org.fiscal_label(year) + f"-{n:04d}" for n in gaps[:20]],
        "gap_count": len(gaps),
        "closed": YearClosing.objects.filter(organization=org, year=year).exists(),
        "cash_counts": CashCount.objects.filter(
            organization=org, kind=CashCount.Kind.COUNT, date__range=(start, last)
        ).count(),
    }


def create(org, year: int, user, **fields) -> CashAudit:
    audit = CashAudit.objects.create(organization=org, year=year, created_by=user, **fields)
    sync_accounts(audit)
    draw(audit)
    return audit


def sync_accounts(audit: CashAudit) -> None:
    """Eine Zeile je Konto, das am Ende des Geschäftsjahres bestand."""
    if audit.status != CashAudit.Status.OPEN:
        return
    org = audit.organization
    _, last = org.fiscal_range(audit.year)
    have = set(audit.accounts.values_list("account_id", flat=True))
    for account in Account.objects.filter(organization=org, opening_date__lte=last):
        if account.pk not in have:
            CashAuditAccount.objects.create(organization=org, audit=audit, account=account)


def draw(audit: CashAudit, count: int | None = None) -> int:
    """Stichproben ziehen: zuerst die größten Ausgaben, dann zufällig weitere Buchungen.

    Zieht nur Buchungen, die noch nicht in der Stichprobe sind; liefert die Anzahl."""
    count = audit.sample_size if count is None else count
    taken = set(audit.samples.values_list("booking_id", flat=True))
    pool = _plain(_year_bookings(audit.organization, audit.year)).exclude(pk__in=taken)
    chosen: list[int] = []
    if not taken:
        chosen = list(
            pool.filter(kind=Booking.Kind.EXPENSE)
            .order_by("-amount", "number")
            .values_list("pk", flat=True)[: min(LARGEST, count)]
        )
    rest = sorted(set(pool.values_list("pk", flat=True)) - set(chosen))
    need = max(count - len(chosen), 0)
    rng = random.SystemRandom()
    chosen += rng.sample(rest, min(need, len(rest)))
    CashAuditSample.objects.bulk_create(
        [
            CashAuditSample(organization=audit.organization, audit=audit, booking_id=pk)
            for pk in chosen
        ]
    )
    return len(chosen)


def book_balances(audit: CashAudit) -> dict[int, Decimal]:
    _, last = audit.organization.fiscal_range(audit.year)
    return services.balances(audit.organization_id, before=last + datetime.timedelta(days=1))


def auditors_with_access(org) -> list[dict]:
    """Konten mit Kassenprüfer-Rechten und bis wann ihr Zugang gilt (aus den Rollen)."""
    from access.models import RoleAssignment

    rights: dict[int, set] = {}
    until: dict[int, datetime.date | None] = {}
    names: dict[int, str] = {}
    for a in (
        RoleAssignment.objects.active()
        .filter(organization=org, user__isnull=False, user__is_active=True)
        .select_related("role", "user", "person")
    ):
        perms = effective(a.role.permissions or [])
        rights.setdefault(a.user_id, set()).update(perms)
        if FINANCE_VIEW in perms:
            prev = until.get(a.user_id, datetime.date.min)
            if prev is not None:
                until[a.user_id] = None if a.valid_until is None else max(prev, a.valid_until)
            names[a.user_id] = (
                str(a.person) if a.person_id else a.user.get_full_name() or a.user.email
            )
    rows = [
        {"name": names[uid], "until": until[uid]}
        for uid, perms in rights.items()
        if uid in names and is_auditor(perms)
    ]
    return sorted(rows, key=lambda r: r["name"].casefold())


def check_rows(audit: CashAudit) -> list[dict]:
    rows = []
    for key, label in CHECKS:
        entry = audit.checks.get(key) or {}
        rows.append(
            {
                "key": key,
                "label": gettext(label),
                "result": entry.get("result", ""),
                "note": entry.get("note", ""),
            }
        )
    return rows


def clean_checks(value) -> dict:
    """Prüfpunkte aus der Anfrage prüfen: {key: {result, note}}."""
    if not isinstance(value, dict):
        raise ValueError(gettext("Ungültige Prüfpunkte."))
    result = {}
    for key, entry in value.items():
        if key not in CHECK_KEYS or not isinstance(entry, dict):
            raise ValueError(gettext("Ungültige Prüfpunkte."))
        res = entry.get("result", "")
        note = entry.get("note", "")
        if res not in RESULTS or not isinstance(note, str) or len(note) > 300:
            raise ValueError(gettext("Ungültige Prüfpunkte."))
        result[key] = {"result": res, "note": note.strip()}
    return result


def open_points(audit: CashAudit) -> int:
    """Noch nicht bearbeitete Stichproben, Konten und Prüfpunkte."""
    samples = audit.samples.filter(result="").count()
    accounts = audit.accounts.filter(statement_balance__isnull=True).count()
    checks = sum(1 for row in check_rows(audit) if not row["result"])
    return samples + accounts + checks


def signer(user) -> str:
    return user.get_full_name() or user.email


def stamp(obj, user) -> None:
    obj.checked_by_name = signer(user)
    obj.checked_at = timezone.now()


def meetings(org) -> list[dict]:
    """Versammlungen der Einheit zur Auswahl (nur mit Modul Versammlungen)."""
    from access.modules import module_on

    if not module_on(org, "meetings"):
        return []
    from meetings.models import Meeting

    qs = (
        Meeting.objects.filter(organization=org, department__isnull=True)
        .exclude(status=Meeting.Status.CANCELLED)
        .select_related("event")
        .order_by("-event__starts_at")
    )
    return [
        {
            "id": m.pk,
            "title": m.event.title,
            "date": timezone.localdate(m.event.starts_at),
        }
        for m in qs[:50]
    ]
