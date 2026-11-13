"""Vorschläge für eingetragene, gemeinnützige Vereine in Deutschland.

Jeder Verein übernimmt, was passt, und ändert Frist, Wiederholung und Zuständigkeit frei.
Die Hinweise nennen nur die Regel, keine Rechtsberatung. ``month``/``day``: übliche Frist im
Jahr (leer: in einem Monat ab heute).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.utils.translation import gettext, gettext_noop


@dataclass(frozen=True)
class Suggestion:
    key: str
    title: str
    note: str
    interval_months: int | None = 12
    month: int | None = None
    day: int | None = None
    remind_days: int = 30
    trigger: str = "date"
    # Nur für eingetragene Vereine (Impressum: „im Register eingetragen“)
    registered_only: bool = False

    def first_due(self, today: datetime.date) -> datetime.date | None:
        if self.trigger != "date":
            return None
        if self.month and self.day:
            due = datetime.date(today.year, self.month, self.day)
            return due if due > today else due.replace(year=today.year + 1)
        return today + datetime.timedelta(days=30)

    def data(self, today: datetime.date) -> dict:
        due = self.first_due(today)
        return {
            "key": self.key,
            "title": gettext(self.title),
            "note": gettext(self.note),
            "trigger": self.trigger,
            "interval_months": self.interval_months if self.trigger == "date" else None,
            "remind_days": self.remind_days,
            "due_date": due.isoformat() if due else None,
            "registered_only": self.registered_only,
        }


ELECTION_KEY = "register_board"

SUGGESTIONS: tuple[Suggestion, ...] = (
    Suggestion(
        "tax_exemption",
        gettext_noop("Steuererklärung und Freistellungsbescheid"),
        gettext_noop(
            "Gemeinnützige Vereine geben in der Regel alle drei Jahre eine Steuererklärung ab "
            "(mit Anlage Gem). Das Finanzamt prüft dabei die Gemeinnützigkeit und erteilt einen "
            "neuen Freistellungsbescheid. Zuwendungsbestätigungen darf der Verein nur ausstellen, "
            "solange der Bescheid nicht älter als fünf Jahre ist (§ 63 Abs. 5 AO). Die genaue "
            "Frist steht im Schreiben des Finanzamts."
        ),
        interval_months=36,
        month=7,
        day=31,
        remind_days=60,
    ),
    Suggestion(
        "cash_audit",
        gettext_noop("Kassenprüfung vor der Jahreshauptversammlung"),
        gettext_noop(
            "Die Kassenprüfer prüfen Kasse, Konten und Belege des abgelaufenen Jahres und "
            "berichten der Mitgliederversammlung; danach folgt die Entlastung des Vorstands. "
            "Wer prüft und wann, regelt die Satzung."
        ),
        remind_days=45,
    ),
    Suggestion(
        "transparency_register",
        gettext_noop("Angaben im Transparenzregister prüfen"),
        gettext_noop(
            "Eingetragene Vereine stehen mit den Angaben aus dem Vereinsregister im "
            "Transparenzregister. Weichen die wirtschaftlich Berechtigten davon ab (zum Beispiel "
            "nach einer Vorstandswahl vor der Eintragung oder bei besonderen Stimmrechten), muss "
            "der Vorstand sie selbst melden (§ 20 GwG)."
        ),
        registered_only=True,
    ),
    Suggestion(
        ELECTION_KEY,
        gettext_noop("Vorstandsänderung beim Registergericht anmelden"),
        gettext_noop(
            "Jede Änderung des Vorstands ist zum Vereinsregister anzumelden (§ 67 BGB), durch "
            "Vorstandsmitglieder in vertretungsberechtigter Zahl und öffentlich beglaubigt, meist "
            "über einen Notar (§ 77 BGB). Eine Abschrift des Wahlprotokolls gehört dazu. Nach "
            "jeder Wahl in ein Amt, das den Verein vertritt, legt HUBIplan dafür eine Aufgabe an."
        ),
        interval_months=None,
        trigger="election",
        registered_only=True,
    ),
    Suggestion(
        "insurance",
        gettext_noop("Versicherungen prüfen"),
        gettext_noop(
            "Vereinshaftpflicht, Veranstaltungen, Unfallversicherung der Helfer, Gebäude und "
            "Inventar: Passen Deckung und Beiträge noch zu Mitgliederzahl und Vorhaben? "
            "Oft lohnt ein Blick auf die Sammelverträge des Verbands."
        ),
    ),
    Suggestion(
        "membership_report",
        gettext_noop("Bestandsmeldung an Verband oder Sportbund"),
        gettext_noop(
            "Viele Verbände und Landessportbünde erheben einmal im Jahr die Mitgliederzahlen, "
            "oft zum 1. Januar. Davon hängen Beiträge und Zuschüsse ab."
        ),
        month=1,
        day=31,
    ),
    Suggestion(
        "data_protection",
        gettext_noop("Datenschutz prüfen"),
        gettext_noop(
            "Verzeichnis der Verarbeitungstätigkeiten, Datenschutzhinweise, Einwilligungen für "
            "Fotos und die Zugriffsrechte im Vorstand einmal im Jahr durchsehen (Art. 30 DSGVO)."
        ),
    ),
)

BY_KEY = {s.key: s for s in SUGGESTIONS}
