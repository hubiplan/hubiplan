"""Vollübernahme: Jedes Modell mit Vereinsbezug kommt mit oder steht hier mit Grund
(Gesamtaudit 13.11., V-03).

Ein neues Modul fällt damit auf, statt beim Umzug eines Vereins still zu fehlen.
"""

from pathlib import Path

from django.apps import apps

from datatransfer import tables

# Kommt bewusst nicht mit: Zugänge, Links und Schlüssel gelten nur auf der alten Instanz,
# Aufträge und Protokolle beschreiben deren Betrieb.
NICHT = {
    "music.GuestAccess": "Gastzugang (Link), wird am Ziel neu vergeben",
    "music.RehearsalGuestAccess": "Gastzugang (Link), wird am Ziel neu vergeben",
    "music.MusicReminderTask": "geplante Erinnerung, entsteht am Ziel neu",
    "music.RehearsalNotice": "versandte Benachrichtigung",
    "admission.KioskLink": "Link des Stand-Modus, höchstens sieben Tage gültig",
    "core.DataKey": "Schlüssel der alten Instanz",
    "core.DataKeyRotation": "Schlüsselwechsel der alten Instanz",
    "organizations.InstanceAddress": "Adresse der alten Instanz",
    "audit.AuditEntry": "Protokoll bleibt auf der alten Instanz (Nachweis dort)",
    "audit.AuditCheck": "Prüfkette des Protokolls der alten Instanz",
    "members.PhotoUploadLink": "Link, wird am Ziel neu vergeben",
    "exchange.ExportJob": "Auftrag der alten Instanz",
    "exchange.ImportJob": "Auftrag der alten Instanz",
    "outbox.OutgoingMail": "Postausgang der alten Instanz",
    "portal.PortalAccess": "Zugänge hängen an Konten; Mitglieder werden am Ziel neu eingeladen",
    "portal.LoginLink": "Anmeldelink, kurzlebig",
    "billing.IncomingMailbox": "Zugangsdaten des Postfachs, am Ziel neu einrichten",
    "billing.IncomingMail": "Eingang des Postfachs der alten Instanz",
    "cards.MemberCard": "Ausweise tragen Schlüssel der alten Instanz, am Ziel neu ausstellen",
    "events.PersonalCalendar": "Kalender-Abo (Link), am Ziel neu abonnieren",
    "circulars.InboundMail": "Eingang der Verteiler der alten Instanz",
    "changes.ChangeSet": "Änderungsverlauf der alten Instanz",
    "changes.ChangeRecord": "Änderungsverlauf der alten Instanz",
    "website.WebsiteDomain": "Domain zeigt auf die alte Instanz, am Ziel neu verbinden",
    "website.PreviewLink": "Vorschau-Link, wird am Ziel neu vergeben",
    "meetings.Poll": "Online-Abstimmung; das Ergebnis steht im übernommenen Beschluss",
    "meetings.PollOption": "Online-Abstimmung; das Ergebnis steht im übernommenen Beschluss",
    "meetings.VoteCast": "Wer online abgestimmt hat; das Ergebnis steht im übernommenen Beschluss",
    "meetings.Ballot": "Stimmzettel, geheime ohne Person; das Ergebnis steht im Beschluss",
    "website.ImageUploadLink": "Hochladelink, wird am Ziel neu vergeben",
    "website.HeldMessage": "angehaltene Nachrichten des Kontaktformulars",
    "competitions.StandAccess": "Standzugang (Link), am Ziel neu vergeben",
    "peering.SpinOff": "Ausgründung, gehört zur Kopplung der alten Instanz",
    "oidc.Client": "Anmeldung für Nextcloud, am Ziel neu einrichten",
    "mcpserver.McpGrant": "Freigabe der KI-Schnittstelle, am Ziel neu erteilen",
    "todos.TodoShare": "Freigaben an Konten, am Ziel neu vergeben (wie SECRET_FIELDS todos)",
    "todos.TodoNotice": "versandte Benachrichtigung",
    "todos.TodoReminder": "geplante Erinnerung",
    "todos.TodoPortalGrant": "Freigabe an Zugänge, die nicht mitkommen",
    "todos.TodoRemoteShare": "Freigabe an eine Kopplung der alten Instanz",
    "todos.TodoRemoteTask": "Aufgabe einer Kopplung der alten Instanz",
    # Fachfrage 5 (13.11.): alles Übrige kommt mit, Online-Anträge ausdrücklich nicht
    "admission.ApplicationForm": "Einstellungen des Online-Antrags, am Ziel neu einrichten",
    "admission.Application": "Online-Anträge bleiben auf der alten Instanz",
    "admission.Approval": "Zustimmungen zu Online-Anträgen der alten Instanz",
    "admission.ApplicationEvent": "Verlauf der Online-Anträge der alten Instanz",
    "materials.MaterialRevision": "Änderungsverlauf der alten Instanz (wird dort auch gelöscht)",
    "music.MusicReminderPreference": "Einstellung eines Kontos; Konten kommen nicht mit",
    "todos.TodoReminderConfig": "Erinnerung eines Kontos; Konten kommen nicht mit",
    "todos.TodoProgress": "Verteilung an andere Einheiten, am Ziel neu verteilen",
    "todos.TodoPortalPublication": "Freigabe im Mitgliederbereich, am Ziel neu vergeben",
}


def _fehlend() -> set[str]:
    source = "".join(
        p.read_text(encoding="utf-8") for p in Path(tables.__file__).parent.glob("*.py")
    )
    have = {m.lower() for m in tables.MODULE_MODELS}
    missing = set()
    for model in apps.get_models():
        if not any(f.name == "organization" for f in model._meta.concrete_fields):
            continue
        label = model._meta.label
        # Kernbestand (Mitglieder, Rollen, Einheiten …) hat eigene Export-Bausteine
        if label.lower() in have or model.__name__ in source:
            continue
        missing.add(label)
    return missing


def test_jedes_vereinsmodell_kommt_mit_oder_ist_begruendet():
    assert _fehlend() - set(NICHT) == set()


def test_listen_sind_aktuell():
    # was inzwischen mitkommt, fliegt aus den Listen
    assert set(NICHT) - _fehlend() == set()
