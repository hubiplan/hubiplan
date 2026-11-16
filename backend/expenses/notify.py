"""Bescheide zu Auslagen: an die Prüfer (neu eingereicht, bestätigt) und an den Antragsteller
(Rückfrage, freigegeben, abgelehnt, ausgezahlt).

Wer die App mit Push nutzt, bekommt einen Push (``{"t": "info", "expense": …}``), sonst eine
Mail. Ein Fehler beim Versand ändert nichts an der Auslage.
"""

from __future__ import annotations

import logging

from django.utils.translation import gettext as _

from core.i18n import language_of_org
from core.tenancy import rls_bypass
from outbox import mail

from . import services
from .models import ExpenseClaim

logger = logging.getLogger(__name__)

TO_MEMBER = {"question", "approved", "rejected", "paid"}


def send_safely(claim_id: int, what: str) -> int:
    try:
        return send(claim_id, what)
    except Exception:  # noqa: BLE001 - Bescheid ist Zusatz, darf den Ablauf nie stören
        logger.exception("Bescheid zur Auslage %s (%s) fehlgeschlagen", claim_id, what)
        return 0


def _member_text(claim: ExpenseClaim, what: str) -> tuple[str, str]:
    amount = services.comma(claim.amount_due)
    if what == "question":
        last = claim.events.filter(kind="question").order_by("-created_at").first()
        return (
            _("Rückfrage zu deiner Auslage {number}").format(number=claim.number),
            _("Die Kasse fragt nach: {text}").format(text=last.text if last else ""),
        )
    if what == "approved":
        return (
            _("Auslage {number} freigegeben").format(number=claim.number),
            _("{amount} € werden dir erstattet.").format(amount=amount),
        )
    if what == "rejected":
        return (
            _("Auslage {number} abgelehnt").format(number=claim.number),
            _("Grund: {reason}").format(reason=claim.reject_reason),
        )
    return (
        _("Auslage {number} ausgezahlt").format(number=claim.number),
        _("{amount} € sind auf dem Weg zu dir.").format(amount=amount)
        if claim.payout == ExpenseClaim.Payout.BANK
        else _("{amount} € wurden bar ausgezahlt.").format(amount=amount),
    )


def _to_member(claim: ExpenseClaim, what: str) -> int:
    from devices.push import app_accesses, send_to_user
    from events.rsvp import email_of
    from organizations.addresses import base_url
    from portal.models import PortalAccess

    org = claim.organization
    with language_of_org(org):
        title, text = _member_text(claim, what)
    if claim.membership_id:
        accesses = app_accesses([claim.membership_id])
        access_id = accesses.get(claim.membership_id)
        if access_id:
            user_id = (
                PortalAccess.objects.filter(pk=access_id).values_list("user_id", flat=True).first()
            )
            payload = {
                "v": 1,
                "t": "info",
                "access": access_id,
                "expense": claim.pk,
                "title": title[:200],
                "text": text[:300],
            }
            if user_id and send_to_user(user_id, payload) > 0:
                return 1
        address = email_of(claim.membership)
        url = f"{base_url(org)}/mein-bereich/auslagen/{claim.pk}"
        first = claim.membership.person.first_name
    else:
        address = claim.email
        url = ""
        first = claim.name
    if not address:
        return 0
    with language_of_org(org):
        lines = [_("Hallo {name},").format(name=first), "", text, ""]
        if claim.purpose:
            lines += [_("Zweck: {purpose}").format(purpose=claim.purpose), ""]
        if url:
            lines += [_("Zur Auslage: {url}").format(url=url), ""]
        lines.append(org.name)
    return int(
        mail.send(
            address,
            title,
            "\n".join(lines) + "\n",
            organization=org,
            kind="auslage",
            fail_silently=True,
        )
    )


def reviewers(claim: ExpenseClaim) -> list[tuple[str, int | None]]:
    """(Mail, Mitgliedschaft) der Personen, die jetzt handeln: Leitung der Untereinheit oder
    die Kasse."""
    from access.catalog import effective, effective_for
    from access.models import RoleAssignment

    org = claim.organization
    out: dict[str, int | None] = {}
    unit = services.confirm_unit(claim) if claim.status == ExpenseClaim.Status.SUBMITTED else None
    if unit is not None:
        from events.rsvp import email_of
        from members.models import DepartmentRoleHolder

        on_ids = [n.pk for n in unit.ancestors() if n.type == "unit"]
        holders = (
            DepartmentRoleHolder.objects.active()
            .filter(
                role__department_id__in=on_ids,
            )
            .select_related("role", "membership__person", "membership__organization")
        )
        for holder in holders:
            if services.EDIT not in effective_for(holder.role.permissions, org, dept=True):
                continue
            if holder.membership_id == claim.membership_id:
                continue
            address = email_of(holder.membership)
            if address:
                out[address] = holder.membership_id
        return list(out.items())
    for assignment in (
        RoleAssignment.objects.active()
        .filter(organization=org, user__isnull=False, user__is_active=True)
        .select_related("role", "user")
    ):
        if services.EDIT not in effective(assignment.role.permissions or []):
            continue
        if assignment.user_id in (claim.user_id, claim.created_by_id):
            continue
        if assignment.user.email:
            out[assignment.user.email.lower()] = None
    return list(out.items())


def _to_reviewers(claim: ExpenseClaim, what: str) -> int:
    from organizations.addresses import base_url

    org = claim.organization
    sent = 0
    unit = services.confirm_unit(claim) if claim.status == ExpenseClaim.Status.SUBMITTED else None
    for address, _membership in reviewers(claim):
        with language_of_org(org):
            if unit is not None:
                title = _("Auslage {number} bitte bestätigen").format(number=claim.number)
                url = f"{base_url(org)}/auslagen"
            else:
                title = _("Neue Auslage {number} zu prüfen").format(number=claim.number)
                url = f"{base_url(org)}/finanzen/auslagen/{claim.pk}"
            body = "\n".join(
                [
                    _("Hallo,"),
                    "",
                    _("{name} hat eine Auslage über {amount} € eingereicht:").format(
                        name=services.person_name(claim), amount=services.comma(claim.total)
                    ),
                    claim.purpose,
                    "",
                    _("Zur Prüfung: {url}").format(url=url),
                    "",
                    org.name,
                ]
            )
        sent += int(
            mail.send(
                address, title, body + "\n", organization=org, kind="auslage", fail_silently=True
            )
        )
    return sent


def send(claim_id: int, what: str) -> int:
    with rls_bypass():
        claim = (
            ExpenseClaim.objects.select_related("organization", "membership__person", "department")
            .prefetch_related("lines")
            .filter(pk=claim_id)
            .first()
        )
        if claim is None:
            return 0
        if what in TO_MEMBER:
            return _to_member(claim, what)
        if what in ("submitted", "confirmed"):
            return _to_reviewers(claim, what)
    return 0
