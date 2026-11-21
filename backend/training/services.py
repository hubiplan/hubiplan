"""Training und Anwesenheit: Termine, Anwesenheit, Einchecken per QR-Code, Schießbuch und die
Prüfung des Schießnachweises nach § 14 WaffG.

§ 14 Abs. 3 WaffG (Erwerb): seit mindestens zwölf Monaten Mitglied und in den letzten zwölf
Monaten mit erlaubnispflichtigen Schusswaffen geschossen, entweder in jedem Monat dieses
Zeitraums oder 18 Mal insgesamt.

§ 14 Abs. 4 WaffG (Besitz, Prüfung alle fünf Jahre): in den letzten 24 Monaten einmal alle drei
Monate oder sechsmal in jedem der beiden Zwölfmonatszeiträume, bei Kurz- und Langwaffen
jeweils für beide Arten. Nach zehn Jahren genügt die Mitgliedschaft.

Richtlinie des BSSB (20.11.2024): je Schießtag zählt höchstens eine Einheit je Disziplin,
höchstens vier Monate ohne Schießtermin, überwiegend im eigenen Verein. HUBIplan zeigt das als
Hinweis; was genau anerkannt wird, entscheidet der Verband.

Die Monate und Quartale zählen rückwärts ab dem Prüftag: Der erste Monat endet am Prüftag,
der vorige einen Monat früher usw. Am Monatsletzten sind das genau die Kalendermonate.
"""

from __future__ import annotations

import calendar
import datetime
import hashlib
import hmac
import secrets
import time

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from audit.log import diff, record, snapshot

from . import access
from .models import MAX_NOTE, Attendance, ShootingEntry, TrainingSession, WeaponClass

# Ein Code gilt für dieses Zeitfenster und das vorige (also 30 bis 60 Sekunden)
WINDOW = 30
# Einchecken per QR-Code geht vom Vortag bis zum Folgetag des Termins
CHECKIN_DAYS = 1
# Anwesenheit und Schießbuch werden nach zehn Jahren gelöscht (danach genügt für das
# waffenrechtliche Bedürfnis die Mitgliedschaft, § 14 Abs. 4 Satz 3 WaffG)
KEEP_YEARS = 10
# Höchstens so viele Termine in einer Liste
LIST_LIMIT = 300
# BSSB-Richtlinie: höchstens so viele Monate ohne Schießtermin
MAX_GAP_MONTHS = 4

# Vorschläge für Disziplinen: (Bezeichnung, Waffenart, erlaubnispflichtig, Kaliber)
DISCIPLINES = (
    ("Luftgewehr", WeaponClass.LONG, False, "4,5 mm"),
    ("Luftpistole", WeaponClass.SHORT, False, "4,5 mm"),
    ("KK-Gewehr", WeaponClass.LONG, True, ".22 lfB"),
    ("KK-Pistole", WeaponClass.SHORT, True, ".22 lfB"),
    ("Sportpistole", WeaponClass.SHORT, True, ".22 lfB"),
    ("Zentralfeuerpistole", WeaponClass.SHORT, True, ".32 S&W long"),
    ("Großkaliber-Pistole", WeaponClass.SHORT, True, "9 mm Luger"),
    ("Großkaliber-Revolver", WeaponClass.SHORT, True, ".357 Mag."),
    ("Großkaliber-Gewehr", WeaponClass.LONG, True, ".308 Win."),
    ("Ordonnanzgewehr", WeaponClass.LONG, True, "8x57 IS"),
    ("Unterhebelrepetierer", WeaponClass.LONG, True, ".44 Mag."),
    ("Flinte (Trap/Skeet)", WeaponClass.LONG, True, "12/70"),
    ("Vorderlader", WeaponClass.LONG, True, ""),
)


def today() -> datetime.date:
    return timezone.localdate()


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "ja", "on", "yes")


def person_name(membership) -> str:
    person = membership.person
    if person.is_organization:
        return person.display_name
    return f"{person.first_name} {person.last_name}".strip()


def user_name(user, org) -> str:
    from pinboard.services import author_name

    if user is None:
        return ""
    # Konten ohne Namen: wenigstens die Anmeldung, damit klar bleibt, wer bestätigt hat
    return author_name(user, org) or user.get_username()[:200]


def add_months(day: datetime.date, months: int) -> datetime.date:
    """Datum um ganze Monate verschieben; am Monatsende bleibt es am Monatsende."""
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    last = calendar.monthrange(year, month)[1]
    if day.day == calendar.monthrange(day.year, day.month)[1]:
        return datetime.date(year, month, last)
    return datetime.date(year, month, min(day.day, last))


# --- Vorschläge -------------------------------------------------------------------------


def disciplines(org) -> list[dict]:
    """Vorschläge: die Liste oben und was der Verein schon eingetragen hat."""
    known = {d[0].lower() for d in DISCIPLINES}
    out = [
        {"name": n, "weapon_class": w.value, "permit_required": p, "caliber": c}
        for n, w, p, c in DISCIPLINES
    ]
    used = (
        ShootingEntry.objects.filter(organization=org)
        .exclude(discipline="")
        .values_list("discipline", "weapon_class", "permit_required", "caliber")
        .order_by("-date")[:500]
    )
    for name, wclass, permit, caliber in used:
        if name.lower() in known:
            continue
        known.add(name.lower())
        out.append(
            {"name": name, "weapon_class": wclass, "permit_required": permit, "caliber": caliber}
        )
    return out


# --- Termine ----------------------------------------------------------------------------


def _clean_time(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.time):
        return value
    try:
        return datetime.time.fromisoformat(str(value)[:5])
    except ValueError:
        raise ValidationError({field: _("Bitte eine Uhrzeit wie 19:30 angeben.")}) from None


def _clean_date(value, field="date", *, required=True):
    if value in (None, ""):
        if required:
            raise ValidationError({field: _("Bitte ein Datum angeben.")})
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValidationError({field: _("Bitte ein gültiges Datum angeben.")}) from None


def _text(data, key, limit) -> str:
    value = str(data.get(key) or "").strip()
    if len(value) > limit:
        raise ValidationError({key: _("Höchstens {n} Zeichen.").format(n=limit)})
    return value


def clean_session(data, *, partial=False) -> dict:
    out: dict = {}
    if not partial or "date" in data:
        out["date"] = _clean_date(data.get("date"))
    for key in ("starts_at", "ends_at"):
        if key in data:
            out[key] = _clean_time(data.get(key), key)
    if not partial or "title" in data:
        out["title"] = _text(data, "title", 200)
        if not out["title"]:
            raise ValidationError({"title": _("Bitte eine Bezeichnung angeben.")})
    if "kind" in data:
        kind = str(data.get("kind") or "")
        if kind not in TrainingSession.Kind.values:
            raise ValidationError({"kind": _("Unbekannte Art.")})
        out["kind"] = kind
    for key, limit in (("location", 200), ("leader", 200), ("note", MAX_NOTE)):
        if key in data:
            out[key] = _text(data, key, limit)
    if "shooting" in data:
        out["shooting"] = as_bool(data.get("shooting"))
    if "discipline" in data:
        out["discipline"] = _text(data, "discipline", 100)
    if "caliber" in data:
        out["caliber"] = _text(data, "caliber", 40)
    if "weapon_class" in data:
        wclass = str(data.get("weapon_class") or "")
        if wclass and wclass not in WeaponClass.values:
            raise ValidationError({"weapon_class": _("Bitte Kurz- oder Langwaffe wählen.")})
        out["weapon_class"] = wclass
    if "permit_required" in data:
        out["permit_required"] = as_bool(data.get("permit_required"))
    starts, ends = out.get("starts_at"), out.get("ends_at")
    if starts and ends and ends < starts:
        raise ValidationError({"ends_at": _("Das Ende liegt vor dem Beginn.")})
    return out


def check_shooting(session: TrainingSession) -> None:
    if session.shooting and (not session.discipline or not session.weapon_class):
        raise ValidationError(
            {"discipline": _("Für einen Schießtermin bitte Disziplin und Waffenart angeben.")}
        )


def duration_hours(session: TrainingSession) -> float | None:
    if not session.starts_at or not session.ends_at:
        return None
    start = datetime.datetime.combine(session.date, session.starts_at)
    end = datetime.datetime.combine(session.date, session.ends_at)
    return round((end - start).total_seconds() / 3600, 2)


def session_data(session: TrainingSession, *, count: int | None = None) -> dict:
    return {
        "id": session.pk,
        "department": session.department_id,
        "department_name": session.department.name if session.department_id else "",
        "event": session.event_id,
        "date": session.date,
        "starts_at": session.starts_at.strftime("%H:%M") if session.starts_at else None,
        "ends_at": session.ends_at.strftime("%H:%M") if session.ends_at else None,
        "hours": duration_hours(session),
        "title": session.title,
        "kind": session.kind,
        "kind_label": session.get_kind_display(),
        "location": session.location,
        "leader": session.leader,
        "note": session.note,
        "shooting": session.shooting,
        "discipline": session.discipline,
        "weapon_class": session.weapon_class,
        "caliber": session.caliber,
        "permit_required": session.permit_required,
        "checkin_open": session.checkin_open,
        "count": count if count is not None else session.attendances.count(),
        "version": session.version,
    }


def create_session(org, department, user, data) -> TrainingSession:
    fields = clean_session(data)
    event = data.get("_event")
    session = TrainingSession(
        organization=org, department=department, event=event, created_by=user, **fields
    )
    if not access.shooting_on(org):
        session.shooting = False
    check_shooting(session)
    session.save()
    record(org, user, "create", session, diff({}, snapshot(session)))
    return session


def update_session(session: TrainingSession, user, data) -> TrainingSession:
    version = data.get("version")
    if version is not None and str(version) != str(session.version):
        from rest_framework.exceptions import APIException

        exc = APIException(_("Der Termin wurde inzwischen geändert. Bitte neu laden."))
        exc.status_code = 409
        raise exc
    before = snapshot(session)
    for key, value in clean_session(data, partial=True).items():
        setattr(session, key, value)
    if not access.shooting_on(session.organization):
        session.shooting = False
    check_shooting(session)
    session.version += 1
    session.save()
    sync_shooting(session, user)
    changes = diff(before, snapshot(session))
    if changes:
        record(session.organization, user, "update", session, changes)
    return session


def session_from_event(event, occurrence: datetime.date | None) -> dict:
    """Vorschlag für einen Trainingstermin aus einem Termin des Kalenders."""
    starts = timezone.localtime(event.starts_at)
    ends = timezone.localtime(event.ends_at) if event.ends_at else None
    return {
        "date": occurrence or starts.date(),
        "starts_at": None if event.all_day else starts.time(),
        "ends_at": None if event.all_day or ends is None else ends.time(),
        "title": event.title,
        "location": event.location,
    }


# --- Anwesenheit ------------------------------------------------------------------------


def candidates(session: TrainingSession):
    """Wer eingetragen werden kann: aktuelle Mitglieder der Einheit und wer schon da ist."""
    from circulars.recipients import club_base
    from members.models import Membership

    department = session.department if session.department_id else None
    base = club_base(session.organization, department)
    present = set(session.attendances.values_list("membership_id", flat=True))
    ids = set(base.values_list("pk", flat=True)) | present
    return Membership.objects.filter(pk__in=ids, organization=session.organization)


def attendance_rows(session: TrainingSession) -> list[dict]:
    from members.personsearch import ordered

    present = {a.membership_id: a for a in session.attendances.select_related("shooting").all()}
    rows = []
    for m in ordered(candidates(session).select_related("person")):
        att = present.get(m.pk)
        rows.append(
            {
                "membership": m.pk,
                "name": person_name(m),
                "first_name": m.person.first_name,
                "last_name": m.person.last_name,
                "present": att is not None,
                "source": att.source if att else None,
                "shooting": bool(att and hasattr(att, "shooting")),
            }
        )
    return rows


def _shooting_from(session: TrainingSession, att: Attendance, user) -> None:
    if not (session.shooting and access.shooting_on(session.organization)):
        return
    if ShootingEntry.objects.filter(attendance=att).exists():
        return
    ShootingEntry.objects.create(
        organization=session.organization,
        membership_id=att.membership_id,
        attendance=att,
        date=session.date,
        discipline=session.discipline,
        weapon_class=session.weapon_class,
        caliber=session.caliber,
        permit_required=session.permit_required,
        competition=session.kind == TrainingSession.Kind.COMPETITION,
        place=session.location,
        status=ShootingEntry.Status.CONFIRMED,
        source=ShootingEntry.Source.TRAINING,
        confirmed_by=user,
        confirmed_by_name=user_name(user, session.organization) if user else "",
        confirmed_at=timezone.now(),
    )


def sync_shooting(session: TrainingSession, user) -> None:
    """Nach einer Änderung des Termins: Schießbuch-Einträge der Anwesenden angleichen."""
    linked = ShootingEntry.objects.filter(attendance__session=session)
    if not (session.shooting and access.shooting_on(session.organization)):
        linked.delete()
        return
    linked.update(
        date=session.date,
        discipline=session.discipline,
        weapon_class=session.weapon_class,
        caliber=session.caliber,
        permit_required=session.permit_required,
        competition=session.kind == TrainingSession.Kind.COMPETITION,
        place=session.location,
    )
    for att in session.attendances.filter(shooting__isnull=True):
        _shooting_from(session, att, user)


def set_present(session: TrainingSession, membership, present: bool, user, *, source=None) -> bool:
    """Anwesenheit eintragen oder austragen. Gibt zurück, ob sich etwas geändert hat."""
    existing = Attendance.objects.filter(session=session, membership=membership).first()
    if present:
        if existing is not None:
            return False
        try:
            with transaction.atomic():
                att = Attendance.objects.create(
                    organization=session.organization,
                    session=session,
                    membership=membership,
                    source=source or Attendance.Source.HAND,
                    created_by=user,
                )
        except IntegrityError:
            return False
        _shooting_from(session, att, user)
        record(session.organization, user, "create", att, diff({}, snapshot(att)))
        return True
    if existing is None:
        return False
    record(session.organization, user, "delete", existing, diff(snapshot(existing), {}))
    existing.delete()
    return True


# --- Einchecken per QR-Code -------------------------------------------------------------


def _window(now: float | None = None) -> int:
    return int((now if now is not None else time.time()) // WINDOW)


def _sign(session: TrainingSession, window: int) -> str:
    digest = hmac.new(
        session.checkin_key.encode(), f"t{session.pk}:{window}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{window}-{digest[:16]}"


def current_code(session: TrainingSession) -> dict:
    now = time.time()
    window = _window(now)
    return {
        "code": _sign(session, window),
        "refresh_in": max(1, int((window + 1) * WINDOW - now)),
        "session": session.pk,
        "club": session.organization_id,
    }


def code_valid(session: TrainingSession, code: str) -> bool:
    if not session.checkin_open or not session.checkin_key or not code:
        return False
    window = _window()
    return any(hmac.compare_digest(_sign(session, w), str(code)) for w in (window, window - 1))


def checkin_possible(session: TrainingSession, on: datetime.date | None = None) -> bool:
    on = on or today()
    return abs((session.date - on).days) <= CHECKIN_DAYS


def open_checkin(session: TrainingSession, open_: bool) -> None:
    if open_ and not checkin_possible(session):
        raise ValidationError(
            {"detail": _("Einchecken geht nur am Tag des Trainings und am Tag davor oder danach.")}
        )
    session.checkin_open = open_
    if open_ and not session.checkin_key:
        session.checkin_key = secrets.token_urlsafe(32)
    if not open_:
        # Neuer Schlüssel beim nächsten Öffnen: alte Fotos des Codes gelten nicht mehr
        session.checkin_key = ""
    session.save(update_fields=["checkin_open", "checkin_key", "updated_at"])


def check_in(session: TrainingSession, membership, code: str, user) -> None:
    if not session.checkin_open or not checkin_possible(session):
        raise ValidationError({"detail": _("Einchecken ist für dieses Training nicht geöffnet.")})
    if not code_valid(session, code):
        raise ValidationError(
            {"code": _("Der Code ist abgelaufen. Bitte den aktuellen Code scannen.")}
        )
    if membership.person.is_organization:
        raise ValidationError({"detail": _("Organisationsmitglieder können nicht einchecken.")})
    set_present(session, membership, True, user, source=Attendance.Source.CODE)


# --- Schießbuch -------------------------------------------------------------------------


def clean_entry(data, *, partial=False) -> dict:
    out: dict = {}
    if not partial or "date" in data:
        out["date"] = _clean_date(data.get("date"))
        if out["date"] > today():
            raise ValidationError({"date": _("Das Datum liegt in der Zukunft.")})
    if not partial or "discipline" in data:
        out["discipline"] = _text(data, "discipline", 100)
        if not out["discipline"]:
            raise ValidationError({"discipline": _("Bitte eine Disziplin angeben.")})
    if not partial or "weapon_class" in data:
        wclass = str(data.get("weapon_class") or "")
        if wclass not in WeaponClass.values:
            raise ValidationError({"weapon_class": _("Bitte Kurz- oder Langwaffe wählen.")})
        out["weapon_class"] = wclass
    for key, limit in (("caliber", 40), ("place", 200), ("note", MAX_NOTE)):
        if key in data:
            out[key] = _text(data, key, limit)
    for key in ("permit_required", "competition", "external"):
        if key in data:
            out[key] = as_bool(data.get(key))
    if "own_weapon" in data:
        raw = data.get("own_weapon")
        out["own_weapon"] = None if raw in (None, "", "null") else as_bool(raw)
    return out


def entry_data(entry: ShootingEntry) -> dict:
    return {
        "id": entry.pk,
        "membership": entry.membership_id,
        "date": entry.date,
        "discipline": entry.discipline,
        "weapon_class": entry.weapon_class,
        "weapon_class_label": entry.get_weapon_class_display(),
        "caliber": entry.caliber,
        "permit_required": entry.permit_required,
        "own_weapon": entry.own_weapon,
        "competition": entry.competition,
        "place": entry.place,
        "external": entry.external,
        "note": entry.note,
        "status": entry.status,
        "status_label": entry.get_status_display(),
        "source": entry.source,
        "source_label": entry.get_source_display(),
        "from_training": entry.attendance_id is not None,
        "confirmed_by": entry.confirmed_by_name,
        "confirmed_at": entry.confirmed_at,
    }


def add_entry(org, membership, user, data, *, by_member: bool) -> ShootingEntry:
    fields = clean_entry(data)
    entry = ShootingEntry(organization=org, membership=membership, **fields)
    if by_member:
        entry.status = ShootingEntry.Status.REPORTED
        entry.source = ShootingEntry.Source.MEMBER
    else:
        entry.status = ShootingEntry.Status.CONFIRMED
        entry.source = ShootingEntry.Source.BOARD
        entry.confirmed_by = user
        entry.confirmed_by_name = user_name(user, org)
        entry.confirmed_at = timezone.now()
    entry.save()
    record(org, user, "create", entry, diff({}, snapshot(entry)), person=membership.person)
    return entry


def update_entry(entry: ShootingEntry, user, data) -> ShootingEntry:
    if entry.attendance_id is not None:
        raise ValidationError(
            {"detail": _("Dieser Eintrag kommt aus dem Training. Bitte dort ändern.")}
        )
    before = snapshot(entry)
    for key, value in clean_entry(data, partial=True).items():
        setattr(entry, key, value)
    entry.save()
    changes = diff(before, snapshot(entry))
    if changes:
        record(entry.organization, user, "update", entry, changes)
    return entry


def decide_entry(entry: ShootingEntry, user, confirm: bool) -> ShootingEntry:
    before = snapshot(entry)
    entry.status = ShootingEntry.Status.CONFIRMED if confirm else ShootingEntry.Status.REJECTED
    entry.confirmed_by = user
    entry.confirmed_by_name = user_name(user, entry.organization)
    entry.confirmed_at = timezone.now()
    entry.save()
    record(entry.organization, user, "update", entry, diff(before, snapshot(entry)))
    return entry


# --- Prüfung nach § 14 WaffG ------------------------------------------------------------


def _units(entries) -> list[tuple[datetime.date, str]]:
    """Je Schießtag höchstens eine Einheit je Disziplin (BSSB-Richtlinie)."""
    return sorted({(e.date, e.discipline.strip().lower()) for e in entries})


def _slices(
    on: datetime.date, months: int, count: int
) -> list[tuple[datetime.date, datetime.date]]:
    """Zeiträume von je ``months`` Monaten rückwärts ab ``on``: (erster Tag, letzter Tag)."""
    out = []
    end = on
    for _i in range(count):
        start = add_months(end, -months) + datetime.timedelta(days=1)
        out.append((start, end))
        end = start - datetime.timedelta(days=1)
    return list(reversed(out))


def _count(units, start, end) -> int:
    return sum(1 for d, _disc in units if start <= d <= end)


def _longest_gap(units, start: datetime.date, end: datetime.date) -> int:
    """Längste Zeit ohne Schießtermin in Tagen zwischen ``start`` und ``end``."""
    days = sorted({d for d, _disc in units if start <= d <= end})
    points = [start - datetime.timedelta(days=1), *days, end + datetime.timedelta(days=1)]
    return max((b - a).days - 1 for a, b in zip(points, points[1:], strict=False))


def member_since(membership, on: datetime.date) -> datetime.date | None:
    period = membership.current_period(on)
    return period.entry_date if period else None


def evaluate(membership, on: datetime.date | None = None) -> dict:
    """Stand des Schießnachweises zum Prüftag ``on``."""
    on = on or today()
    start24 = add_months(on, -24) + datetime.timedelta(days=1)
    start12 = add_months(on, -12) + datetime.timedelta(days=1)
    entries = list(
        ShootingEntry.objects.filter(
            membership=membership,
            status=ShootingEntry.Status.CONFIRMED,
            permit_required=True,
            date__gte=start24,
            date__lte=on,
        )
    )
    since = member_since(membership, on)
    member_12 = since is not None and since <= add_months(on, -12)
    units = _units(entries)
    months = [{"start": s, "end": e, "count": _count(units, s, e)} for s, e in _slices(on, 1, 12)]
    count12 = _count(units, start12, on)
    by_months = all(m["count"] for m in months)
    by_count = count12 >= 18
    gap = _longest_gap(units, start12, on)
    recent = [e for e in entries if e.date >= start12]
    external = sum(1 for e in recent if e.external)
    acquisition = {
        "ok": member_12 and (by_months or by_count),
        "member_12_months": member_12,
        "by_months": by_months,
        "by_count": by_count,
        "count": count12,
        "needed": 18,
        "months": months,
        "longest_gap_days": gap,
        "gap_ok": gap <= MAX_GAP_MONTHS * 31,
        "external": external,
        "internal": len(recent) - external,
        "mostly_own_club": external * 2 <= len(recent),
    }
    possession = []
    for wclass in WeaponClass:
        own = _units([e for e in entries if e.weapon_class == wclass])
        quarters = [
            {"start": s, "end": e, "count": _count(own, s, e)} for s, e in _slices(on, 3, 8)
        ]
        years = [{"start": s, "end": e, "count": _count(own, s, e)} for s, e in _slices(on, 12, 2)]
        by_quarters = all(q["count"] for q in quarters)
        by_six = all(y["count"] >= 6 for y in years)
        possession.append(
            {
                "weapon_class": wclass.value,
                "label": wclass.label,
                "count": len(own),
                "ok": by_quarters or by_six,
                "by_quarters": by_quarters,
                "by_six": by_six,
                "quarters": quarters,
                "years": years,
            }
        )
    return {
        "on": on,
        "start_12": start12,
        "start_24": start24,
        "member_since": since,
        "acquisition": acquisition,
        "possession": possession,
        "pending": ShootingEntry.objects.filter(
            membership=membership, status=ShootingEntry.Status.REPORTED
        ).count(),
    }


def entries_for(membership, start: datetime.date, end: datetime.date, wclass: str = ""):
    qs = ShootingEntry.objects.filter(
        membership=membership,
        status=ShootingEntry.Status.CONFIRMED,
        date__gte=start,
        date__lte=end,
    )
    if wclass:
        qs = qs.filter(weapon_class=wclass)
    return qs.order_by("date", "pk")


# --- Auswertung -------------------------------------------------------------------------


def report(org, department_id, start: datetime.date, end: datetime.date) -> dict:
    """Teilnahmen je Mitglied und Termine im Zeitraum (Übungsleiterabrechnung, Zuschüsse)."""
    from members.models import Membership

    sessions = list(
        TrainingSession.objects.filter(
            organization=org, department_id=department_id, date__gte=start, date__lte=end
        )
        .select_related("department")
        .order_by("date", "starts_at", "pk")
    )
    ids = [s.pk for s in sessions]
    rows = Attendance.objects.filter(session_id__in=ids).values_list("membership_id", "session_id")
    per_member: dict[int, int] = {}
    per_session: dict[int, int] = {}
    for membership_id, session_id in rows:
        per_member[membership_id] = per_member.get(membership_id, 0) + 1
        per_session[session_id] = per_session.get(session_id, 0) + 1
    members = Membership.objects.filter(pk__in=per_member, organization=org).select_related(
        "person"
    )
    total = len(sessions)
    people = sorted(
        (
            {
                "membership": m.pk,
                "name": person_name(m),
                "count": per_member[m.pk],
                "share": round(100 * per_member[m.pk] / total) if total else 0,
            }
            for m in members
        ),
        key=lambda r: (-r["count"], r["name"].lower()),
    )
    hours = sum(h for s in sessions if (h := duration_hours(s)))
    return {
        "start": start,
        "end": end,
        "sessions": [session_data(s, count=per_session.get(s.pk, 0)) for s in sessions],
        "members": people,
        "total_sessions": total,
        "total_attendances": sum(per_session.values()),
        "total_hours": round(hours, 2),
    }


def member_attendance(membership, start: datetime.date, end: datetime.date) -> list[dict]:
    rows = (
        Attendance.objects.filter(
            membership=membership, session__date__gte=start, session__date__lte=end
        )
        .select_related("session__department")
        .order_by("-session__date", "-pk")
    )
    return [
        {
            "session": a.session_id,
            "date": a.session.date,
            "title": a.session.title,
            "kind": a.session.kind,
            "kind_label": a.session.get_kind_display(),
            "department_name": a.session.department.name if a.session.department_id else "",
            "source": a.source,
        }
        for a in rows[:LIST_LIMIT]
    ]


# --- Löschen ----------------------------------------------------------------------------


def forget_membership(membership) -> None:
    """Mitgliedsdaten gelöscht: Anwesenheit und Schießbuch der Person entfallen."""
    ShootingEntry.objects.filter(membership=membership).delete()
    Attendance.objects.filter(membership=membership).delete()


def purge_due(on: datetime.date | None = None) -> int:
    """Termine mit Anwesenheit und Schießbuch-Einträge nach zehn Jahren löschen."""
    from core.tenancy import rls_bypass

    on = on or today()
    limit = datetime.date(on.year - KEEP_YEARS, 1, 1)
    with rls_bypass():
        removed = ShootingEntry.objects.filter(date__lt=limit).delete()[0]
        removed += TrainingSession.objects.filter(date__lt=limit).delete()[0]
    return removed
