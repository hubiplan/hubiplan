# Anmeldung an der Nextcloud mit dem HUBIplan-Konto

App `backend/oidc`, Seite Einstellungen › Nextcloud (`frontend/src/pages/settings/NextcloudPage.tsx`),
Anmeldeseite `/oidc/anmelden` (`frontend/src/pages/NextcloudLoginPage.tsx`), Abmeldeseite
`/oidc/abmelden` (`frontend/src/pages/NextcloudLogoutPage.tsx`).
Konzept: `konzepte/nextcloud-anbindung.md` im Projektordner (Schritt N6).

HUBIplan ist Anmeldedienst nach OpenID Connect. Die Nextcloud eines Vereins (oder
Dachverbands) nutzt die offizielle App **„OpenID Connect user backend“ (`user_oidc`)**.
Wer sich dort mit „Mit HUBIplan anmelden“ anmeldet, landet kurz bei HUBIplan
(Anmeldung wie immer, mit Zwei-Faktor-Anmeldung, falls eingerichtet) und kommt ohne
Rückfrage zurück. Die Nextcloud legt das Konto bei der ersten Anmeldung selbst an und
übernimmt die Gruppen.

## Wer darf hinein

Nur, was bei der eintragenden Einheit gilt (Rechte höherer Einheiten zählen nicht):

- aktive Rollen der Einheit am Benutzerkonto (Vorstand, Kassierer, …),
- Ämter in Untereinheiten (z. B. Zugführer) über die eigene Mitgliedschaft,
- bei „Nur Rollen dieser Einheit“ zählen Ämter in Untereinheiten nicht (weder für den
  Zugang noch als Gruppe),
- bei „zusätzlich Mitglieder mit Zugang“ (nur Vereine): jedes Konto mit
  Mitgliederzugang und laufender Mitgliedschaft.

Austritt, Ende der Rolle oder gesperrtes Konto: Die nächste Anmeldung scheitert. Laufende
Nextcloud-Sitzungen endet HUBIplan nur mit „Konten automatisch deaktivieren“ (siehe unten und
„Wie lange eine Anmeldung gilt“); sonst das Konto in der Nextcloud von Hand deaktivieren.

Optional „nur mit Zwei-Faktor-Anmeldung“: Die HUBIplan-Sitzung muss mit zweitem Faktor
entstanden sein (`amr` enthält `mfa`), sonst erklärt die Anmeldeseite, was zu tun ist.

## Was die Nextcloud erfährt

Im ID-Token und unter `userinfo` (je nach angefragtem `scope`):

| Angabe | Inhalt |
|---|---|
| `sub` | Kennung je Dienst (HMAC aus Benutzernummer und Salz des Eintrags), 32 Zeichen; zwei Dienste können Nutzer darüber nicht zusammenführen |
| `name`, `given_name`, `family_name` | aus der Mitgliedsakte, sonst aus dem Konto |
| `preferred_username` | nur bei Eintrag unter „Bisherige Benutzernamen“ (Scope `profile`): der vorhandene Benutzername in der Nextcloud |
| `email` | Anmelde-E-Mail |
| `groups` | je nach Einstellung „Vorstand“, Rollennamen bzw. die unter „Gruppen für einzelne Rollen“ eingetragenen Gruppen, „Amt (Untereinheit)“, Namen der Untereinheiten, „Mitglieder“ (höchstens 64 Zeichen je Name) |
| `amr`, `auth_time` | wie und wann die HUBIplan-Sitzung angemeldet wurde |

Gruppennamen sind fest (nicht übersetzt). Wird eine Rolle oder Untereinheit umbenannt,
entsteht in der Nextcloud eine neue Gruppe; Freigaben dort ggf. anpassen.

### Gruppen für einzelne Rollen

Unter „Gruppen für einzelne Rollen anpassen“ bekommt jede Rolle (auch Ämter in
Untereinheiten) ein Feld für ihre Gruppen in der Nextcloud, mehrere mit Komma. Beispiel:
„1. Kassierer“ und „2. Kassierer“ beide `Kassierer`, „1. Vorsitzender“ `Kassierer,
Schriftführer`. Mit Eintrag gehen nur diese Gruppen mit (auch wenn „je Rolle eine Gruppe“
aus ist), ohne Eintrag wie bisher der Rollenname. Gespeichert wird an der Rolle selbst
(`role_groups`: Rollen-ID → Gruppen), Umbenennen ändert also nichts; gelöschte Rollen fallen
beim nächsten Speichern weg.

Damit `user_oidc` diese Gruppen verwaltet, sie in die Whitelist aufnehmen, z. B.
`/^(HUBIplan|Vorstand|Kassierer|Schriftführer)$/u`. Gruppen außerhalb der Whitelist (etwa
Ordnergruppen, die von Hand gepflegt werden) bleiben unberührt. Vorher vergleichen, wer heute
in diesen Gruppen ist: Wer keine passende Rolle hat, fällt bei der nächsten Anmeldung heraus
und verliert die Gruppenordner.

## Vorhandene Nextcloud-Konten übernehmen

Gibt es die Nextcloud schon, legt `user_oidc` sonst bei der ersten Anmeldung ein neues,
leeres Konto an. Damit jemand in seinem bisherigen Konto landet, trägt die Einheit unter
„Bisherige Benutzernamen“ je Zeile `Anmelde-E-Mail = Benutzername` ein (z. B.
`maria.muster@example.org = mmuster`). HUBIplan schickt dann `preferred_username`.

In der Nextcloud dazu beim Anbieter:

- Benutzer-ID-Zuordnung (`mapping-uid`): `preferred_username`,
- „Eindeutige Benutzer-ID verwenden“ aus (`--unique-uid=0`), sonst bildet `user_oidc`
  eine Prüfsumme statt des Namens,
- in der `config.php` „soft auto provisioning“ an (`occ config:system:set user_oidc soft_auto_provision --type=boolean --value=true`),
  damit ein vorhandenes Konto mit diesem Namen übernommen statt abgelehnt wird.

Die Liste wird bewusst von Hand gepflegt und nicht aus Vor- und Nachnamen abgeleitet:
Sonst könnte jemand mit einer Namensänderung in HUBIplan ein fremdes Konto bekommen. Wer
die Liste ändern darf („Rollen und Rechte verwalten“), kann damit jede Person mit jedem
Nextcloud-Konto verbinden, also nur eintragen, was sicher dieselbe Person ist. Nicht
aufgeführte Personen bekommen wie bisher ein neues Konto mit der Kennung `sub`.

Die Gruppen-Provisionierung von `user_oidc` setzt die Gruppen bei jeder Anmeldung neu.
Gruppen, die nur in der Nextcloud gepflegt werden (z. B. `admin`), vorher prüfen.

## Konten automatisch deaktivieren

Endet der Zugang bei HUBIplan (Rolle oder Amt beendet, Austritt, Konto gesperrt), scheitert nur
die nächste Anmeldung; Sitzungen, Sync-Apps (App-Passwörter) und alte Nextcloud-Passwörter
gingen weiter. Mit „Konten automatisch deaktivieren“ deaktiviert HUBIplan das Konto in der
Nextcloud selbst (OCS Provisioning API, `PUT /ocs/v2.php/cloud/users/<name>/disable`); das
beendet auch Sitzungen und App-Passwörter. Bekommt die Person wieder Zugang, aktiviert HUBIplan
das Konto wieder, aber nur, wenn HUBIplan es selbst deaktiviert hat. Dateien bleiben.

- Angefasst werden nur Konten, die sich über HUBIplan angemeldet haben (Tabelle `oidc_account`,
  unter RLS; Benutzername = bisheriger Name aus der Liste, sonst `sub`). `admin` und Konten
  ohne Anmeldung über HUBIplan nie.
- Auslöser: Änderung an Rolle, Amt, Mitgliederzugang, Mitgliedschaftszeitraum oder Konto
  (Hintergrundauftrag `oidc.tasks.sync_user`) und jede Nacht `oidc.tasks.sync_all` (auch
  Rollen, die zu einem Datum enden). Grundlage ist dieselbe Prüfung wie bei der Anmeldung.
- Obergrenze: Würde ein Lauf mehr als 3 Konten oder mehr als die Hälfte auf einmal
  deaktivieren, hält er an (Hinweis auf der Seite, E-Mail). „Jetzt abgleichen“ auf der Seite
  bestätigt dann von Hand.
- Jede Änderung ins Änderungsprotokoll und per E-Mail an alle mit „Rollen und Rechte
  verwalten“ in der Einheit. Die Seite zeigt je Konto, was der nächste Abgleich täte.

Einrichtung in der Nextcloud:

1. Gruppe anlegen, z. B. `HUBIplan`, und in HUBIplan als „Gruppe der Konten über HUBIplan“
   eintragen. HUBIplan schickt sie bei jeder Anmeldung mit.
2. Beim Anbieter „Gruppen-Provisionierung“ an, Gruppen-Zuordnung `groups`, Whitelist
   `/^HUBIplan$/` (mit Schrägstrichen, sonst greift sie nicht). Dann setzt `user_oidc` nur
   diese Gruppe; alle anderen Gruppen (auch `admin`) bleiben, wie sie sind.
3. Eigenes Konto `hubiplan-dienst` anlegen, als Gruppen-Admin der Gruppe `HUBIplan`
   eintragen, angemeldet ein App-Passwort erzeugen (Persönliche Einstellungen › Sicherheit).
   Benutzername und App-Passwort in HUBIplan eintragen („Verbindung prüfen“). Das Passwort
   wird verschlüsselt gespeichert (`MFA_ENCRYPTION_KEY`) und nie wieder angezeigt.
4. Konten, die schon vorher da waren, kommen bei ihrer nächsten Anmeldung über HUBIplan in die
   Gruppe. Erst dann kann das Dienstkonto sie deaktivieren.

## Gruppen laufend abgleichen

`user_oidc` setzt Gruppen nur beim Anmelden. Endet eine Rolle, bleibt das Konto aber aktiv (andere
Rolle, Mitgliederzugang), behielt die Person die Gruppe samt Gruppenordnern und geteilten
Kalendern; Sync-Apps melden sich nie neu an. Mit „Gruppen laufend abgleichen“ (`sync_groups`)
setzt HUBIplan die Gruppen selbst (`oidc/nc_groups.py`, OCS Provisioning API
`GET/POST/DELETE /ocs/v2.php/cloud/users/<name>/groups`).

- Abgeglichen werden nur die Gruppen unter „Gruppen, die HUBIplan abgleicht“
  (`sync_groups_list`) und die Kontengruppe (`Client.managed_groups()`), nie `admin`. Von Hand
  gepflegte Gruppen (z. B. Ordnergruppen) bleiben unberührt.
- Soll ist dieselbe Berechnung wie im Token (`claims.profile`). Wer keinen Zugang mehr hat,
  behält nur die Kontengruppe, damit das Dienstkonto das Konto weiter verwalten kann (die
  Nextcloud lässt einen Gruppen-Admin niemanden aus seiner letzten Gruppe nehmen).
- Nur Konten, die sich über HUBIplan angemeldet haben (`oidc_account`), ohne Verwaltungs- und
  Dienstkonten.
- Auslöser wie beim Kontenabgleich (Rolle, Amt, Mitgliederzugang, Mitgliedschaftszeitraum, Konto)
  und zusätzlich Wechsel der Untereinheit; nach dem Speichern der Einstellungen
  (`oidc.tasks.sync_client_groups`); jede Nacht mit `oidc.tasks.sync_all`.
- Obergrenze: Verlören mehr als 3 Konten (oder mehr als die Hälfte) auf einmal Gruppen, hält der
  Lauf an (Hinweis, Mail an alle mit „Rollen und Rechte verwalten“); „Gruppen jetzt abgleichen“
  bestätigt. Jede Änderung im Änderungsprotokoll und per Mail.
- „Gruppen vergleichen“ (`GET …/nextcloud/<eintrag>/groups/`) zeigt Soll und Ist je Konto und,
  soweit die Nextcloud es dem Dienstkonto verrät (`subadmin` in `cloud/user`), Gruppen ohne
  Gruppen-Admin-Recht. Es ändert nichts.
- Einschalten und Ändern der Liste verlangen eine frische Bestätigung; dafür braucht es
  Dienstkonto, App-Passwort und Kontengruppe.

Einrichtung: Dienstkonto in der Nextcloud zum Gruppen-Admin jeder abgeglichenen Gruppe machen
(Benutzerverwaltung › Konto › „Gruppen-Admin für“). Vorher mit „Gruppen vergleichen“ prüfen, wer
herausfiele: Wer heute von Hand in einer abgeglichenen Gruppe steht, ohne die Rolle zu haben,
verliert sie. Ordnerrechte ohne Amt besser über eigene, nicht abgeglichene Gruppen vergeben.

## Dateien ablegen und übernehmen

`oidc/nc_files.py` (WebDAV `remote.php/dav/files/<dienstkonto>/`, Freigaben über
`apps/files_sharing/api/v1/shares`), Schnittstelle `oidc/files_views.py`.

**In Nextcloud ablegen** (`files_enabled`): Knopf neben Kassenbericht (Jahresabschluss und
Übersicht), Steuerauswertung, Kassenzählung, Protokoll (freigegeben), Beschlussbuch und Dokumenten
der Ablage (`components/NextcloudFiles.tsx`, `NextcloudSave`). Der Browser holt die Datei wie beim
Herunterladen und schickt sie an `POST /api/orgs/<id>/nextcloud-dateien/` (Ziel, Art, Dateiname).

- Ziele: Ordner `<files_root>/Vorstand`, `…/Kasse`, `…/Mitglieder` im Dienstkonto, je nur lesend
  (Recht 1) an eine Gruppe freigegeben (`files_board_group`, `files_finance_group`,
  `files_members_group`, voreingestellt `Vorstand`, `Kassierer`, `Mitglieder`). Andere Gruppe:
  HUBIplan nimmt seine alte Freigabe zurück (`files_shares`). Von Hand erweiterte Rechte setzt der
  nächste Upload auf „lesen“ zurück.
- Ablegen dürfen: Vorstand `docs.manage`, `finance.view` oder `roles.manage`; Kasse
  `finance.view`; Mitglieder `docs.manage`.
- Nie überschreiben (`If-None-Match: *`, sonst „name (2).pdf“), höchstens 50 MB.
- Frist je Art (`FileItem.category`, Entscheidung 20.11.): Beschlüsse und Grundlagen sowie
  Statistik ohne Personen dauerhaft, Kassen- und Steuerunterlagen 10 Jahre und Meldungen an
  Verbände 6 Jahre nach Jahresende, personenbezogene Listen 92 Tage, Sonstiges 2 Jahre;
  `files_retention` (Jahre, 0 dauerhaft) geht vor. `oidc.tasks.purge_files` löscht täglich in den
  Papierkorb des Dienstkontos. Personenbezogene Listen nur mit Bestätigung und nie nach
  „Mitglieder“.
- Jede Ablage und jedes Löschen im Änderungsprotokoll (`oidc_fileitem`, RLS).

**Aus Nextcloud übernehmen** (`files_source`): Der Verein gibt einen Ordner an das Dienstkonto frei.
`GET …/nextcloud-dateien/quelle/?pfad=` listet ihn (PROPFIND, Tiefe 1, defusedxml), `…/datei/`
liefert eine Datei (`application/octet-stream`, `nosniff`, höchstens 50 MB) an den Browser, der sie
in den vorhandenen Hochladen-Weg gibt (gleiche Prüfungen wie vom eigenen Rechner). Pfade mit `..`,
versteckte Teile und Steuerzeichen werden abgelehnt. Blättern darf, wer irgendwo hochladen darf
(`docs.manage`, `finance.edit`, `website.*`, `events.manage`, `circulars.send`, `photos.edit`).

Einstellen von Ablage, Gruppen und Ordner zum Übernehmen verlangt eine frische Bestätigung.

## Termine in den Kalender der Nextcloud

HUBIplan schreibt Termine per CalDAV in Kalender des Dienstkontos (`oidc/nc_calendars.py`) und
gibt sie **nur lesend** für eine Gruppe der Nextcloud frei. Die Richtung ist HUBIplan →
Nextcloud; in der Nextcloud bearbeitet niemand diese Termine. Umgekehrt holt HUBIplan einen
Nextcloud-Kalender über „Fremde Kalender“ (iCal-Link) ab, siehe [fremde-kalender.md](fremde-kalender.md).

| Schalter | Kalender im Dienstkonto | Inhalt | Freigabe (Voreinstellung) |
|---|---|---|---|
| Termine für Mitglieder | `hubiplan-<eintrag>-termine` | was jedes Mitglied der Einheit sieht (wie das Kalender-Abo eines Mitglieds ohne Untereinheit, mit Terminen des Dachverbands nach seiner Freigabe) | Gruppe `Mitglieder` |
| Termine „nur Vorstand“ | `hubiplan-<eintrag>-vorstand` | Termine „nur Vorstand“ der Einheit (wie das Vorstands-Abo) | Gruppe `Vorstand` |

- Fenster wie die Abos: 30 Tage zurück, 400 Tage voraus. Jeder Termin einer Serie ist ein
  eigener Eintrag (`hp-<prüfsumme>.ics`), abgesagte heißen „Abgesagt: …“.
- Abgleich alle 15 Minuten (`oidc.tasks.sync_calendars`), nach dem Speichern der Einstellungen
  und mit **Kalender jetzt abgleichen**. Geschrieben wird nur, was sich geändert hat
  (Tabelle `oidc_calendaritem` mit Prüfsumme, unter RLS); was nicht mehr dazugehört, wird
  gelöscht. Wurde der Kalender in der Nextcloud gelöscht, legt der nächste Lauf ihn neu an.
- Schalter aus, Eintrag ausgeschaltet oder entfernt: Der Kalender wird in der Nextcloud gelöscht.
- Andere Gruppe: Die alte Freigabe wird zurückgenommen. Den Vorstandskalender einschalten
  oder seine Gruppe ändern verlangt wie die Gruppen der Rollen eine frische Bestätigung.
- Fehler stehen auf der Seite; der letzte Stand in der Nextcloud bleibt stehen.

Einrichtung: Dienstkonto und App-Passwort wie oben (für die Kalender reicht ein gewöhnliches
Konto). Die App „Kalender“ muss in der Nextcloud an sein. Die Gruppen `Mitglieder` und
`Vorstand` legt die Anmeldung über HUBIplan an („Gruppe „Vorstand““, „Gruppe „Mitglieder““);
ist Teilen nur innerhalb eigener Gruppen erlaubt, muss das Dienstkonto in diesen Gruppen sein.
Den Vorstandskalender nur für eine Gruppe freigeben, in der allein der Vorstand ist.

## Videoraum am Termin (Talk)

`talk_enabled` am Eintrag schaltet den Videoraum ein (braucht Dienstkonto und App-Passwort sowie
Talk in der Nextcloud). Wer einen Termin bearbeiten darf, sieht in der Termin-Antwort
`video_available` und legt mit `POST …/events/<id>/video/` ein Gespräch an (`oidc/nc_talk.py`):
öffentliches Talk-Gespräch (`roomType=3`) im Dienstkonto, Name „Titel (Datum)“, mit einem
zufälligen Passwort (16 Zeichen, Groß, klein, Ziffer, Sonderzeichen), das HUBIplan verschlüsselt
in `oidc_talkroom` speichert. Lässt sich das Passwort nicht setzen, löscht HUBIplan den Raum
gleich wieder. `DELETE …/video/` löscht ihn.

Link und Passwort stehen als `video` (`url`, `password`, `created_at`) in Termin und Terminliste
für alle, die den Termin sehen (Verwaltung, Mitgliederbereich, Apps), dazu in Einladung und
Erinnerung und in der Beschreibung der Termine im Kalender der Nextcloud. Öffentliche Webseite,
Kalender-Abos (ICS) und Rückmelde-Links tragen ihn nie.

Täglich (`oidc.tasks.purge_talk`, 4:50) löscht HUBIplan Räume, deren Termin seit
`talk_keep_days` Tagen (voreingestellt 7) vorbei ist (Serien: ab `repeat_until`, offene Serien
nie) oder gelöscht wurde. Antwortet die Nextcloud nicht, bleibt der Eintrag für den nächsten
Versuch.

## Wie lange eine Anmeldung gilt

HUBIplan stellt nur den Code und einen kurzen Zugriffsschlüssel aus (keine Refresh-Token). Wie
lange man danach in der Nextcloud angemeldet bleibt, bestimmt allein die Nextcloud
(`config.php`). In der Vereins-Nextcloud sind keine eigenen Werte gesetzt, es gelten die
Standards (Stand 02.11.2026):

| Wert | Standard | Bedeutung |
|---|---|---|
| `session_lifetime` | 86400 (24 h) | Sitzung ohne Aktivität |
| `session_keepalive` | `true` | offene Browser-Tabs halten die Sitzung am Leben |
| `remember_login_cookie_lifetime` | 1296000 (15 Tage) | „angemeldet bleiben“ |
| `auto_logout` | `false` | kein Abmelden beim Schließen des Browsers |
| `token_auth_enforced` | `false` | Sync-Apps auch ohne App-Passwort |

Sync-Apps (Desktop, Handy) bekommen bei der Einrichtung ein App-Passwort, das bis zum Widerruf
gilt; eine Anmeldung über HUBIplan läuft dort nicht erneut.

Was bei Sperre, Rollenende oder Austritt passiert:

- **Mit „Konten automatisch deaktivieren“**: HUBIplan deaktiviert das Konto sofort nach der
  Änderung (Hintergrundauftrag) und spätestens im nächtlichen Abgleich, bei Rollen mit Enddatum
  in der Nacht nach dem Ende. Die Nextcloud lässt deaktivierte Konten nicht mehr hinein: Browser-
  Sitzungen enden bei der nächsten Anfrage, App-Passwörter und Sync-Apps greifen nicht mehr.
  Ausnahme: Die Obergrenze hält den Abgleich an, dann erst nach „Jetzt abgleichen“.
- **Ohne**: Nur die nächste Anmeldung über HUBIplan scheitert. Eine offene Sitzung kann mit
  Keepalive bzw. „angemeldet bleiben“ bis zu 15 Tage weiterlaufen, App-Passwörter unbegrenzt.
  Dann das Konto in der Nextcloud von Hand deaktivieren.

Kürzer geht es in der Nextcloud, z. B. `occ config:system:set session_lifetime --type=integer
--value=28800` (8 h) oder `remember_login_cookie_lifetime` auf 0 (kein „angemeldet bleiben“).

## Ablauf und Schutz

- Nur Authorization Code Flow, nur Clients mit Geheimnis (`client_secret_basic` oder
  `client_secret_post`). Gespeichert ist nur die SHA-256-Prüfsumme des Geheimnisses; es
  wird beim Anlegen bzw. „Neues Geheimnis“ einmal angezeigt.
- Rückleitung nur an `<Nextcloud>/apps/user_oidc/code` bzw. mit `/index.php` (genauer
  Vergleich). Unbekannte Rückleitungen werden nie benutzt.
- PKCE nur mit `S256` (`plain` wird abgelehnt). Seit der Fachfrage FQ26 (Audit 02.11.)
  Pflicht: ohne `code_challenge` scheitert die Anmeldung mit `invalid_request`. `user_oidc`
  schickt S256 von selbst, sobald die Discovery es anbietet (Systemwert `use_pkce`, Standard
  an). Nur für ältere Anwendungen ohne PKCE lässt sich das je Eintrag ausschalten
  („Nur mit PKCE (S256)“, Feld `require_pkce`).
- Code 60 Sekunden, nur einmal einlösbar; Zugriffsschlüssel 5 Minuten; keine
  Refresh-Token. Beides nur im Cache (Redis), nie in der Datenbank.
- ID-Token RS256; Schlüssel `PRIVATE_ROOT/oidc/signing.pem` (in den Backups enthalten),
  wird beim ersten Gebrauch angelegt. Anderer Ort: `OIDC_KEY_FILE`.
- Schlüsselwechsel ohne Unterbrechung: `python manage.py oidc_schluessel_wechseln` legt einen
  neuen Schlüssel an; der bisherige bleibt als `signing.previous.pem` in der Schlüsselliste
  (`/api/oidc/jwks`), damit Dienste bereits ausgestellte Token weiter prüfen können. Nach
  mindestens einem Tag nimmt `python manage.py oidc_schluessel_wechseln --alten-entfernen`
  ihn heraus. Bei Verdacht auf einen abgeflossenen Schlüssel beide Schritte direkt
  nacheinander ausführen.
- Aufrufbremsen: Token und Userinfo 60 je Minute und Adresse, Anmeldung 30 je 10 Minuten
  und Konto.
- Einträge stehen unter RLS (Tabelle `oidc_client`), Änderungen im Änderungsprotokoll
  (ohne Geheimnis). Beim Umzug auf eine andere Instanz werden sie nicht mitgenommen.
- Einstellen darf, wer „Rollen und Rechte verwalten“ hat (damit auch die Pflicht zur
  Zwei-Faktor-Anmeldung für dieses Recht).

## Erneute Anmeldung, Sperren und Löschen

Fachfrage FQ26 (Audit 02.11.): wie sich die Anmeldung über HUBIplan bei erneuter Anmeldung
verhält.

- **Bestehende HUBIplan-Sitzung:** Wer in HUBIplan angemeldet ist, kommt ohne neue
  Passworteingabe in die Nextcloud; die Anmeldeseite leitet gleich weiter.
- **`prompt=none`:** Ohne HUBIplan-Sitzung antwortet HUBIplan mit `login_required`, ohne
  Seite.
- **`prompt=login`, `consent`, `select_account`:** HUBIplan meldet nicht still an, sondern
  zeigt die Seite mit dem Knopf „Bei der Nextcloud anmelden“ (Antwort 409 `confirm`, nach
  dem Klick POST mit `confirm=1`). Eine frische Passworteingabe erzwingt das nicht;
  `auth_time` im ID-Token nennt, wann die HUBIplan-Sitzung entstanden ist, und die
  Nextcloud kann danach selbst ablehnen. `max_age` wertet HUBIplan nicht aus. „Nur mit
  Zwei-Faktor-Anmeldung“ verlangt eine Sitzung mit zweitem Faktor (`amr` mit `mfa`), keine
  frische.
- **Abmelden in der Nextcloud** (RP-Initiated Logout 1.0): Die Discovery nennt
  `end_session_endpoint` (`/oidc/abmelden`); `user_oidc` schickt den Browser beim Abmelden
  dorthin (Systemeinstellung `user_oidc.single_logout`, Standard an) mit `client_id`,
  `post_logout_redirect_uri` und auf Wunsch `id_token_hint`. HUBIplan merkt sich in der
  Sitzung, dass man sich von dieser Nextcloud abgemeldet hat. Die nächste Anmeldung dort
  geht dann erst nach einem Klick, sonst würde die Nextcloud-Anmeldeseite sofort still
  wieder anmelden. Die Seite fragt, ob man sich auch bei HUBIplan abmelden möchte
  (Entscheidung Ralf 22.11.2026). Eine neue Anmeldung bei HUBIplan hebt den Vermerk auf.
  Zurück geht es nur an die Herkunft der eingetragenen Nextcloud, sonst an ihre Adresse.
  Die Nextcloud liest die Discovery zwischengespeichert; neu eingetragene Abmeldung wirkt
  dort erst, wenn sie die Discovery neu holt.
- **Abmelden in HUBIplan:** beendet nur die HUBIplan-Sitzung. Die Nextcloud-Sitzung läuft
  weiter, bis sie dort endet (kein Back-Channel-Logout).
- **Sperren** (Konto gesperrt, Rolle oder Amt beendet, Austritt): Die nächste Anmeldung
  scheitert; was mit laufenden Sitzungen geschieht, steht unter „Wie lange eine Anmeldung
  gilt“.
- **Löschen** des HUBIplan-Kontos oder des Eintrags hier: Anmeldungen über HUBIplan gehen
  nicht mehr. Das Nextcloud-Konto und seine Dateien bleiben; löschen oder übertragen muss
  sie die Nextcloud-Verwaltung. Ein neuer Eintrag bekommt ein neues Salz, also neue
  `sub`-Kennungen: Bisherige Konten passen dann nur über die Liste der bisherigen
  Benutzernamen.

## Schnittstellen

| Pfad | Zweck |
|---|---|
| `/api/oidc/.well-known/openid-configuration` | Discovery (in der Nextcloud eintragen) |
| `/api/oidc/jwks` | öffentlicher Schlüssel |
| `/oidc/anmelden` | Anmeldeseite (Authorization Endpoint, Oberfläche) |
| `/api/oidc/authorize/` | GET: Dienst beschreiben, POST: Code ausstellen (angemeldet, CSRF) |
| `/oidc/abmelden` | Abmeldeseite (End Session Endpoint, Oberfläche) |
| `/api/oidc/end-session/` | POST: Abmeldung von der Nextcloud vermerken, Rückleitung prüfen |
| `/api/oidc/token` | Code einlösen (Server der Nextcloud) |
| `/api/oidc/userinfo` | Angaben mit Zugriffsschlüssel |
| `/api/orgs/<id>/nextcloud/` | Einträge der Einheit; `<eintrag>/secret/` erneuert das Geheimnis |
| `/api/orgs/<id>/nextcloud/<eintrag>/calendars/` | POST: Kalender jetzt abgleichen |
| `/api/orgs/<id>/nextcloud/<eintrag>/groups/` | GET: Gruppen vergleichen, POST: Gruppen jetzt abgleichen |
| `/api/orgs/<id>/nextcloud-dateien/` | GET: Stand, POST: Datei ablegen |
| `/api/orgs/<id>/nextcloud-dateien/quelle/` | GET: Ordner zum Übernehmen listen; `datei/`: Datei holen |
| `/api/orgs/<id>/events/<termin>/video/` | POST: Videoraum anlegen, DELETE: löschen (auch `/api/depts/…`) |

Kennung als Anbieter (`issuer`): `FRONTEND_URL/api/oidc`, änderbar mit `OIDC_ISSUER`.

## In der Nextcloud einrichten

1. Als Administrator die App „OpenID Connect user backend“ installieren.
2. Verwaltung › OpenID Connect › Anbieter hinzufügen: Name (z. B. „HUBIplan“),
   Client-ID, Client-Geheimnis und Discovery-Endpunkt aus Einstellungen › Nextcloud.
3. „Gruppen-Provisionierung“ einschalten, Gruppen-Zuordnung `groups`; Anzeigename
   `name`, E-Mail `email`.
4. Mit einem Testkonto anmelden und die Gruppen prüfen, bevor Ordner danach
   freigegeben werden.
