"""Umsätze im Format MT940 lesen, so wie deutsche Banken sie über FinTS liefern.

Gelesen werden die Felder :25: (Konto), :60F:/:60M: (Anfangssaldo), :61: (Umsatz),
:86: (Verwendungszweck, strukturiert mit ?00 bis ?63 und den SEPA-Kürzeln EREF+, SVWZ+ …)
und :62F:/:62M: (Endsaldo). Das Ergebnis hat dieselbe Form wie ein CAMT-Kontoauszug
(``camt.Statement``), damit Doppelerkennung und Vorschläge unverändert gelten.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation

from django.utils.translation import gettext

from .camt import MAX_AMOUNT, MAX_LINES, CamtError, Line, Statement

MAX_SIZE = 20 * 1024 * 1024

TAG = re.compile(r"^:(\d{2}[A-Z]?):")
# Wertstellung JJMMTT, Buchungstag MMTT (optional), Soll/Haben (auch Storno RC/RD),
# dritter Buchstabe der Währung (optional), Betrag, Buchungsschlüssel, Referenzen
ENTRY = re.compile(
    r"^(?P<value>\d{6})(?P<entry>\d{4})?(?P<mark>R?[CD])(?P<funds>[A-Z])?"
    r"(?P<amount>\d+,\d{0,2})(?P<type>[A-Z][A-Z0-9]{3})(?P<ref>[^/\n]*)(?://(?P<bank>[^\n]*))?"
)
BALANCE = re.compile(r"^(?P<mark>[CD])(?P<date>\d{6})(?P<ccy>[A-Z]{3})(?P<amount>\d+,\d{0,2})")
SEPA = (
    "EREF",
    "KREF",
    "MREF",
    "CRED",
    "DEBT",
    "SVWZ",
    "ABWA",
    "ABWE",
    "IBAN",
    "BIC",
    "COAM",
    "OAMT",
    "PURP",
)
SEPA_TAG = re.compile(r"^(" + "|".join(SEPA) + r")\+")
# Geschäftsvorfälle für Rücklastschriften
RETURN_CODES = {"108", "109", "159"}


def _amount(raw: str) -> Decimal:
    try:
        value = Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        raise CamtError(gettext("Ungültiger Betrag „{raw}“.").format(raw=raw)) from None
    if not value.is_finite() or value > MAX_AMOUNT:
        raise CamtError(gettext("Ungültiger Betrag „{raw}“.").format(raw=raw))
    return value.quantize(Decimal("0.01"))


def _date(raw: str) -> datetime.date:
    try:
        return datetime.datetime.strptime(raw, "%y%m%d").date()
    except ValueError:
        raise CamtError(gettext("Ungültiges Datum „{raw}“ im Umsatz.").format(raw=raw)) from None


def _entry_date(value: datetime.date, raw: str | None) -> datetime.date:
    """Buchungstag MMTT; das Jahr kommt von der Wertstellung (Jahreswechsel beachten)."""
    if not raw:
        return value
    month, day = int(raw[:2]), int(raw[2:])
    for year in (value.year, value.year + 1, value.year - 1):
        try:
            candidate = datetime.date(year, month, day)
        except ValueError:
            continue
        if abs((candidate - value).days) <= 180:
            return candidate
    return value


def _records(text: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").replace("@@", "\n").split("\n"):
        line = raw.rstrip()
        if not line or line == "-":
            continue
        match = TAG.match(line)
        if match:
            records.append((match.group(1), line[match.end() :]))
        elif records:
            tag, value = records[-1]
            records[-1] = (tag, value + "\n" + line)
    return records


def _details(raw: str) -> dict:
    """Feld :86: zerlegen. Liefert name, iban, purpose, end_to_end, code, extension."""
    flat = raw.replace("\n", "")
    out = {"name": "", "iban": "", "purpose": "", "end_to_end": "", "code": "", "extension": ""}
    if "?" not in flat or not re.match(r"^\d{3}\?", flat):
        out["purpose"] = " ".join(raw.split())
        return out
    out["code"] = flat[:3]
    fields: dict[str, str] = {}
    for part in flat[3:].split("?")[1:]:
        if len(part) >= 2 and part[:2].isdigit():
            fields[part[:2]] = fields.get(part[:2], "") + part[2:]
    purpose_parts = [fields[k] for k in sorted(fields) if "20" <= k <= "29" or "60" <= k <= "63"]
    # SEPA-Kürzel beginnen ein Teilfeld; alles bis zum nächsten Kürzel gehört dazu
    tagged: dict[str, str] = {}
    current = None
    free: list[str] = []
    for part in purpose_parts:
        match = SEPA_TAG.match(part)
        if match:
            current = match.group(1)
            tagged[current] = tagged.get(current, "") + part[match.end() :]
        elif current:
            tagged[current] += part
        else:
            free.append(part)
    purpose = tagged.get("SVWZ", "") if tagged else ""
    if not purpose:
        purpose = "".join(free)
    elif free:
        purpose = "".join(free) + " " + purpose
    out["purpose"] = " ".join(purpose.split())
    e2e = " ".join(tagged.get("EREF", "").split())
    out["end_to_end"] = "" if e2e.upper() == "NOTPROVIDED" else e2e
    out["name"] = " ".join((fields.get("32", "") + fields.get("33", "")).split())
    account = fields.get("31", "").replace(" ", "").upper()
    out["iban"] = account if re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", account) else ""
    out["extension"] = fields.get("34", "").strip()
    return out


def parse(data: bytes, iban: str) -> Statement:
    """Alle Umsätze der Antwort als ein Auszug des Kontos ``iban``."""
    if len(data) > MAX_SIZE:
        raise CamtError(gettext("Die Antwort der Bank ist zu groß."))
    text = data.decode("iso-8859-1")
    statement = Statement(iban=iban)
    last = None
    for tag, value in _records(text):
        if tag in {"60F", "60M"}:
            match = BALANCE.match(value)
            if match and match.group("ccy") != "EUR":
                raise CamtError(
                    gettext("Nur Konten in Euro (Auszug in {currency}).").format(
                        currency=match.group("ccy")
                    )
                )
            if match and statement.opening is None and tag == "60F":
                amount = _amount(match.group("amount"))
                statement.opening = -amount if match.group("mark") == "D" else amount
                statement.date_from = _date(match.group("date"))
        elif tag in {"62F", "62M"}:
            match = BALANCE.match(value)
            if match and tag == "62F":
                amount = _amount(match.group("amount"))
                statement.closing = -amount if match.group("mark") == "D" else amount
                statement.date_to = _date(match.group("date"))
        elif tag == "61":
            first = value.split("\n", 1)[0]
            match = ENTRY.match(first)
            if match is None:
                raise CamtError(
                    gettext("Ein Umsatz der Bank ist nicht lesbar. Eingelesen wurde nichts.")
                )
            value_date = _date(match.group("value"))
            mark = match.group("mark")
            reversal = mark.startswith("R")
            # Storno einer Gutschrift (RC) mindert das Konto, Storno einer Belastung (RD) erhöht es
            credit = (mark[-1] == "C") != reversal
            bank_ref = (match.group("bank") or "").strip()
            last = Line(
                date=_entry_date(value_date, match.group("entry")),
                value_date=value_date,
                amount=_amount(match.group("amount")),
                credit=credit,
                bank_ref=bank_ref[:100],
                return_code="REVERSAL" if reversal else "",
            )
            statement.lines.append(last)
            if len(statement.lines) > MAX_LINES:
                raise CamtError(gettext("Höchstens {n} Umsätze je Datei.").format(n=MAX_LINES))
        elif tag == "86" and last is not None:
            details = _details(value)
            last.name = details["name"][:200]
            last.iban = details["iban"][:34]
            last.purpose = details["purpose"][:500]
            last.end_to_end = details["end_to_end"][:35]
            if not last.return_code and (
                details["code"] in RETURN_CODES or details["extension"].startswith("9")
            ):
                last.return_code = (details["extension"] or "RETURN")[:10]
            last = None
    days = [line.date for line in statement.lines]
    if days:
        statement.date_from = min([*days, statement.date_from or min(days)])
        statement.date_to = max([*days, statement.date_to or max(days)])
    statement.number_occurrences()
    return statement
