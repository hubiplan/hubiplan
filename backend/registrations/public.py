"""Öffentliche Anmeldung für Nichtmitglieder (Stufe A4).

Ein öffentlicher Termin mit „Öffentliche Anmeldung“ hat ein Formular unter
``/anmeldung/<public_key>``. Wer es abschickt, bekommt eine Mail mit Bestätigungslink (24
Stunden gültig); erst mit dem Klick entsteht die Anmeldung mit Platz und Rechnung (Fachfrage
F2). Spamschutz wie beim Kontaktformular und beim Online-Antrag: Rechenaufgabe, Honigtopf,
Grenze je IP und Einheit.

Danach führt ein signierter Link („Anmeldung ansehen“) zur eigenen Anmeldung: Stand,
Rechnung, Abmelden nach der Stornoregel. Er erlischt mit der Löschfrist (F12).
"""

from __future__ import annotations

import datetime
import hashlib
import secrets

from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from core.tenancy import rls_bypass

from . import extras as ex
from . import services
from .models import PendingRegistration, PriceOption, Registration, RegistrationSetup

CONFIRM_HOURS = 24
LINK_SALT = "registrations.public.link"
MAX_PENDING = 3  # unbestätigte Anmeldungen je E-Mail-Adresse und Termin


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ChallengeKey:
    """Spamschutz mit eigener Kennung je Anmeldung (wie beim Online-Antrag)."""

    def __init__(self, setup: RegistrationSetup):
        self.public_key = f"registration:{setup.public_key}"


def public_allowed(setup: RegistrationSetup) -> bool:
    """Öffentlich nur bei öffentlichen, nicht abgesagten Terminen einer aktiven Einheit."""
    from events.models import Event

    event = setup.event
    return (
        setup.public
        and bool(setup.public_key)
        and event.visibility == Event.Visibility.PUBLIC
        and setup.organization.is_active
        and services.module_on(setup.organization)
    )


def ensure_key(setup: RegistrationSetup) -> None:
    if setup.public and not setup.public_key:
        setup.public_key = secrets.token_urlsafe(12)


def form_url(setup: RegistrationSetup) -> str | None:
    if not setup.public or not setup.public_key:
        return None
    from organizations.addresses import base_url

    return f"{base_url(setup.organization)}/anmeldung/{setup.public_key}"


def setup_by_key(key: str) -> RegistrationSetup | None:
    if not key or len(key) > 40:
        return None
    with rls_bypass():
        setup = (
            RegistrationSetup.objects.select_related("organization", "event")
            .filter(public_key=key)
            .first()
        )
    if setup is None or not public_allowed(setup):
        return None
    return setup


def guest_prices(offer: dict) -> list[dict]:
    """Tarife, die Nichtmitglieder buchen können."""
    return [p for p in offer["prices"] if p.get("applies") != PriceOption.Applies.MEMBERS]


def schema(setup: RegistrationSetup, request=None) -> dict:
    """Alles, was das öffentliche Formular zeigt: Termin, Tarife, Fragen, Regeln."""
    from admission.public import _club_frame

    event = setup.event
    org = setup.organization
    offer = services.offer_data(setup)
    offer["prices"] = guest_prices(offer)
    # Nichts aus der Verwaltung nach außen
    for field in ("category", "taken", "due_days", "is_open", "expire_unpaid_days"):
        offer.pop(field, None)
    return {
        "organization": org.name,
        **_club_frame(org, request),
        "privacy_text": privacy_text(org),
        "event": {
            "id": event.pk,
            "title": event.title,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "all_day": event.all_day,
            "location": event.location,
            "address": event.address,
            "directions": event.directions,
            "description": event.description,
            "programme": event.programme,
        },
        "offer": offer,
        "cancel_text": cancel_text(setup),
    }


def privacy_text(org) -> str:
    return gettext(
        "{org} verarbeitet deine Angaben, um die Anmeldung durchzuführen und abzurechnen "
        "(Art. 6 Abs. 1 lit. b DSGVO). Die Daten liegen verschlüsselt in HUBIplan und sind nur "
        "für die zuständigen Personen im Verein sichtbar. Ohne Bestätigung deiner E-Mail-Adresse "
        "wird die Anmeldung nach 24 Stunden gelöscht; sonst werden die Angaben ein halbes Jahr "
        "nach der Veranstaltung gelöscht, Rechnungen nach den gesetzlichen Fristen."
    ).format(org=org.name)


def cancel_text(setup: RegistrationSetup) -> str:
    """Abmelderegel in Klartext: „Bis 1. Mai kostenfrei abmelden, danach …“."""
    from core.i18n import date_text

    rules = services.rules_of(setup)
    start = services.first_day(setup)
    if not rules and not setup.cancel_fee_fixed:
        return gettext("Abmelden ist bis zum Anmeldeschluss kostenfrei möglich.")
    parts = []
    for rule in rules:
        day = start - datetime.timedelta(days=rule["days"])
        parts.append(
            gettext("ab {date}: {percent} % der Gebühr").format(
                date=date_text(day), percent=rule["percent"]
            )
        )
    text = (
        gettext("Stornogebühren beim Abmelden: {rules}.").format(rules="; ".join(parts))
        if (parts)
        else ""
    )
    if setup.cancel_fee_fixed:
        fee = gettext("Bearbeitungsgebühr {amount} €").format(
            amount=f"{setup.cancel_fee_fixed:.2f}".replace(".", ",")
        )
        text = f"{text} {fee}.".strip()
    return text


# --- Eingaben ---


class GuardianIn(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    email = serializers.CharField(max_length=254, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class PersonIn(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    price_id = serializers.IntegerField()
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    addons = serializers.DictField(required=False, default=dict)
    answers = serializers.DictField(required=False, default=dict)
    health = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    guardians = GuardianIn(many=True, required=False, default=list)


class SubmitIn(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    persons = PersonIn(many=True)
    addons = serializers.DictField(required=False, default=dict)
    answers = serializers.DictField(required=False, default=dict)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    terms_accepted = serializers.BooleanField(required=False, default=False)
    privacy_accepted = serializers.BooleanField(required=False, default=False)
    health_consent = serializers.BooleanField(required=False, default=False)
    language = serializers.CharField(max_length=8, required=False, allow_blank=True, default="")
    challenge = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    nonce = serializers.IntegerField(required=False, allow_null=True, default=None)
    # Honigtopf: Menschen sehen das Feld nicht
    homepage = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


def _ids(raw: dict) -> dict[int, int]:
    result = {}
    for key, value in (raw or {}).items():
        if value in (None, "", 0):
            continue  # „nicht gewünscht“
        try:
            result[int(key)] = int(value)
        except (TypeError, ValueError):
            raise ValidationError(gettext("Bitte eine gültige Auswahl treffen.")) from None
    return result


def stored(v: dict) -> dict:
    """Formularangaben so, wie sie bis zur Bestätigung liegen (JSON)."""
    return {
        "name": v["name"].strip(),
        "email": v["email"].strip(),
        "phone": v["phone"].strip(),
        "address": v["address"].strip(),
        "persons": [
            {
                "name": p["name"].strip(),
                "price_id": p["price_id"],
                "birth_date": p["birth_date"].isoformat() if p["birth_date"] else None,
                "addons": {str(k): val for k, val in _ids(p["addons"]).items()},
                "answers": dict(p["answers"]),
                "health": p["health"],
                "guardians": [dict(g) for g in p["guardians"]],
            }
            for p in v["persons"]
        ],
        "addons": {str(k): val for k, val in _ids(v["addons"]).items()},
        "answers": dict(v["answers"]),
        "note": v["note"].strip(),
        "terms_accepted": v["terms_accepted"],
        "health_consent": v["health_consent"],
    }


def _inputs(setup: RegistrationSetup, data: dict) -> list[services.PersonInput]:
    prices = {p.pk: p for p in setup.prices.all()}
    persons = []
    for p in data["persons"]:
        price = prices.get(p["price_id"])
        if price is None:
            raise ValidationError(gettext("Bitte einen gültigen Tarif wählen."))
        birth = datetime.date.fromisoformat(p["birth_date"]) if p.get("birth_date") else None
        persons.append(
            services.PersonInput(
                membership=None,
                name=p["name"],
                birth_date=birth,
                price=price,
                extras=ex.Extras(
                    addons=_ids(p.get("addons") or {}),
                    answers=p.get("answers") or {},
                    health=p.get("health") or "",
                    guardians=p.get("guardians") or [],
                ),
            )
        )
    return persons


def _register(setup: RegistrationSetup, data: dict, *, check_only: bool, nonce: str = ""):
    return services.register(
        setup,
        _inputs(setup, data),
        booker=None,
        name=data["name"],
        email=data["email"],
        phone=data.get("phone", ""),
        address=data.get("address", ""),
        note=data.get("note", ""),
        source=Registration.Source.PUBLIC,
        terms_accepted=bool(data.get("terms_accepted")),
        extras=ex.Extras(addons=_ids(data.get("addons") or {}), answers=data.get("answers") or {}),
        health_consent=bool(data.get("health_consent")),
        check_only=check_only,
        access_nonce=nonce,
    )


def check(setup: RegistrationSetup, data: dict, privacy_accepted: bool) -> None:
    """Alles prüfen wie bei der Anmeldung selbst, ohne etwas anzulegen."""
    if not privacy_accepted:
        raise ValidationError(gettext("Bitte den Datenschutzhinweis bestätigen."))
    if not data["persons"]:
        raise ValidationError(gettext("Bitte mindestens eine Person anmelden."))
    with transaction.atomic():
        _register(setup, data, check_only=True)


def submit(setup: RegistrationSetup, data: dict, language: str) -> str:
    """Unbestätigte Anmeldung ablegen; gibt den Token für den Bestätigungslink zurück."""
    email = data["email"].lower()
    now = timezone.now()
    open_rows = [
        row
        for row in PendingRegistration.objects.filter(setup=setup, expires_at__gt=now)
        if row.email.lower() == email
    ]
    if len(open_rows) >= MAX_PENDING:
        raise ValidationError(
            gettext(
                "Für diese E-Mail-Adresse liegen schon unbestätigte Anmeldungen vor. Bitte den "
                "Link in der Mail anklicken."
            )
        )
    token = secrets.token_urlsafe(24)
    PendingRegistration.objects.create(
        setup=setup,
        token_hash=hash_token(token),
        email=data["email"],
        data=data,
        language=language,
        expires_at=now + datetime.timedelta(hours=CONFIRM_HOURS),
    )
    return token


def find_pending(token: str) -> PendingRegistration | None:
    if not token or len(token) > 100:
        return None
    with rls_bypass():
        return (
            PendingRegistration.objects.select_related(
                "setup__organization", "setup__event", "organization"
            )
            .filter(token_hash=hash_token(token))
            .first()
        )


@transaction.atomic
def confirm(pending: PendingRegistration) -> Registration:
    """E-Mail-Adresse bestätigt: jetzt verbindlich anmelden (oder auf die Warteliste)."""
    row = PendingRegistration.objects.select_for_update().filter(pk=pending.pk).first()
    if row is None:
        raise ValidationError(gettext("Diese Anmeldung ist schon bestätigt."))
    if row.expires_at < timezone.now():
        row.delete()
        raise ValidationError(gettext("Der Link ist abgelaufen. Bitte noch einmal anmelden."))
    setup = row.setup
    data = row.data
    nonce = secrets.token_urlsafe(12)
    try:
        with transaction.atomic():
            reg = _register(setup, data, check_only=False, nonce=nonce)
    except ValidationError:
        # Inzwischen voll oder geschlossen: die Angaben nicht weiter aufheben
        row.delete()
        raise
    row.delete()
    return reg


def purge_pending(now: datetime.datetime | None = None) -> int:
    """Unbestätigte Anmeldungen nach Ablauf löschen."""
    now = now or timezone.now()
    with rls_bypass():
        deleted, _ = PendingRegistration.objects.filter(expires_at__lt=now).delete()
    return deleted


# --- Link „Anmeldung ansehen“ ---


def link_token(reg: Registration) -> str | None:
    if not reg.access_nonce:
        return None
    return signing.dumps({"r": reg.pk, "n": reg.access_nonce}, salt=LINK_SALT, compress=True)


def link_url(reg: Registration) -> str | None:
    token = link_token(reg)
    if token is None:
        return None
    from organizations.addresses import base_url

    return f"{base_url(reg.organization)}/meine-anmeldung/{token}"


def find_by_link(token: str) -> Registration | None:
    if not token or len(token) > 300:
        return None
    try:
        value = signing.loads(token, salt=LINK_SALT)
    except signing.BadSignature:
        return None
    if not isinstance(value, dict):
        return None
    with rls_bypass():
        reg = (
            Registration.objects.select_related(
                "organization", "setup__event", "setup__organization", "invoice", "fee_invoice"
            )
            .prefetch_related("participants__bookings__choice", "bookings__choice")
            .filter(pk=value.get("r"))
            .first()
        )
    if reg is None or not reg.access_nonce or reg.access_nonce != value.get("n"):
        return None
    return reg
