"""Vorschläge für das Verzeichnis der Verarbeitungstätigkeiten (Art. 30 Abs. 1 DSGVO).

Je eingeschaltetem Modul eine Tätigkeit mit Zweck, Rechtsgrundlage, Betroffenen, Daten,
Empfängern und Löschfrist. Fristen und Rechtsgrundlagen folgen docs/aufbewahrung.md; wer dort
etwas ändert, passt den Katalog mit an. ``module`` leer: gilt für jeden Verein. Ein Vorschlag,
keine Rechtsberatung.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext, gettext_noop


@dataclass(frozen=True)
class Activity:
    key: str
    module: str
    title: str
    purpose: str
    legal_basis: str
    subjects: str
    categories: str
    recipients: str
    retention: str

    def data(self) -> dict:
        return {
            "key": self.key,
            "module": self.module,
            "title": gettext(self.title),
            "purpose": gettext(self.purpose),
            "legal_basis": gettext(self.legal_basis),
            "subjects": gettext(self.subjects),
            "categories": gettext(self.categories),
            "recipients": gettext(self.recipients),
            "third_country": gettext("keine"),
            "retention": gettext(self.retention),
        }


MEMBERS_SUBJECTS = gettext_noop("Mitglieder, ehemalige Mitglieder, Erziehungsberechtigte")
NOBODY = gettext_noop("keine Weitergabe außerhalb des Vereins")

ACTIVITIES: tuple[Activity, ...] = (
    Activity(
        "members",
        "members",
        gettext_noop("Mitgliederverwaltung"),
        gettext_noop("Begründung und Durchführung der Mitgliedschaft nach der Satzung"),
        gettext_noop("Art. 6 Abs. 1 lit. b DSGVO (Mitgliedschaft)"),
        MEMBERS_SUBJECTS,
        gettext_noop(
            "Name, Anschrift, Geburtsdatum, Kontaktdaten, Mitgliedsart, Eintritt und Austritt, "
            "Ämter, Zusatzfelder"
        ),
        gettext_noop(
            "Vorstand und berechtigte Funktionsträger; übergeordnete Verbände, soweit "
            "die Satzung eine Meldung vorsieht"
        ),
        gettext_noop(
            "Nach Ende der Mitgliedschaft und Ablauf der Löschfrist (Standard 24 Monate) gelöscht; "
            "Name, Geburtsjahr und Mitgliedszeiten bleiben für die Vereinsgeschichte"
        ),
    ),
    Activity(
        "admission",
        "members",
        gettext_noop("Mitgliedsanträge"),
        gettext_noop("Aufnahme neuer Mitglieder, auch über den Online-Antrag"),
        gettext_noop("Art. 6 Abs. 1 lit. b DSGVO (Anbahnung der Mitgliedschaft)"),
        gettext_noop("Antragsteller, Erziehungsberechtigte"),
        gettext_noop("Angaben des Antrags, Unterschrift, gegebenenfalls SEPA-Mandat"),
        NOBODY,
        gettext_noop(
            "Angaben nach der Antragsfrist entfernt, das PDF mit den Mitgliedsdaten gelöscht"
        ),
    ),
    Activity(
        "fees",
        "billing",
        gettext_noop("Beiträge, Rechnungen und Lastschrift"),
        gettext_noop("Erhebung der Beiträge und Gebühren, Einzug per SEPA-Lastschrift"),
        gettext_noop("Art. 6 Abs. 1 lit. b und c DSGVO, § 147 AO"),
        gettext_noop("Mitglieder, Zahler von Haushalten, Kunden"),
        gettext_noop("Name, Anschrift, Kontoverbindung, Mandatsreferenz, Beträge, Zahlungsstand"),
        gettext_noop("Kreditinstitut des Vereins, Steuerberater, Finanzamt bei Prüfungen"),
        gettext_noop(
            "Rechnungen 8 Jahre, SEPA-Mandate mit den Büchern; danach Kontodaten anonymisiert"
        ),
    ),
    Activity(
        "finance",
        "finance",
        gettext_noop("Buchführung und Kasse"),
        gettext_noop("Ordnungsgemäße Buchführung und Nachweis gegenüber dem Finanzamt"),
        gettext_noop("Art. 6 Abs. 1 lit. c DSGVO, § 147 AO"),
        gettext_noop("Mitglieder, Geschäftspartner, Spender"),
        gettext_noop("Namen in Buchungen und Belegen, Beträge, Kontoauszüge"),
        gettext_noop("Kassenprüfer, Steuerberater, Finanzamt"),
        gettext_noop("Belege nach 8 Jahren gelöscht, Bücher nach 10 Jahren anonymisiert"),
    ),
    Activity(
        "expenses",
        "expenses",
        gettext_noop("Auslagenerstattung"),
        gettext_noop("Erstattung von Auslagen der Mitglieder"),
        gettext_noop("Art. 6 Abs. 1 lit. b und c DSGVO, § 147 AO"),
        gettext_noop("Mitglieder"),
        gettext_noop("Name, Kontoverbindung, Belege, Beträge"),
        gettext_noop("Kreditinstitut des Vereins, Kassenprüfer"),
        gettext_noop(
            "Ausgezahlt wie Belege und Bücher; abgelehnt: Belege und Bankverbindung nach 6 Monaten"
        ),
    ),
    Activity(
        "donations",
        "donations",
        gettext_noop("Spenden und Zuwendungsbestätigungen"),
        gettext_noop("Ausstellung von Zuwendungsbestätigungen nach amtlichem Muster"),
        gettext_noop("Art. 6 Abs. 1 lit. c DSGVO, § 50 EStDV"),
        gettext_noop("Spender"),
        gettext_noop("Name, Anschrift, Betrag, Datum der Zuwendung"),
        gettext_noop("Finanzamt bei Prüfungen"),
        gettext_noop("Wie Belege: 8 Jahre"),
    ),
    Activity(
        "partners",
        "",
        gettext_noop("Geschäftspartner"),
        gettext_noop("Zusammenarbeit mit Lieferanten, Dienstleistern und Sponsoren"),
        gettext_noop("Art. 6 Abs. 1 lit. b und f DSGVO"),
        gettext_noop("Ansprechpartner von Geschäftspartnern"),
        gettext_noop("Name, Funktion, Kontaktdaten, Vereinbarungen"),
        NOBODY,
        gettext_noop("Bis zum Ende der Zusammenarbeit; Belege wie in der Buchführung"),
    ),
    Activity(
        "events",
        "events",
        gettext_noop("Termine und Rückmeldungen"),
        gettext_noop("Planung von Terminen, Zu- und Absagen"),
        gettext_noop("Art. 6 Abs. 1 lit. b DSGVO"),
        gettext_noop("Mitglieder"),
        gettext_noop("Name, Rückmeldung, Bemerkung"),
        NOBODY,
        gettext_noop("Bemerkungen mit den Mitgliedsdaten gelöscht"),
    ),
    Activity(
        "registrations",
        "registrations",
        gettext_noop("Anmeldungen zu Veranstaltungen"),
        gettext_noop("Anmeldung, Teilnahmegebühr und Einlass bei Veranstaltungen"),
        gettext_noop("Art. 6 Abs. 1 lit. b DSGVO"),
        gettext_noop("Teilnehmende, auch Gäste"),
        gettext_noop("Name, Kontaktdaten, Antworten auf Fragen, Zahlung, Einlass"),
        NOBODY,
        gettext_noop("Nach der Veranstaltung und dem Zahlungsnachweis wie Belege"),
    ),
    Activity(
        "meetings",
        "meetings",
        gettext_noop("Versammlungen"),
        gettext_noop("Einladung, Anwesenheit, Abstimmungen und Protokoll nach der Satzung"),
        gettext_noop("Art. 6 Abs. 1 lit. b und c DSGVO"),
        gettext_noop("Mitglieder"),
        gettext_noop("Name, Anwesenheit, Vollmachten, Wortmeldungen im Protokoll"),
        gettext_noop("Registergericht (Protokollauszug bei Vorstandswahlen)"),
        gettext_noop("Protokolle dauerhaft als Vereinsunterlage"),
    ),
    Activity(
        "training",
        "training",
        gettext_noop("Training und Anwesenheit"),
        gettext_noop(
            "Anwesenheit bei Übungsabenden und Trainings für Übungsleiterabrechnung und "
            "Zuschüsse; bei Sportschützen das Schießbuch als Nachweis für das waffenrechtliche "
            "Bedürfnis (§ 14 WaffG)"
        ),
        gettext_noop("Art. 6 Abs. 1 lit. b und c DSGVO"),
        gettext_noop("Mitglieder"),
        gettext_noop("Name, Anwesenheit; Schießtermine mit Disziplin, Waffenart und Kaliber"),
        gettext_noop("Schießsportverband und Waffenbehörde (Bestätigung auf Antrag)"),
        gettext_noop("nach zehn Jahren gelöscht, mit den Mitgliedsdaten früher"),
    ),
    Activity(
        "helpers",
        "helpers",
        gettext_noop("Helferdienste"),
        gettext_noop("Einteilung von Helferinnen und Helfern bei Veranstaltungen"),
        gettext_noop("Art. 6 Abs. 1 lit. b DSGVO"),
        gettext_noop("Mitglieder und Helfer ohne Mitgliedschaft"),
        gettext_noop("Name, Telefon, Schicht"),
        NOBODY,
        gettext_noop("Name und Telefon mit den Mitgliedsdaten gelöscht"),
    ),
    Activity(
        "circulars",
        "circulars",
        gettext_noop("Rundschreiben und Glückwünsche"),
        gettext_noop("Information der Mitglieder per Mail, Brief und App"),
        gettext_noop("Art. 6 Abs. 1 lit. b und f DSGVO"),
        gettext_noop("Mitglieder"),
        gettext_noop("Name, Anschrift, Mailadresse, Geburtstag und Jubiläum bei Glückwünschen"),
        gettext_noop("Mail-Dienst der Instanz"),
        gettext_noop(
            "Mailtexte im Postausgang nach 30 Tagen geleert; Empfängerdaten mit den "
            "Mitgliedsdaten gelöscht"
        ),
    ),
    Activity(
        "website",
        "website",
        gettext_noop("Vereinswebseite"),
        gettext_noop("Öffentliche Darstellung des Vereins, Kontaktformular"),
        gettext_noop("Art. 6 Abs. 1 lit. a und f DSGVO"),
        gettext_noop("Mitglieder mit Funktion, Abgebildete, Besucher der Webseite"),
        gettext_noop(
            "Name und Funktion, Fotos mit Einwilligung, Anfragen über das Kontaktformular"
        ),
        gettext_noop("Öffentlichkeit (nur veröffentlichte Inhalte)"),
        gettext_noop("Bis zum Widerruf bzw. Widerspruch; Kontaktformular nach 7 Tagen geleert"),
    ),
    Activity(
        "honors",
        "honors",
        gettext_noop("Ehrungen und Vereinsgeschichte"),
        gettext_noop("Ehrungen, Würden und Chronik des Vereins"),
        gettext_noop("Art. 6 Abs. 1 lit. f DSGVO (Vereinsgeschichte)"),
        gettext_noop("Mitglieder und ehemalige Mitglieder"),
        gettext_noop("Name, Ehrung oder Würde, Jahr, Fotos mit Einwilligung"),
        gettext_noop("Öffentlichkeit, soweit in der Chronik auf der Webseite"),
        gettext_noop("Dauerhaft; Namen auf Widerspruch entfernt"),
    ),
    Activity(
        "competitions",
        "competitions",
        gettext_noop("Wettbewerbe und Ergebnisse"),
        gettext_noop("Durchführung von Wettbewerben und Veröffentlichung der Ergebnisse"),
        gettext_noop("Art. 6 Abs. 1 lit. b und f DSGVO"),
        gettext_noop("Teilnehmende"),
        gettext_noop("Name, Mannschaft, Ergebnisse"),
        gettext_noop("Verband, Öffentlichkeit bei veröffentlichten Ergebnissen"),
        gettext_noop("Dauerhaft als Vereinsgeschichte; Namen auf Widerspruch entfernt"),
    ),
    Activity(
        "qualifications",
        "qualifications",
        gettext_noop("Qualifikationen"),
        gettext_noop("Nachweis von Übungsleiter-, Trainer- und Sachkundescheinen"),
        gettext_noop("Art. 6 Abs. 1 lit. b und c DSGVO"),
        gettext_noop("Mitglieder mit Qualifikation"),
        gettext_noop("Art der Qualifikation, Gültigkeit, Nachweis"),
        gettext_noop("Verband bei Zuschussanträgen"),
        gettext_noop("Mit den Mitgliedsdaten gelöscht"),
    ),
    Activity(
        "api",
        "api",
        gettext_noop("Weitergabe über die API für andere Programme"),
        gettext_noop(
            "Abgleich mit angebundenen Programmen, zum Beispiel Verbandssoftware oder "
            "Fachsoftware, über einzeln freigegebene API-Zugänge"
        ),
        gettext_noop(
            "Art. 6 Abs. 1 lit. b oder f DSGVO; bei Dienstleistern Vertrag nach Art. 28 DSGVO"
        ),
        MEMBERS_SUBJECTS,
        gettext_noop(
            "Je Zugang gewählt: Name, Geburtsdatum, Mitgliedsnummer, Kontakt und Anschrift, "
            "Mitgliedschaft, Untereinheiten, Ehrungen, Qualifikationen"
        ),
        gettext_noop(
            "Die an den API-Zugängen benannten Geschäftspartner (Einstellungen › API-Zugänge)"
        ),
        gettext_noop(
            "Abrufprotokoll 90 Tage; beim Empfänger nach dessen Vertrag oder Rechtsgrundlage"
        ),
    ),
    Activity(
        "accounts",
        "",
        gettext_noop("Benutzerkonten und Anmeldung"),
        gettext_noop("Zugang zu HUBIplan, Mitgliederbereich und App"),
        gettext_noop("Art. 6 Abs. 1 lit. b DSGVO, Art. 32 DSGVO"),
        gettext_noop("Mitglieder und Funktionsträger mit Zugang"),
        gettext_noop("Anmelde-E-Mail, Passkeys, Zwei-Faktor-Daten, Geräte, Anmeldezeitpunkte"),
        gettext_noop("Betreiber der HUBIplan-Instanz (Hosting)"),
        gettext_noop("90 Tage nach Ende des letzten Zugangs gelöscht; Geräte nach 180 Tagen"),
    ),
    Activity(
        "audit",
        "",
        gettext_noop("Änderungsprotokoll und Sicherungen"),
        gettext_noop("Nachvollziehbarkeit von Änderungen, Wiederherstellung"),
        gettext_noop("Art. 6 Abs. 1 lit. c und f DSGVO, Art. 32 DSGVO"),
        MEMBERS_SUBJECTS,
        gettext_noop("Geänderte Werte, Bearbeiter, Zeitpunkt; Sicherungskopien aller Daten"),
        gettext_noop("Betreiber der HUBIplan-Instanz (Hosting)"),
        gettext_noop(
            "Inhalte zu einer Person mit deren Löschung geleert; Sicherungen nach 30 Tagen"
        ),
    ),
)

BY_KEY = {a.key: a for a in ACTIVITIES}

DEFAULT_TOMS = gettext_noop(
    "Zugang nur mit persönlichem Konto, Zwei-Faktor-Anmeldung für Funktionsträger; Rechte je "
    "Rolle nach dem Bedarf des Amts; verschlüsselte Übertragung (HTTPS); verschlüsselte "
    "Speicherung besonders schützenswerter Felder; Trennung der Vereine in der Datenbank "
    "(Zeilenschutz); Änderungsprotokoll; tägliche Sicherung; automatische Löschung nach "
    "festen Fristen."
)


def suggestions(org) -> list[Activity]:
    modules = set(org.enabled_modules or [])
    return [a for a in ACTIVITIES if not a.module or a.module in modules]
