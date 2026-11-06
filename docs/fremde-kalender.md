# Fremde Kalender (Vereinsplaner, iCal)

Eine Einheit (Verein oder Dachverband) übernimmt die Termine eines fremden Kalenders in ihren
eigenen Kalender, z. B. die des Dachverbands, der Vereinsplaner nutzt. Oberfläche:
**Termine › Einrichtung › Fremde Kalender** (Recht „Termine verwalten“). Konzept: `konzepte/fremde-termine.md`
im Projektordner.

## Quellen

| Art | Eingabe | Abruf |
| --- | --- | --- |
| Vereinsplaner | Token (`x-api-token`), bei privaten Tokens zusätzlich Secret (`x-api-secret`) | `GET https://api.vereinsplaner.com/public/v1/resources/public-events`, alle Seiten mit `per_page=100` |
| iCal | `https://`- oder `webcal://`-Link | die Datei; Serien (`RRULE`, `EXDATE`, `RECURRENCE-ID`) werden zu einzelnen Terminen |

Vereinsplaner liefert nur Termine, die der andere Verein dort für die Schnittstelle freigegeben
hat. Token, Secret und Link liegen verschlüsselt (`accounts.mfa.encrypt`), kommen nie zurück an
die Oberfläche und nie ins Änderungsprotokoll. Alle Abrufe laufen über `core/safehttp.py` (keine
internen Adressen, keine Weiterleitungen), Antworten sind begrenzt (JSON 2 MB je Seite, iCal 4 MB,
höchstens 1000 Termine).

## Abgleich

- Celery-Job `events.tasks.sync_external_calendars` stündlich, dazu **Jetzt abrufen** und ein
  Abruf direkt nach dem Anlegen (`events/external.py`).
- Übernommen wird das Fenster 90 Tage zurück bis zwei Jahre voraus.
- Kopien sind gewöhnliche Termine der Einheit mit `Event.external_source` und
  `remote_uid = "ext:<kalender>:<kennung>"`. Wie Verbund-Termine kann sie niemand bearbeiten;
  Zu- und Absagen, Erinnerungen und E-Mails gibt es für sie nicht. Sie gehen nicht nach oben und
  nicht über den Verbund weiter; nach unten je nach Schalter am fremden Kalender.
- Kategorie und Sichtbarkeit stellt der fremde Kalender für alle seine Termine ein; „nach außen
  öffentlich“ bringt sie auch in den öffentlichen Link und auf die Webseite.
- Was die Quelle nicht mehr liefert, verschwindet. Geht ein Abruf schief, bleibt der letzte Stand
  stehen und der Fehler steht am fremden Kalender.
- Liegt der letzte erfolgreiche Abruf 14 Tage zurück (`external.STALE_AFTER`), setzt der nächste
  Fehlschlag `Event.source_stale` an allen Kopien. `Viewer.visible_q()` und die Webseite zeigen
  solche Kopien nicht; gespeichert bleiben sie. Wer in der Einheit Termine verwaltet, bekommt
  dabei einmal eine Mail. Der nächste erfolgreiche Abruf setzt das Feld zurück (Fachfrage FQ22,
  Gesamtaudit 03.11.).
- **Hier ausblenden** am Termin merkt sich die Kennung (`ExternalCalendar.hidden`); der Termin
  bleibt bei jedem Abruf weg, bis jemand ihn unter „Fremde Kalender“ wieder zeigt.
- Abruf aus oder fremden Kalender entfernen: Die Kopien verschwinden.

## API

`/api/orgs/<id>/events/external/` (GET, POST), `…/external/<pk>/` (PATCH, DELETE),
`…/external/<pk>/sync/` (POST), `…/external/<pk>/show/` (POST `{key}`),
`/api/orgs/<id>/events/<pk>/hide/` (POST).
