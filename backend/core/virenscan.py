"""Virenprüfung hochgeladener Dateien mit dem ClamAV des Servers (Fachfrage 4, 31.10.b).

Ist ``CLAMD_SOCKET`` gesetzt (Unix-Socket des clamd auf dem Rechner, in die Container
eingehängt), läuft jede hochgeladene Datei noch während des Hochladens durch clamd
(INSTREAM). Ein Fund lehnt das Hochladen ab und schickt eine Alarm-Mail. Ist clamd nicht
erreichbar, wird ebenfalls abgelehnt (lieber kein Upload als ein ungeprüfter) und gemeldet.
Dateien über ``CLAMD_MAX_BYTES`` (Grenze StreamMaxLength des clamd) bleiben ungeprüft und
werden protokolliert. Ohne ``CLAMD_SOCKET`` (Testserver, Entwicklung) gibt es keine Prüfung.

Vor der Weitergabe an viele (Rundschreiben) oder an alle (öffentliche Dokumente) läuft
jede Datei noch einmal durch clamd, mit den dann aktuellen Signaturen (Fachfrage FQ16,
Audit 02.11.; ``release_ok``). Mit ``VIRUS_SCAN_REQUIRED`` wird dort nichts ungeprüft
weitergegeben: weder ohne eingerichteten Scanner noch bei Dateien über der Grenze.

Quarantäne (Fachfrage 2, Gesamtaudit 10.11.): Eingehende Dokumente (Ansichten mit
``virus_quarantine = True``, z. B. Dokumentenablage, Anhänge, Belege) werden bei
ausgefallenem Scanner nicht mehr abgelehnt, sondern angenommen und gesperrt
(:class:`core.models.QuarantinedFile`). Herunterladen und Weitergeben gehen erst, wenn
``recheck_quarantine`` sie nachgeprüft hat; ein Fund sperrt sie dauerhaft. Mails an
Verteiler bleiben bei ausgefallenem Scanner ungelesen im Sammelpostfach liegen.
"""

from __future__ import annotations

import logging
import socket
import struct

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadhandler import FileUploadHandler
from django.utils.translation import gettext, gettext_lazy
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class VirusFound(APIException):
    status_code = 422
    default_code = "virus_found"
    default_detail = gettext_lazy("Die Datei enthält Schadsoftware und wurde abgelehnt.")


class ScanUnavailable(APIException):
    status_code = 503
    default_code = "scan_unavailable"
    default_detail = gettext_lazy(
        "Die Virenprüfung ist gerade nicht erreichbar. Bitte später noch einmal hochladen."
    )


class NotScanned(APIException):
    status_code = 422
    default_code = "not_scanned"
    default_detail = gettext_lazy(
        "Die Datei konnte nicht auf Viren geprüft werden und wird deshalb nicht weitergegeben."
    )


class Quarantined(APIException):
    status_code = 423
    default_code = "quarantined"
    default_detail = gettext_lazy(
        "Die Datei wartet noch auf die Virenprüfung und ist bis dahin gesperrt. "
        "Bitte später noch einmal versuchen."
    )


class Infected(APIException):
    status_code = 423
    default_code = "infected"
    default_detail = gettext_lazy(
        "In der Datei wurde Schadsoftware gefunden. Sie ist gesperrt und kann nicht "
        "heruntergeladen werden."
    )


class ScanError(Exception):
    pass


# Merker am hochgeladenen File (content_type_extra), wenn die Datei in Quarantäne geht
UPLOAD_MARK = "virenscan"
PENDING = "pending"


def enabled() -> bool:
    return bool(getattr(settings, "CLAMD_SOCKET", ""))


def required() -> bool:
    """Weitergabe nur geprüfter Dateien (Rundschreiben, öffentliche Dokumente)."""
    return bool(getattr(settings, "VIRUS_SCAN_REQUIRED", False))


def max_bytes() -> int:
    return int(getattr(settings, "CLAMD_MAX_BYTES", 25 * 1024 * 1024))


class Stream:
    """Eine INSTREAM-Prüfung bei clamd (Daten in Stücken senden, am Ende Ergebnis lesen)."""

    def __init__(self):
        self.sent = 0
        self.too_big = False
        self.sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(float(getattr(settings, "CLAMD_TIMEOUT", 60)))
            sock.connect(settings.CLAMD_SOCKET)
            sock.sendall(b"zINSTREAM\0")
            self.sock = sock
        except OSError as exc:
            raise ScanError(gettext("clamd nicht erreichbar: {exc}").format(exc=exc)) from exc

    def feed(self, data: bytes) -> None:
        if self.too_big or not data:
            return
        if self.sent + len(data) > max_bytes():
            # Über der Grenze des clamd: nicht weiter senden, Datei bleibt ungeprüft
            self.too_big = True
            self.close()
            return
        try:
            self.sock.sendall(struct.pack("!L", len(data)) + data)
        except OSError as exc:
            self.close()
            raise ScanError(
                gettext("clamd hat die Verbindung beendet: {exc}").format(exc=exc)
            ) from exc
        self.sent += len(data)

    def result(self) -> str | None:
        """None: sauber (oder zu groß); sonst Name des Funds."""
        if self.too_big:
            return None
        try:
            self.sock.sendall(struct.pack("!L", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                part = self.sock.recv(4096)
                if not part:
                    break
                reply += part
        except OSError as exc:
            raise ScanError(gettext("clamd antwortet nicht: {exc}").format(exc=exc)) from exc
        finally:
            self.close()
        text = reply.rstrip(b"\0").decode("utf-8", "replace").strip()
        if text.endswith("OK"):
            return None
        if text.endswith("FOUND"):
            return text.removeprefix("stream:").removesuffix("FOUND").strip() or "unbekannt"
        raise ScanError(gettext("clamd meldet: {x}").format(x=text[:200]))

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


def _alert(subject: str, lines: list[str], key: str) -> None:
    from core.alarm import send_alert

    # Höchstens eine Mail je Art und Stunde (z. B. clamd länger aus)
    if cache.add(f"virenscan-alarm:{key}", 1, 60 * 60):
        send_alert(subject, lines)


def _who(request) -> str:
    user = getattr(request, "user", None) if request is not None else None
    email = getattr(user, "email", "") if user is not None else ""
    path = getattr(request, "path", "") if request is not None else ""
    return f"{email or 'unbekannt'} über {path or '?'}"


def found(name: str, signature: str, request=None) -> None:
    logger.warning("Virenfund beim Hochladen: %s (%s) von %s", name, signature, _who(request))
    from core.alarm import send_alert

    send_alert(
        "Schadsoftware beim Hochladen abgelehnt",
        [f"Datei: {name}", f"Fund: {signature}", f"Von: {_who(request)}"],
    )
    raise VirusFound(f"Die Datei „{name}“ enthält Schadsoftware ({signature}) und wurde abgelehnt.")


def unavailable(exc: Exception, request=None) -> None:
    logger.error("Virenprüfung nicht möglich: %s", exc)
    _alert(
        "Virenprüfung nicht erreichbar",
        [
            f"Fehler: {exc}",
            f"Zuletzt bei: {_who(request)}",
            "Uploads werden abgelehnt, bis clamd wieder antwortet "
            "(ggf. backend und worker neu starten, siehe docs/betrieb.md).",
        ],
        "unavailable",
    )
    raise ScanUnavailable()


def scan_bytes(data: bytes, name: str, request=None) -> None:
    """Inhalt prüfen, der nicht als Upload kommt (z. B. Bild als base64 aus der App)."""
    if not enabled():
        return
    try:
        stream = Stream()
        for start in range(0, len(data), 64 * 1024):
            stream.feed(data[start : start + 64 * 1024])
        signature = stream.result()
    except ScanError as exc:
        unavailable(exc, request)
    if stream.too_big:
        logger.info("Nicht auf Viren geprüft (zu groß): %s, %s Bytes", name, len(data))
    if signature:
        found(name, signature, request)


def quarantine_allowed(request) -> bool:
    """Darf diese Ansicht Uploads bei ausgefallenem Scanner in Quarantäne nehmen?"""
    match = getattr(request, "resolver_match", None)
    func = getattr(match, "func", None)
    for owner in (getattr(func, "cls", None), getattr(func, "view_class", None), func):
        if getattr(owner, "virus_quarantine", False):
            return True
    return False


def _warn_unavailable(exc: Exception, request=None) -> None:
    logger.error("Virenprüfung nicht möglich, Datei in Quarantäne: %s", exc)
    _alert(
        "Virenprüfung nicht erreichbar",
        [
            f"Fehler: {exc}",
            f"Zuletzt bei: {_who(request)}",
            "Eingehende Dokumente bleiben in Quarantäne, andere Uploads werden abgelehnt, "
            "bis clamd wieder antwortet (ggf. backend und worker neu starten, siehe "
            "docs/betrieb.md).",
        ],
        "unavailable",
    )


class ClamavUploadHandler(FileUploadHandler):
    """Erster Upload-Handler: reicht alle Daten weiter und prüft sie nebenbei bei clamd.

    In Ansichten mit ``virus_quarantine`` lehnt ein ausgefallener Scanner (oder Pflicht
    ohne eingerichteten Scanner) nicht ab: Die Datei bekommt einen Merker und geht beim
    Speichern in Quarantäne (``PrivateFieldFile.save``).
    """

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.stream = None
        self.size = 0
        self.held = False
        self.quarantine = quarantine_allowed(self.request)
        if enabled():
            try:
                self.stream = Stream()
            except ScanError as exc:
                self._unavailable(exc)
        elif required() and self.quarantine:
            self._hold()

    def _hold(self) -> None:
        self.held = True
        if isinstance(self.content_type_extra, dict):
            self.content_type_extra[UPLOAD_MARK] = PENDING

    def _unavailable(self, exc: Exception) -> None:
        if not self.quarantine:
            unavailable(exc, self.request)
        _warn_unavailable(exc, self.request)
        if self.stream is not None:
            self.stream.close()
        self.stream = None
        self._hold()

    def receive_data_chunk(self, raw_data, start):
        self.size += len(raw_data)
        if self.stream is not None:
            try:
                self.stream.feed(raw_data)
            except ScanError as exc:
                self._unavailable(exc)
        return raw_data

    def file_complete(self, file_size):
        stream, self.stream = self.stream, None
        if stream is None:
            return None
        try:
            signature = stream.result()
        except ScanError as exc:
            self._unavailable(exc)
            return None
        if signature:
            found(self.file_name, signature, self.request)
        if stream.too_big:
            logger.info(
                "Nicht auf Viren geprüft (über %s Bytes): %s, %s Bytes",
                max_bytes(),
                self.file_name,
                self.size,
            )
            if self.quarantine and required():
                raise NotScanned(
                    gettext(
                        "Die Datei „{name}“ ist zu groß für die Virenprüfung (höchstens {mb} MB)."
                    ).format(name=self.file_name, mb=max_bytes() // (1024 * 1024))
                )
        return None

    def upload_interrupted(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def upload_held(content) -> bool:
    """Trägt die hochgeladene Datei den Quarantäne-Merker des Upload-Handlers?"""
    extra = getattr(content, "content_type_extra", None)
    return isinstance(extra, dict) and extra.get(UPLOAD_MARK) == PENDING


def hold(name: str, org_id: int | None, label: str = "") -> None:
    """Gespeicherte Datei sperren, bis ``recheck_quarantine`` sie geprüft hat."""
    from core.models import QuarantinedFile

    cache.delete(ANY_HELD)
    QuarantinedFile.objects.update_or_create(
        name=name,
        defaults={
            "org_id": org_id,
            "label": label[:200],
            "status": QuarantinedFile.Status.PENDING,
        },
    )
    logger.warning("Datei in Quarantäne bis zur Virenprüfung: %s (%s)", label, name)


# Merker „es gibt überhaupt gesperrte Dateien“, damit Listen ohne Quarantäne keine
# Abfrage je Datei brauchen
ANY_HELD = "virenscan:gesperrt"


def _any_held() -> bool:
    from core.models import QuarantinedFile

    value = cache.get(ANY_HELD)
    if value is None:
        value = QuarantinedFile.objects.exists()
        cache.set(ANY_HELD, value, 60)
    return bool(value)


def ensure_released(file) -> None:
    """Vor dem Herunterladen: gesperrte Dateien (Quarantäne, Fund) nicht ausliefern."""
    name = getattr(file, "name", "") or ""
    if not name:
        return
    from core.models import QuarantinedFile

    status = QuarantinedFile.objects.filter(name=name).values_list("status", flat=True).first()
    if status is None:
        return
    if status == QuarantinedFile.Status.INFECTED:
        raise Infected()
    raise Quarantined()


def counts() -> dict:
    """Anzahl gesperrter Dateien für die Plattformverwaltung."""
    from django.db.models import Count

    from core.models import QuarantinedFile

    rows = QuarantinedFile.objects.values("status").annotate(n=Count("pk"))
    result = {"pending": 0, "infected": 0}
    for row in rows:
        result[row["status"]] = row["n"]
    return result


def scan_state(file) -> str:
    """„“ (frei), „pending“ (wartet auf Prüfung) oder „infected“ (Fund) für die Oberfläche."""
    name = getattr(file, "name", "") or ""
    if not name or not _any_held():
        return ""
    from core.models import QuarantinedFile

    return QuarantinedFile.objects.filter(name=name).values_list("status", flat=True).first() or ""


def recheck_quarantine(limit: int = 200) -> dict:
    """Gesperrte Dateien nachprüfen (regelmäßig im Dienst „beat“).

    Sauber: Sperre fällt weg. Fund: bleibt gesperrt (Status „infected“), Alarm.
    Scanner weiter aus: alles bleibt, wie es ist.
    """
    from django.utils import timezone

    from core.models import QuarantinedFile

    counts = {"released": 0, "infected": 0, "waiting": 0}
    cache.delete(ANY_HELD)
    pending = QuarantinedFile.objects.filter(status=QuarantinedFile.Status.PENDING)
    if not enabled():
        counts["waiting"] = pending.count()
        return counts
    from exchange.models import private_storage

    storage = private_storage()
    # Gesperrte Funde, deren Datei inzwischen gelöscht ist, fallen weg
    for item in QuarantinedFile.objects.filter(status=QuarantinedFile.Status.INFECTED):
        if not storage.exists(item.name):
            item.delete()
    for item in pending.order_by("checked_at", "pk")[:limit]:
        try:
            handle = storage.open(item.name, "rb")
        except FileNotFoundError:
            item.delete()  # Datei inzwischen gelöscht
            continue
        try:
            stream = Stream()
            with handle:
                while chunk := handle.read(64 * 1024):
                    stream.feed(chunk)
                    if stream.too_big:
                        break
            signature = stream.result()
        except ScanError as exc:
            _warn_unavailable(exc)
            counts["waiting"] = pending.count()
            return counts
        item.checked_at = timezone.now()
        item.attempts += 1
        if signature:
            item.status = QuarantinedFile.Status.INFECTED
            item.signature = signature[:200]
            item.save(update_fields=["status", "signature", "checked_at", "attempts"])
            logger.warning("Virenfund in Quarantäne: %s (%s)", item.label, signature)
            from core.alarm import send_alert

            send_alert(
                "Schadsoftware in Quarantäne gefunden",
                [
                    f"Datei: {item.label or item.name}",
                    f"Fund: {signature}",
                    f"Verein: {item.org_id or '-'}",
                    "Die Datei bleibt gesperrt.",
                ],
            )
            counts["infected"] += 1
        elif stream.too_big and required():
            item.signature = gettext("zu groß für die Virenprüfung")
            item.save(update_fields=["signature", "checked_at", "attempts"])
            counts["waiting"] += 1
        else:
            item.delete()
            counts["released"] += 1
    return counts


def inbound_ok(data: bytes, name: str, source: str) -> bool:
    """Datei aus Mail oder Verbund prüfen (Gesamtaudit 01.11., GA-I01).

    False: Schadsoftware gefunden (Alarm ist raus), die Datei wird nicht übernommen.
    Ist der Scanner nicht erreichbar, geht ``ScanUnavailable`` weiter: Die Nachricht
    wird dann später erneut zugestellt bzw. abgewiesen, nicht ungeprüft gespeichert.
    """
    if not enabled() and required():
        # Pflicht ohne Scanner: nichts ungeprüft übernehmen (bleibt in der Warteschlange)
        raise ScanUnavailable()
    try:
        scan_bytes(data, f"{name} ({source})")
    except VirusFound:
        return False
    return True


# Wie lange ein „sauber“ vor der Weitergabe gilt (danach neu mit aktuellen Signaturen)
RELEASE_CLEAN_SECONDS = 6 * 60 * 60


def release_ok(file, name: str, what: str, key: str) -> None:
    """Datei vor der Weitergabe prüfen (Fachfrage FQ16).

    ``file``: Django-Datei (FieldFile), ``key``: eindeutig je Dateistand, für den Merker.
    Fund: ``VirusFound`` mit Alarm. clamd nicht erreichbar: ``ScanUnavailable``.
    Ungeprüft (kein Scanner oder Datei zu groß): mit ``VIRUS_SCAN_REQUIRED``
    ``NotScanned``, sonst durchgelassen und protokolliert. Gesperrte Dateien (Quarantäne)
    gehen nur nach einer sauberen Prüfung hinaus, die dann auch die Sperre aufhebt.
    """
    from core.models import QuarantinedFile

    stored = getattr(file, "name", "") or ""
    held = (
        QuarantinedFile.objects.filter(name=stored).values_list("status", flat=True).first()
        if stored
        else None
    )
    if held == QuarantinedFile.Status.INFECTED:
        raise Infected()
    if not enabled():
        if held is not None:
            raise Quarantined()
        if required():
            logger.error("Weitergabe ohne Virenprüfung abgelehnt: %s (%s)", name, what)
            raise NotScanned(
                gettext(
                    "Die Datei „{name}“ wurde nicht weitergegeben: Die Virenprüfung ist nicht "
                    "eingerichtet."
                ).format(name=name)
            )
        return
    marker = f"virenscan-frei:{key}"
    if held is None and cache.get(marker):
        return
    try:
        stream = Stream()
        with file.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                stream.feed(chunk)
                if stream.too_big:
                    break
        signature = stream.result()
    except ScanError as exc:
        unavailable(exc)
    if signature:
        if held is not None:
            QuarantinedFile.objects.filter(name=stored).update(
                status=QuarantinedFile.Status.INFECTED, signature=signature[:200]
            )
        found(f"{name} ({what})", signature)
    if stream.too_big:
        if held is not None:
            raise Quarantined()
        logger.warning("Vor der Weitergabe nicht geprüft (zu groß): %s (%s)", name, what)
        if required():
            raise NotScanned(
                gettext(
                    "Die Datei „{name}“ ist zu groß für die Virenprüfung und wird deshalb "
                    "nicht weitergegeben."
                ).format(name=name)
            )
        return
    if held is not None:
        QuarantinedFile.objects.filter(name=stored).delete()
        cache.delete(ANY_HELD)
    cache.set(marker, 1, RELEASE_CLEAN_SECONDS)
