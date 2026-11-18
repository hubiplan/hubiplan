"""Zusatzleistungen, Zusatzfragen, Gesundheitsangaben und Erziehungsberechtigte (Stufe A5).

Zusatzleistungen (``AddOn`` mit ``AddOnChoice``) werden je Person oder je Anmeldung gebucht
(``Booking``) und mit festgehaltenem Preis in Rechnung gestellt. Zusatzfragen haben keinen
Preis; die Antworten liegen verschlüsselt an Anmeldung und Person.

Gesundheitsangaben (Allergien, Unverträglichkeiten) sind besondere Daten (Art. 9 DSGVO): nur
bei Veranstaltungen mit Verpflegung (Ralf F11), freiwillig, mit Einwilligung, nur für die
Verwaltung sichtbar und 14 Tage nach dem Ende gelöscht.

Bei „Minderjährige möglich“ wird das Geburtsdatum immer erfragt; unter 18 (am ersten Tag) sind
Name, Telefon und E-Mail einer/eines Erziehungsberechtigten Pflicht (F13).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import ValidationError

from .models import (
    MAX_GUARDIANS,
    AddOn,
    AddOnChoice,
    Booking,
    Participant,
    Per,
    Question,
    Registration,
    RegistrationSetup,
)

ZERO = Decimal("0.00")
ADULT = 18
HEALTH_KEEP_DAYS = 14
MAX_ANSWER = 500


def label(obj, lang: str = "de") -> str:
    """Name oder Frage in der Sprache, sonst Deutsch."""
    if hasattr(obj, "text"):
        return (obj.text_en if lang == "en" and obj.text_en else obj.text) or ""
    return (obj.name_en if lang == "en" and obj.name_en else obj.name) or ""


def health_allowed(setup: RegistrationSetup) -> bool:
    """Gesundheitsangaben nur bei Verpflegung oder einer Zusatzleistung der Art Essen (F11)."""
    if setup.catering:
        return True
    return setup.addons.filter(is_active=True, kind=AddOn.Kind.MEAL).exists()


def active_addons(setup: RegistrationSetup) -> list[AddOn]:
    from django.db.models import Prefetch

    choices = Prefetch("choices", queryset=AddOnChoice.objects.filter(is_active=True))
    return list(setup.addons.filter(is_active=True).prefetch_related(choices))


def active_questions(setup: RegistrationSetup) -> list[Question]:
    rows = list(setup.questions.filter(is_active=True))
    if not health_allowed(setup):
        rows = [q for q in rows if q.kind != Question.Kind.HEALTH]
    return rows


def _booked(choice: AddOnChoice) -> int:
    """Belegte Plätze einer Auswahl: aktive Personen bzw. aktive Anmeldungen."""
    return (
        Booking.objects.filter(choice=choice, registration__status=Registration.Status.REGISTERED)
        .filter(Q(participant__isnull=True) | Q(participant__status=Participant.Status.ACTIVE))
        .count()
    )


def counts(setup: RegistrationSetup) -> dict[int, int]:
    """Gebuchte Plätze je Auswahl (Zählung „32 Schnitzel“)."""
    rows = (
        Booking.objects.filter(
            registration__setup=setup, registration__status=Registration.Status.REGISTERED
        )
        .filter(Q(participant__isnull=True) | Q(participant__status=Participant.Status.ACTIVE))
        .values_list("choice_id", flat=True)
    )
    result: dict[int, int] = {}
    for choice_id in rows:
        result[choice_id] = result.get(choice_id, 0) + 1
    return result


def addon_data(addon: AddOn, booked: dict[int, int] | None = None, *, full: bool = False) -> dict:
    choices = list(addon.choices.all())
    data = {
        "id": addon.pk,
        "name": addon.name,
        "name_en": addon.name_en,
        "kind": addon.kind,
        "per": addon.per,
        "required": addon.required,
        "is_active": addon.is_active,
        "choices": [],
    }
    for c in choices:
        if not full and not c.is_active:
            continue
        taken = (booked or {}).get(c.pk, 0)
        row = {
            "id": c.pk,
            "name": c.name,
            "name_en": c.name_en,
            "amount": str(c.amount),
            "vat_rate": str(c.vat_rate) if c.vat_rate is not None else None,
            "capacity": c.capacity,
            "free": None if c.capacity is None else max(0, c.capacity - taken),
            "is_active": c.is_active,
        }
        if full:
            row["taken"] = taken
        data["choices"].append(row)
    return data


def question_data(q: Question) -> dict:
    return {
        "id": q.pk,
        "text": q.text,
        "text_en": q.text_en,
        "kind": q.kind,
        "choices": list(q.choices or []),
        "required": q.required and q.kind != Question.Kind.HEALTH,
        "per": Per.PERSON if q.kind == Question.Kind.HEALTH else q.per,
        "is_active": q.is_active,
    }


# --- Eingaben prüfen ---


@dataclass
class Extras:
    """Zusatzangaben einer Person (oder, ohne Person, der Anmeldung)."""

    addons: dict[int, int] = field(default_factory=dict)  # AddOn-ID → Auswahl-ID
    answers: dict[str, object] = field(default_factory=dict)  # Frage-ID → Antwort
    health: str = ""
    guardians: list[dict] = field(default_factory=list)


def _clean_answer(q: Question, value, who: str, board: bool):
    if value is None or value == "" or value == []:
        if q.required and not board:
            raise ValidationError(
                gettext("Bitte „{question}“ beantworten{who}.").format(question=q.text, who=who)
            )
        return None
    if q.kind == Question.Kind.YESNO:
        if not isinstance(value, bool):
            raise ValidationError(
                gettext("Bitte „{question}“ mit Ja oder Nein beantworten.").format(question=q.text)
            )
        return value
    if q.kind == Question.Kind.CHOICE:
        if value not in (q.choices or []):
            raise ValidationError(
                gettext("Bitte bei „{question}“ eine der Antworten wählen.").format(question=q.text)
            )
        return value
    if not isinstance(value, str):
        raise ValidationError(gettext("Bitte „{question}“ beantworten.").format(question=q.text))
    return value.strip()[:MAX_ANSWER] or None


def clean_answers(
    questions: list[Question], raw: dict, per: str, who: str, board: bool
) -> dict[str, object]:
    result: dict[str, object] = {}
    raw = raw or {}
    for q in questions:
        if q.kind == Question.Kind.HEALTH:
            continue
        if q.per != per:
            continue
        value = _clean_answer(q, raw.get(str(q.pk)), who, board)
        if value is not None:
            result[str(q.pk)] = value
    return result


def clean_addons(
    addons: list[AddOn], raw: dict[int, int], per: str, who: str, board: bool
) -> list[AddOnChoice]:
    chosen = []
    raw = {int(k): v for k, v in (raw or {}).items()}
    for addon in addons:
        if addon.per != per:
            continue
        value = raw.get(addon.pk)
        if value in (None, "", 0):
            if addon.required and not board:
                raise ValidationError(
                    gettext("Bitte bei „{addon}“ etwas wählen{who}.").format(
                        addon=addon.name, who=who
                    )
                )
            continue
        choice = next((c for c in addon.choices.all() if c.pk == value), None)
        if choice is None:
            raise ValidationError(
                gettext("Bitte bei „{addon}“ eine gültige Auswahl treffen.").format(
                    addon=addon.name
                )
            )
        chosen.append(choice)
    return chosen


def clean_guardians(raw: list, name: str, board: bool) -> list[dict]:
    rows = []
    for item in (raw or [])[:MAX_GUARDIANS]:
        if not isinstance(item, dict):
            continue
        row = {
            "name": str(item.get("name") or "").strip()[:200],
            "phone": str(item.get("phone") or "").strip()[:50],
            "email": str(item.get("email") or "").strip()[:254],
            "address": str(item.get("address") or "").strip()[:1000],
        }
        if any(row.values()):
            rows.append(row)
    first = rows[0] if rows else {}
    needed = ("name", "phone") if board else ("name", "phone", "email")
    if not all(first.get(k) for k in needed):
        raise ValidationError(
            gettext(
                "{name} ist unter 18: Bitte Name, Telefon und E-Mail einer oder eines "
                "Erziehungsberechtigten angeben."
            ).format(name=name)
        )
    return rows


def needs_guardian(setup: RegistrationSetup, birth: datetime.date | None, start) -> bool:
    from .services import age_on

    return setup.minors and birth is not None and age_on(birth, start) < ADULT


def check_capacity(chosen: list[AddOnChoice]) -> None:
    """Platzgrenzen der Auswahlen (unter der Sperre der Anmeldung)."""
    wanted: dict[int, int] = {}
    by_pk = {}
    for c in chosen:
        wanted[c.pk] = wanted.get(c.pk, 0) + 1
        by_pk[c.pk] = c
    for pk, n in wanted.items():
        c = by_pk[pk]
        if c.capacity is not None and _booked(c) + n > c.capacity:
            raise ValidationError(
                gettext("Bei „{addon}“ ist „{choice}“ leider ausgebucht.").format(
                    addon=c.addon.name, choice=c.name
                )
            )


def book(reg: Registration, participant: Participant | None, choice: AddOnChoice) -> Booking:
    addon = choice.addon
    name = addon.name if choice.name == addon.name else f"{addon.name}: {choice.name}"
    return Booking.objects.create(
        registration=reg,
        participant=participant,
        choice=choice,
        name=name[:210],
        amount=choice.amount,
        vat_rate=choice.vat_rate,
    )


# --- Beträge ---


def person_total(p: Participant) -> Decimal:
    return p.amount + sum((b.amount for b in p.bookings.all()), ZERO)


def registration_bookings(reg: Registration):
    return reg.bookings.filter(participant__isnull=True)


def booking_total(reg: Registration) -> Decimal:
    return sum((b.amount for b in registration_bookings(reg)), ZERO)


# --- Ausgabe ---


def booking_data(b: Booking) -> dict:
    return {
        "id": b.pk,
        "choice_id": b.choice_id,
        "addon_id": b.choice.addon_id,
        "name": b.name,
        "amount": str(b.amount),
    }


def answer_lines(questions: list[Question], answers: dict) -> list[dict]:
    rows = []
    for q in questions:
        if str(q.pk) in (answers or {}):
            value = answers[str(q.pk)]
            if isinstance(value, bool):
                value = gettext("ja") if value else gettext("nein")
            rows.append({"question_id": q.pk, "question": q.text, "answer": str(value)})
    return rows


# --- Datenschutz ---


def wipe_health(setup: RegistrationSetup) -> int:
    """Gesundheitsangaben der Anmeldung löschen (Verpflegung entfernt oder Frist um)."""
    done = 0
    for p in Participant.objects.filter(registration__setup=setup):
        if p.health:
            p.health = ""
            p.save(update_fields=["health"])
            done += 1
    return done


def purge_health_due(now: datetime.datetime | None = None) -> int:
    """Gesundheitsangaben 14 Tage nach dem Ende der Veranstaltung löschen (F11)."""
    from core.tenancy import rls_bypass

    now = now or timezone.now()
    limit = now - datetime.timedelta(days=HEALTH_KEEP_DAYS)
    done = 0
    with rls_bypass():
        rows = Registration.objects.filter(
            health_purged_at__isnull=True, setup__event__ends_at__lt=limit
        )
        for reg in rows.iterator():
            for p in reg.participants.all():
                if p.health:
                    p.health = ""
                    p.save(update_fields=["health"])
            reg.health_purged_at = now
            reg.save(update_fields=["health_purged_at", "updated_at"])
            done += 1
    return done
