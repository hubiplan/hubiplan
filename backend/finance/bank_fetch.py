"""Bankzugänge: einrichten und Umsätze direkt bei der Bank abrufen (FT1).

Ablauf eines Vorgangs: ``begin`` startet ihn mit der PIN des Nutzers. Verlangt die Bank eine
Freigabe, entsteht ein ``BankTask`` im Zustand „wartet auf Freigabe“; ``proceed`` setzt ihn
mit PIN und TAN fort (bei Freigabe in der App ohne TAN, bis die Bank bestätigt). Die PIN
wird nie gespeichert. Ein angehaltener Dialog verfällt nach ``DIALOG_MINUTES``.

Schutz vor einer Sperre bei der Bank: Nach einer abgelehnten PIN braucht der nächste Versuch
eine ausdrückliche Bestätigung, nach der zweiten ruht der Zugang ``LOCK_HOURS`` Stunden.
"""

from __future__ import annotations

import base64
import datetime
import io
import zipfile
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext

from audit.log import record

from . import bank_import, bankweg, camt, mt940
from .bankweg import BankError
from .models import Account, BankAccess, BankTask

DIALOG_MINUTES = 5
LOCK_HOURS = 24
FIRST_DAYS = 90
OVERLAP_DAYS = 7
BUSY_SECONDS = 150


def available() -> bool:
    return bankweg.fints_available()


def enabled(org) -> bool:
    return available() and bool(org.bank_access_enabled)


def linked_accounts(access: BankAccess) -> list[Account]:
    return list(
        Account.objects.filter(
            organization_id=access.organization_id, bank_access=access, is_active=True
        ).order_by("position", "name")
    )


def expire_tasks(access: BankAccess) -> None:
    """Abgelaufene oder liegen gebliebene Dialoge leeren."""
    now = timezone.now()
    for task in BankTask.objects.filter(access=access, status=BankTask.Status.TAN):
        if task.expires_at is None or task.expires_at <= now:
            _finish(task, BankTask.Status.EXPIRED, gettext("Die Freigabe kam nicht rechtzeitig."))


def _finish(task: BankTask, status: str, message: str = "") -> None:
    task.status = status
    task.dialog = {}
    task.message = message[:300]
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "dialog", "message", "finished_at"])


class _Busy:
    """Höchstens ein Vorgang je Zugang gleichzeitig (auch über mehrere Worker)."""

    def __init__(self, access: BankAccess):
        self.key = f"bankweg:{access.pk}"
        self.held = False

    def __enter__(self):
        self.held = cache.add(self.key, 1, BUSY_SECONDS)
        if not self.held:
            raise BankError(
                "busy", gettext("Für diesen Bankzugang läuft gerade ein anderer Vorgang.")
            )
        return self

    def __exit__(self, *exc):
        if self.held:
            cache.delete(self.key)


def _check_lock(access: BankAccess, confirm_retry: bool) -> None:
    now = timezone.now()
    if access.locked_until and access.locked_until > now:
        raise BankError(
            "paused",
            gettext(
                "Nach zwei abgelehnten Anmeldungen ruht dieser Bankzugang bis {time}, damit die "
                "Bank ihn nicht sperrt. Bitte PIN im Online-Banking der Bank prüfen."
            ).format(time=timezone.localtime(access.locked_until).strftime("%d.%m.%Y %H:%M")),
        )
    if access.failures and not confirm_retry:
        raise BankError(
            "pin_retry",
            gettext(
                "Die letzte Anmeldung hat die Bank abgelehnt. Viele Banken sperren den Zugang "
                "nach drei falschen PINs. Bitte die PIN genau prüfen und den Versuch bestätigen."
            ),
        )


def _note_failure(access: BankAccess, exc: BankError) -> None:
    if exc.code != "pin":
        return
    access.failures += 1
    fields = ["failures"]
    if access.failures >= 2:
        access.locked_until = timezone.now() + datetime.timedelta(hours=LOCK_HOURS)
        fields.append("locked_until")
    access.save(update_fields=fields)


def _note_success(access: BankAccess, state: str | None) -> None:
    access.failures = 0
    access.locked_until = None
    access.last_success = timezone.now()
    if state:
        access.state = state
    access.save(update_fields=["failures", "locked_until", "last_success", "state"])


def fetch_job(access: BankAccess, today: datetime.date | None = None) -> dict:
    today = today or timezone.localdate()
    accounts = []
    for account in linked_accounts(access):
        iban = account.iban.replace(" ", "").upper()
        if not iban:
            continue
        if account.bank_fetched_until:
            start = account.bank_fetched_until - datetime.timedelta(days=OVERLAP_DAYS)
        else:
            start = today - datetime.timedelta(days=FIRST_DAYS)
        accounts.append(
            {"iban": iban, "from": min(start, today).isoformat(), "to": today.isoformat()}
        )
    if not accounts:
        raise BankError(
            "unsupported",
            gettext(
                "Zu diesem Bankzugang gehört noch kein Konto. Bitte beim Konto die IBAN "
                "eintragen und den Zugang neu einrichten."
            ),
        )
    return {"kind": "fetch", "accounts": accounts}


def begin(
    org, access: BankAccess, user, pin: str, kind: str, *, options=None, confirm_retry=False
) -> dict:
    """Vorgang starten. Liefert das Ergebnis für die API (siehe ``_answer``)."""
    if not enabled(org):
        raise BankError("unsupported", gettext("Die Bankanbindung ist nicht eingeschaltet."))
    if kind == BankTask.Kind.FETCH and not access.ready:
        raise BankError("unsupported", gettext("Bitte den Bankzugang zuerst fertig einrichten."))
    _check_lock(access, confirm_retry)
    with _Busy(access):
        expire_tasks(access)
        if kind == BankTask.Kind.SETUP:
            job = {"kind": "setup", **(options or {})}
        else:
            job = fetch_job(access)
        task = BankTask(organization=org, access=access, kind=kind, user=user)
        way = bankweg.get(access.way)
        try:
            step = way.start(access, pin, job)
        except BankError as exc:
            _note_failure(access, exc)
            task.status = BankTask.Status.FAILED
            task.message = exc.message[:300]
            task.finished_at = timezone.now()
            task.save()
            raise
        return _after_step(org, access, task, user, step)


def proceed(org, task: BankTask, user, pin: str, tan: str) -> dict:
    access = task.access
    if not enabled(org):
        raise BankError("unsupported", gettext("Die Bankanbindung ist nicht eingeschaltet."))
    with _Busy(access):
        expire_tasks(access)
        task.refresh_from_db()
        if task.status != BankTask.Status.TAN:
            raise BankError(
                "expired",
                gettext("Der Vorgang ist abgelaufen oder beendet. Bitte neu beginnen."),
            )
        way = bankweg.get(access.way)
        try:
            step = way.resume(access, pin, task.dialog, tan)
        except BankError as exc:
            _note_failure(access, exc)
            _finish(task, BankTask.Status.FAILED, exc.message)
            raise
        return _after_step(org, access, task, user, step)


def cancel(task: BankTask) -> None:
    if task.status == BankTask.Status.TAN:
        _finish(task, BankTask.Status.FAILED, gettext("Abgebrochen."))


def _after_step(org, access: BankAccess, task: BankTask, user, step) -> dict:
    if not step.done:
        task.status = BankTask.Status.TAN
        task.dialog = step.dialog
        task.decoupled = step.decoupled
        task.expires_at = task.expires_at or (
            timezone.now() + datetime.timedelta(minutes=DIALOG_MINUTES)
        )
        task.save()
        return {
            "status": "tan",
            "task": task.pk,
            "challenge": step.challenge,
            "decoupled": step.decoupled,
            "image": step.image,
            "expires_at": task.expires_at.isoformat(),
        }
    result = step.result
    if result.get("need"):
        # Der Nutzer wählt TAN-Verfahren oder Gerät; es ist noch nichts gespeichert außer
        # dem Sitzungsstand
        if step.state:
            access.state = step.state
            access.save(update_fields=["state"])
        if task.pk:
            _finish(task, BankTask.Status.DONE)
        return {
            "status": "choose",
            "need": result["need"],
            "mechanisms": result.get("mechanisms", []),
            "media": result.get("media", []),
            "mechanism": result.get("mechanism", ""),
        }
    _note_success(access, step.state)
    if task.kind == BankTask.Kind.SETUP:
        answer = _setup_done(org, access, user, result)
    else:
        try:
            answer = _fetch_done(org, access, user, result)
        except (ValidationError, camt.CamtError) as exc:
            text = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            task.status = BankTask.Status.FAILED
            task.dialog = {}
            task.message = text[:300]
            task.finished_at = timezone.now()
            task.save()
            raise BankError("import", text) from exc
    task.status = BankTask.Status.DONE
    task.dialog = {}
    task.message = answer.pop("_message", "")[:300]
    task.finished_at = timezone.now()
    task.save()
    return answer


def _setup_done(org, access: BankAccess, user, result: dict) -> dict:
    ibans = [a["iban"].replace(" ", "").upper() for a in result.get("accounts", []) if a["iban"]]
    access.ibans = ibans
    access.tan_mechanism = result.get("mechanism", "")[:10]
    access.tan_mechanism_name = result.get("mechanism_name", "")[:100]
    access.tan_medium = result.get("medium", "")[:100]
    access.ready = True
    access.save(
        update_fields=["ibans", "tan_mechanism", "tan_mechanism_name", "tan_medium", "ready"]
    )
    linked = []
    for account in Account.objects.filter(organization=org, is_active=True):
        iban = account.iban.replace(" ", "").upper()
        if iban and iban in ibans:
            if account.bank_access_id != access.pk:
                account.bank_access = access
                account.save(update_fields=["bank_access"])
            linked.append(iban)
        elif account.bank_access_id == access.pk:
            account.bank_access = None
            account.save(update_fields=["bank_access"])
    record(
        org,
        user,
        "update",
        access,
        {"Bankzugang eingerichtet": [None, f"{len(linked)} Konten verbunden"]},
    )
    return {
        "status": "done",
        "kind": "setup",
        "linked": linked,
        "unlinked": [iban for iban in ibans if iban not in linked],
        "_message": f"{len(linked)} Konten verbunden",
    }


def _decimal(raw) -> Decimal | None:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01")) if raw not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def _merge(parts: list, iban: str, start: datetime.date, end: datetime.date) -> camt.Statement:
    """Alle Antworten der Bank zu einem Konto als ein Auszug über den Abrufzeitraum."""
    merged = camt.Statement(iban=iban)
    for part in parts:
        merged.lines += part.lines
    days = [line.date for line in merged.lines]
    merged.date_from = min([start, *days])
    merged.date_to = max([end, *days])
    dated = [p for p in parts if p.opening is not None and p.date_from is not None]
    if dated:
        merged.opening = min(dated, key=lambda p: p.date_from).opening
    merged.number_occurrences()
    return merged


def _fetch_done(org, access: BankAccess, user, result: dict) -> dict:
    today = timezone.localdate()
    accounts = {a.iban.replace(" ", "").upper(): a for a in linked_accounts(access)}
    job = {a["iban"]: a for a in fetch_job(access, today)["accounts"]}
    raw_files: list[tuple[str, bytes]] = []
    parsed = []
    for entry in result.get("statements", []):
        iban = entry["iban"]
        account = accounts.get(iban)
        if account is None:
            continue
        parts = []
        for number, blob in enumerate(entry.get("camt") or [], start=1):
            data = base64.b64decode(blob)
            raw_files.append((f"{iban}-{number}.xml", data))
            for st in camt.parse_fetched(data):
                if st.iban and st.iban != iban:
                    raise camt.CamtError(
                        gettext(
                            "Die Bank hat Umsätze eines anderen Kontos geliefert ({iban})."
                        ).format(iban=st.iban)
                    )
                parts.append(st)
        if entry.get("mt940"):
            data = base64.b64decode(entry["mt940"])
            raw_files.append((f"{iban}.mt940", data))
            parts.append(mt940.parse(data, iban))
        spec = job.get(iban) or {"from": today.isoformat(), "to": today.isoformat()}
        merged = _merge(
            parts,
            iban,
            datetime.date.fromisoformat(spec["from"]),
            datetime.date.fromisoformat(spec["to"]),
        )
        # Der Saldo der Bank gilt für heute; nur dann taugt er als Endsaldo des Abrufs
        balance = _decimal(entry.get("balance"))
        if balance is not None and merged.date_to == today:
            merged.closing = balance
        parsed.append((merged, account))
    if not parsed:
        return {"status": "done", "kind": "fetch", "lines": 0, "duplicates": 0, "statements": []}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in raw_files:
            zf.writestr(name, data)
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    label = gettext("Abruf vom {date}").format(date=timezone.localtime().strftime("%d.%m.%Y %H:%M"))
    outcome = bank_import.import_file(
        org,
        archive.getvalue(),
        f"{label} ({stamp}).zip" if raw_files else label,
        user,
        parsed=parsed,
        channel=access.way,
    )
    for _statement, account in parsed:
        account.bank_fetched_until = today
        account.save(update_fields=["bank_fetched_until"])
    for st in outcome["statements"]:
        record(
            org,
            user,
            "create",
            st,
            {"Kontoauszug": [None, f"Abruf bei der Bank: {st.line_count} Umsätze eingelesen"]},
        )
    return {
        "status": "done",
        "kind": "fetch",
        "lines": outcome["lines"],
        "duplicates": outcome["duplicates"],
        "statements": [st.pk for st in outcome["statements"]],
        "_message": f"{outcome['lines']} Umsätze eingelesen, {outcome['duplicates']} schon bekannt",
    }
