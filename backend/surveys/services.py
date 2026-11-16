"""Umfragen: Zielgruppe, Antworten prüfen und speichern, Ergebnis zählen.

Konzept: konzepte/umfragen-meinungsbilder.md. Die Ansichten (Verwaltung,
Mitgliederbereich, Mail-Link) rufen nur diese Funktionen; RLS setzen sie vorher.
"""

from __future__ import annotations

import datetime
import logging
import random

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from members.models import Membership

from .models import (
    ANONYMOUS_MIN,
    Survey,
    SurveyAnswer,
    SurveyOption,
    SurveyParticipation,
    SurveyQuestion,
)

logger = logging.getLogger(__name__)

Kind = SurveyQuestion.Kind
Value = SurveyAnswer.Value
MAX_TEXT = 500
# Mengenauswahl ohne Termin und ohne eigene Grenze
DEFAULT_QUANTITY = 1


def person_name(membership: Membership | None) -> str:
    if membership is None:
        return _("gelöschte Person")
    person = membership.person
    return f"{person.first_name} {person.last_name}".strip()


def as_ints(value) -> list[int]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, int) and not isinstance(v, bool) and v > 0]


# --- Zustand ---


def status_of(survey: Survey, now: datetime.datetime | None = None) -> str:
    """Status mit abgelaufenem Ende (die Hintergrundaufgabe schließt später nach)."""
    now = now or timezone.now()
    if survey.status == Survey.Status.OPEN and survey.closes_at and survey.closes_at <= now:
        return Survey.Status.CLOSED
    return survey.status


def is_open(survey: Survey, now: datetime.datetime | None = None) -> bool:
    return status_of(survey, now) == Survey.Status.OPEN


# --- Zielgruppe ---


def eligible(survey: Survey):
    """Mitgliedschaften, die die Umfrage beantworten dürfen (laufend geprüft)."""
    from circulars.recipients import club_base, club_filtered

    org = survey.organization
    if org.type != "club":
        return Membership.objects.none()
    if survey.audience in (Survey.Audience.EVENT, Survey.Audience.EVENT_YES):
        from events.models import EventResponse
        from events.rsvp import invited

        if survey.event_id is None:
            return Membership.objects.none()
        qs = invited(survey.event, sort=False)
        if survey.audience == Survey.Audience.EVENT_YES:
            qs = qs.filter(
                event_responses__event_id=survey.event_id,
                event_responses__status=EventResponse.Status.YES,
            )
        return qs
    base = club_base(org, survey.department)
    if survey.audience == Survey.Audience.PERSONS:
        return base.filter(pk__in=as_ints(survey.persons))
    qs, _jubilees = club_filtered(org, base, survey.filters or {})
    return qs


def is_eligible(survey: Survey, membership_id: int) -> bool:
    return eligible(survey).filter(pk=membership_id).exists()


def eligible_ids(survey: Survey) -> list[int]:
    return list(eligible(survey).order_by().values_list("pk", flat=True).distinct())


# --- Antworten ---


def guests_of(survey: Survey, membership_id: int) -> int:
    """Begleitpersonen aus der Zusage zum Termin der Umfrage."""
    from events.models import EventResponse

    if survey.event_id is None:
        return 0
    row = EventResponse.objects.filter(
        event_id=survey.event_id, membership_id=membership_id, status=EventResponse.Status.YES
    ).first()
    return row.guests if row else 0


def quantity_limit(question: SurveyQuestion, membership_id: int) -> int:
    survey = question.survey
    if survey.event_id and survey.audience in (
        Survey.Audience.EVENT,
        Survey.Audience.EVENT_YES,
    ):
        return 1 + guests_of(survey, membership_id)
    return question.max_choices or DEFAULT_QUANTITY


def _used(option: SurveyOption, kind: str, exclude_participation: int | None) -> int:
    qs = option.answers.all()
    if exclude_participation:
        qs = qs.exclude(participation_id=exclude_participation)
    if kind == Kind.QUANTITY:
        return qs.aggregate(n=Sum("quantity"))["n"] or 0
    if kind == Kind.DATES:
        return qs.filter(value=Value.YES).count()
    return qs.count()


def _check_capacity(option: SurveyOption, kind: str, wanted: int, own: int | None) -> None:
    if not option.capacity or wanted <= 0:
        return
    if _used(option, kind, own) + wanted > option.capacity:
        raise ValidationError(
            {"detail": _("„{label}“ ist ausgebucht.").format(label=option_label(option))}
        )


def option_label(option: SurveyOption) -> str:
    if option.label:
        return option.label
    if option.starts_at:
        from core.i18n import date_text

        start = timezone.localtime(option.starts_at)
        if option.all_day:
            return date_text(start)
        return f"{date_text(start)} {start:%H:%M}"
    return "–"


def parse_answers(
    survey: Survey, data, membership_id: int, own_participation: int | None
) -> list[SurveyAnswer]:
    """Prüft die Eingabe und gibt die (noch nicht gespeicherten) Antworten zurück.

    ``data`` ist eine Liste je Frage: ``{"question": id, "options": [ids]}``,
    ``{"question": id, "value": "yes"|"no"|"abstain"}``,
    ``{"question": id, "dates": {option_id: "yes"|"maybe"|"no"}}``,
    ``{"question": id, "quantities": {option_id: n}}`` oder ``{"question": id, "text": "…"}``.
    """
    if not isinstance(data, list):
        raise ValidationError({"answers": _("Ungültige Antworten.")})
    given: dict[int, dict] = {}
    for row in data:
        if not isinstance(row, dict) or not isinstance(row.get("question"), int):
            raise ValidationError({"answers": _("Ungültige Antworten.")})
        given[row["question"]] = row
    questions = list(survey.questions.prefetch_related("options"))
    known = {q.pk for q in questions}
    if set(given) - known:
        raise ValidationError({"answers": _("Ungültige Antworten.")})
    result: list[SurveyAnswer] = []
    for q in questions:
        row = given.get(q.pk) or {}
        options = {o.pk: o for o in q.options.all()}
        made = _parse_one(q, row, options, membership_id, own_participation)
        if not made and q.required:
            raise ValidationError(
                {"detail": _("Bitte beantworte die Frage „{text}“.").format(text=q.text)}
            )
        for a in made:
            a.organization_id = survey.organization_id
            a.survey = survey
            a.question = q
        result.extend(made)
    return result


def _invalid():
    return ValidationError({"answers": _("Ungültige Antworten.")})


def _parse_one(q, row, options, membership_id, own) -> list[SurveyAnswer]:
    if q.kind in (Kind.SINGLE, Kind.MULTIPLE):
        ids = row.get("options") or []
        if not isinstance(ids, list) or len(set(ids)) != len(ids):
            raise _invalid()
        if any(i not in options for i in ids):
            raise _invalid()
        if q.kind == Kind.SINGLE and len(ids) > 1:
            raise ValidationError({"detail": _("Bitte nur eine Antwort wählen.")})
        if q.kind == Kind.MULTIPLE and q.max_choices and len(ids) > q.max_choices:
            raise ValidationError(
                {"detail": _("Bitte höchstens {n} Antworten wählen.").format(n=q.max_choices)}
            )
        for i in ids:
            _check_capacity(options[i], q.kind, 1, own)
        return [SurveyAnswer(option=options[i]) for i in ids]
    if q.kind == Kind.YESNO:
        value = row.get("value") or ""
        if not value:
            return []
        if value not in (Value.YES, Value.NO, Value.ABSTAIN):
            raise _invalid()
        return [SurveyAnswer(value=value)]
    if q.kind == Kind.DATES:
        dates = row.get("dates")
        if dates is None:
            return []
        if not isinstance(dates, dict):
            raise _invalid()
        allowed = {Value.YES, Value.NO} | ({Value.MAYBE} if q.allow_maybe else set())
        made = []
        for key, value in dates.items():
            try:
                pk = int(key)
            except (TypeError, ValueError):
                raise _invalid() from None
            if pk not in options or value not in allowed:
                raise _invalid()
            if value == Value.NO:
                continue
            if value == Value.YES:
                _check_capacity(options[pk], q.kind, 1, own)
            made.append(SurveyAnswer(option=options[pk], value=value))
        # Ein Termin mit nur „Nein“ ist auch eine Antwort: als leere Zeile ohne Möglichkeit
        if not made and dates:
            made.append(SurveyAnswer(value=Value.NO))
        return made
    if q.kind == Kind.QUANTITY:
        amounts = row.get("quantities")
        if amounts is None:
            return []
        if not isinstance(amounts, dict):
            raise _invalid()
        made = []
        total = 0
        for key, n in amounts.items():
            try:
                pk = int(key)
            except (TypeError, ValueError):
                raise _invalid() from None
            if pk not in options or not isinstance(n, int) or isinstance(n, bool) or n < 0:
                raise _invalid()
            if n == 0:
                continue
            total += n
            _check_capacity(options[pk], q.kind, n, own)
            made.append(SurveyAnswer(option=options[pk], quantity=n))
        limit = quantity_limit(q, membership_id)
        if total > limit:
            raise ValidationError({"detail": _("Zusammen höchstens {n} Stück.").format(n=limit)})
        return made
    # Freitext
    text = row.get("text")
    if text is None:
        return []
    if not isinstance(text, str):
        raise _invalid()
    text = text.strip()
    if len(text) > MAX_TEXT:
        raise ValidationError(
            {"detail": _("Der Text ist zu lang (höchstens {n} Zeichen).").format(n=MAX_TEXT)}
        )
    return [SurveyAnswer(text=text)] if text else []


def save_answers(
    survey: Survey, membership: Membership, data, *, source: str
) -> SurveyParticipation:
    """Antworten speichern. Die Umfrage muss gesperrt sein (select_for_update)."""
    if not is_open(survey):
        raise ValidationError({"detail": _("Die Umfrage ist beendet.")})
    if not is_eligible(survey, membership.pk):
        raise ValidationError({"detail": _("Diese Umfrage richtet sich nicht an dich.")})
    part = SurveyParticipation.objects.filter(survey=survey, membership=membership).first()
    if part is not None and survey.anonymous:
        raise ValidationError(
            {"detail": _("Du hast schon geantwortet. Anonyme Antworten lassen sich nicht ändern.")}
        )
    own = part.pk if part is not None else None
    answers = parse_answers(survey, data, membership.pk, own)
    if not answers:
        raise ValidationError({"detail": _("Bitte mindestens eine Frage beantworten.")})
    if part is None:
        part = SurveyParticipation(
            organization_id=survey.organization_id, survey=survey, membership=membership
        )
    else:
        part.answers.all().delete()
    part.source = source
    # Anonym: kein Zeitpunkt, der sich neben Zugriffsprotokolle legen ließe
    part.answered_at = None if survey.anonymous else timezone.now()
    part.save()
    if survey.anonymous:
        random.shuffle(answers)
    else:
        for a in answers:
            a.participation = part
    SurveyAnswer.objects.bulk_create(answers)
    return part


def withdraw(survey: Survey, membership_id: int) -> None:
    """Eigene Antwort zurückziehen (nur mit Namen, nur solange offen)."""
    if survey.anonymous:
        raise ValidationError({"detail": _("Anonyme Antworten lassen sich nicht ändern.")})
    if not is_open(survey):
        raise ValidationError({"detail": _("Die Umfrage ist beendet.")})
    SurveyParticipation.objects.filter(survey=survey, membership_id=membership_id).delete()


def drop_after_decline(event_id: int, membership_id: int) -> None:
    """Absage zum Termin: Antworten mit Namen in Umfragen „nur wer zugesagt hat“ entfallen."""
    SurveyParticipation.objects.filter(
        survey__event_id=event_id,
        survey__audience=Survey.Audience.EVENT_YES,
        survey__status=Survey.Status.OPEN,
        membership_id=membership_id,
    ).exclude(survey__names=Survey.Names.ANONYMOUS).delete()


def my_answers(survey: Survey, membership_id: int) -> list[dict] | None:
    """Eigene Antworten als Eingabeformat (nur mit Namen; anonym: None)."""
    if survey.anonymous:
        return None
    part = SurveyParticipation.objects.filter(survey=survey, membership_id=membership_id).first()
    if part is None:
        return None
    rows: dict[int, dict] = {}
    kinds = dict(survey.questions.values_list("pk", "kind"))
    for a in part.answers.all():
        row = rows.setdefault(a.question_id, {"question": a.question_id})
        kind = kinds.get(a.question_id)
        if kind in (Kind.SINGLE, Kind.MULTIPLE):
            row.setdefault("options", []).append(a.option_id)
        elif kind == Kind.YESNO:
            row["value"] = a.value
        elif kind == Kind.DATES:
            row.setdefault("dates", {})
            if a.option_id:
                row["dates"][str(a.option_id)] = a.value
        elif kind == Kind.QUANTITY:
            row.setdefault("quantities", {})[str(a.option_id)] = a.quantity
        else:
            row["text"] = a.text
    return list(rows.values())


# --- Ergebnis ---


def participants(survey: Survey) -> int:
    return survey.participations.count()


def results_hidden(survey: Survey, count: int, now=None) -> bool:
    """Anonym und zu wenige Antworten: niemand sieht ein Ergebnis (UM-7). Anonym und noch nicht
    beendet: auch die Verwaltung nicht (Gesamtaudit 15.11., FF-22 (a)); wer zusieht, wie sich das
    Ergebnis nach jeder Antwort ändert, könnte sonst auf einzelne Personen schließen."""
    if not survey.anonymous:
        return False
    # Erst nach dem förmlichen Schließen, das die Antworten mischt (GEH-1); per Zeitablauf
    # beendet, aber noch nicht geschlossen: bis zum nächsten Stundenlauf warten
    return count < ANONYMOUS_MIN or survey.status != Survey.Status.CLOSED


def result_data(survey: Survey, *, with_names: bool) -> dict:
    if survey.archived is not None:
        return {**survey.archived, "archived": True}
    count = participants(survey)
    if results_hidden(survey, count):
        # until_close: anonym und noch nicht geschlossen (FF-22); sonst zu wenige Antworten
        until_close = survey.status != Survey.Status.CLOSED
        return {"participants": count, "hidden": True, "until_close": until_close, "questions": []}
    names_on = with_names and not survey.anonymous
    name_of: dict[int, str] = {}
    if names_on:
        for part in survey.participations.select_related("membership__person"):
            name_of[part.pk] = person_name(part.membership)
    questions = []
    for q in survey.questions.prefetch_related("options"):
        answers = list(q.answers.all())
        row = {"id": q.pk, "kind": q.kind, "text": q.text, "answered": 0}
        row["answered"] = len({a.participation_id for a in answers} if names_on else answers)
        if q.kind == Kind.YESNO:
            row["values"] = {
                v: {
                    "count": sum(1 for a in answers if a.value == v),
                    "names": sorted(
                        name_of.get(a.participation_id, "") for a in answers if a.value == v
                    )
                    if names_on
                    else [],
                }
                for v in (Value.YES, Value.NO, Value.ABSTAIN)
            }
            row["answered"] = len(answers)
        elif q.kind == Kind.TEXT:
            texts = [
                {"text": a.text, "name": name_of.get(a.participation_id, "") if names_on else ""}
                for a in answers
            ]
            if names_on:
                texts.sort(key=lambda t: t["name"])
            row["texts"] = texts
            row["answered"] = len(answers)
        else:
            opts = []
            for o in q.options.all():
                mine = [a for a in answers if a.option_id == o.pk]
                item = {
                    "id": o.pk,
                    "label": option_label(o),
                    "starts_at": o.starts_at,
                    "ends_at": o.ends_at,
                    "all_day": o.all_day,
                    "capacity": o.capacity,
                }
                if q.kind == Kind.DATES:
                    yes = [a for a in mine if a.value == Value.YES]
                    maybe = [a for a in mine if a.value == Value.MAYBE]
                    item["count"] = len(yes)
                    item["maybe"] = len(maybe)
                    item["names"] = (
                        sorted(name_of.get(a.participation_id, "") for a in yes) if names_on else []
                    )
                    item["maybe_names"] = (
                        sorted(name_of.get(a.participation_id, "") for a in maybe)
                        if names_on
                        else []
                    )
                elif q.kind == Kind.QUANTITY:
                    item["count"] = sum(a.quantity for a in mine)
                    item["names"] = (
                        sorted(
                            f"{name_of.get(a.participation_id, '')} ({a.quantity})"
                            if a.quantity > 1
                            else name_of.get(a.participation_id, "")
                            for a in mine
                        )
                        if names_on
                        else []
                    )
                else:
                    item["count"] = len(mine)
                    item["names"] = (
                        sorted(name_of.get(a.participation_id, "") for a in mine)
                        if names_on
                        else []
                    )
                opts.append(item)
            row["options"] = opts
            if q.kind == Kind.DATES:
                # Bei Terminfindung haben alle Teilnehmenden die Frage gesehen
                row["answered"] = len({a.participation_id for a in answers}) if names_on else count
                best = max((o["count"] for o in opts), default=0)
                row["best"] = [o["id"] for o in opts if best and o["count"] == best]
        questions.append(row)
    return {"participants": count, "hidden": False, "questions": questions}


def member_sees_results(survey: Survey, answered: bool, now=None) -> bool:
    closed = status_of(survey, now) == Survey.Status.CLOSED
    mode = survey.results
    if mode == Survey.Results.ALWAYS:
        return True
    if mode == Survey.Results.AFTER_ANSWER:
        return answered or closed
    if mode == Survey.Results.AFTER_CLOSE:
        return closed
    return False


# Anonyme Umfragen zeigen ihr Ergebnis erst nach dem Ende (Gesamtaudit 15.11., FF-22 (a))
ANONYMOUS_RESULTS = (Survey.Results.AFTER_CLOSE, Survey.Results.MANAGERS)


# --- Ablauf ---


def mix_answers(survey: Survey) -> int:
    """Antworten einer anonymen Umfrage in zufälliger Reihenfolge neu schreiben (Gesamtaudit
    15.11., GEH-1). Teilnahme und Antwort entstehen in derselben Transaktion; ohne Mischen
    ließen sie sich über die Transaktionsnummer (xmin) und die Lage in der Tabelle (ctid)
    einander zuordnen. Danach tragen alle Antworten dieselbe neue Transaktionsnummer, neue
    Kennungen und eine zufällige Reihenfolge. Die Umfrage muss gesperrt sein
    (select_for_update), damit keine Stimme dazwischen kommt. Zählungen ändern sich nicht."""
    if not survey.anonymous:
        return 0
    fields = [f.attname for f in SurveyAnswer._meta.concrete_fields if not f.primary_key]
    found = list(SurveyAnswer.objects.filter(survey=survey))
    if not found:
        return 0
    rows = [{k: getattr(a, k) for k in fields} for a in found]
    random.SystemRandom().shuffle(rows)
    # Nur die gelesenen Zeilen: eine Stimme, die doch dazwischen kam, bleibt erhalten
    SurveyAnswer.objects.filter(pk__in=[a.pk for a in found]).delete()
    SurveyAnswer.objects.bulk_create([SurveyAnswer(**r) for r in rows])
    return len(rows)


def mix_open() -> int:
    """Stündlich: offene anonyme Umfragen mischen. Gerade gesperrte (jemand stimmt ab) kommen
    beim nächsten Lauf dran; beim Schließen wird ohnehin gemischt."""
    from core.tenancy import rls_bypass

    done = 0
    with rls_bypass():
        ids = list(
            Survey.objects.filter(
                names=Survey.Names.ANONYMOUS, status=Survey.Status.OPEN
            ).values_list("pk", flat=True)
        )
        for pk in ids:
            with transaction.atomic():
                survey = (
                    Survey.objects.select_for_update(skip_locked=True)
                    .filter(pk=pk, status=Survey.Status.OPEN)
                    .first()
                )
                if survey is not None and mix_answers(survey):
                    done += 1
    return done


def close(survey: Survey, now: datetime.datetime | None = None) -> None:
    """Umfrage schließen; die Umfrage muss gesperrt sein. Anonyme Antworten werden vorher
    gemischt, erst danach erscheint das Ergebnis (GEH-1)."""
    now = now or timezone.now()
    mix_answers(survey)
    survey.invited = len(eligible_ids(survey))
    survey.status = Survey.Status.CLOSED
    survey.closed_at = now
    survey.version += 1
    survey.save(update_fields=["invited", "status", "closed_at", "version", "updated_at"])


def stricter(old: str, new: str, order: list[str]) -> bool:
    return order.index(new) >= order.index(old)


NAMES_ORDER = [Survey.Names.OPEN, Survey.Names.MANAGERS, Survey.Names.ANONYMOUS]
RESULTS_ORDER = [
    Survey.Results.ALWAYS,
    Survey.Results.AFTER_ANSWER,
    Survey.Results.AFTER_CLOSE,
    Survey.Results.MANAGERS,
]


def counts_by_survey(surveys) -> dict[int, int]:
    ids = [s.pk for s in surveys]
    rows = (
        SurveyParticipation.objects.filter(survey_id__in=ids)
        .values("survey_id")
        .annotate(n=Count("pk"))
    )
    return {r["survey_id"]: r["n"] for r in rows}


def answered_ids(membership_id: int, survey_ids) -> set[int]:
    return set(
        SurveyParticipation.objects.filter(
            survey_id__in=list(survey_ids), membership_id=membership_id
        ).values_list("survey_id", flat=True)
    )


def forget_membership(membership: Membership) -> None:
    """Daten eines Mitglieds gelöscht: Teilnahmen bleiben gezählt, ohne Person."""
    SurveyParticipation.objects.filter(membership=membership).update(membership=None)


def purge_due(now: datetime.datetime | None = None) -> int:
    """Antworten nach der Frist löschen, das Ergebnis als Zahlen behalten (UM-10)."""
    from core.tenancy import rls_bypass

    now = now or timezone.now()
    done = 0
    with rls_bypass():
        rows = Survey.objects.filter(
            status=Survey.Status.CLOSED, purged_at__isnull=True, closed_at__isnull=False
        )
        for survey in rows.iterator():
            if survey.closed_at + datetime.timedelta(days=30 * survey.keep_months) > now:
                continue
            # Alles oder nichts, und erst löschen, dann vermerken: Bricht der Lauf ab, bleibt
            # die Umfrage unbereinigt und kommt beim nächsten Lauf wieder (Gesamtaudit 15.11.,
            # PF-14). Vorher stand „bereinigt“ schon da, die Antworten aber noch.
            try:
                with transaction.atomic():
                    data = result_data(survey, with_names=False)
                    survey.participations.all().delete()
                    survey.answers.all().delete()
                    Survey.objects.filter(pk=survey.pk).update(archived=data, purged_at=now)
            except Exception:  # noqa: BLE001 – eine Umfrage darf die übrigen nicht aufhalten
                logger.exception("Umfrage %s nicht bereinigt", survey.pk)
                continue
            done += 1
    return done


def close_due(now: datetime.datetime | None = None) -> int:
    from core.tenancy import rls_bypass

    now = now or timezone.now()
    done = 0
    with rls_bypass():
        ids = list(
            Survey.objects.filter(status=Survey.Status.OPEN, closes_at__lte=now).values_list(
                "pk", flat=True
            )
        )
        for pk in ids:
            with transaction.atomic():
                survey = (
                    Survey.objects.select_for_update(of=("self",))
                    .filter(pk=pk, status=Survey.Status.OPEN)
                    .select_related("organization", "department", "event")
                    .first()
                )
                if survey is None:
                    continue
                close(survey, now)
                done += 1
    return done


def has_open(membership_id: int, org) -> int:
    """Zahl offener, noch nicht beantworteter Umfragen für ein Mitglied."""
    now = timezone.now()
    n = 0
    for survey in Survey.objects.filter(organization=org, status=Survey.Status.OPEN).filter(
        Q(closes_at__isnull=True) | Q(closes_at__gt=now)
    ):
        if SurveyParticipation.objects.filter(survey=survey, membership_id=membership_id).exists():
            continue
        if is_eligible(survey, membership_id):
            n += 1
    return n
