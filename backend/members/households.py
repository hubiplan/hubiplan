"""Haushalte und Firmen (Konzept Familien, Haushalte und Firmen, H1).

Ein Haushalt verbindet mehrere Mitgliedschaften eines Vereins. Die Zugehörigkeit hat
einen Zeitraum (``HouseholdMember``); beendet wird sie mit einem Bis-Datum, nicht durch
Überschreiben. Eine Mitgliedschaft gehört gleichzeitig zu höchstens einem Familienhaushalt
und höchstens einer Firma.
"""

from __future__ import annotations

import datetime
import unicodedata

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext
from rest_framework import serializers

from .models import Gender, Household, HouseholdMember, Membership, PersonKind, today


def open_on(on: datetime.date) -> Q:
    return Q(valid_from__lte=on) & (Q(valid_until__isnull=True) | Q(valid_until__gte=on))


def current_links(membership_ids, on: datetime.date | None = None, kind: str | None = None):
    """Aktuelle Zugehörigkeiten der Mitgliedschaften (mit Haushalt)."""
    qs = HouseholdMember.objects.filter(membership_id__in=list(membership_ids)).filter(
        open_on(on or today())
    )
    if kind:
        qs = qs.filter(kind=kind)
    return qs.select_related("household")


def households_by_membership(
    membership_ids, on: datetime.date | None = None
) -> dict[int, list[dict]]:
    """Je Mitgliedschaft die aktuellen Haushalte (für Liste, Akte, Rundschreiben)."""
    result: dict[int, list[dict]] = {}
    for link in current_links(membership_ids, on).order_by("kind", "pk"):
        result.setdefault(link.membership_id, []).append(
            {
                "id": link.household_id,
                "name": link.household.name,
                "kind": link.kind,
                "role": link.role,
                "link": link.pk,
                "since": link.valid_from,
            }
        )
    return result


def _is_active(membership: Membership, on: datetime.date) -> bool:
    if membership.purged_at is not None:
        return False
    return (
        membership.periods.filter(entry_date__lte=on)
        .filter(Q(exit_date__isnull=True) | Q(exit_date__gte=on))
        .exists()
        or membership.periods.filter(entry_date__gt=on).exists()
    )


@transaction.atomic
def add_member(
    household: Household,
    membership: Membership,
    *,
    role: str = "",
    valid_from: datetime.date | None = None,
    move: bool = False,
    pays_via: bool = False,
) -> HouseholdMember:
    """Mitgliedschaft in den Haushalt aufnehmen.

    Gehört sie schon zu einem anderen Haushalt derselben Art, gibt es einen Fehler, außer
    ``move``: dann endet die bisherige Zugehörigkeit am Vortag."""
    valid_from = valid_from or today()
    if membership.organization_id != household.organization_id:
        raise serializers.ValidationError(
            {"membership": gettext("Das Mitglied gehört zu einem anderen Verein.")}
        )
    if membership.person.is_organization:
        raise serializers.ValidationError(
            {
                "membership": gettext(
                    "Organisationsmitglieder gehören keinem Haushalt an; "
                    "ihre Ansprechpartner stehen in der Akte."
                )
            }
        )
    if not _is_active(membership, valid_from):
        raise serializers.ValidationError(
            {"membership": gettext("Das Mitglied ist zu diesem Datum kein Mitglied.")}
        )
    if household.kind != Household.Kind.FAMILY:
        role = ""
    elif role not in HouseholdMember.Role.values:
        raise serializers.ValidationError({"role": gettext("Unbekannte Rolle im Haushalt.")})
    Membership.objects.select_for_update().filter(pk=membership.pk).first()
    open_links = HouseholdMember.objects.filter(
        membership=membership, kind=household.kind, valid_until__isnull=True
    ).select_related("household")
    later = HouseholdMember.objects.filter(
        membership=membership, kind=household.kind, valid_until__gte=valid_from
    ).exclude(valid_until__isnull=True)
    if later.exists():
        raise serializers.ValidationError(
            {
                "valid_from": gettext(
                    "Das Mitglied gehörte zu diesem Datum noch zu einem anderen Haushalt. "
                    "Bitte ein späteres Datum wählen."
                )
            }
        )
    for link in open_links:
        if link.household_id == household.pk:
            raise serializers.ValidationError(
                {"membership": gettext("Das Mitglied gehört schon zu diesem Haushalt.")}
            )
        if not move:
            raise serializers.ValidationError(
                {
                    "membership": gettext(
                        "Das Mitglied gehört schon zu „{name}“. Dort zuerst beenden "
                        "oder „wechseln“ wählen."
                    ).format(name=link.household.name),
                    "code": "other_household",
                }
            )
        if link.valid_from >= valid_from:
            raise serializers.ValidationError(
                {
                    "valid_from": gettext(
                        "Der Wechsel muss nach dem Beginn im bisherigen Haushalt liegen."
                    )
                }
            )
        link.valid_until = valid_from - datetime.timedelta(days=1)
        link.save(update_fields=["valid_until"])
    if pays_via:
        check_pays_via(membership)
    return HouseholdMember.objects.create(
        organization_id=household.organization_id,
        household=household,
        membership=membership,
        kind=household.kind,
        role=role,
        valid_from=valid_from,
        pays_via=pays_via,
    )


def check_pays_via(membership: Membership, exclude: int | None = None) -> None:
    """Der Beitrag läuft über höchstens einen Haushalt bzw. eine Firma (H2)."""
    other = (
        HouseholdMember.objects.filter(
            membership=membership, pays_via=True, valid_until__isnull=True
        )
        .exclude(pk=exclude)
        .select_related("household")
        .first()
    )
    if other is not None:
        raise serializers.ValidationError(
            {
                "pays_via": gettext(
                    "Der Beitrag läuft schon über „{name}“. Dort zuerst ausschalten."
                ).format(name=other.household.name)
            }
        )


def end_member(link: HouseholdMember, valid_until: datetime.date) -> HouseholdMember:
    if valid_until < link.valid_from:
        raise serializers.ValidationError(
            {"valid_until": gettext("Das Ende liegt vor dem Beginn.")}
        )
    link.valid_until = valid_until
    link.save(update_fields=["valid_until"])
    return link


# --- Anschriften: Vorschläge und Briefkopf ---


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = text.replace("straße", "str").replace("strasse", "str").replace("str.", "str")
    return " ".join(text.replace(",", " ").split())


def address_key(street: str, postal_code: str, city: str) -> str:
    """Vergleichsschlüssel einer Anschrift (Schreibweisen wie „Str.“/„Straße“ gleich)."""
    if not (street or "").strip() or not (city or "").strip():
        return ""
    return "|".join((_norm(street), _norm(postal_code), _norm(city)))


def suggestions(org, limit: int = 50) -> list[dict]:
    """Aktuelle Mitglieder mit gleicher Anschrift, die noch nicht gemeinsam in einem
    Familienhaushalt sind. Nur Vorschläge; angelegt wird nichts."""
    from .views import member_queryset, member_rows

    members = list(
        member_queryset(org)
        .filter(is_current=True, purged_at__isnull=True, person__kind=PersonKind.PERSON)
        .order_by("pk")
    )
    rows = member_rows(members, org)
    families = {
        link.membership_id: link.household_id
        for link in current_links([m.pk for m in members], kind=Household.Kind.FAMILY)
    }
    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = address_key(row["street"], row["postal_code"], row["city"])
        if key:
            groups.setdefault(key, []).append(row)
    result = []
    for rows_ in groups.values():
        if len(rows_) < 2:
            continue
        homes = {families.get(r["id"]) for r in rows_}
        if len(homes) == 1 and None not in homes:
            continue  # schon alle gemeinsam in einem Haushalt
        first = rows_[0]
        names = sorted({r["last_name"] for r in rows_})
        result.append(
            {
                "name": gettext("Familie {name}").format(name=" / ".join(names)),
                "street": first["street"],
                "postal_code": first["postal_code"],
                "city": first["city"],
                "members": [
                    {
                        "id": r["id"],
                        "first_name": r["first_name"],
                        "last_name": r["last_name"],
                        "birth_date": r["birth_date"],
                        "household": families.get(r["id"]),
                    }
                    for r in rows_
                ],
            }
        )
        if len(result) >= limit:
            break
    return result


def letter_name(people: list[tuple[str, str, str, str]]) -> str:
    """Anschriftzeile für einen gemeinsamen Brief. ``people``: (Titel, Vorname, Name,
    Geschlecht), Erwachsene zuerst.

    Gleicher Nachname: „Familie Erika und Max Muster“, ab vier Personen „Familie Muster“;
    verschiedene Nachnamen: „Frau Erika Muster und Herrn Max Beispiel“. Schreiben des
    Vereins bleiben in der Vereinssprache (docs/uebersetzung.md), daher ohne gettext."""
    from .models import with_title

    if len(people) == 1:
        title, first, last, _ = people[0]
        return with_title(title, first, last)
    last_names = {p[2] for p in people}
    if len(last_names) == 1:
        last = next(iter(last_names))
        if len(people) >= 4:
            return f"Familie {last}"
        firsts = [p[1] for p in people if p[1]]
        if not firsts:
            return f"Familie {last}"
        return f"Familie {and_join(firsts)} {last}"
    parts = []
    for title, first, last, gender in people[:3]:
        name = with_title(title, first, last)
        if gender == Gender.MALE:
            name = f"Herrn {name}"
        elif gender == Gender.FEMALE:
            name = f"Frau {name}"
        parts.append(name)
    if len(people) > 3:
        parts.append("weitere")
    return and_join(parts)


def family_last_name(people: list[tuple[str, str, str, str]]) -> str:
    """Nachname(n) für „Liebe Familie …“: einer bei gleichem Namen, sonst mit „und“."""
    names: list[str] = []
    for p in people:
        if p[2] and p[2] not in names:
            names.append(p[2])
    if len(names) <= 1:
        return names[0] if names else ""
    return and_join(names)


def and_join(parts: list[str]) -> str:
    """„A“, „A und B“, „A, B und C“."""
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return ", ".join(parts[:-1]) + " und " + parts[-1]
