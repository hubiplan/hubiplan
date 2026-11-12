"""Öffentliches Formular: Aufbau für den Browser und Prüfung der Eingaben.

Der Browser holt den Aufbau und schickt den Antrag direkt an HUBIplan (wie das
Kontaktformular der Webseite, Spamschutz aus website/contact.py). Die Webseite selbst
speichert nichts.
"""

from __future__ import annotations

import datetime
import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers

from core.i18n import available, normalize
from members.serializers import OptionalDateField

from . import services
from .models import ApplicationForm

FIELD_STATES = ("required", "optional", "off")
# „family“: Familienantrag, weitere Personen im selben Antrag (Haushalte H6); an = „optional“
FIELD_KEYS = ("phone", "gender", "birth_date", "unit", "entry_wish", "note", "family")
GUARDIAN_LIMIT = 2
FAMILY_LIMIT = 8


class ChallengeKey:
    """Spamschutz des Kontaktformulars mit eigener Kennung je Formular."""

    def __init__(self, form: ApplicationForm):
        self.public_key = f"join:{form.public_key}"


def _text(value, language: str) -> str:
    if isinstance(value, dict):
        return (value.get(language) or value.get("de") or "").strip()
    return str(value or "").strip()


def sepa_state(form: ApplicationForm) -> tuple[str, dict]:
    """Lastschrift im Formular: eingestellt und beim Verein wirklich möglich."""
    org = form.organization
    if form.sepa == ApplicationForm.Sepa.OFF or "billing" not in (org.enabled_modules or []):
        return "off", {}
    from billing import sepa
    from billing.services import settings_for

    cfg = settings_for(org)
    if not (cfg.sepa_enabled and sepa.creditor_id_valid(cfg.creditor_id)):
        return "off", {}
    reference = gettext("wird bei der Aufnahme vergeben")
    return form.sepa, {
        "creditor_id": cfg.creditor_id,
        "text": sepa.mandate_text(org, cfg.creditor_id, reference),
    }


def fee_of(org, member_type) -> str | None:
    from billing.models import FeeRate

    if "billing" not in (org.enabled_modules or []):
        return None
    rate = FeeRate.objects.filter(member_type=member_type).first()
    return f"{rate.amount:.2f}".replace(".", ",") if rate else None


def statute_docs(org, request=None) -> dict:
    """Öffentliche Satzung und Beitragsordnung mit Fassung (Datum) und Link."""
    from django.urls import reverse

    from statutes.models import StatutePublication, StatuteVersion

    result = {}
    for kind in ("statute", "fee_rules"):
        pub = StatutePublication.objects.filter(
            organization=org, department__isnull=True, kind=kind, is_public=True
        ).first()
        version = (
            StatuteVersion.objects.filter(organization=org, department__isnull=True, kind=kind)
            .order_by("-valid_from", "-uploaded_at")
            .first()
        )
        if version is None:
            continue
        url = None
        if pub is not None:
            path = reverse("public-statute", args=[pub.public_key])
            url = request.build_absolute_uri(path) if request is not None else path
        result[kind] = {"url": url, "version": version.valid_from.isoformat()}
    return result


def privacy_text(org) -> str:
    return gettext(
        "{org} verarbeitet deine Angaben, um über deinen Mitgliedsantrag zu entscheiden und "
        "die Mitgliedschaft zu führen (Art. 6 Abs. 1 lit. b DSGVO). Die Daten liegen "
        "verschlüsselt in HUBIplan und sind nur für die zuständigen Personen im Verein "
        "sichtbar. Ohne Bestätigung deiner E-Mail-Adresse wird der Antrag nach 48 Stunden "
        "gelöscht, ein abgelehnter oder zurückgezogener Antrag nach der vom Verein "
        "festgelegten Frist."
    ).format(org=org.name)


def confirmations(form: ApplicationForm, request=None) -> list[dict]:
    org = form.organization
    docs = statute_docs(org, request)
    items = []
    if form.confirm_statute and "statute" in docs:
        items.append(
            {
                "key": services.CONFIRM_STATUTE,
                "label": gettext("Ich habe die Satzung gelesen und erkenne sie an."),
                **docs["statute"],
            }
        )
    if form.confirm_fee_rules and "fee_rules" in docs:
        items.append(
            {
                "key": services.CONFIRM_FEE_RULES,
                "label": gettext("Ich habe die Beitragsordnung gelesen und erkenne sie an."),
                **docs["fee_rules"],
            }
        )
    items.append(
        {
            "key": services.CONFIRM_PRIVACY,
            "label": gettext("Ich habe die Datenschutzhinweise gelesen."),
            "text": privacy_text(org),
        }
    )
    return items


def consent_choices(form: ApplicationForm) -> list[dict]:
    from website.models import PublicationConsent

    labels = {
        services.CONSENT_PHOTO: gettext(
            "Der Verein darf Fotos von mir für die Vereinsarbeit verwenden."
        ),
    }
    for value, label in PublicationConsent.Category.choices:
        if value in PublicationConsent.OBJECTION_CATEGORIES:
            continue  # gilt ohnehin bis zum Widerspruch
        labels[value] = gettext("Auf der Webseite darf erscheinen: {what}").format(what=str(label))
    return [{"key": k, "label": labels[k]} for k in form.consents or [] if k in labels]


def allowed_consents() -> list[dict]:
    """Für die Einrichtung: welche freiwilligen Einwilligungen es gibt."""
    from website.models import PublicationConsent

    items = [{"key": services.CONSENT_PHOTO, "label": gettext("Fotos für die Vereinsarbeit")}]
    for value, label in PublicationConsent.Category.choices:
        if value not in PublicationConsent.OBJECTION_CATEGORIES:
            items.append({"key": value, "label": gettext("Webseite: {what}").format(what=label)})
    return items


def type_entries(form: ApplicationForm, language: str) -> list[dict]:
    from members.models import MemberType

    org = form.organization
    known = {t.pk: t for t in MemberType.objects.filter(organization=org, is_archived=False)}
    result = []
    for entry in form.types or []:
        mt = known.get(entry.get("id"))
        if mt is None:
            continue
        result.append(
            {
                "id": mt.pk,
                "label": _text(entry.get("label"), language) or mt.name,
                "text": _text(entry.get("text"), language),
                "fee": fee_of(org, mt),
                "organizations": bool(entry.get("organizations")),
            }
        )
    return result


def units_of(org):
    from organizations.models import Department

    return list(
        Department.objects.filter(organization=org, is_active=True, is_remote=False).order_by(
            "sort_order", "name"
        )
    )


def custom_entries(form: ApplicationForm) -> list:
    from customfields.views import definitions_for

    wanted = [int(i) for i in form.custom_fields or [] if isinstance(i, int)]
    defs = {
        d.pk: d
        for d in definitions_for(form.organization)
        if not d.is_archived and not d.repeatable
    }
    return [defs[i] for i in wanted if i in defs]


def company_of(form: ApplicationForm, token: str):
    """Firma aus dem Link „Mitarbeiter melden“ (Konzept Familien, H5), sonst None."""
    if not token or "billing" not in (form.organization.enabled_modules or []):
        return None
    from billing.company_portal import read_token

    return read_token(form.organization, token)


def schema(form: ApplicationForm, language: str, request=None, unit_hint: str = "") -> dict:
    org = form.organization
    sepa, mandate = sepa_state(form)
    company = company_of(form, request.query_params.get("firma", "")) if request else None
    if company is not None and sepa == "required":
        # Den Beitrag zahlt die Firma: Lastschrift des Mitarbeiters nur freiwillig
        sepa = "offer"
    fields = {k: (form.fields or {}).get(k, "off") for k in FIELD_KEYS}
    units = []
    preselect = None
    if fields["unit"] != "off":
        for u in units_of(org):
            units.append({"id": u.pk, "name": u.name})
            if unit_hint and unit_hint == str(u.pk):
                preselect = u.pk
    return {
        "organization": org.name,
        "language": language,
        "languages": available(),
        "intro": services.text_of(form, "intro", language),
        "thanks": services.text_of(form, "thanks", language),
        "types": type_entries(form, language),
        "fields": fields,
        "units": units,
        "unit": preselect,
        "unit_label": org.department_label or gettext("Untereinheit"),
        "custom_fields": [
            {
                "id": d.pk,
                "label": d.label,
                "type": d.field_type,
                "choices": d.choices or [],
                "help": d.help_text,
            }
            for d in custom_entries(form)
        ],
        "sepa": sepa,
        "mandate": mandate,
        "confirmations": confirmations(form, request),
        "consents": consent_choices(form),
        "signature": form.signature,
        "minors": form.minors,
        "min_age": form.min_age,
        "company": company.name if company is not None else None,
    }


# --- Prüfung ---


class GuardianSerializer(serializers.Serializer):
    last_name = serializers.CharField(max_length=100)
    first_name = serializers.CharField(max_length=100)
    email = serializers.EmailField(max_length=200)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)


class FamilyMemberSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    birth_date = OptionalDateField()
    member_type = serializers.IntegerField(required=False, allow_null=True)


class MandateSerializer(serializers.Serializer):
    holder = serializers.CharField(max_length=70)
    iban = serializers.CharField(max_length=40)
    bic = serializers.CharField(max_length=11, required=False, allow_blank=True)


class SubmitSerializer(serializers.Serializer):
    language = serializers.CharField(max_length=5, required=False, default="de")
    kind = serializers.ChoiceField(choices=["person", "organization"], default="person")
    member_type = serializers.IntegerField()
    last_name = serializers.CharField(max_length=100)
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    birth_date = OptionalDateField()
    adult = serializers.BooleanField(required=False, allow_null=True, default=None)
    gender = serializers.CharField(max_length=10, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=200)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    street = serializers.CharField(max_length=200)
    address_extra = serializers.CharField(max_length=200, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=10)
    city = serializers.CharField(max_length=100)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    unit = serializers.IntegerField(required=False, allow_null=True)
    entry_wish = OptionalDateField()
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    custom = serializers.DictField(required=False, default=dict)
    mandate = MandateSerializer(required=False, allow_null=True)
    confirmations = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False, default=list
    )
    consents = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False, default=list
    )
    guardians = GuardianSerializer(many=True, required=False, default=list)
    # Familienantrag (H6): weitere Personen mit gleicher Anschrift
    family = FamilyMemberSerializer(many=True, required=False, default=list)
    signature = serializers.JSONField(required=False, allow_null=True)
    # Spamschutz (nicht im Stand-Modus)
    homepage = serializers.CharField(max_length=200, required=False, allow_blank=True)
    challenge = serializers.CharField(max_length=500, required=False, allow_blank=True)
    nonce = serializers.IntegerField(min_value=0, required=False)
    # Link „Mitarbeiter melden“: Firma, die den Beitrag zahlt (H5)
    company = serializers.CharField(max_length=500, required=False, allow_blank=True)


def age_on(birth: datetime.date, on: datetime.date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def clean_submission(form: ApplicationForm, v: dict, *, kiosk: bool = False) -> dict:
    """Prüft einen Antrag gegen die Einstellungen; gibt die Werte für ``services.create``."""
    from django.core.exceptions import ValidationError as DjValidationError

    from finance import signature as signature_mod
    from members.models import Gender, MemberType

    org = form.organization
    errors: dict = {}
    language = normalize(v.get("language"))
    types = {t["id"]: t for t in type_entries(form, language)}
    entry = types.get(v["member_type"])
    member_type = None
    if entry is None:
        errors["member_type"] = gettext("Bitte eine Mitgliedsart wählen.")
    else:
        member_type = MemberType.objects.get(pk=entry["id"])
    kind = v["kind"]
    if kind == "organization" and entry is not None and not entry["organizations"]:
        errors["kind"] = gettext("Diese Mitgliedsart können nur Personen beantragen.")
    fields = {k: (form.fields or {}).get(k, "off") for k in FIELD_KEYS}
    person = kind == "person"
    data = {
        "last_name": v["last_name"].strip(),
        "first_name": (v.get("first_name") or "").strip() if person else "",
        "email": v["email"].strip().lower(),
        "street": v["street"].strip(),
        "address_extra": (v.get("address_extra") or "").strip(),
        "postal_code": v["postal_code"].strip(),
        "city": v["city"].strip(),
        "country": (v.get("country") or "").strip() or "Deutschland",
    }
    if person and not data["first_name"]:
        errors["first_name"] = gettext("Pflichtfeld.")
    if not re.fullmatch(r"[0-9A-Za-z \-]{3,10}", data["postal_code"]):
        errors["postal_code"] = gettext("Bitte eine gültige Postleitzahl angeben.")

    def optional(key: str, value):
        state = fields.get(key, "off")
        if state == "off":
            return None
        if state == "required" and value in (None, ""):
            errors[key] = gettext("Pflichtfeld.")
        return value

    phone = optional("phone", (v.get("phone") or "").strip())
    if phone:
        data["phone"] = phone
    if person:
        gender = optional("gender", v.get("gender") or "")
        if gender:
            if gender not in Gender.values:
                errors["gender"] = gettext("Ungültige Angabe.")
            data["gender"] = gender
        birth = optional("birth_date", v.get("birth_date"))
        today = timezone.localdate()
        if birth:
            if birth > today or birth.year < today.year - 120:
                errors["birth_date"] = gettext("Bitte das Geburtsdatum prüfen.")
            data["birth_date"] = birth.isoformat()
    note = optional("note", (v.get("note") or "").strip())
    if note:
        data["note"] = note
    unit = None
    unit_id = optional("unit", v.get("unit"))
    if unit_id:
        unit = next((u for u in units_of(org) if u.pk == unit_id), None)
        if unit is None:
            errors["unit"] = gettext("Bitte neu wählen.")
    entry_wish = optional("entry_wish", v.get("entry_wish"))

    # Minderjährige (B3)
    guardians = list(v.get("guardians") or [])
    minor = False
    if person:
        if data.get("birth_date"):
            age = age_on(datetime.date.fromisoformat(data["birth_date"]), timezone.localdate())
            minor = age < 18
            if form.min_age and age < form.min_age:
                errors["birth_date"] = gettext(
                    "Eine Mitgliedschaft ist erst ab {age} Jahren möglich."
                ).format(age=form.min_age)
        elif v.get("adult") is False:
            minor = True
        elif v.get("adult") is None and fields["birth_date"] == "off":
            errors["adult"] = gettext("Bitte angeben, ob du volljährig bist.")
    if minor:
        if not form.minors:
            errors["birth_date"] = gettext("Online können nur Volljährige beantragen.")
        elif not guardians:
            errors["guardians"] = gettext("Bitte einen Erziehungsberechtigten angeben.")
    else:
        guardians = []
    guardians = [
        {k: (g.get(k) or "").strip() for k in ("last_name", "first_name", "email", "phone")}
        for g in guardians[:GUARDIAN_LIMIT]
    ]

    # Familienantrag (H6)
    family = _clean_family(form, v, data, types, fields, person, minor, errors, language)
    if family:
        data["family"] = family

    # Zusatzfelder (B5)
    custom_values, custom_labels = {}, {}
    defs = {str(d.pk): d for d in custom_entries(form)}
    raw = v.get("custom") or {}
    from customfields.models import clean_value

    for def_id, value in raw.items():
        d = defs.get(str(def_id))
        if d is None or value in ("", None):
            continue
        try:
            clean = clean_value(d, value)
        except DjangoValidationError as exc:
            errors[f"custom_{def_id}"] = " ".join(exc.messages)
            continue
        custom_values[str(d.pk)] = clean
        custom_labels[d.label] = str(clean)
    if custom_values:
        data["custom_values"] = custom_values
        data["custom"] = custom_labels

    # Lastschrift (B2)
    sepa, mandate_info = sepa_state(form)
    company = company_of(form, v.get("company") or "")
    if v.get("company") and company is None:
        errors["company"] = gettext(
            "Der Link der Firma ist abgelaufen. Bitte bei der Firma einen neuen anfordern."
        )
    if company is not None:
        data["company_household"] = company.pk
        data["company_name"] = company.name
        if sepa == "required":
            sepa = "offer"
    mandate = {}
    given = v.get("mandate")
    if sepa == "required" and not given:
        errors["mandate"] = gettext("Bitte die Bankverbindung für die Lastschrift angeben.")
    if given and sepa != "off":
        from billing import sepa as sepa_mod

        try:
            clean = sepa_mod.validate_mandate_data(
                given.get("holder", ""), given.get("iban", ""), given.get("bic", "")
            )
            mandate = {**clean, "text": mandate_info.get("text", "")}
        except DjValidationError as exc:
            errors["mandate"] = exc.message_dict

    # Bestätigungen und Einwilligungen
    now = timezone.now().isoformat()
    consents = []
    given_confirms = set(v.get("confirmations") or [])
    required = confirmations(form)
    if minor:
        required.append(
            {
                "key": services.CONFIRM_GUARDIAN,
                "label": gettext(
                    "Ich bin erziehungsberechtigt und stimme dem Antrag zu (bei zwei "
                    "Erziehungsberechtigten mit Einverständnis des anderen)."
                ),
            }
        )
    if mandate:
        required.append(
            {"key": services.CONFIRM_MANDATE, "label": gettext("Ich erteile das SEPA-Mandat.")}
        )
    for item in required:
        if item["key"] not in given_confirms:
            errors.setdefault("confirmations", {})[item["key"]] = gettext("Bitte bestätigen.")
            continue
        consents.append(
            {
                "key": item["key"],
                "label": item["label"],
                "text": item.get("text")
                or (mandate.get("text") if item["key"] == "mandate" else ""),
                "version": item.get("version", ""),
                "at": now,
                "given": True,
                "required": True,
            }
        )
    offered = {c["key"]: c["label"] for c in consent_choices(form)}
    for key in v.get("consents") or []:
        if key in offered:
            consents.append(
                {"key": key, "label": offered[key], "at": now, "given": True, "required": False}
            )

    # Unterschrift
    signature = {}
    if v.get("signature"):
        try:
            signature = signature_mod.normalize(v["signature"])
        except DjValidationError as exc:
            errors["signature"] = exc.messages
    elif kiosk and form.signature == ApplicationForm.Signature.REQUIRED:
        errors["signature"] = gettext("Bitte unterschreiben.")

    if errors:
        raise serializers.ValidationError(errors)
    return {
        "language": language,
        "kind": kind,
        "data": data,
        "member_type": member_type,
        "unit": unit,
        "entry_wish": entry_wish,
        "mandate": mandate,
        "consents": consents,
        "guardians": guardians,
        "signature": signature,
    }


def _clean_family(form, v, data, types, fields, person, minor, errors, language) -> list[dict]:
    """Weitere Personen des Familienantrags: Vorname Pflicht, Name wie beim Antragsteller,
    Geburtsdatum wie im Formular eingestellt, Mitgliedsart aus den angebotenen."""
    given = list(v.get("family") or [])
    if not given or not person or fields.get("family", "off") == "off":
        return []
    if minor:
        errors["family"] = gettext(
            "Weitere Familienmitglieder kann nur eine volljährige Person mit beantragen."
        )
        return []
    if len(given) > FAMILY_LIMIT:
        errors["family"] = gettext("Höchstens {n} weitere Personen.").format(n=FAMILY_LIMIT)
        return []
    today = timezone.localdate()
    out, problems = [], {}
    for i, f in enumerate(given):
        row = {
            "first_name": (f.get("first_name") or "").strip(),
            "last_name": (f.get("last_name") or "").strip() or data["last_name"],
        }
        issue = {}
        if not row["first_name"]:
            issue["first_name"] = gettext("Pflichtfeld.")
        entry = types.get(f.get("member_type") or v["member_type"])
        if entry is None:
            issue["member_type"] = gettext("Bitte eine Mitgliedsart wählen.")
        else:
            row["member_type"] = entry["id"]
            row["member_type_label"] = entry["label"]
        birth = f.get("birth_date") if fields.get("birth_date", "off") != "off" else None
        if fields.get("birth_date") == "required" and not birth:
            issue["birth_date"] = gettext("Pflichtfeld.")
        if birth:
            if birth > today or birth.year < today.year - 120:
                issue["birth_date"] = gettext("Bitte das Geburtsdatum prüfen.")
            elif form.min_age and age_on(birth, today) < form.min_age:
                issue["birth_date"] = gettext(
                    "Eine Mitgliedschaft ist erst ab {age} Jahren möglich."
                ).format(age=form.min_age)
            elif not form.minors and age_on(birth, today) < 18:
                issue["birth_date"] = gettext("Online können nur Volljährige beantragen.")
            row["birth_date"] = birth.isoformat()
        if issue:
            problems[str(i)] = issue
        out.append(row)
    if problems:
        errors["family"] = problems
    return out


def clean_settings(form: ApplicationForm, payload: dict) -> dict:
    """Einstellungen aus der Einrichtung prüfen (nur bekannte Schlüssel)."""
    from members.models import MemberType

    from . import rules

    org = form.organization
    errors: dict = {}
    out: dict = {}
    if "enabled" in payload:
        out["enabled"] = bool(payload["enabled"])
    if "types" in payload:
        known = set(
            MemberType.objects.filter(organization=org, is_archived=False).values_list(
                "pk", flat=True
            )
        )
        items = []
        for t in payload["types"] or []:
            if not isinstance(t, dict) or t.get("id") not in known:
                errors["types"] = gettext("Unbekannte Mitgliedsart.")
                break
            items.append(
                {
                    "id": t["id"],
                    "label": _lang_dict(t.get("label")),
                    "text": _lang_dict(t.get("text"), 500),
                    "organizations": bool(t.get("organizations")),
                }
            )
        out["types"] = items
    if "fields" in payload:
        raw = payload["fields"] or {}
        out["fields"] = {k: raw.get(k) if raw.get(k) in FIELD_STATES else "off" for k in FIELD_KEYS}
    if "custom_fields" in payload:
        from customfields.views import definitions_for

        known = {d.pk for d in definitions_for(org) if not d.repeatable}
        ids = [i for i in payload["custom_fields"] or [] if isinstance(i, int) and i in known]
        out["custom_fields"] = list(dict.fromkeys(ids))
    for key in ("sepa", "signature", "entry_date"):
        if key in payload:
            choices = {
                "sepa": ApplicationForm.Sepa.values,
                "signature": ApplicationForm.Signature.values,
                "entry_date": ApplicationForm.EntryDate.values,
            }[key]
            if payload[key] not in choices:
                errors[key] = gettext("Ungültige Auswahl.")
            else:
                out[key] = payload[key]
    for key in ("confirm_statute", "confirm_fee_rules", "minors"):
        if key in payload:
            out[key] = bool(payload[key])
    if "consents" in payload:
        keys = {c["key"] for c in allowed_consents()}
        out["consents"] = list(dict.fromkeys(k for k in payload["consents"] or [] if k in keys))
    if "texts" in payload:
        raw = payload["texts"] or {}
        out["texts"] = {
            k: _lang_dict(raw.get(k), 3000) for k in ("intro", "thanks", "welcome", "rejection")
        }
    if "notify_roles" in payload:
        from access.models import Role

        known = set(Role.objects.filter(organization=org).values_list("pk", flat=True))
        out["notify_roles"] = [i for i in payload["notify_roles"] or [] if i in known]
    if "rule" in payload:
        out["rule"] = rules.clean_rule(payload["rule"], org)
    if "purge_months" in payload:
        n = payload["purge_months"]
        if not isinstance(n, int) or not 1 <= n <= 36:
            errors["purge_months"] = gettext("Zwischen 1 und 36 Monaten.")
        else:
            out["purge_months"] = n
    if "min_age" in payload:
        n = payload["min_age"]
        if n in (None, ""):
            out["min_age"] = None
        elif not isinstance(n, int) or not 0 <= n <= 99:
            errors["min_age"] = gettext("Bitte ein Alter zwischen 0 und 99 angeben.")
        else:
            out["min_age"] = n
    if errors:
        raise serializers.ValidationError(errors)
    return out


def _lang_dict(value, limit: int = 100) -> dict:
    if isinstance(value, str):
        value = {"de": value}
    if not isinstance(value, dict):
        return {}
    return {
        lang: str(value.get(lang) or "").strip()[:limit]
        for lang in available()
        if str(value.get(lang) or "").strip()
    }
