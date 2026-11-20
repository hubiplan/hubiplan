"""Verzeichnis, Auftragsverarbeiter und Datenpannen zusammenstellen."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext

from .catalog import DEFAULT_TOMS, suggestions
from .models import DataBreach, PrivacySettings, ProcessingActivity


def settings_for(org) -> PrivacySettings:
    obj = PrivacySettings.objects.filter(organization=org).first()
    return obj or PrivacySettings(organization=org, toms=gettext(DEFAULT_TOMS))


def controller(org) -> dict:
    """Verantwortlicher (Art. 30 Abs. 1 lit. a) aus dem Impressum der Einheit."""
    from organizations.models import Imprint

    imp = Imprint.objects.filter(organization=org).first()
    if imp is None:
        return {"name": org.name, "address": "", "representatives": "", "contact": ""}
    place = " ".join(p for p in (imp.postal_code, imp.city) if p)
    address = ", ".join(p for p in (imp.street, imp.address_extra, place) if p)
    contact = " · ".join(p for p in (imp.email, imp.phone) if p)
    return {
        "name": imp.name or org.name,
        "address": address,
        "representatives": imp.representatives,
        "contact": contact,
    }


def own_data(a: ProcessingActivity) -> dict:
    return {
        "id": a.pk,
        "key": "",
        "module": "",
        "title": a.title,
        "purpose": a.purpose,
        "legal_basis": a.legal_basis,
        "subjects": a.subjects,
        "categories": a.categories,
        "recipients": a.recipients,
        "third_country": a.third_country,
        "retention": a.retention,
        "version": a.version,
    }


def activities(org, settings: PrivacySettings, *, with_hidden: bool) -> list[dict]:
    hidden = set(settings.hidden_keys or [])
    rows = []
    for s in suggestions(org):
        if s.key in hidden and not with_hidden:
            continue
        rows.append({**s.data(), "id": None, "hidden": s.key in hidden})
    rows += [
        {**own_data(a), "hidden": False}
        for a in ProcessingActivity.objects.filter(organization=org)
    ]
    return rows


def processors(org) -> list[dict]:
    """Geschäftspartner mit der Rolle „Auftragsverarbeiter“ und ihre Verträge dazu."""
    from billing.models import BusinessPartner, PartnerAgreement

    today = timezone.localdate()
    out = []
    partners = BusinessPartner.objects.filter(organization=org, is_active=True).prefetch_related(
        "agreements"
    )
    for p in sorted(partners, key=lambda x: (x.name or "").lower()):
        if BusinessPartner.Role.PROCESSOR not in (p.roles or []):
            continue
        dpas = [
            a
            for a in p.agreements.all()
            if a.kind == PartnerAgreement.Kind.DPA and (a.end is None or a.end >= today)
        ]
        out.append(
            {
                "id": p.pk,
                "name": p.name,
                "agreement": agreement_data(dpas[0]) if dpas else None,
            }
        )
    return out


def agreement_data(a) -> dict:
    return {
        "id": a.pk,
        "title": a.title,
        "start": a.start.isoformat(),
        "end": a.end.isoformat() if a.end else None,
    }


def breach_status(b: DataBreach, now) -> str:
    if b.closed_at:
        return "closed"
    if b.needs_report and not b.reported_at:
        return "overdue" if now > b.report_deadline else "report_due"
    return "open"


def open_breaches(org):
    return DataBreach.objects.filter(organization=org, closed_at__isnull=True)
