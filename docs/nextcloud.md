# Anmeldung an der Nextcloud mit dem HUBIplan-Konto

App `backend/oidc`, Seite Einstellungen › Nextcloud (`frontend/src/pages/settings/NextcloudPage.tsx`),
Anmeldeseite `/oidc/anmelden` (`frontend/src/pages/NextcloudLoginPage.tsx`).
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
die Liste ändern darf („Rollen und Benutzer verwalten“), kann damit jede Person mit jedem
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
- Jede Änderung ins Änderungsprotokoll und per E-Mail an alle mit „Rollen und Benutzer
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
- PKCE nur mit `S256` (`plain` wird abgelehnt), optional. `user_oidc` (ab 8.x) nutzt PKCE
  von selbst, sobald die Discovery `S256` anbietet; abschalten ließe es sich nur systemweit in
  der Nextcloud (`user_oidc` › `use_pkce` = `false`, nicht tun).
- Code 60 Sekunden, nur einmal einlösbar; Zugriffsschlüssel 5 Minuten; keine
  Refresh-Token. Beides nur im Cache (Redis), nie in der Datenbank.
- ID-Token RS256; Schlüssel `PRIVATE_ROOT/oidc/signing.pem` (in den Backups enthalten),
  wird beim ersten Gebrauch angelegt. Anderer Ort: `OIDC_KEY_FILE`.
- Aufrufbremsen: Token und Userinfo 60 je Minute und Adresse, Anmeldung 30 je 10 Minuten
  und Konto.
- Einträge stehen unter RLS (Tabelle `oidc_client`), Änderungen im Änderungsprotokoll
  (ohne Geheimnis). Beim Umzug auf eine andere Instanz werden sie nicht mitgenommen.
- Einstellen darf, wer „Rollen und Benutzer verwalten“ hat (damit auch die Pflicht zur
  Zwei-Faktor-Anmeldung für dieses Recht).

## Schnittstellen

| Pfad | Zweck |
|---|---|
| `/api/oidc/.well-known/openid-configuration` | Discovery (in der Nextcloud eintragen) |
| `/api/oidc/jwks` | öffentlicher Schlüssel |
| `/oidc/anmelden` | Anmeldeseite (Authorization Endpoint, Oberfläche) |
| `/api/oidc/authorize/` | GET: Dienst beschreiben, POST: Code ausstellen (angemeldet, CSRF) |
| `/api/oidc/token` | Code einlösen (Server der Nextcloud) |
| `/api/oidc/userinfo` | Angaben mit Zugriffsschlüssel |
| `/api/orgs/<id>/nextcloud/` | Einträge der Einheit; `<eintrag>/secret/` erneuert das Geheimnis |

Kennung als Anbieter (`issuer`): `FRONTEND_URL/api/oidc`, änderbar mit `OIDC_ISSUER`.

## In der Nextcloud einrichten

1. Als Administrator die App „OpenID Connect user backend“ installieren.
2. Verwaltung › OpenID Connect › Anbieter hinzufügen: Name (z. B. „HUBIplan“),
   Client-ID, Client-Geheimnis und Discovery-Endpunkt aus Einstellungen › Nextcloud.
3. „Gruppen-Provisionierung“ einschalten, Gruppen-Zuordnung `groups`; Anzeigename
   `name`, E-Mail `email`.
4. Mit einem Testkonto anmelden und die Gruppen prüfen, bevor Ordner danach
   freigegeben werden.
