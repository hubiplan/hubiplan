"""Ermäßigung mit Nachweis im Online-Mitgliedsantrag (Fachfrage F10).

Das Formular bietet die Ermäßigungen des Vereins an. Wer eine wählt, lädt den Nachweis auf
der Seite seines Antrags hoch (Link aus der Bestätigungsmail) oder reicht ihn nach: Nach der
Aufnahme bleiben dann ``late_join_days`` Tage (Vorgabe 4 Wochen), und die Erinnerungen laufen
wie bei allen. Bei der Aufnahme wird die Ermäßigung ab dem Eintrittstag zugeordnet; hochgeladene
Nachweise werden zu Nachweisen für das Beitragsjahr des Eintritts.
"""

from __future__ import annotations

import hashlib

from django.core.files.base import ContentFile
from django.utils.translation import gettext

from . import services
from .models import ApplicationProof, DiscountAssignment, FeeProof, ProofDiscount

MAX_FILES = 3


def offered(org, member_type_id: int | None = None) -> list[ProofDiscount]:
    if not services.module_on(org):
        return []
    rows = ProofDiscount.objects.filter(organization=org, is_archived=False)
    return [d for d in rows if d.member_type_id in (None, member_type_id) or member_type_id is None]


def choices(org) -> list[dict]:
    return [
        {"id": d.pk, "name": d.name, "member_type": d.member_type_id, "kinds": list(d.kinds or [])}
        for d in offered(org)
    ]


def clean(org, value, member_type, kind: str, errors: dict) -> int | None:
    if not value:
        return None
    if kind != "person":
        errors["discount"] = gettext("Diese Ermäßigung gibt es nur für Personen.")
        return None
    try:
        pk = int(value)
    except (TypeError, ValueError):
        errors["discount"] = gettext("Unbekannte Ermäßigung.")
        return None
    member_type_id = getattr(member_type, "pk", None)
    if not any(d.pk == pk for d in offered(org, member_type_id)):
        errors["discount"] = gettext("Diese Ermäßigung passt nicht zur Mitgliedsart.")
        return None
    return pk


def chosen(app) -> ProofDiscount | None:
    pk = (app.data or {}).get("discount")
    if not pk:
        return None
    return ProofDiscount.objects.filter(organization_id=app.organization_id, pk=pk).first()


def status(app) -> dict | None:
    """Für die Seite des Antrags (ohne Anmeldung): gewählte Ermäßigung und Dateien."""
    from core.tenancy import rls_bypass

    with rls_bypass():
        discount = chosen(app)
        if discount is None:
            return None
        files = [p.file_name for p in app.fee_proofs.all()]
    return {
        "name": discount.name,
        "kinds": list(discount.kinds or []),
        "files": files,
        "can_upload": app.status in ("unconfirmed", "unsigned", "open") and len(files) < MAX_FILES,
    }


def board_view(app) -> dict | None:
    discount = chosen(app)
    if discount is None:
        return None
    return {
        "name": discount.name,
        "files": [
            {"id": p.pk, "name": p.file_name, "precheck": p.precheck or {}}
            for p in app.fee_proofs.all()
        ],
    }


def add_file(app, name: str, content_type: str, data: bytes) -> ApplicationProof:
    from rest_framework.exceptions import ValidationError

    from . import precheck

    discount = chosen(app)
    if discount is None:
        raise ValidationError(gettext("Für diesen Antrag ist keine Ermäßigung gewählt."))
    if app.fee_proofs.count() >= MAX_FILES:
        raise ValidationError(gettext("Höchstens drei Dateien."))
    content_type = services.content_type_of(name, content_type)
    problem = services.file_problem(name, content_type, data)
    if problem:
        raise ValidationError({"file": problem})
    safe = services.safe_file_name(name, content_type)
    row = ApplicationProof(
        organization_id=app.organization_id,
        application=app,
        discount=discount,
        file_name=(name or safe)[:200],
        content_type=content_type,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    d = app.data or {}
    from django.utils import timezone

    try:
        import datetime

        birth = d.get("birth_date")
        row.precheck = precheck.check(
            data,
            content_type,
            first_name=d.get("first_name", ""),
            last_name=d.get("last_name", ""),
            birth_date=datetime.date.fromisoformat(birth) if birth else None,
            needed_until=timezone.localdate(),
        )
    except Exception:  # noqa: BLE001 - nur ein Hinweis
        row.precheck = {"level": "yellow", "reasons": ["error"]}
    row.file.save(safe, ContentFile(data), save=False)
    row.save()
    return row


def on_accept(app, membership, entry_date, user) -> None:
    """Ermäßigung ab Eintritt zuordnen und hochgeladene Nachweise übernehmen."""
    discount = chosen(app)
    if discount is None or discount.is_archived:
        return
    org = app.organization
    DiscountAssignment.objects.create(
        organization=org,
        membership=membership,
        discount=discount,
        valid_from=entry_date,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    year = org.fiscal_year_of(entry_date)
    for row in list(app.fee_proofs.all()):
        proof = FeeProof(
            organization=org,
            membership=membership,
            discount=discount,
            year=year,
            channel=FeeProof.Channel.APPLICATION,
            received_on=row.created_at.date(),
            file_name=row.file_name,
            content_type=row.content_type,
            size=row.size,
            sha256=row.sha256,
            precheck=row.precheck,
        )
        if row.file:
            with row.file.open("rb") as fh:
                proof.file.save(
                    services.safe_file_name(row.file_name, row.content_type),
                    ContentFile(fh.read()),
                    save=False,
                )
        proof.save()
        row.delete()
