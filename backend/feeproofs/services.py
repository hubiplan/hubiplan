"""Regeln der Ermäßigung mit Nachweis: Fristen, Stand je Beitragsjahr, Beitrag.

Beitragsjahr ist das Geschäftsjahr des Vereins (meist das Kalenderjahr). Die Frist liegt am
eingestellten Tag im Beitragsjahr (Vorgabe 28.02.). Wer erst im Beitragsjahr eintritt oder die
Ermäßigung erst dann bekommt, hat ab diesem Tag ``late_join_days`` Zeit (Vorgabe 4 Wochen),
höchstens aber nie weniger als bis zur normalen Frist. Danach kommt die Kulanzzeit.

Stand je Mitglied, Ermäßigung und Jahr:

- ``accepted``: anerkannter Nachweis → Ermäßigung
- ``pending``/``question``: rechtzeitig eingereicht, noch nicht entschieden → Ermäßigung
  vorläufig (der Vorstand entscheidet noch)
- ``open``: noch kein Nachweis, Frist samt Kulanzzeit läuft → Ermäßigung vorläufig
- ``missing``: Frist samt Kulanzzeit vorbei ohne anerkannten Nachweis → normaler Beitrag

Ein Nachweis zählt für das Beitragsjahr, für das er eingereicht wird. Einreichen lässt er sich
ab drei Monaten vor Beginn des Beitragsjahres (z. B. ab 01.10. für das Folgejahr), damit eine
Wintersemester-Bescheinigung aus dem Herbst reicht. Anerkannt wird er nur, wenn er am
Eingangstag oder zu Beginn des Beitragsjahres gültig ist. Ein Nachweis wirkt nie über sein
Beitragsjahr hinaus; fallen die Voraussetzungen im Jahr weg, bleibt die Ermäßigung bis zum
Ende des Beitragsjahres (Ermäßigung endet mit Ablauf des Jahres).
"""

from __future__ import annotations

import calendar
import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.utils.translation import gettext

from core.i18n import date_text

from .models import DiscountAssignment, FeeProof, ProofDiscount

CENT = Decimal("0.01")
# So lange vor Beginn des Beitragsjahres lässt sich ein Nachweis dafür einreichen
OPEN_BEFORE_DAYS = 92
ONE_DAY = datetime.timedelta(days=1)

ACCEPTED = "accepted"
PENDING = "pending"
QUESTION = "question"
OPEN = "open"
MISSING = "missing"

S = FeeProof.Status


def module_on(org) -> bool:
    from organizations.models import Organization

    return (
        org.type in (Organization.Type.CLUB, Organization.Type.FEDERATION)
        and org.keeps_members
        and "billing" in (org.enabled_modules or [])
    )


def day_in(year: int, month: int, day: int) -> datetime.date:
    """Datum mit Tag höchstens am Monatsende (29.02. in Nicht-Schaltjahren → 28.02.)."""
    return datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def in_fee_year(org, year: int, month: int, day: int) -> datetime.date:
    """Erster Tag mit diesem Tag und Monat ab Beginn des Beitragsjahres."""
    start = org.fiscal_start(year)
    found = day_in(start.year, month, day)
    return found if found >= start else day_in(start.year + 1, month, day)


def deadline(org, discount: ProofDiscount, year: int) -> datetime.date:
    return in_fee_year(org, year, discount.deadline_month, discount.deadline_day)


def opens_on(org, year: int) -> datetime.date:
    return org.fiscal_start(year) - datetime.timedelta(days=OPEN_BEFORE_DAYS)


def years_open(org, on: datetime.date) -> list[int]:
    """Beitragsjahre, für die man am Tag ``on`` einreichen kann (ab Herbst auch das nächste)."""
    year = org.fiscal_year_of(on)
    years = [year]
    if on >= opens_on(org, year + 1):
        years.append(year + 1)
    return years


def first_reminder(org, discount: ProofDiscount, year: int) -> datetime.date | None:
    if not discount.remind_month or not discount.remind_day:
        return None
    start = opens_on(org, year)
    found = day_in(start.year, discount.remind_month, discount.remind_day)
    return (
        found
        if found >= start
        else day_in(start.year + 1, discount.remind_month, discount.remind_day)
    )


@dataclass
class Dates:
    due: datetime.date
    final: datetime.date
    late_start: bool  # erst im Beitragsjahr begonnen (Eintritt oder Ermäßigung)


def dates_for(org, discount: ProofDiscount, year: int, began: datetime.date | None) -> Dates:
    """Frist und letzter Tag (mit Kulanzzeit) für ein Mitglied, das am ``began`` angefangen hat."""
    due = deadline(org, discount, year)
    late = False
    if began is not None:
        start, end = org.fiscal_range(year)
        if start < began <= end:
            late = True
            due = max(due, began + datetime.timedelta(days=discount.late_join_days))
    final = due + datetime.timedelta(days=discount.grace_days or 0)
    return Dates(due, final, late)


def began_in_year(org, year: int, assignments, periods) -> datetime.date | None:
    """Beginn im Beitragsjahr: der spätere von Ermäßigung und Mitgliedschaft (sonst None)."""
    start, end = org.fiscal_range(year)

    def first(rows, begin, finish):
        days = [
            getattr(r, begin)
            for r in rows
            if getattr(r, begin) <= end
            and (getattr(r, finish) is None or getattr(r, finish) >= start)
        ]
        return min(days) if days else None

    a = first(assignments, "valid_from", "valid_until")
    p = first(periods, "entry_date", "exit_date")
    days = [d for d in (a, p) if d is not None]
    if not days:
        return None
    began = max(days)
    return began if began > start else None


RANK = {S.ACCEPTED: 0, S.RECEIVED: 1, S.QUESTION: 2, S.REJECTED: 3}


def best_proof(proofs) -> FeeProof | None:
    rows = sorted(proofs, key=lambda q: (RANK[q.status], -q.received_on.toordinal(), -q.pk))
    return rows[0] if rows else None


@dataclass
class YearState:
    discount: ProofDiscount
    year: int
    dates: Dates
    proof: FeeProof | None
    state: str

    @property
    def applies(self) -> bool:
        return self.state != MISSING

    @property
    def provisional(self) -> bool:
        return self.state in (PENDING, QUESTION, OPEN)


def state_of(dates: Dates, proofs, on: datetime.date) -> tuple[str, FeeProof | None]:
    proofs = list(proofs)
    accepted = [q for q in proofs if q.status == S.ACCEPTED]
    if accepted:
        return ACCEPTED, best_proof(accepted)
    waiting = [
        q for q in proofs if q.status in (S.RECEIVED, S.QUESTION) and q.received_on <= dates.final
    ]
    if waiting:
        q = best_proof(waiting)
        return (QUESTION if q.status == S.QUESTION else PENDING), q
    if on <= dates.final:
        return OPEN, best_proof(proofs)
    return MISSING, best_proof(proofs)


def year_state(
    membership,
    discount,
    year: int,
    on: datetime.date,
    *,
    assignments=None,
    periods=None,
    proofs=None,
) -> YearState:
    org = membership.organization
    if assignments is None:
        assignments = list(
            DiscountAssignment.objects.filter(membership=membership, discount=discount)
        )
    if periods is None:
        periods = list(membership.periods.all())
    if proofs is None:
        proofs = FeeProof.objects.filter(membership=membership, discount=discount, year=year)
    dates = dates_for(org, discount, year, began_in_year(org, year, assignments, periods))
    state, proof = state_of(dates, proofs, on)
    return YearState(discount, year, dates, proof, state)


def requirements(membership, on: datetime.date) -> list[YearState]:
    """Was das Mitglied am Tag ``on`` einreichen kann oder eingereicht hat (offene Jahre)."""
    org = membership.organization
    if not module_on(org):
        return []
    rows = list(
        DiscountAssignment.objects.filter(
            membership=membership, discount__is_archived=False
        ).select_related("discount")
    )
    periods = list(membership.periods.all())
    result = []
    for year in years_open(org, on):
        start, end = org.fiscal_range(year)
        member_in_year = any(
            p.entry_date <= end and (p.exit_date is None or p.exit_date >= start) for p in periods
        )
        if not member_in_year:
            continue
        for discount in {a.discount_id: a.discount for a in rows}.values():
            mine = [a for a in rows if a.discount_id == discount.pk]
            if not any(
                a.valid_from <= end and (a.valid_until is None or a.valid_until >= start)
                for a in mine
            ):
                continue
            result.append(
                year_state(membership, discount, year, on, assignments=mine, periods=periods)
            )
    result.sort(key=lambda s: (s.year, s.discount.sort_order, s.discount.name))
    return result


def portal_summary(membership, on: datetime.date) -> tuple[bool, int]:
    """Für Mitgliederbereich und App: Menüpunkt zeigen? Wie viele Jahre brauchen noch etwas?"""
    if not module_on(membership.organization):
        return False, 0
    if not DiscountAssignment.objects.filter(membership=membership).exists():
        return False, 0
    due = sum(1 for st in requirements(membership, on) if st.state in (OPEN, QUESTION, MISSING))
    return True, due


# --- Prüfung eines Nachweises ---


def check_valid_until(proof: FeeProof, valid_until: datetime.date | None) -> None:
    """Gültig am Eingangstag oder zu Beginn des Beitragsjahres (Fachfrage F3)."""
    from rest_framework.exceptions import ValidationError

    if valid_until is None:
        return
    org = proof.organization
    needed = min(proof.received_on, org.fiscal_start(proof.year))
    if valid_until < needed:
        raise ValidationError(
            {
                "valid_until": gettext(
                    "Der Nachweis muss am {day} noch gültig sein (Eingang oder Beginn des "
                    "Beitragsjahres)."
                ).format(day=date_text(needed))
            }
        )


def drop_file(proof: FeeProof) -> None:
    """Datei nach der Entscheidung löschen; der Vermerk bleibt (Fachfrage F5)."""
    from django.utils import timezone

    from core.files import delete_on_commit

    if proof.file:
        delete_on_commit(proof.file)
        proof.file = ""
        proof.file_deleted_at = timezone.now()


# --- Beitrag ---


def reduced(discount: ProofDiscount, yearly: Decimal) -> Decimal:
    """Ermäßigter Jahresbeitrag; eine Ermäßigung verteuert nie."""
    if discount.amount is not None:
        return min(discount.amount, yearly)
    factor = (Decimal(100) - (discount.discount_percent or Decimal(0))) / Decimal(100)
    return (yearly * factor).quantize(CENT, ROUND_HALF_UP)


class BillingContext:
    """Für den Beitragslauf: Ermäßigungen und Nachweise aller Mitglieder einmal laden."""

    def __init__(self, org, membership_ids: list[int], year: int, on: datetime.date):
        self.org, self.year, self.on = org, year, on
        self.enabled = module_on(org) and bool(membership_ids)
        self.assignments: dict[int, list[DiscountAssignment]] = {}
        self.proofs: dict[tuple[int, int], list[FeeProof]] = {}
        self.regular = 0
        self.provisional = 0
        self.unreviewed = 0
        if not self.enabled:
            return
        for a in DiscountAssignment.objects.filter(
            organization=org, membership_id__in=membership_ids, discount__is_archived=False
        ).select_related("discount"):
            self.assignments.setdefault(a.membership_id, []).append(a)
        if not self.assignments:
            self.enabled = False
            return
        for q in FeeProof.objects.filter(
            organization=org, year=year, membership_id__in=list(self.assignments)
        ):
            self.proofs.setdefault((q.membership_id, q.discount_id), []).append(q)

    def adjust(self, membership, spans, ref: datetime.date, member_type_id: int, yearly: Decimal):
        """(Jahresbeitrag, Hinweis für die Rechnung); None ohne zugeordnete Ermäßigung."""
        if not self.enabled:
            return None
        rows = [
            a
            for a in self.assignments.get(membership.pk, [])
            if a.covers(ref) and a.discount.member_type_id in (None, member_type_id)
        ]
        if not rows:
            return None
        best = None
        for a in rows:
            discount = a.discount
            mine = [x for x in self.assignments[membership.pk] if x.discount_id == discount.pk]
            st = year_state(
                membership,
                discount,
                self.year,
                self.on,
                assignments=mine,
                periods=spans,
                proofs=self.proofs.get((membership.pk, discount.pk), []),
            )
            if st.applies:
                amount = reduced(discount, yearly)
                note = discount.name
                if st.provisional:
                    note = gettext("{name} (Nachweis offen)").format(name=discount.name)
                cand = (amount, note, st)
            else:
                cand = (
                    yearly,
                    gettext("{name}: kein Nachweis bis {day}, normaler Beitrag").format(
                        name=discount.name, day=date_text(st.dates.final)
                    ),
                    st,
                )
            if best is None or cand[0] < best[0]:
                best = cand
        amount, note, st = best
        if not st.applies:
            self.regular += 1
        elif st.provisional:
            self.provisional += 1
            if st.state in (PENDING, QUESTION):
                self.unreviewed += 1
        return amount, note


# --- Einreichen und entscheiden ---

MAX_FILE_BYTES = 10 * 1024 * 1024
FILE_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


def file_problem(name: str, content_type: str, data: bytes) -> str:
    """Fehlertext für eine ungeeignete Datei (leer: passt)."""
    if len(data) > MAX_FILE_BYTES:
        return gettext("Die Datei ist größer als 10 MB.")
    if content_type not in FILE_TYPES:
        return gettext("Erlaubt sind PDF und Fotos (JPEG, PNG, WebP, HEIC).")
    if content_type == "application/pdf" and not data.startswith(b"%PDF"):
        return gettext("Die Datei ist kein PDF.")
    if not data:
        return gettext("Die Datei ist leer.")
    return ""


def content_type_of(name: str, given: str) -> str:
    import mimetypes

    content_type = (given or "").split(";")[0].strip().lower()
    if content_type not in FILE_TYPES:
        guessed = (mimetypes.guess_type(name or "")[0] or "").lower()
        if guessed in FILE_TYPES:
            content_type = guessed
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    return content_type


def safe_file_name(name: str, content_type: str) -> str:
    safe = "".join(c if c.isalnum() or c in ".-_" else "_" for c in (name or ""))[-80:]
    if not safe or "." not in safe:
        safe = "nachweis" + FILE_TYPES.get(content_type, "")
    return safe


def window_for(membership, discount, year: int, on: datetime.date) -> YearState | None:
    """Stand, wenn das Mitglied für dieses Jahr einreichen darf (sonst None)."""
    for st in requirements(membership, on):
        if st.discount.pk == discount.pk and st.year == year:
            return st
    return None


def submit(
    membership,
    discount: ProofDiscount,
    year: int,
    *,
    channel: str,
    name: str = "",
    content_type: str = "",
    data: bytes | None = None,
    kind: str = "",
    member_note: str = "",
    user=None,
    on: datetime.date | None = None,
    check_window: bool = True,
) -> FeeProof:
    """Nachweis anlegen, Datei speichern, vorprüfen und ggf. automatisch anerkennen."""
    import hashlib

    from django.core.files.base import ContentFile
    from django.utils import timezone
    from rest_framework.exceptions import ValidationError

    from members.models import today

    on = on or today()
    org = membership.organization
    if check_window and window_for(membership, discount, year, on) is None:
        raise ValidationError(
            gettext("Für {year} ist hier kein Nachweis vorgesehen.").format(
                year=org.fiscal_label(year)
            )
        )
    kind = (kind or "").strip()[:100]
    if kind and discount.kinds and kind not in discount.kinds:
        kind = ""
    proof = FeeProof(
        organization=org,
        membership=membership,
        discount=discount,
        year=year,
        kind=kind,
        channel=channel,
        received_on=on,
        member_note=(member_note or "").strip()[:500],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    assignments = list(DiscountAssignment.objects.filter(membership=membership, discount=discount))
    dates = dates_for(
        org, discount, year, began_in_year(org, year, assignments, list(membership.periods.all()))
    )
    proof.late = dates.due < on <= dates.final
    if data:
        content_type = content_type_of(name, content_type)
        problem = file_problem(name, content_type, data)
        if problem:
            raise ValidationError({"file": problem})
        safe = safe_file_name(name, content_type)
        proof.file_name = (name or safe).rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:200]
        proof.content_type = content_type
        proof.size = len(data)
        proof.sha256 = hashlib.sha256(data).hexdigest()
        proof.file.save(safe, ContentFile(data), save=False)
        from . import precheck

        person = membership.person
        try:
            proof.precheck = precheck.check(
                data,
                content_type,
                first_name=person.first_name,
                last_name=person.last_name,
                birth_date=person.birth_date,
                needed_until=min(on, org.fiscal_start(year)),
            )
        except Exception:  # noqa: BLE001 - Vorprüfung ist nur ein Hinweis
            import logging

            logging.getLogger(__name__).exception("Vorprüfung eines Nachweises fehlgeschlagen")
            proof.precheck = {"level": "yellow", "reasons": ["error"]}
    proof.save()
    from .models import ProofSettings

    cfg = ProofSettings.objects.filter(organization=org).first()
    if (
        cfg is not None
        and cfg.auto_accept
        and proof.file
        and proof.precheck.get("level") == "green"
        and on <= dates.final
    ):
        until = proof.precheck.get("valid_until")
        decide(
            proof,
            "accept",
            None,
            valid_until=datetime.date.fromisoformat(until) if until else None,
            kind=proof.kind or _kind_from_hint(discount, proof.precheck.get("kind_hint")),
            auto=True,
            now=timezone.now(),
        )
    return proof


def _kind_from_hint(discount: ProofDiscount, hint: str | None) -> str:
    kinds = list(discount.kinds or [])
    if not kinds:
        return ""
    if hint == "doctoral":
        return next((k for k in kinds if "dokto" in k.lower() or "promo" in k.lower()), kinds[0])
    return kinds[0]


def decide(
    proof: FeeProof,
    action: str,
    user,
    *,
    valid_until: datetime.date | None = None,
    kind: str | None = None,
    note: str = "",
    auto: bool = False,
    now=None,
) -> FeeProof:
    """Anerkennen, ablehnen oder nachfragen. Nach Anerkennen und Ablehnen ist die Datei weg."""
    from django.utils import timezone
    from rest_framework.exceptions import ValidationError

    note = (note or "").strip()[:500]
    if kind is not None:
        kind = kind.strip()[:100]
        if kind and proof.discount.kinds and kind not in proof.discount.kinds:
            raise ValidationError({"kind": gettext("Unbekannte Art des Nachweises.")})
        proof.kind = kind
    if action == "accept":
        check_valid_until(proof, valid_until)
        proof.valid_until = valid_until
        proof.status = S.ACCEPTED
        assignments = list(
            DiscountAssignment.objects.filter(membership=proof.membership, discount=proof.discount)
        )
        dates = dates_for(
            proof.organization,
            proof.discount,
            proof.year,
            began_in_year(
                proof.organization, proof.year, assignments, list(proof.membership.periods.all())
            ),
        )
        proof.outside_deadline = proof.received_on > dates.final
        proof.note = ""
    elif action == "reject":
        if not note:
            raise ValidationError({"note": gettext("Bitte einen Grund angeben.")})
        proof.status = S.REJECTED
        proof.note = note
    elif action == "question":
        if not note:
            raise ValidationError({"note": gettext("Bitte die Rückfrage eingeben.")})
        proof.status = S.QUESTION
        proof.note = note
    else:
        raise ValidationError({"action": gettext("Unbekannte Entscheidung.")})
    proof.reviewed_by = user if getattr(user, "is_authenticated", False) else None
    proof.reviewed_at = now or timezone.now()
    proof.auto_accepted = auto
    if action in ("accept", "reject"):
        drop_file(proof)
    proof.save()
    from . import notify

    notify.decision(proof)
    return proof
