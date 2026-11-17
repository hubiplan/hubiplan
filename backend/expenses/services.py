"""Ablauf einer Auslage: anlegen, einreichen, prüfen, freigeben, auszahlen.

Regeln aus docs/auslagen.md:

- Wer den Antrag gestellt oder für jemanden erfasst hat, bestätigt und gibt ihn nicht selbst
  frei. Ausnahme ist die Kleinbetragsgrenze (``ExpenseSettings.self_limit``, Vorgabe 200 €):
  darunter darf sich die Kasse die eigene Auslage selbst freigeben; der Antrag landet dann
  in „Nachträglich sichten“ für eine zweite Person (AE-5).
- Ab ``second_from`` braucht die Freigabe zwei verschiedene Personen (AE-7).
- Gebucht wird erst bei der Auszahlung (AE-8), immer der ganze Betrag (AE-9).
- Nach der Auszahlung wird die Bankverbindung im Antrag geleert (AE-10).
"""

from __future__ import annotations

import datetime
import hashlib
import mimetypes
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext

from .models import (
    ExpenseClaim,
    ExpenseEvent,
    ExpenseFile,
    ExpenseLine,
    ExpenseSettings,
)

MODULE = "expenses"
VIEW = "expenses.view"
EDIT = "expenses.edit"
CENT = Decimal("0.01")
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES = 10
MAX_LINES = 20
MAX_AMOUNT = Decimal("100000.00")
MAX_KM = Decimal("5000")
FILE_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/xml",
    "text/xml",
}
# Gleicher Betrag und Kaufdatum vom selben Mitglied innerhalb dieser Frist: Hinweis
DUPLICATE_DAYS = 60
# Aufbewahrung abgelehnter/zurückgezogener Anträge (AE-11) und von Entwürfen
PURGE_FILES_DAYS = 183
DRAFT_DAYS = 90

S = ExpenseClaim.Status
OPEN_FOR_MEMBER = (S.DRAFT, S.QUESTION)
IN_REVIEW = (S.SUBMITTED, S.CONFIRMED)
FINAL = (S.PAID, S.REJECTED, S.WITHDRAWN, S.WAIVED)


def enabled(org) -> bool:
    return MODULE in (org.enabled_modules or []) and "finance" in (org.enabled_modules or [])


def settings_for(org, *, lock: bool = False) -> ExpenseSettings:
    qs = ExpenseSettings.objects
    if lock:
        qs = qs.select_for_update()
    cfg = qs.filter(organization=org).first()
    if cfg is None:
        cfg, _ = ExpenseSettings.objects.get_or_create(organization=org)
        if lock:
            cfg = ExpenseSettings.objects.select_for_update().get(pk=cfg.pk)
    return cfg


def money(value) -> Decimal:
    try:
        amount = Decimal(str(value).replace(",", ".")).quantize(CENT, rounding=ROUND_HALF_UP)
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ValidationError({"amount": gettext("Bitte einen gültigen Betrag angeben.")}) from exc
    if not amount.is_finite():
        raise ValidationError({"amount": gettext("Bitte einen gültigen Betrag angeben.")})
    return amount


def comma(value: Decimal) -> str:
    return f"{value:.2f}".replace(".", ",")


def person_name(claim: ExpenseClaim) -> str:
    if claim.membership_id:
        return str(claim.membership.person)
    return claim.name


def user_name(user) -> str:
    if user is None:
        return ""
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return full or getattr(user, "email", "") or str(user)


def log(claim: ExpenseClaim, kind: str, user=None, text: str = "", who: str = "") -> ExpenseEvent:
    return ExpenseEvent.objects.create(
        organization_id=claim.organization_id,
        claim=claim,
        kind=kind,
        user=user if getattr(user, "is_authenticated", False) else None,
        who=(who or user_name(user))[:200],
        text=(text or "")[:2000],
    )


# --- Wer darf was ---


def own_membership_ids(user, org) -> set[int]:
    """Mitgliedschaften dieses Kontos im Verein (über den Mitgliederzugang)."""
    if not getattr(user, "is_authenticated", False):
        return set()
    from portal.models import PortalAccess

    return set(
        PortalAccess.objects.filter(user=user, organization=org).values_list(
            "membership_id", flat=True
        )
    )


def is_own(claim: ExpenseClaim, user) -> bool:
    """Eigene Auslage: selbst gestellt, für einen selbst oder von einem selbst erfasst."""
    uid = getattr(user, "pk", None)
    if uid is None:
        return False
    if claim.user_id == uid or claim.created_by_id == uid:
        return True
    return bool(claim.membership_id) and claim.membership_id in own_membership_ids(
        user, claim.organization
    )


def is_officer(org, membership) -> bool:
    """Amt oder Rolle im Verein oder in einer Untereinheit (Einstellung „nur mit Amt“)."""
    from access.models import RoleAssignment

    on = timezone.localdate()
    return (
        RoleAssignment._base_manager.filter(
            Q(organization=org, person_id=membership.person_id) | Q(membership=membership),
            valid_from__lte=on,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
        .exists()
    )


def may_submit(org, membership) -> bool:
    if membership is None or not membership.current_period():
        return False
    if membership.person.kind != "person":
        return False
    cfg = settings_for(org)
    if cfg.submitters == ExpenseSettings.Submitters.OFFICERS:
        return is_officer(org, membership)
    return True


def confirm_unit(claim: ExpenseClaim, cfg: ExpenseSettings | None = None):
    """Untereinheit, deren Leitung sachlich bestätigt (sie selbst oder eine darüber)."""
    if not claim.department_id:
        return None
    cfg = cfg or settings_for(claim.organization)
    wanted = {int(i) for i in (cfg.confirm_departments or []) if str(i).isdigit()}
    if not wanted:
        return None
    from organizations.models import Department

    for node in claim.department.ancestors():
        if node.pk in wanted:
            return Department.objects.filter(pk=node.pk).first()
    return None


def needs_confirm(claim: ExpenseClaim, cfg: ExpenseSettings | None = None) -> bool:
    return claim.confirmed_at is None and confirm_unit(claim, cfg) is not None


def needs_second(claim: ExpenseClaim, cfg: ExpenseSettings | None = None) -> bool:
    cfg = cfg or settings_for(claim.organization)
    return cfg.second_from is not None and claim.payout_amount >= cfg.second_from


# --- Bearbeiten durch das Mitglied ---


def _clean_text(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _date(value, field: str) -> datetime.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError({field: gettext("Bitte ein gültiges Datum angeben.")}) from exc


def _payee(data) -> dict:
    if not data:
        return {}
    from billing.sepa import clean_iban, sepa_text
    from finance.models import iban_valid

    holder = _clean_text(data.get("holder"), 70)
    iban = clean_iban(str(data.get("iban") or ""))
    bic = str(data.get("bic") or "").replace(" ", "").upper()[:11]
    if not holder and not iban:
        return {}
    if not holder or not sepa_text(holder, 70):
        raise ValidationError({"payee": gettext("Bitte den Kontoinhaber angeben.")})
    if not iban_valid(iban):
        raise ValidationError({"payee": gettext("Die IBAN ist ungültig.")})
    return {"holder": holder, "iban": iban, "bic": bic}


def suggested_payee(org, membership) -> dict:
    """Vorschlag aus dem gültigen SEPA-Mandat des Mitglieds (AE-10)."""
    if membership is None:
        return {}
    from billing.models import Mandate

    mandate = (
        Mandate.objects.filter(
            organization=org, membership=membership, status=Mandate.Status.ACTIVE
        )
        .order_by("-signed_on", "-pk")
        .first()
    )
    if mandate is None or not getattr(mandate, "iban", ""):
        return {}
    return {"holder": mandate.holder, "iban": mandate.iban, "bic": mandate.bic or ""}


def apply_changes(claim: ExpenseClaim, data: dict, *, treasury: bool = False) -> None:
    """Felder und Positionen eines Entwurfs bzw. eines Antrags mit Rückfrage übernehmen."""
    org = claim.organization
    cfg = settings_for(org)
    if "kind" in data and claim.status == S.DRAFT:
        kind = data["kind"]
        if kind not in ExpenseClaim.Kind.values:
            raise ValidationError({"kind": gettext("Unbekannte Art.")})
        if kind == ExpenseClaim.Kind.MILEAGE and not cfg.mileage_enabled:
            raise ValidationError({"kind": gettext("Fahrtkosten sind nicht eingeschaltet.")})
        if kind == ExpenseClaim.Kind.ADVANCE and not cfg.advances_enabled:
            raise ValidationError({"kind": gettext("Vorschüsse sind nicht eingeschaltet.")})
        claim.kind = kind
    if "purpose" in data:
        claim.purpose = str(data.get("purpose") or "").strip()[:1000]
    if "note" in data:
        claim.note = _clean_text(data.get("note"), 300)
    if "purchase_date" in data:
        claim.purchase_date = _date(data.get("purchase_date"), "purchase_date")
    if "invoice_to" in data:
        if data["invoice_to"] not in ExpenseClaim.InvoiceTo.values:
            raise ValidationError({"invoice_to": gettext("Bitte eine Auswahl treffen.")})
        claim.invoice_to = data["invoice_to"]
    if "payout" in data:
        if data["payout"] not in (ExpenseClaim.Payout.BANK, ExpenseClaim.Payout.CASH):
            raise ValidationError({"payout": gettext("Bitte Überweisung oder bar wählen.")})
        claim.payout = data["payout"]
    if "payee" in data:
        claim.payee = _payee(data.get("payee") or {})
    if "department" in data:
        claim.department = _department(org, data.get("department"))
    if "project" in data:
        claim.project = _project(org, data.get("project"))
    if "advance" in data:
        claim.advance = _advance(claim, data.get("advance"))
    if claim.kind == ExpenseClaim.Kind.MILEAGE:
        if "route" in data:
            claim.route = _clean_text(data.get("route"), 300)
        if "km" in data:
            claim.km = _km(data.get("km"))
        claim.km_rate = cfg.km_rate
    claim.save()
    if claim.kind == ExpenseClaim.Kind.MILEAGE:
        _mileage_line(claim)
    elif "lines" in data:
        set_lines(claim, data.get("lines") or [], treasury=treasury)


def _km(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        km = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.1"))
    except (ArithmeticError, ValueError) as exc:
        raise ValidationError({"km": gettext("Bitte die Kilometer als Zahl angeben.")}) from exc
    if km <= 0 or km > MAX_KM:
        raise ValidationError({"km": gettext("Bitte zwischen 0,1 und 5000 km angeben.")})
    return km


def _mileage_line(claim: ExpenseClaim) -> None:
    claim.lines.all().delete()
    if claim.km and claim.km_rate:
        amount = (claim.km * claim.km_rate).quantize(CENT, rounding=ROUND_HALF_UP)
        if amount > 0:
            ExpenseLine.objects.create(
                organization_id=claim.organization_id,
                claim=claim,
                amount=amount,
                text=gettext("{km} km × {rate} €").format(
                    km=str(claim.km).replace(".", ","), rate=comma(claim.km_rate)
                ),
                category=_mileage_category(claim.organization),
            )


def _mileage_category(org):
    from finance.models import Category

    return (
        Category.objects.filter(organization=org, kind__in=("expense", "both"))
        .filter(Q(name__icontains="fahrt") | Q(name__icontains="reise"))
        .order_by("pk")
        .first()
    )


def _department(org, value):
    if value in (None, ""):
        return None
    from organizations.models import Department

    dept = Department.objects.filter(organization=org, pk=value, is_active=True).first()
    if dept is None:
        raise ValidationError({"department": gettext("Unbekannte Untereinheit.")})
    return dept


def _project(org, value):
    if value in (None, ""):
        return None
    from finance.models import Project

    project = Project.objects.filter(organization=org, pk=value).first()
    if project is None:
        raise ValidationError({"project": gettext("Unbekannte Veranstaltung.")})
    return project


def _advance(claim: ExpenseClaim, value):
    if value in (None, ""):
        return None
    adv = ExpenseClaim.objects.filter(
        organization_id=claim.organization_id,
        pk=value,
        kind=ExpenseClaim.Kind.ADVANCE,
        status=S.PAID,
        membership_id=claim.membership_id,
    ).first()
    if adv is None or adv.pk == claim.pk:
        raise ValidationError({"advance": gettext("Unbekannter Vorschuss.")})
    other = getattr(adv, "settlement", None)
    if other is not None and other.pk != claim.pk and other.status not in (S.REJECTED, S.WITHDRAWN):
        raise ValidationError({"advance": gettext("Dieser Vorschuss ist schon abgerechnet.")})
    return adv


def set_lines(claim: ExpenseClaim, rows, *, treasury: bool = False) -> None:
    from finance.models import Category

    if not isinstance(rows, list) or len(rows) > MAX_LINES:
        raise ValidationError({"lines": gettext("Bitte höchstens 20 Positionen angeben.")})
    org_id = claim.organization_id
    clean = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError({"lines": gettext("Ungültige Position.")})
        amount = money(row.get("amount"))
        if amount <= 0 or amount > MAX_AMOUNT:
            raise ValidationError(
                {"lines": gettext("Jede Position braucht einen Betrag größer als 0.")}
            )
        category = None
        if row.get("category") not in (None, ""):
            category = Category.objects.filter(organization_id=org_id, pk=row["category"]).first()
            if category is None or not category.allows("expense"):
                raise ValidationError({"lines": gettext("Unbekannte Kategorie.")})
        clean.append((i, amount, _clean_text(row.get("text"), 200), category))
    claim.lines.all().delete()
    for i, amount, text, category in clean:
        ExpenseLine.objects.create(
            organization_id=org_id,
            claim=claim,
            amount=amount,
            text=text,
            category=category,
            position=i,
        )


def add_file(claim: ExpenseClaim, upload, user) -> ExpenseFile:
    if upload is None:
        raise ValidationError({"file": gettext("Bitte eine Datei wählen.")})
    if claim.files.count() >= MAX_FILES:
        raise ValidationError({"file": gettext("Höchstens 10 Belege je Auslage.")})
    if upload.size > MAX_FILE_BYTES:
        raise ValidationError({"file": gettext("Die Datei ist größer als 15 MB.")})
    content_type = (upload.content_type or mimetypes.guess_type(upload.name)[0] or "").lower()
    if content_type not in FILE_TYPES:
        raise ValidationError(
            {
                "file": gettext(
                    "Erlaubt sind PDF, Fotos (JPEG, PNG, WebP, HEIC) und E-Rechnungen (XML)."
                )
            }
        )
    data = upload.read()
    upload.seek(0)
    if content_type == "application/pdf" and not data.startswith(b"%PDF"):
        raise ValidationError({"file": gettext("Die Datei ist kein PDF.")})
    info: dict = {}
    if content_type in ("application/pdf", "application/xml", "text/xml"):
        from finance import einvoice

        try:
            found = einvoice.read(data, content_type)
        except einvoice.EInvoiceError as exc:
            raise ValidationError({"file": str(exc)}) from exc
        if found:
            full = einvoice.as_json(found)
            info = {k: full.get(k) for k in ("number", "seller", "date", "payable")}
        if content_type != "application/pdf":
            content_type = "application/xml"
    name = upload.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:200] or "beleg"
    row = ExpenseFile(
        organization_id=claim.organization_id,
        claim=claim,
        name=name,
        content_type=content_type,
        size=upload.size,
        sha256=hashlib.sha256(data).hexdigest(),
        einvoice=info,
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
    )
    safe = "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)[-80:] or "beleg"
    row.file.save(safe, upload, save=False)
    row.save()
    return row


def problems(claim: ExpenseClaim, *, treasury: bool = False) -> dict:
    """Was zum Einreichen fehlt (leer: vollständig)."""
    errors: dict[str, str] = {}
    lines = list(claim.lines.all())
    if not claim.purpose.strip():
        errors["purpose"] = gettext("Bitte den Zweck angeben (wofür, für wen).")
    if claim.kind != ExpenseClaim.Kind.ADVANCE:
        if claim.purchase_date is None:
            errors["purchase_date"] = gettext("Bitte das Datum des Kaufs bzw. der Fahrt angeben.")
        elif claim.purchase_date > timezone.localdate():
            errors["purchase_date"] = gettext("Das Datum liegt in der Zukunft.")
    if claim.kind == ExpenseClaim.Kind.MILEAGE:
        if not claim.route:
            errors["route"] = gettext("Bitte Start, Ziel und Anlass der Fahrt angeben.")
        if not claim.km:
            errors["km"] = gettext("Bitte die gefahrenen Kilometer angeben.")
    elif not lines:
        errors["lines"] = gettext("Bitte den Betrag angeben.")
    if (
        claim.kind == ExpenseClaim.Kind.EXPENSE
        and not claim.files.exists()
        and not (treasury and claim.note)
    ):
        errors["files"] = gettext(
            "Bitte ein Foto oder eine Datei des Belegs hinzufügen. Ohne Beleg nur von der Kasse "
            "mit einer Begründung (Eigenbeleg)."
        )
    if claim.payout == ExpenseClaim.Payout.BANK and not claim.payee.get("iban"):
        errors["payee"] = gettext("Bitte die Bankverbindung für die Überweisung angeben.")
    return errors


def _next_number(org, year: int) -> str:
    cfg = settings_for(org, lock=True)
    counters = dict(cfg.counters or {})
    n = int(counters.get(str(year), 0)) + 1
    counters[str(year)] = n
    cfg.counters = counters
    cfg.save(update_fields=["counters", "updated_at"])
    return f"A{year}-{n:04d}"


@transaction.atomic
def submit(claim: ExpenseClaim, user, *, treasury: bool = False) -> ExpenseClaim:
    claim = ExpenseClaim.objects.select_for_update().get(pk=claim.pk)
    if claim.status not in OPEN_FOR_MEMBER:
        raise ValidationError(gettext("Die Auslage ist schon eingereicht."))
    errors = problems(claim, treasury=treasury)
    if errors:
        raise ValidationError(errors)
    answer = claim.status == S.QUESTION
    if not claim.number:
        org = claim.organization
        claim.year = org.fiscal_year_of(timezone.localdate())
        claim.number = _next_number(org, claim.year)
        claim.submitted_at = timezone.now()
    claim.status = S.CONFIRMED if claim.confirmed_at else S.SUBMITTED
    claim.version += 1
    claim.save()
    if not answer:
        log(claim, ExpenseEvent.Kind.SUBMITTED, user)
    transaction.on_commit(lambda: _notify(claim.pk, "submitted"))
    return claim


def _notify(claim_id: int, what: str) -> None:
    from . import notify

    notify.send_safely(claim_id, what)


@transaction.atomic
def answer(claim: ExpenseClaim, user, text: str) -> ExpenseClaim:
    if claim.status != S.QUESTION:
        raise ValidationError(gettext("Zu dieser Auslage gibt es keine offene Rückfrage."))
    text = str(text or "").strip()
    if text:
        log(claim, ExpenseEvent.Kind.ANSWER, user, text)
    return submit(claim, user, treasury=claim.source == ExpenseClaim.Source.TREASURY)


@transaction.atomic
def withdraw(claim: ExpenseClaim, user) -> ExpenseClaim:
    claim = ExpenseClaim.objects.select_for_update().get(pk=claim.pk)
    if claim.status not in (S.DRAFT, S.SUBMITTED, S.QUESTION, S.CONFIRMED):
        raise ValidationError(gettext("Eine freigegebene Auslage lässt sich nicht zurückziehen."))
    if claim.status == S.DRAFT and not claim.number:
        claim.delete()
        return claim
    claim.status = S.WITHDRAWN
    claim.decided_at = timezone.now()
    claim.version += 1
    claim.save()
    log(claim, ExpenseEvent.Kind.WITHDRAWN, user)
    return claim


# --- Prüfen durch Untereinheit und Kasse ---


def _locked(claim: ExpenseClaim, version=None) -> ExpenseClaim:
    row = ExpenseClaim.objects.select_for_update().select_related("organization").get(pk=claim.pk)
    if version not in (None, "") and str(row.version) != str(version):
        raise ValidationError(
            gettext("Die Auslage wurde inzwischen geändert. Bitte neu laden und erneut prüfen.")
        )
    return row


@transaction.atomic
def ask(claim: ExpenseClaim, user, text: str, version=None) -> ExpenseClaim:
    claim = _locked(claim, version)
    if claim.status not in IN_REVIEW:
        raise ValidationError(gettext("Zu dieser Auslage ist keine Rückfrage möglich."))
    text = str(text or "").strip()
    if len(text) < 3:
        raise ValidationError({"text": gettext("Bitte schreiben, was fehlt.")})
    claim.status = S.QUESTION
    claim.approved_by = None
    claim.approved_at = None
    claim.version += 1
    claim.save()
    log(claim, ExpenseEvent.Kind.QUESTION, user, text)
    transaction.on_commit(lambda: _notify(claim.pk, "question"))
    return claim


@transaction.atomic
def confirm(claim: ExpenseClaim, user, department_ids: set[int], version=None) -> ExpenseClaim:
    """Sachliche Bestätigung durch die Leitung der Untereinheit (A4)."""
    claim = _locked(claim, version)
    if claim.status != S.SUBMITTED:
        raise ValidationError(gettext("Diese Auslage wartet nicht auf eine Bestätigung."))
    unit = confirm_unit(claim)
    if unit is None or unit.pk not in department_ids:
        raise ValidationError(gettext("Diese Auslage bestätigt eine andere Untereinheit."))
    if is_own(claim, user):
        raise ValidationError(gettext("Die eigene Auslage bestätigt bitte eine andere Person."))
    claim.status = S.CONFIRMED
    claim.confirmed_by = user
    claim.confirmed_at = timezone.now()
    claim.version += 1
    claim.save()
    log(claim, ExpenseEvent.Kind.CONFIRMED, user)
    transaction.on_commit(lambda: _notify(claim.pk, "confirmed"))
    return claim


@transaction.atomic
def approve(
    claim: ExpenseClaim, user, *, amount=None, reason: str = "", version=None
) -> ExpenseClaim:
    claim = _locked(claim, version)
    cfg = settings_for(claim.organization)
    if claim.status not in IN_REVIEW:
        raise ValidationError(gettext("Diese Auslage wartet nicht auf eine Freigabe."))
    if needs_confirm(claim, cfg):
        raise ValidationError(
            gettext("Die Untereinheit {name} muss die Auslage zuerst sachlich bestätigen.").format(
                name=confirm_unit(claim, cfg).name
            )
        )
    if amount not in (None, ""):
        amount = money(amount)
        if amount <= 0 or amount > claim.total:
            raise ValidationError(
                {"amount": gettext("Der freigegebene Betrag liegt zwischen 0 und der Summe.")}
            )
        if amount < claim.total:
            reason = _clean_text(reason, 300)
            if len(reason) < 3:
                raise ValidationError(
                    {"reason": gettext("Bitte begründen, warum weniger freigegeben wird.")}
                )
            if claim.approved_by_id and claim.approved_amount != amount:
                raise ValidationError(
                    gettext("Die zweite Freigabe ändert den Betrag nicht. Bitte Rückfrage stellen.")
                )
            claim.approved_amount = amount
            claim.reduce_reason = reason
        elif not claim.approved_by_id:
            claim.approved_amount = None
            claim.reduce_reason = ""
    own = is_own(claim, user)
    now = timezone.now()
    if own:
        limit = cfg.self_limit or Decimal(0)
        if limit <= 0 or claim.payout_amount > limit or needs_second(claim, cfg):
            raise ValidationError(
                gettext(
                    "Die eigene Auslage gibt bitte eine andere Person frei (über {limit} € oder "
                    "Grenze ausgeschaltet)."
                ).format(limit=comma(limit))
            )
        claim.self_approved = True
        claim.approved_by = user
        claim.approved_at = now
        claim.status = S.APPROVED
        kind = ExpenseEvent.Kind.SELF
    elif needs_second(claim, cfg) and not claim.approved_by_id:
        claim.approved_by = user
        claim.approved_at = now
        kind = ExpenseEvent.Kind.APPROVED
    elif needs_second(claim, cfg):
        if claim.approved_by_id == user.pk:
            raise ValidationError(gettext("Die zweite Freigabe gibt bitte eine andere Person."))
        claim.second_by = user
        claim.second_at = now
        claim.status = S.APPROVED
        kind = ExpenseEvent.Kind.SECOND
    else:
        claim.approved_by = user
        claim.approved_at = now
        claim.status = S.APPROVED
        kind = ExpenseEvent.Kind.APPROVED
    if claim.status == S.APPROVED:
        claim.decided_at = now
    claim.version += 1
    claim.save()
    text = ""
    if claim.approved_amount is not None:
        text = gettext("{amount} € statt {total} €: {reason}").format(
            amount=comma(claim.approved_amount),
            total=comma(claim.total),
            reason=claim.reduce_reason,
        )
    log(claim, kind, user, text)
    if claim.status == S.APPROVED:
        transaction.on_commit(lambda: _notify(claim.pk, "approved"))
    return claim


@transaction.atomic
def reject(claim: ExpenseClaim, user, reason: str, version=None) -> ExpenseClaim:
    claim = _locked(claim, version)
    if claim.status not in (*IN_REVIEW, S.APPROVED):
        raise ValidationError(gettext("Diese Auslage lässt sich nicht mehr ablehnen."))
    if claim.transfers.filter(released=False).exists():
        raise ValidationError(gettext("Die Auslage steckt in einer Sammelüberweisung."))
    reason = _clean_text(reason, 500)
    if len(reason) < 3:
        raise ValidationError({"reason": gettext("Bitte einen Grund angeben.")})
    claim.status = S.REJECTED
    claim.reject_reason = reason
    claim.decided_at = timezone.now()
    claim.version += 1
    claim.save()
    log(claim, ExpenseEvent.Kind.REJECTED, user, reason)
    transaction.on_commit(lambda: _notify(claim.pk, "rejected"))
    return claim


@transaction.atomic
def review(claims, user) -> int:
    """Nachträgliche Sichtung selbst freigegebener Auslagen durch eine zweite Person."""
    done = 0
    for claim in claims:
        claim = ExpenseClaim.objects.select_for_update().get(pk=claim.pk)
        if not claim.self_approved or claim.reviewed_at or is_own(claim, user):
            continue
        claim.reviewed_by = user
        claim.reviewed_at = timezone.now()
        claim.save(update_fields=["reviewed_by", "reviewed_at", "updated_at"])
        log(claim, ExpenseEvent.Kind.REVIEWED, user)
        done += 1
    return done


# --- Auszahlen ---


def booking_text(claim: ExpenseClaim) -> str:
    if claim.kind == ExpenseClaim.Kind.ADVANCE:
        prefix = gettext("Vorschuss")
    elif claim.kind == ExpenseClaim.Kind.MILEAGE:
        prefix = gettext("Fahrtkosten")
    else:
        prefix = gettext("Auslage")
    return f"{prefix} {claim.number} {claim.purpose}".strip()[:200]


def _parts(claim: ExpenseClaim, categories: dict | None = None) -> list[tuple]:
    """Beträge je Kategorie (gekürzte Freigabe: anteilig auf die Positionen verteilt)."""
    from finance.models import Category

    categories = categories or {}
    lines = list(claim.lines.all())
    rows = []
    for line in lines:
        cat_id = categories.get(str(line.pk)) or categories.get(line.pk) or line.category_id
        category = (
            Category.objects.filter(organization_id=claim.organization_id, pk=cat_id).first()
            if cat_id
            else None
        )
        if category is None or not category.allows("expense"):
            raise ValidationError(
                {
                    "categories": gettext(
                        "Bitte für jede Position eine Kategorie für Ausgaben wählen."
                    )
                }
            )
        rows.append([line, category, line.amount])
    if claim.approved_amount is not None and claim.approved_amount != claim.total:
        from billing.advances import split_amount

        shares = split_amount(claim.approved_amount, [r[2] for r in rows])
        for row, share in zip(rows, shares, strict=True):
            row[2] = share
    return [(line, cat, amount) for line, cat, amount in rows if amount > 0]


@transaction.atomic
def pay(
    claim: ExpenseClaim,
    user,
    *,
    account,
    date: datetime.date | None = None,
    categories: dict | None = None,
    version=None,
    transfer=None,
):
    """Auslage auszahlen: Ausgabebuchung (Splitbuchung je Kategorie) mit den Belegen."""
    from finance import services as fin
    from finance.models import Booking, Receipt

    claim = _locked(claim, version)
    org = claim.organization
    if claim.status != S.APPROVED:
        raise ValidationError(gettext("Nur freigegebene Auslagen lassen sich auszahlen."))
    if transfer is None and claim.transfers.filter(released=False).exists():
        raise ValidationError(gettext("Die Auslage steckt in einer Sammelüberweisung."))
    if account is None or account.organization_id != org.pk or not account.is_active:
        raise ValidationError({"account": gettext("Bitte ein Konto wählen.")})
    date = date or timezone.localdate()
    if date > timezone.localdate() + datetime.timedelta(days=365):
        raise ValidationError({"date": gettext("Bitte ein gültiges Datum angeben.")})
    fin.ensure_bookable(org, date)
    year = org.fiscal_year_of(date)
    due = claim.amount_due
    name = person_name(claim)
    head = None
    if due > 0:
        parts = _parts(claim, categories)
        # Abrechnung eines Vorschusses: nur der Rest wird ausgezahlt
        if claim.advance_id:
            from billing.advances import split_amount

            shares = split_amount(due, [p[2] for p in parts])
            parts = [
                (line, cat, share) for (line, cat, _), share in zip(parts, shares, strict=True)
            ]
            parts = [p for p in parts if p[2] > 0]
        for line, category, amount in parts:
            booking = Booking.objects.create(
                organization=org,
                year=year,
                number=fin.next_number(org.pk, year),
                date=date,
                kind=Booking.Kind.EXPENSE,
                amount=amount,
                account=account,
                category=category,
                project=claim.project,
                text=(
                    booking_text(claim) if head is None else f"{booking_text(claim)}: {line.text}"
                )[:200],
                reference=claim.number,
                counterparty=name[:200],
                membership=claim.membership,
                department=claim.department,
                vat_rate=category.vat_rate,
                split_of=head,
                created_by=user,
            )
            head = head or booking
    elif due < 0:
        # Vorschuss war höher: Rückzahlung des Mitglieds als Einnahme
        from finance.models import Category

        adv_booking = claim.advance.booking
        category = adv_booking.category if adv_booking else None
        if category is None:
            category = Category.objects.filter(organization=org, kind="both").first()
        head = Booking.objects.create(
            organization=org,
            year=year,
            number=fin.next_number(org.pk, year),
            date=date,
            kind=Booking.Kind.INCOME,
            amount=-due,
            account=account,
            category=category,
            project=claim.project,
            text=gettext("Rückzahlung Vorschuss {number}").format(number=claim.advance.number)[
                :200
            ],
            reference=claim.number,
            counterparty=name[:200],
            membership=claim.membership,
            department=claim.department,
            created_by=user,
        )
    if head is not None:
        fin.ensure_cash_ok([account], date)
        for row in claim.files.filter(receipt__isnull=True):
            if not row.file:
                continue
            receipt = Receipt(
                organization=org,
                booking=head,
                name=row.name,
                content_type=row.content_type,
                size=row.size,
                uploaded_by=None,
                einvoice=row.einvoice or {},
            )
            # Dieselbe Datei: der Antragsbeleg wird Buchungsbeleg (keine Kopie)
            receipt.file.name = row.file.name
            receipt.save()
            row.receipt = receipt
            row.save(update_fields=["receipt"])
    claim.status = S.PAID
    claim.booking = head
    claim.paid_at = timezone.now()
    # Bankverbindung nur noch in Buchung bzw. Überweisungsdatei (AE-10)
    claim.payee = {}
    claim.version += 1
    claim.save()
    text = gettext("{amount} € von {account}").format(amount=comma(due), account=account.name)
    if head is not None:
        text += f" ({head.display_number})"
    log(claim, ExpenseEvent.Kind.PAID, user, text)
    from audit.log import record

    record(org, user, "update", claim, {"Auslage ausgezahlt": [claim.number, text]})
    transaction.on_commit(lambda: _notify(claim.pk, "paid"))
    return claim


def booking_cancelled(booking) -> None:
    """Storno der Auszahlung: Die Auslage ist wieder freigegeben (aus finance.services)."""
    claim = ExpenseClaim.objects.filter(booking=booking).first()
    if claim is None and booking.split_of_id:
        claim = ExpenseClaim.objects.filter(booking_id=booking.split_of_id).first()
    if claim is None or claim.status != S.PAID:
        return
    claim.status = S.APPROVED
    claim.booking = None
    claim.paid_at = None
    claim.version += 1
    claim.save()
    for row in claim.files.all():
        row.receipt = None
        row.save(update_fields=["receipt"])
    log(claim, ExpenseEvent.Kind.REOPENED, None, booking.display_number, who="Kasse")


# --- Verzicht (Aufwandsspende, A5) ---


def waiver_possible(claim: ExpenseClaim) -> bool:
    org = claim.organization
    cfg = settings_for(org)
    return (
        claim.status == S.APPROVED
        and claim.kind != ExpenseClaim.Kind.ADVANCE
        and not claim.advance_id
        and claim.membership_id is not None
        and bool(cfg.waiver_basis)
        and cfg.waiver_basis_date is not None
        and "donations" in (org.enabled_modules or [])
        and not claim.transfers.filter(released=False).exists()
    )


@transaction.atomic
def waive(claim: ExpenseClaim, user) -> ExpenseClaim:
    """Mitglied verzichtet auf die Erstattung: Zuwendung „Verzicht auf Erstattung“."""
    from finance.donations import check_donation, donor_from_membership
    from finance.models import Donation

    claim = _locked(claim)
    if not waiver_possible(claim):
        raise ValidationError(gettext("Ein Verzicht ist für diese Auslage nicht möglich."))
    org = claim.organization
    name, address = donor_from_membership(org, claim.membership)
    donation = Donation(
        organization=org,
        date=timezone.localdate(),
        kind=Donation.Kind.MONEY,
        amount=claim.payout_amount,
        waiver=True,
        membership=claim.membership,
        donor_name=name,
        donor_address=address,
    )
    check_donation(org, donation)
    if hasattr(donation, "purpose"):
        donation.purpose = claim.purpose[:200]
    donation.save()
    claim.donation = donation
    claim.status = S.WAIVED
    claim.decided_at = timezone.now()
    claim.payee = {}
    claim.version += 1
    claim.save()
    log(claim, ExpenseEvent.Kind.WAIVED, user, comma(donation.amount) + " €")
    return claim


# --- Hinweise für die Prüfung ---


def hints(claim: ExpenseClaim) -> list[str]:
    out: list[str] = []
    cfg = settings_for(claim.organization)
    if claim.purchase_date and cfg.hint_months:
        limit = timezone.localdate() - datetime.timedelta(days=int(cfg.hint_months) * 30)
        if claim.purchase_date < limit:
            out.append(
                gettext("Der Kauf liegt mehr als {n} Monate zurück.").format(n=cfg.hint_months)
            )
    hashes = list(claim.files.values_list("sha256", flat=True))
    if hashes:
        other = (
            ExpenseFile.objects.filter(organization_id=claim.organization_id, sha256__in=hashes)
            .exclude(claim=claim)
            .exclude(claim__status__in=(S.REJECTED, S.WITHDRAWN))
            .select_related("claim")
            .first()
        )
        if other:
            out.append(
                gettext("Derselbe Beleg steckt schon in {number}.").format(
                    number=other.claim.number or gettext("einem Entwurf")
                )
            )
    if claim.membership_id and claim.purchase_date and claim.kind == ExpenseClaim.Kind.EXPENSE:
        near = (
            ExpenseClaim.objects.filter(
                organization_id=claim.organization_id,
                membership_id=claim.membership_id,
                purchase_date__range=(
                    claim.purchase_date - datetime.timedelta(days=DUPLICATE_DAYS),
                    claim.purchase_date + datetime.timedelta(days=DUPLICATE_DAYS),
                ),
            )
            .exclude(pk=claim.pk)
            .exclude(status__in=(S.DRAFT, S.REJECTED, S.WITHDRAWN))
        )
        total = claim.total
        for other in near.prefetch_related("lines"):
            if other.total == total and other.purchase_date == claim.purchase_date:
                out.append(
                    gettext("{number} hat denselben Betrag und dasselbe Datum.").format(
                        number=other.number
                    )
                )
                break
    for f in claim.files.all():
        payable = (f.einvoice or {}).get("payable")
        if payable not in (None, ""):
            try:
                if Decimal(str(payable)) != claim.total and not claim.note:
                    out.append(
                        gettext(
                            "Die E-Rechnung nennt {x} €, beantragt sind {y} € ohne Hinweis."
                        ).format(x=comma(Decimal(str(payable))), y=comma(claim.total))
                    )
            except ArithmeticError:
                pass
    if claim.invoice_to == ExpenseClaim.InvoiceTo.ME:
        from billing.models import BillingSettings

        vat = (
            BillingSettings.objects.filter(organization_id=claim.organization_id)
            .values_list("vat_enabled", flat=True)
            .first()
        )
        if vat and claim.total > Decimal("250"):
            out.append(
                gettext("Die Rechnung lautet auf das Mitglied: kein Vorsteuerabzug (über 250 €).")
            )
    return out


def budget_hint(claim: ExpenseClaim) -> list[dict]:
    """Haushaltsplan je Kategorie der Positionen: Plan, Ist, offen freigegeben, mit diesem."""
    from finance import budget

    org = claim.organization
    year = org.fiscal_year_of(claim.purchase_date or timezone.localdate())
    try:
        rep = budget.report(org, year)
    except Exception:  # noqa: BLE001 - nur Hinweis, darf die Prüfung nie verhindern
        return []
    rows = []
    by_cat: dict[int, Decimal] = {}
    for line in claim.lines.all():
        if line.category_id:
            by_cat[line.category_id] = by_cat.get(line.category_id, Decimal(0)) + line.amount
    lines = rep.get("lines") or []
    for cat_id, amount in by_cat.items():
        match = None
        for row in lines:
            if row.get("kind") != "expense" or row.get("category") != cat_id:
                continue
            dept = row.get("department")
            if dept == claim.department_id or (dept is None and match is None):
                match = row
        if match is None or match.get("actual") is None:
            continue
        open_sum = open_amount(org, category_id=cat_id, department_id=match.get("department"))
        rows.append(
            {
                "category": cat_id,
                "department": match.get("department"),
                "plan": str(match.get("amount")),
                "actual": str(match.get("actual")),
                "open": str(open_sum),
                "with_this": str(Decimal(str(match.get("actual") or 0)) + open_sum + amount),
            }
        )
    return rows


def open_amount(org, *, category_id=None, department_id=None) -> Decimal:
    """Freigegebene, noch nicht ausgezahlte Auslagen (Verbindlichkeiten)."""
    lines = ExpenseLine.objects.filter(organization=org, claim__status=S.APPROVED)
    if category_id is not None:
        lines = lines.filter(category_id=category_id)
    if department_id is not None:
        lines = lines.filter(claim__department_id=department_id)
    return sum((line.amount for line in lines), Decimal("0.00"))


def liabilities(org) -> dict:
    """Offene Auslagen für Übersicht, Vermögensübersicht und Jahresabschluss (A3)."""
    claims = list(
        ExpenseClaim.objects.filter(organization=org, status=S.APPROVED).prefetch_related(
            "lines", "advance"
        )
    )
    review_open = ExpenseClaim.objects.filter(
        organization=org, status__in=(S.SUBMITTED, S.CONFIRMED, S.QUESTION)
    ).count()
    return {
        "approved_count": len(claims),
        "approved_sum": str(sum((c.amount_due for c in claims), Decimal("0.00"))),
        "in_review": review_open,
        "unreviewed": ExpenseClaim.objects.filter(
            organization=org, self_approved=True, reviewed_at__isnull=True
        ).count(),
    }


# --- Aufbewahrung (AE-11) ---


def purge(now: datetime.datetime | None = None) -> dict:
    """Belege abgelehnter/zurückgezogener Anträge nach 6 Monaten löschen, Eckdaten bis Ende des
    Folgejahres; Entwürfe nach 90 Tagen ohne Änderung."""
    from core.files import delete_on_commit
    from core.tenancy import rls_bypass

    now = now or timezone.now()
    stats = {"files": 0, "claims": 0, "drafts": 0}
    with rls_bypass(), transaction.atomic():
        old = ExpenseClaim.objects.filter(
            status__in=(S.REJECTED, S.WITHDRAWN),
            decided_at__lt=now - datetime.timedelta(days=PURGE_FILES_DAYS),
            files_purged_at__isnull=True,
        )
        for claim in old:
            for row in claim.files.all():
                if row.file and not row.receipt_id:
                    delete_on_commit(row.file)
                row.delete()
                stats["files"] += 1
            claim.payee = {}
            claim.files_purged_at = now
            claim.save(update_fields=["payee", "files_purged_at", "updated_at"])
        gone = ExpenseClaim.objects.filter(
            status__in=(S.REJECTED, S.WITHDRAWN),
            files_purged_at__isnull=False,
            decided_at__year__lt=now.year - 1,
        )
        for claim in gone:
            if ExpenseClaim.objects.filter(advance=claim).exists():
                continue
            claim.delete()
            stats["claims"] += 1
        drafts = ExpenseClaim.objects.filter(
            status=S.DRAFT, updated_at__lt=now - datetime.timedelta(days=DRAFT_DAYS)
        )
        for claim in drafts:
            for row in claim.files.all():
                if row.file:
                    delete_on_commit(row.file)
            claim.delete()
            stats["drafts"] += 1
    return stats


def ensure_db_lock() -> None:
    if not connection.in_atomic_block:
        raise RuntimeError("nur innerhalb einer Transaktion")
