# Mitgliedsausweis in Google und Apple Wallet

Google Wallet ist optional. Ohne Konfiguration erscheinen keine Wallet-Schaltflächen.
Mitglieder wählen unter „Mein Bereich → Ausweis“ die Ausgabe nach Google Wallet.
Erst dieser Klick überträgt Name, Vereinsname und QR-Prüfadresse. Mitgliederfotos,
Anschrift, Geburtsdatum und Beitragsdaten werden nicht übertragen.

## Einrichtung durch den Betreiber

1. Ein [Google Wallet Issuer-Konto](https://developers.google.com/wallet/generic/getting-started/issuer-onboarding)
   anlegen, die Wallet API im Google-Cloud-Projekt aktivieren und einen Service Account
   mit Schlüsseldatei anlegen. Diesen Account im Wallet-Ausstellerkonto als Entwickler
   berechtigen. Der private Schlüssel bleibt ausschließlich beim Backend und Worker.
2. `GOOGLE_WALLET_ISSUER_ID` auf die numerische Issuer-ID setzen.
3. `GOOGLE_WALLET_CREDENTIALS_FILE` auf die Service-Account-JSON-Datei setzen.
   In Docker ist dies der Pfad **im Container**. Die Datei ausschließlich lesbar
   in Backend und Worker einhängen, beispielsweise mit einer zusätzlichen Compose-Datei:

   ```yaml
   services:
     backend:
       volumes:
         - /srv/hubiplan-secrets/google-wallet.json:/run/secrets/google-wallet.json:ro
     worker:
       volumes:
         - /srv/hubiplan-secrets/google-wallet.json:/run/secrets/google-wallet.json:ro
   ```

   Dazu `GOOGLE_WALLET_CREDENTIALS_FILE=/run/secrets/google-wallet.json` setzen.
   Die Datei niemals im Repository, Medienordner oder Frontend ablegen.
4. Optional `GOOGLE_WALLET_LOGO_URL` auf ein öffentliches HTTPS-Vereins-/Betreiberlogo
   setzen. Das ist ein gemeinsames Logo dieser Installation; kein Personenfoto verwenden.
5. Migrationen ausführen, Backend und Worker neu starten. Celery Worker und Beat
   müssen für den regelmäßigen Abgleich laufen.
6. Im Demo-Modus nur mit im Wallet-Konto hinterlegten Testkonten testen. Für andere
   Mitglieder [Produktivfreigabe beantragen](https://developers.google.com/wallet/generic/test-and-go-live/request-publishing-access).

Bei mehreren Vereinen verwendet jeder Pass seinen Vereinsnamen; Issuer und optionales
Logo gehören zum Betreiber. Die Ausgabe im Namen der angeschlossenen Vereine ist bei
der Einrichtung des Ausstellerkontos zu berücksichtigen.

## Aussehen, Sprache und Schalter je Einheit

- Beide Pässe zeigen Name, Verein, Mitgliedsart, Abteilung(en) mit der Bezeichnung der
  Einheit (z. B. „Zug“) und den Dachverband. Kein Foto, keine Mitgliedsnummer, kein Datum.
  Inhalt: `cards/passcontent.py`.
- Farben und Logo kommen aus dem Erscheinungsbild der Einheit (wie Prüfseite). Bei Google
  braucht das Logo eine öffentliche `https`-Adresse (`FRONTEND_URL` + Logo-Pfad); ohne
  `https` gilt `GOOGLE_WALLET_LOGO_URL`. Apple bekommt das Logo als Datei im Pass.
- Feste Texte gibt es in Deutsch und Englisch: Apple über `de.lproj`/`en.lproj/pass.strings`,
  Google über `translatedValues`. Die Wallet wählt nach der Sprache des Telefons.
- Mitglieder › Einrichtung › Mitgliederbereich & Fotos: Schalter „Mitgliedsausweis“
  (`Organization.card_wallet_enabled`, Standard an). Er erscheint nur, wenn Apple oder
  Google eingerichtet ist. Ausschalten blendet die Knöpfe aus und setzt Google-Pässe beim
  nächsten Abgleich auf inaktiv.

## Gültigkeit und Betrieb

Die bestehende QR-Prüfseite bleibt maßgeblich: Sperren und Neuausstellen wirken dort
sofort. Ein offline vorgezeigter Wallet-Pass allein beweist keine aktuelle Mitgliedschaft.
Celery gleicht ausgegebene Pässe alle fünf Minuten ab, auch bei Austritt, zukünftigen
Eintrittsdaten, Namensänderungen und deaktivierten Vereinen. Nach einem Anbieterfehler
wird beim nächsten Lauf erneut versucht. Unveränderte Pässe werden nicht übertragen.
Auf dem Gerät können Änderungen wegen fehlender Verbindung später sichtbar werden.

Jede QR-Version hat ein eigenes Google-Objekt. Alte Versionen werden inaktiv gesetzt
und erhalten keinen neuen QR-Schlüssel. Nach „Neu erzeugen“ muss sich das Mitglied
anmelden und den neuen Pass hinzufügen. Speicherlinks referenzieren nur bereits
angelegte Google-Objekte und enthalten keine neuen Passinhalte zur Reaktivierung.
Zugangsdaten oder Aussteller-ID nicht wechseln, ohne vorher ausgegebene Pässe beim
alten Aussteller zu deaktivieren. Die Referenzen werden unter `wallet_passes.google`
am mandantengeschützten Ausweis gespeichert.

## Apple Wallet als Dateidownload

Apple funktioniert unabhängig von der Google-Konfiguration. Beim Betreiber müssen
ein Apple Developer Account, ein Pass Type ID-Zertifikat und der private Schlüssel
vorhanden sein. Einrichtung:

1. Einen Pass Type Identifier registrieren und dafür ein Zertifikat ausstellen lassen.
2. Zertifikat und privaten Schlüssel zusammen als PKCS#12 (`.p12`) exportieren.
3. Das zugehörige Apple-WWDR-Zwischenzertifikat als PEM bereithalten.
4. `APPLE_WALLET_PASS_TYPE_ID` (z. B. `pass.de.example.membership`) und
   `APPLE_WALLET_TEAM_ID` auf die Werte des Zertifikats setzen.
5. `APPLE_WALLET_CERTIFICATE_FILE` auf die `.p12`-Datei und
   `APPLE_WALLET_CERTIFICATE_PASSWORD` auf deren Passwort setzen.
6. `APPLE_WALLET_WWDR_FILE` auf das passende PEM-Zwischenzertifikat setzen.
   Die Dateien wie den Google-Schlüssel nur lesbar ins Backend einhängen; Pfade
   beziehen sich auf den Container. Danach Backend neu starten.

Im Mitgliederbereich erscheint „Zu Apple Wallet hinzufügen“. Der Download enthält
einen signierten generischen Pass (Inhalt siehe oben). Das Paket enthält
keine Mitgliederfotos. Google-Zugangsdaten sind dafür nicht erforderlich.

Der Apple-Pass wird **nicht automatisch aktualisiert**: Änderungen werden durch
erneuten Download übernommen. Sperren und Neuausstellung wirken sofort auf der
online geöffneten QR-Prüfseite. Nach Neuausstellung hat der Pass eine neue Seriennummer;
die alte Kopie bleibt ungültig. Automatische Apple-Updates würden zusätzlich einen
Update-Webservice mit Geräteregistrierung und Push erfordern und sind später möglich.
Ob Google Wallet diesen Dateidownload auf einem bestimmten Gerät importiert,
muss dort getestet werden; die direkte Google-Anbindung bleibt separat verfügbar.

Details: [Apple-Anleitung zur Pass-Erstellung](https://developer.apple.com/library/archive/documentation/UserExperience/Conceptual/PassKit_PG/Creating.html).

## Abnahme vor Produktivfreigabe

Mit einem Google-Testkonto Pass speichern; QR mit HUBIplan prüfen. Danach Sperren,
Wiederfreigabe, Austritt und Neuausstellung prüfen. Alte Versionen dürfen nach
Neuausstellung auch über alte Speicherlinks keinen gültigen QR-Code zurückerhalten.
Fehlerhafte Zugangsdaten müssen eine verständliche Fehlermeldung liefern.
