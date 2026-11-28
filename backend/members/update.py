"""Stammdaten einer Mitgliedschaft ändern (Name, Geburtsdatum, Nummer, Kontakt) samt Protokoll.

Der Aufrufer hat Rechte geprüft, die Mitgliedschaft gesperrt gelesen und klammert den Vorgang
in einer Transaktion (members/views.py, MemberDetailView.patch).
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers

from audit.log import diff, record, snapshot
from organizations.models import Organization
from organizations.terms import fill

from . import services
from .models import (
    Membership,
)
from .serializers import (
    check_birth_before_entries,
)


def update_member(org: Organization, membership: Membership, values: dict, user) -> dict:
    """Ändert Name, Geburtsdatum, Vereinsnummer und Kontakt; schreibt das Protokoll."""
    person = membership.person
    if person.is_organization:
        # Organisationen haben weder Vorname noch Geburtsdatum noch Geschlecht
        fields = ("last_name", *services.ORGANIZATION_FIELDS, "size")
        if "last_name" in values and not values["last_name"].strip():
            raise serializers.ValidationError({"last_name": gettext("Pflichtfeld.")})
    else:
        fields = ("last_name", "first_name", "birth_date", "gender", "title")
        if "birth_date" in values and values["birth_date"] != person.birth_date:
            check_birth_before_entries(person, values["birth_date"])
    before_person = snapshot(person)
    for field in fields:
        if field in values:
            setattr(person, field, values[field])
    if person.birth_date is None:
        person.birth_year_only = False  # ohne Datum auch kein „nur Jahr“
    person.save()
    changes = diff(before_person, snapshot(person))

    if "club_number" in values and values["club_number"] != membership.club_number:
        changes[fill("Mitgliedsnummer {e_im}", membership.organization)] = [
            membership.club_number,
            values["club_number"],
        ]
        membership.club_number = values["club_number"]
        membership.save()

    if "pays_fee_self" in values and values["pays_fee_self"] != membership.pays_fee_self:
        changes["zahlt Beitrag selbst"] = [membership.pays_fee_self, values["pays_fee_self"]]
        membership.pays_fee_self = values["pays_fee_self"]
        membership.save()

    if "info_opt_out" in values and values["info_opt_out"] != (
        membership.info_opt_out_at is not None
    ):
        changes["Informationen per E-Mail"] = (
            ["erhalten", "abbestellt"] if values["info_opt_out"] else ["abbestellt", "erhalten"]
        )
        membership.info_opt_out_at = timezone.now() if values["info_opt_out"] else None
        membership.save()

    if "greetings_opt_out" in values and values["greetings_opt_out"] != (
        membership.greetings_opt_out_at is not None
    ):
        changes["Glückwünsche"] = (
            ["erhalten", "widersprochen"]
            if values["greetings_opt_out"]
            else ["widersprochen", "erhalten"]
        )
        membership.greetings_opt_out_at = timezone.now() if values["greetings_opt_out"] else None
        membership.save()

    contact_values = {k: values[k] for k in services.CONTACT_FIELDS if k in values}
    if contact_values:
        old = services.contact_for(person, org)
        before = snapshot(old) if old else {}
        new = services.save_contact(person, org, contact_values)
        changes.update(diff(before, snapshot(new)))
    changes.pop("Verbandsbereich", None)
    changes.pop("person", None)
    if changes:
        record(org, user, "update", membership, changes, person=person)
    return changes
