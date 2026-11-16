"""Antworten der Schnittstelle (Browser, Mitgliederbereich, App).

Die Felder sind Teil der App-Schnittstelle: nur abwärtsverträglich ändern."""

from __future__ import annotations

from contextlib import contextmanager

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from . import services
from .models import ExpenseClaim, ExpenseSettings


@contextmanager
def drf_errors():
    """Fehler aus ``services`` als 400 mit Feldern an die Oberfläche geben."""
    try:
        yield
    except DjangoValidationError as exc:
        raise serializers.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        ) from exc


def masked(iban: str) -> str:
    iban = (iban or "").replace(" ", "")
    if len(iban) < 8:
        return iban
    return f"{iban[:4]} …{iban[-4:]}"


def epc_payload(claim: ExpenseClaim) -> str:
    """Inhalt eines GiroCodes (EPC-QR, Fassung 002) für die Überweisung der Auslage."""
    payee = claim.payee or {}
    if not payee.get("iban"):
        return ""
    amount = claim.amount_due
    if amount <= 0:
        return ""
    text = f"{services.booking_text(claim)}"[:140]
    return "\n".join(
        [
            "BCD",
            "002",
            "1",
            "SCT",
            payee.get("bic", ""),
            payee.get("holder", "")[:70],
            payee["iban"],
            f"EUR{amount:.2f}",
            "",
            "",
            text,
        ]
    )


def settings_data(cfg: ExpenseSettings) -> dict:
    return {
        "submitters": cfg.submitters,
        "self_limit": str(cfg.self_limit),
        "second_from": str(cfg.second_from) if cfg.second_from is not None else None,
        "hint_months": cfg.hint_months,
        "confirm_departments": list(cfg.confirm_departments or []),
        "mileage_enabled": cfg.mileage_enabled,
        "km_rate": str(cfg.km_rate),
        "waiver_basis": cfg.waiver_basis,
        "waiver_basis_date": cfg.waiver_basis_date,
        "advances_enabled": cfg.advances_enabled,
        "links_enabled": cfg.links_enabled,
    }


def claim_data(
    claim: ExpenseClaim,
    *,
    viewer=None,
    full: bool = False,
    treasury: bool = False,
    member: bool = False,
) -> dict:
    """Eine Auslage. ``treasury``: Sicht der Kasse (Hinweise, ganze IBAN, Rechte),
    ``member``: Sicht des Antragstellers."""
    lines = list(claim.lines.all())
    row = {
        "id": claim.pk,
        "number": claim.number,
        "kind": claim.kind,
        "status": claim.status,
        "status_label": claim.get_status_display(),
        "source": claim.source,
        "name": services.person_name(claim),
        "membership": claim.membership_id,
        "purpose": claim.purpose,
        "note": claim.note,
        "purchase_date": claim.purchase_date,
        "department": claim.department_id,
        "department_name": claim.department.name if claim.department_id else "",
        "project": claim.project_id,
        "project_name": claim.project.name if claim.project_id else "",
        "invoice_to": claim.invoice_to,
        "payout": claim.payout,
        "route": claim.route,
        "km": str(claim.km) if claim.km is not None else None,
        "km_rate": str(claim.km_rate) if claim.km_rate is not None else None,
        "advance": claim.advance_id,
        "advance_number": claim.advance.number if claim.advance_id else "",
        "total": str(claim.total),
        "approved_amount": (
            str(claim.approved_amount) if claim.approved_amount is not None else None
        ),
        "reduce_reason": claim.reduce_reason,
        "amount_due": str(claim.amount_due),
        "reject_reason": claim.reject_reason,
        "self_approved": claim.self_approved,
        "reviewed": claim.reviewed_at is not None,
        "approved_once": bool(claim.approved_by_id) and claim.status != claim.Status.APPROVED,
        "submitted_at": claim.submitted_at,
        "decided_at": claim.decided_at,
        "paid_at": claim.paid_at,
        "created_at": claim.created_at,
        "version": claim.version,
        "file_count": len(claim.files.all()),
        "lines": [
            {
                "id": line.pk,
                "amount": str(line.amount),
                "text": line.text,
                "category": line.category_id,
                "category_name": line.category.name if line.category_id else "",
            }
            for line in lines
        ],
    }
    payee = claim.payee or {}
    if payee:
        row["payee"] = (
            dict(payee)
            if treasury or member
            else {"holder": payee.get("holder", ""), "iban": masked(payee.get("iban", ""))}
        )
    else:
        row["payee"] = None
    if claim.booking_id:
        row["booking"] = claim.booking_id
        row["booking_number"] = claim.booking.display_number
    if not full:
        return row
    row["files"] = [
        {
            "id": f.pk,
            "name": f.name,
            "content_type": f.content_type,
            "size": f.size,
            "created_at": f.created_at,
            "einvoice": f.einvoice or None,
        }
        for f in claim.files.all()
    ]
    row["events"] = [
        {
            "kind": e.kind,
            "label": e.get_kind_display(),
            "who": e.who,
            "text": e.text,
            "at": e.created_at,
        }
        for e in claim.events.all()
    ]
    if member:
        row["can_edit"] = claim.status in services.OPEN_FOR_MEMBER
        row["can_withdraw"] = claim.status in (
            claim.Status.DRAFT,
            claim.Status.SUBMITTED,
            claim.Status.QUESTION,
            claim.Status.CONFIRMED,
        )
        row["can_waive"] = services.waiver_possible(claim)
        row["problems"] = (
            services.problems(claim) if claim.status in services.OPEN_FOR_MEMBER else {}
        )
    if treasury:
        cfg = services.settings_for(claim.organization)
        own = services.is_own(claim, viewer)
        unit = services.confirm_unit(claim, cfg)
        row["own"] = own
        row["needs_confirm"] = services.needs_confirm(claim, cfg)
        row["confirm_unit"] = unit.name if unit else ""
        row["needs_second"] = services.needs_second(claim, cfg)
        row["hints"] = services.hints(claim)
        row["budget"] = services.budget_hint(claim)
        row["epc"] = epc_payload(claim) if claim.status == claim.Status.APPROVED else ""
        row["problems"] = (
            services.problems(claim, treasury=True)
            if claim.status in services.OPEN_FOR_MEMBER
            else {}
        )
        row["self_limit"] = str(cfg.self_limit)
    return row
