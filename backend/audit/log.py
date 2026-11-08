"""Einträge ins Änderungsprotokoll schreiben."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from decimal import Decimal
from typing import Any

from django.db import models
from django.db.models.fields.files import FieldFile
from django.utils import translation
from django.utils.functional import Promise
from django.utils.translation import gettext_noop

from changes.tracking import current_set_id
from core.tenancy import tenant_context

from .models import AuditEntry

# Herkunft der Änderungen dieser Anfrage (Verwaltung in der App setzt „App (Gerät)“)
current_via: ContextVar[str] = ContextVar("hubiplan_audit_via", default="")

IGNORED_FIELDS = {"created_at", "updated_at", "id", "organization", "uuid"}

# Lesbare Namen der protokollierten Objekte
OBJECT_TYPES = {
    "businesspartner": gettext_noop("Geschäftspartner"),
    "incominginvoice": gettext_noop("Rechnungseingang"),
    "invoiceartifact": gettext_noop("E-Rechnungsoriginal"),
    "invoicehybridartifact": gettext_noop("ZUGFeRD-Original"),
    "invoicedelivery": gettext_noop("E-Rechnungsversand"),
    "invoiceadvance": gettext_noop("Anzahlungszuordnung"),
    "todo": gettext_noop("Aufgabe"),
    "organization": gettext_noop("Organisation"),
    "department": gettext_noop("Abteilung"),
    "departmentrole": gettext_noop("Abteilungsrolle"),
    "role": gettext_noop("Rolle"),
    "roleassignment": gettext_noop("Rollenzuordnung"),
    "platformsettings": gettext_noop("Plattform-Einstellungen"),
    "membertype": gettext_noop("Mitgliedsart"),
    "membership": gettext_noop("Mitgliedschaft"),
    "membershipperiod": gettext_noop("Mitgliedszeitraum"),
    "membertypeassignment": gettext_noop("Mitgliedsart-Zuordnung"),
    "departmentmembership": gettext_noop("Abteilungszugehörigkeit"),
    "departmentroleholder": gettext_noop("Abteilungsrolle"),
    "honorarytitle": gettext_noop("Ehrung"),
    "honorarytitleaward": gettext_noop("Ehrung (Verleihung)"),
    "federationmember": gettext_noop("Verbandsmitgliedschaft"),
    "contactdetails": gettext_noop("Kontaktdaten"),
    "person": gettext_noop("Person"),
    "fielddefinition": gettext_noop("Zusatzfeld"),
    "fieldvalue": gettext_noop("Zusatzfeld-Wert"),
    "exportjob": gettext_noop("Export"),
    "exporttemplate": gettext_noop("Exportvorlage"),
    "importjob": gettext_noop("Import"),
    "importtemplate": gettext_noop("Importvorlage"),
    "memberphoto": gettext_noop("Mitgliederfoto"),
    "photouploadlink": gettext_noop("Foto-Upload-Link"),
    "account": gettext_noop("Konto"),
    "category": gettext_noop("Kategorie"),
    "booking": gettext_noop("Buchung"),
    "receipt": gettext_noop("Beleg"),
    "reserve": gettext_noop("Rücklage"),
    "reservemovement": gettext_noop("Rücklagenbewegung"),
    "changerequest": gettext_noop("Datenänderung"),
    "transferjob": gettext_noop("Datenübernahme"),
    "event": gettext_noop("Termin"),
    "eventcategory": gettext_noop("Terminkategorie"),
    "eventexception": gettext_noop("Serientermin"),
    "eventattachment": gettext_noop("Terminanhang"),
    "calendarpublication": gettext_noop("Öffentlicher Kalender"),
    "externalcalendar": gettext_noop("Fremder Kalender"),
    "circular": gettext_noop("Rundschreiben"),
    "circulartemplate": gettext_noop("Vorlage für Rundschreiben"),
    "circularattachment": gettext_noop("Anhang eines Rundschreibens"),
    "website": gettext_noop("Webseite"),
    "designpackage": gettext_noop("Designpaket"),
    "websitedomain": gettext_noop("Domain der Webseite"),
    "previewlink": gettext_noop("Vorschau-Link"),
    "websitetext": gettext_noop("Text der Webseite"),
    "websiteimage": gettext_noop("Bild der Webseite"),
    "heldmessage": gettext_noop("Nachricht von der Webseite"),
    "dignity": gettext_noop("Würde"),
    "reign": gettext_noop("Regentschaft"),
    "companion": gettext_noop("Begleitperson"),
    "reignphoto": gettext_noop("Foto einer Regentschaft"),
}


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, FieldFile):
        return value.name or ""
    if isinstance(value, models.Model):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def snapshot(instance: models.Model) -> dict[str, Any]:
    data = {}
    # Modelle können die protokollierten Felder eingrenzen (z. B. Untereinheiten,
    # die viele Felder der Organisationstabelle nicht nutzen)
    only = getattr(instance, "audit_fields", None)
    for field in instance._meta.concrete_fields:
        if field.attname in getattr(instance, "derived_fields", ()):
            continue
        if field.name in IGNORED_FIELDS or (only is not None and field.name not in only):
            continue
        # Lesbarer deutscher Feldname fürs Protokoll
        data[str(field.verbose_name)] = _plain(getattr(instance, field.attname))
    return data


def type_label(object_type: str) -> str:
    """Lesbarer Name einer protokollierten Objektart; ohne Eintrag in OBJECT_TYPES
    steht der technische Modellname (z. B. „imprint“), dann gilt dessen verbose_name."""
    if object_type in OBJECT_TYPES:
        return OBJECT_TYPES[object_type]
    if object_type.isascii() and object_type.islower():
        from django.apps import apps

        for model in apps.get_models():
            if model._meta.model_name == object_type:
                return str(model._meta.verbose_name)
    return object_type


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        key: [before.get(key), after.get(key)]
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _german(value: Any) -> Any:
    """Übersetzbare Texte (z. B. Auswahl-Beschriftungen) fürs Protokoll auf Deutsch.

    Das Revisionsprotokoll bleibt deutsch (Konzept englisch.md, 4.4) und muss sich als
    JSON speichern lassen.
    """
    if isinstance(value, Promise):
        with translation.override("de"):
            return str(value)
    if isinstance(value, dict):
        return {_german(k): _german(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_german(v) for v in value]
    return value


def record(
    organization,
    user,
    action: str,
    instance: models.Model,
    changes: dict | None = None,
    person=None,
) -> AuditEntry:
    if instance._meta.app_label == "todos":
        if not getattr(instance, "shared", False):
            return None
        # Vereinsprotokoll enthält keine privaten oder lokal ergänzten Aufgabeninhalte.
        changes = {"Aufgabe": {"before": "", "after": action}}
    model = instance._meta.model_name
    # Rollen und Inhaber von Untereinheiten (auch ohne die Sicht DepartmentRole)
    if model == "role" and getattr(instance, "department_id", None):
        model = "departmentrole"
    elif model == "roleassignment" and getattr(instance, "membership_id", None):
        model = "departmentroleholder"
    from .chain import seal_later

    with tenant_context(organization.pk):
        entry = AuditEntry.objects.create(
            organization=organization,
            user=user if user and user.is_authenticated else None,
            user_email=getattr(user, "email", "") or "",
            action=action,
            object_type=OBJECT_TYPES.get(model, model),
            object_id=str(instance.pk),
            object_repr=("Aufgabe" if instance._meta.app_label == "todos" else str(instance))[:200],
            changes=_german(changes or {}),
            person_id=getattr(person, "pk", None),
            change_set=current_set_id(),
            via=current_via.get()[:100],
        )
        seal_later(organization.pk)
        return entry
