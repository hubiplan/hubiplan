"""Beiträge über Haushalt oder Firma (Konzept Familien, Haushalte und Firmen, H2/H3).

Ein Mitglied, dessen Haushalts- oder Firmenzugehörigkeit „Beitrag über den Haushalt“
trägt, erscheint im Beitragslauf nicht mit eigener Rechnung, sondern als Posten der
Rechnung an den Zahler des Haushalts (``HouseholdPayer``). Ohne Zahler bleibt alles wie
bisher; die Prüfliste nennt solche Mitglieder.

Der Familien- bzw. Firmenbeitrag (``HouseholdFeeRule``) wirkt auf die Summe der
Einzelbeiträge einer solchen Rechnung als eigener Abzugsposten. Die Einzelbeiträge
bleiben sichtbar (Nachvollziehbarkeit, Spendenquittung, Austritt mitten im Jahr).
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from members.models import Household, HouseholdMember

from .models import ZERO, HouseholdFeeRule, HouseholdPayer

CENT = Decimal("0.01")
HUNDRED = Decimal(100)


def payer_of(household) -> HouseholdPayer | None:
    """Zahler des Haushalts, nur wenn er wirklich jemanden bezeichnet."""
    payer = HouseholdPayer.objects.filter(household=household).first()
    return payer if payer_ready(payer) else None


def payer_ready(payer: HouseholdPayer | None) -> bool:
    if payer is None:
        return False
    if payer.kind in (HouseholdPayer.Kind.MEMBER, HouseholdPayer.Kind.ORGANIZATION):
        return payer.membership_id is not None
    if payer.kind == HouseholdPayer.Kind.PARTNER:
        return payer.partner_id is not None
    return bool(payer.name.strip())


def paying_links(org, membership_ids) -> dict[int, list[HouseholdMember]]:
    """Je Mitgliedschaft die Zugehörigkeiten mit „Beitrag über den Haushalt“ (alle
    Zeiträume; der Beitragslauf wählt die zum Stichtag)."""
    result: dict[int, list[HouseholdMember]] = {}
    for link in HouseholdMember.objects.filter(
        organization=org, membership_id__in=list(membership_ids), pays_via=True
    ).select_related("household"):
        result.setdefault(link.membership_id, []).append(link)
    return result


def payers_for(org) -> dict[int, HouseholdPayer]:
    """Haushalte des Vereins mit brauchbarem Zahler: Haushalt -> Zahler."""
    return {
        p.household_id: p
        for p in HouseholdPayer.objects.filter(organization=org).select_related(
            "membership__person", "partner"
        )
        if payer_ready(p)
    }


def link_on(links: list[HouseholdMember], on: datetime.date) -> HouseholdMember | None:
    for link in links:
        if link.valid_from <= on and (link.valid_until is None or link.valid_until >= on):
            return link
    return None


def household_recipient(org, household: Household, payer: HouseholdPayer | None = None) -> dict:
    """Empfänger der Haushalts- bzw. Firmenrechnung."""
    from .services import _address, member_recipient

    payer = payer or payer_of(household)
    empty = {
        "recipient_name": household.name,
        "recipient_address": "",
        "recipient_email": "",
        "order_reference": "",
        "leitweg_id": "",
    }
    if payer is None:
        return empty
    if payer.kind in (HouseholdPayer.Kind.MEMBER, HouseholdPayer.Kind.ORGANIZATION):
        data = member_recipient(org, payer.membership)
    elif payer.kind == HouseholdPayer.Kind.PARTNER:
        details = payer.partner.details or {}
        data = {
            "recipient_name": payer.partner.name,
            "recipient_email": details.get("email", ""),
            "recipient_address": "\n".join(
                line
                for line in (
                    details.get("street", ""),
                    f"{details.get('postcode', '')} {details.get('city', '')}".strip(),
                    details.get("country", ""),
                )
                if line
            ),
            "order_reference": "",
            "leitweg_id": details.get("leitweg_id", ""),
        }
    else:
        data = {
            "recipient_name": payer.name.strip(),
            "recipient_address": _address(payer),
            "recipient_email": payer.email,
            "order_reference": "",
            "leitweg_id": "",
        }
    # Angaben am Zahler gehen vor (z. Hd., Bestellnummer, Leitweg-ID der Firma)
    if payer.kind != HouseholdPayer.Kind.EXTERNAL and payer.attention.strip():
        first = data["recipient_name"].split("\n")[0]
        data["recipient_name"] = f"{first}\n{payer.attention.strip()}"
    elif payer.kind == HouseholdPayer.Kind.EXTERNAL and payer.attention.strip():
        data["recipient_name"] = f"{data['recipient_name']}\n{payer.attention.strip()}"
    if payer.kind != HouseholdPayer.Kind.EXTERNAL and payer.email:
        data["recipient_email"] = payer.email
    if payer.order_reference:
        data["order_reference"] = payer.order_reference
    if payer.leitweg_id:
        data["leitweg_id"] = payer.leitweg_id
    return data


def rules_for(org) -> dict[str, HouseholdFeeRule]:
    return {r.kind: r for r in HouseholdFeeRule.objects.filter(organization=org)}


def _share(yearly: Decimal, p) -> Decimal:
    from .services import rate_share

    return rate_share(yearly, p)


def fee_discount(rule: HouseholdFeeRule | None, items, p) -> tuple[Decimal, str]:
    """Abzug (positiv) und Beschreibung für die Posten einer Haushaltsrechnung.

    ``items``: FeeItem mit ``household_role``. Beträge der Regel sind Jahresbeträge und
    werden wie Beiträge auf den Zeitraum verteilt."""
    if rule is None or rule.mode == HouseholdFeeRule.Mode.NONE:
        return ZERO, ""
    counted = list(items)
    if len(counted) < max(rule.min_persons, 1):
        return ZERO, ""
    if rule.adult_required and not any(i.household_role == "adult" for i in counted):
        return ZERO, ""
    total = sum((i.amount for i in counted), ZERO)
    discount = ZERO
    if rule.mode in (HouseholdFeeRule.Mode.CAP, HouseholdFeeRule.Mode.FLAT):
        if rule.amount is None:
            return ZERO, ""
        limit = _share(rule.amount, p)
        discount = max(total - limit, ZERO)
        label = "Höchstbetrag" if rule.mode == HouseholdFeeRule.Mode.CAP else "Pauschale"
        detail = f"{label} {_euro(rule.amount)} je Jahr"
    else:
        # teuerste Beiträge zuerst voll, dann ermäßigt
        ordered_items = sorted(counted, key=lambda i: i.amount, reverse=True)
        for n, item in enumerate(ordered_items):
            pct = ZERO if n == 0 else rule.second_percent if n == 1 else rule.third_percent
            discount += (item.amount * pct / HUNDRED).quantize(CENT, ROUND_HALF_UP)
        parts = []
        if rule.second_percent:
            parts.append(f"2. Person −{_pct(rule.second_percent)} %")
        if rule.third_percent:
            parts.append(f"ab 3. Person −{_pct(rule.third_percent)} %")
        detail = ", ".join(parts)
    discount = min(discount.quantize(CENT, ROUND_HALF_UP), total)
    return (discount if discount > 0 else ZERO), detail


def discount_text(kind: str) -> str:
    # Rechnungstext in Vereinssprache (Deutsch), wie die übrigen Beitragsposten
    return "Firmenbeitrag" if kind == Household.Kind.COMPANY else "Familienbeitrag"


def _euro(value: Decimal) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def _pct(value: Decimal) -> str:
    text = f"{value.normalize():f}"
    return text.replace(".", ",")
