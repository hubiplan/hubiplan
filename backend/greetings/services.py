"""Glückwünsche vorbereiten und versenden (siehe ``models``)."""

from __future__ import annotations

import datetime
import logging

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers

from circulars.models import Circular
from core.i18n import language_of_org
from members.birthdays import birthdays_between
from members.duration import jubilees_between
from members.models import Membership

from .models import MAX_LEAD_DAYS, GreetingBatch, GreetingSettings

logger = logging.getLogger(__name__)

# Nicht freigegebene Entwürfe so lange nach dem Tag noch zeigen, dann auslassen
KEEP_UNSENT_DAYS = 7
# Am Folgetag geht ein verpasster Glückwunsch noch hinaus (Ausfall, Ausrollen)
LATE_DAYS = 1
NOT_SENT = "nicht rechtzeitig versendet"
NOBODY = "keine Empfänger"


def default_texts(org) -> dict[str, str]:
    """Vorgabetexte in der Vereinssprache (Du-Form, im Verein üblich; änderbar)."""
    with language_of_org(org):
        return {
            "birthday_subject": gettext("Herzlichen Glückwunsch zum Geburtstag"),
            "birthday_body": gettext(
                "{Anrede Du},\n\nherzlichen Glückwunsch zu deinem {Alter}. Geburtstag! "
                "Wir wünschen dir alles Gute, Gesundheit und viele schöne Stunden.\n\n"
                "Herzliche Grüße\n{Verein}"
            ),
            "jubilee_subject": gettext("Herzlichen Glückwunsch zum Vereinsjubiläum"),
            "jubilee_body": gettext(
                "{Anrede Du},\n\nseit {Jubiläumsjahre} Jahren bist du Mitglied bei uns. "
                "Dafür sagen wir herzlich Danke und gratulieren dir zu deinem Jubiläum!\n\n"
                "Herzliche Grüße\n{Verein}"
            ),
        }


def settings_for(org) -> GreetingSettings:
    s = GreetingSettings.objects.filter(organization=org).first()
    if s is None:
        s = GreetingSettings(organization=org)
    for key, value in default_texts(org).items():
        if not getattr(s, key):
            setattr(s, key, value)
    return s


def parse_ages(text: str) -> list[int]:
    """„18, 30, 40“ → [18, 30, 40]; Unsinn wird übergangen."""
    ages = set()
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() and 0 < int(part) < 130:
            ages.add(int(part))
    return sorted(ages)


def wants_age(s: GreetingSettings, age: int) -> bool:
    if s.birthdays == GreetingSettings.Birthdays.ALL:
        return True
    if s.birthdays != GreetingSettings.Birthdays.ROUND:
        return False
    if s.every_year_from and age >= s.every_year_from:
        return True
    return age in parse_ages(s.round_ages)


def occasions(org, s: GreetingSettings, start: datetime.date, end: datetime.date) -> list[dict]:
    """Anlässe im Zeitraum: Datum, Anlass, Mitglied, Name, Alter bzw. Jahre."""
    rows: list[dict] = []
    if s.birthdays != GreetingSettings.Birthdays.OFF:
        hits = birthdays_between(org, start, end)
        # Nur Geburtsjahr bekannt: kein echter Geburtstag
        year_only = set(
            Membership.objects.filter(
                pk__in=[h["member_id"] for h in hits], person__birth_year_only=True
            ).values_list("pk", flat=True)
        )
        for h in hits:
            if h["member_id"] in year_only or not wants_age(s, h["age"]):
                continue
            rows.append(
                {
                    "date": h["date"],
                    "kind": GreetingBatch.Kind.BIRTHDAY,
                    "member_id": h["member_id"],
                    "first_name": h["first_name"],
                    "last_name": h["last_name"],
                    "age": h["age"],
                    "years": None,
                }
            )
    if s.jubilees:
        for h in jubilees_between(org, start, end):
            # Nur Jubiläen im Verein selbst, mit Tag oder Monat (jahresgenau kein Datum)
            if h["kind"] != "club" or h.get("precision") == "year":
                continue
            if not start <= h["date"] <= end:
                continue
            rows.append(
                {
                    "date": h["date"],
                    "kind": GreetingBatch.Kind.JUBILEE,
                    "member_id": h["member_id"],
                    "first_name": h["first_name"],
                    "last_name": h["last_name"],
                    "age": None,
                    "years": h["years"],
                }
            )
    rows.sort(key=lambda r: (r["date"], r["kind"], r["last_name"], r["first_name"]))
    return rows


def opted_out(member_ids) -> set[int]:
    return set(
        Membership.objects.filter(
            pk__in=list(member_ids), greetings_opt_out_at__isnull=False
        ).values_list("pk", flat=True)
    )


def _grouped(rows: list[dict]) -> dict[tuple, dict[str, dict]]:
    groups: dict[tuple, dict[str, dict]] = {}
    for r in rows:
        values = {"age": r["age"]} if r["kind"] == GreetingBatch.Kind.BIRTHDAY else {}
        if r["years"]:
            values["years"] = r["years"]
        groups.setdefault((r["date"], r["kind"]), {})[str(r["member_id"])] = values
    return groups


def _circular_values(s: GreetingSettings, kind: str, values: dict[str, dict]) -> dict:
    birthday = kind == GreetingBatch.Kind.BIRTHDAY
    return {
        "subject": (s.birthday_subject if birthday else s.jubilee_subject)[:200],
        "body": s.birthday_body if birthday else s.jubilee_body,
        "via_app": s.via_app,
        "also_mail": s.also_mail,
        "reply_to": s.reply_to,
        "filters": {
            "members": sorted(int(k) for k in values),
            "greeting": values,
            "households_merge": False,
        },
    }


@transaction.atomic
def prepare(org, today: datetime.date) -> int:
    """Entwürfe für die nächsten Tage anlegen oder angleichen; gibt die Zahl der Entwürfe."""
    s = settings_for(org)
    lead = min(max(s.lead_days, 0), MAX_LEAD_DAYS)
    found = (
        _grouped(occasions(org, s, today, today + datetime.timedelta(days=lead)))
        if (s.pk and s.active)
        else {}
    )
    batches = {
        (b.date, b.kind): b
        for b in GreetingBatch.objects.filter(organization=org, date__gte=today).select_related(
            "circular"
        )
    }
    drafts = 0
    for key, values in found.items():
        b = batches.get(key)
        if b is not None and (b.skipped_at or (b.circular and not b.circular.is_draft)):
            continue
        fields = _circular_values(s, key[1], values)
        if b is None:
            circular = Circular.objects.create(
                organization=org,
                kind=Circular.Kind.GREETING,
                audience=Circular.Audience.MEMBERS,
                **fields,
            )
            GreetingBatch.objects.create(
                organization=org, date=key[0], kind=key[1], circular=circular
            )
        elif b.circular is None:
            # Rundschreiben von Hand gelöscht: gilt als ausgelassen
            b.skipped_at = timezone.now()
            b.save(update_fields=["skipped_at"])
            continue
        else:
            changed = [k for k, v in fields.items() if getattr(b.circular, k) != v]
            if changed:
                for k in changed:
                    setattr(b.circular, k, fields[k])
                b.circular.save(update_fields=[*changed, "updated_at"])
        drafts += 1
    # Was nicht mehr ansteht (Austritt, Einstellung geändert), fällt als Entwurf weg
    for key, b in batches.items():
        if key not in found and not b.skipped_at and b.circular and b.circular.is_draft:
            b.circular.delete()
            b.delete()
    # Nicht freigegebene Entwürfe nach einer Woche auslassen
    stale = GreetingBatch.objects.filter(
        organization=org,
        date__lt=today - datetime.timedelta(days=KEEP_UNSENT_DAYS),
        skipped_at__isnull=True,
        circular__status=Circular.Status.DRAFT,
    ).select_related("circular")
    for b in stale:
        skip(b, None, NOT_SENT)
    return drafts


def skip(batch: GreetingBatch, user, note: str = "") -> None:
    """Glückwunsch auslassen: Entwurf löschen, Tag merken (kommt nicht wieder)."""
    if batch.circular and not batch.circular.is_draft:
        raise serializers.ValidationError(gettext("Dieser Glückwunsch ist schon versendet."))
    if batch.circular:
        batch.circular.delete()
    batch.circular = None
    batch.skipped_at = timezone.now()
    batch.skipped_by = user
    batch.note = note[:200]
    batch.save(update_fields=["circular", "skipped_at", "skipped_by", "note"])


def send(batch: GreetingBatch, user) -> dict[str, int]:
    """Glückwunsch jetzt versenden (Vorstand oder Zeitplan)."""
    from circulars.services import start_sending

    circular = batch.circular
    if circular is None or not circular.is_draft:
        raise serializers.ValidationError(gettext("Dieser Glückwunsch ist schon erledigt."))
    try:
        return start_sending(circular, user)
    except serializers.ValidationError:
        # Alle haben widersprochen oder sind ausgetreten: auslassen statt immer neu versuchen
        from circulars import recipients as rcp

        if user is None and not rcp.select(circular).chosen:
            skip(batch, None, NOBODY)
            return {}
        raise


def send_due(org, now: datetime.datetime) -> int:
    """Fällige Glückwünsche ohne Freigabe versenden (ab der eingestellten Stunde)."""
    s = settings_for(org)
    local = timezone.localtime(now)
    if not s.pk or not s.active or s.approval or local.hour < s.send_hour:
        return 0
    today = local.date()
    batches = GreetingBatch.objects.filter(
        organization=org,
        date__gte=today - datetime.timedelta(days=LATE_DAYS),
        date__lte=today,
        skipped_at__isnull=True,
        circular__status=Circular.Status.DRAFT,
    ).select_related("circular")
    sent = 0
    for b in batches:
        try:
            if send(b, None):
                sent += 1
        except serializers.ValidationError as exc:
            logger.warning("Glückwunsch %s nicht versendet: %s", b.pk, exc.detail)
    return sent
