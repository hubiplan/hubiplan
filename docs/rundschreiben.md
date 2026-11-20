# Rundschreiben

Mails und Serienbriefe an ausgewählte Mitglieder (App `backend/circulars`).

## Wer schreibt an wen

Rundschreiben ist ein eigener Menüpunkt (`/rundschreiben`) für Dachverband,
Verein und Abteilung. Alte Adressen unter `/mitglieder/rundschreiben` und
`/abteilung/rundschreiben` leiten dorthin weiter.

- **Dachverband** (Recht `circulars.send`): an die Vorstände seiner Vereine
  (Inhaber von Vorstandsrollen mit Zugang, sonst die Kontaktadresse des Vereins),
  an Mitglieder der Vereine nur mit Zugriff auf die Mitgliedsdaten.
- **Verein** (Recht `circulars.send`): an seine aktuellen Mitglieder oder an die
  Rolleninhaber in den Abteilungen (Empfängerkreis `departments`, Filter nach
  Abteilung und Rollenname, z. B. alle Zugführer) oder an die Rolleninhaber des
  Vereins selbst (Empfängerkreis `roles`, Filter `club_roles`, z. B. nur der
  Kassierer, nur der Schriftführer oder „Alle Vorstandsrollen auswählen“; ohne die
  Rollen der Abteilungen). Inhaber von Vereinsrollen sind Konten; mit Mitgliedsakte
  zählt die Akte, fehlt dort die Mail, geht sie an die Adresse des Kontos.
- **Abteilung** (Recht `dept.circulars.send`): nur an die Mitglieder der eigenen
  Abteilung.

Reiter **Empfangen** (Verein): Rundschreiben des Dachverbands an die Vorstände
(`/api/orgs/<id>/circulars/received/`). Mitglieder sehen ihre Rundschreiben
weiter im Mitgliederbereich.

Die Migration `core/0018` gibt das Recht allen Rollen, die Rollen verwalten.

## Empfänger

Filter (mit UND verknüpft, mehrere Werte je Filter mit ODER): Mitgliedsart,
Abteilung, Abteilungsrollen, Vorstandsrolle, Alter, Jubilare eines Jahres;
beim Dachverband Vereine und „nur gemeldete“. Dazu einzeln hinzufügen und
abwählen. Wer eine E-Mail-Adresse hat, bekommt eine Mail, alle anderen einen
Brief (Serienbrief-PDF mit Briefkopf und Anschriftfeld).

## Arten und Abmeldung

- **Information** an Mitglieder: Mitglieder können sich abmelden – Link in jeder Mail
  (`/rundschreiben/abmelden/<token>`, signiert), im Mitgliederbereich oder durch
  den Vorstand in der Mitgliedsakte (`Membership.info_opt_out_at`). Abgemeldete
  bekommen weder Mail noch Brief. Vorstände und Rolleninhaber können sich nicht
  abmelden.
- **Vereinsmitteilung** (z. B. Einladung zur Versammlung): geht an alle.

## Text

Einfache Auszeichnung: `**fett**`, `*kursiv*`, `[Text](https://…)`, Zeilen mit
`- ` oder `1. ` als Liste. Platzhalter: `{Vorname}`, `{Nachname}`,
`{Abteilung}`, `{Verein}`, `{Mitgliedsjahre}`, `{Jubiläumsjahre}`. Unbekannte
Platzhalter verhindern den Versand.

## Versand

Beim Versand werden die Empfänger festgehalten (`CircularRecipient`, zugleich
Versandprotokoll), die Mails gehen einzeln im Hintergrund (Celery) über den
Postausgang. PDF-Anhänge (bis 5, je 10 MB) liegen einmal im privaten Speicher;
der Postausgang verweist darauf, statt sie je Mail zu kopieren. Versendete
Rundschreiben lassen sich nicht ändern oder löschen, nur „erneut verwenden“.
Mitglieder sehen ihre Rundschreiben im Mitgliederbereich.

Mit `MAIL_RATE_PER_HOUR` (z. B. 100 beim Hestia-Postfach) gehen höchstens 90 % davon
je Stunde als Rundschreiben hinaus (alle Mails der letzten Stunde im Postausgang
zählen mit); der Rest folgt automatisch alle 5 Minuten, bis alles versendet ist.
Dieselbe Grenze gilt seit dem Gesamtaudit 15.11. (PF-09) auch für Termin-Einladungen,
-Änderungen, -Absagen und -Erinnerungen: Ist die Stunde voll, folgen die übrigen
Empfänger nach 10 Minuten, niemand bekommt die Mail doppelt. Anmelde- und Sicherheitsmails
warten nie, für sie bleibt ein Zehntel frei. Ohne `MAIL_RATE_PER_HOUR` gibt es keine Grenze.

Ein Versandlauf (Rundschreiben, Termin-Mails) nutzt eine SMTP-Verbindung für alle Mails.
Lehnt der Mailserver eine Mail vorübergehend ab (4xx) oder kommt die Verbindung nicht
zustande, versucht HUBIplan es nach `MAIL_RETRY_DELAYS` Sekunden erneut (Standard `2,10`,
leer: kein neuer Versuch). Bricht die Verbindung mitten im Senden ab, bleibt es bei einem
Versuch, damit keine Mail doppelt ankommt; die Mail steht dann als fehlgeschlagen im
Postausgang.

## Mailverteiler (aus dem eigenen Mailprogramm)

Reiter **Verteiler** unter Rundschreiben (Verein, Dachverband und Untereinheiten mit
eigenem Recht). Ein Verteiler hat einen Namen und eine Adresse auf der
Verteiler-Domain, z. B. `alle@verein.example.org`. Wer das Recht
„Rundschreiben versenden“ für die Einheit hat, schreibt aus Outlook, Thunderbird oder
vom Handy an diese Adresse. HUBIplan macht daraus ein Rundschreiben
(`backend/circulars/inbound.py`):

Adressen: Kleinbuchstaben, Ziffern, Punkt, Binde- und Unterstrich; Umlaute werden
umgeschrieben (`schriftführer` wird `schriftfuehrer`), denn Umlaut-Adressen kommen
bei vielen Mailservern nicht an. Je Verteiler gibt es bis zu fünf **weitere
Adressen** (`aliases`, z. B. `schriftfuehrerin`, `sf`); alle Adressen sind auf der
ganzen Instanz eindeutig. `name+zusatz@` zählt als `name@`.

**Wer darf schreiben:** alle mit dem Recht, nur ausgewählte Konten, oder **alle**
(`open_senders`, Ralf 2026-10-31, gedacht für sehr kleine Empfängerkreise). Beim
Einschalten fragt die Oberfläche nach. Fremde Absender (ohne Recht oder ohne Konto)
gehen dann ohne Bestätigung direkt an den Verteiler (im Modus „Entwurf“ als Entwurf),
Antworten an den Absender; sie bekommen keine Rückmail. Verworfen werden weiter
automatische Mails, DMARC-Fehler und vom Spamfilter markierte Mails (`X-Spam-Flag`),
und je fremdem Absender gehen höchstens drei Mails am Tag durch.
Große offene Verteiler werden moderiert (Fachfrage FQ15, Audit 02.11.): Hat die Mail
mehr Empfänger als `open_direct_max` (je Verteiler, Standard 50, 0 = immer Freigabe)
oder sind am selben Tag schon `MAILING_OPEN_PER_DAY_TOTAL` (Standard 20) Mails fremder
Absender an den Verteiler hinausgegangen, bleibt sie als Entwurf liegen. Die
eingestellten Absender (sonst alle mit dem Recht, höchstens 20) bekommen einen Hinweis
mit Link und geben sie unter Rundschreiben frei oder löschen sie.

1. Das Sammelpostfach (Catch-all der Domain) wird jede Minute per IMAP abgeholt
   (Celery-Beat `verteiler-abholen`); verarbeitete Mails werden dort gelöscht,
   Mails mit Verarbeitungsfehler bleiben gelesen liegen.
2. Verworfen ohne Antwort: Rückläufer, Abwesenheitsnotizen (`Auto-Submitted`,
   `Precedence`), Mails von HUBIplan selbst, `dmarc=fail` des eigenen Mailservers,
   unbekannte Adressen und Absender ohne Konto mit dem Recht. Der Vorstand sieht
   alle Eingänge beim Verteiler.
3. Absender ist das Konto mit dieser E-Mail-Adresse. Rechte: `circulars.send` in der
   Einheit des Verteilers, bei Verteilern einer Untereinheit auch `dept.circulars.send`
   dort. Je Verteiler lässt sich der Kreis weiter einschränken („Wer darf an den
   Verteiler schreiben?“ → nur ausgewählte, `MailingList.senders`); zur Auswahl stehen
   nur Konten mit dem Recht, und auch Ausgewählte brauchen das Recht weiterhin. Leere
   Auswahl heißt: alle mit dem Recht.
4. Betreff wird Betreff, Text wird Text (HTML-Mails als einfacher Text mit fett,
   Listen und Links), Platzhalter wie `{Vorname}` wirken, andere geschweifte Klammern
   werden zu runden. Nur PDF-Anhänge werden übernommen (wie in der Oberfläche).
5. Empfänger, Art (Information oder Vereinsmitteilung), Empfängerkreis und Zustellung
   stehen im **Muster** des Verteilers: einem Rundschreiben-Entwurf, der nie versendet
   wird und nicht in der Liste erscheint. Die Auswahl wird bei jedem Eingang neu
   berechnet.
6. **Versand** je Verteiler:
   - *Absender bestätigt per Link* (Standard): Mail an die Kontoadresse des Absenders
     mit Empfängerzahlen und Link `/rundschreiben/bestaetigen/<token>` (7 Tage gültig).
     Erst der Knopf „Jetzt versenden“ versendet (das Öffnen allein nicht, weil
     Virenscanner Links vorab laden). Ein gefälschter Absender bekommt den Link nie.
     Beim Klick wird das Recht erneut geprüft.
   - *als Entwurf ablegen*: Das Rundschreiben liegt unter Rundschreiben und wird dort
     versendet.
   - *direkt versenden (ohne Bestätigung)*: Mails berechtigter Absender (Konto und
     Recht) gehen sofort hinaus; der Absender bekommt nur eine Versandmeldung. Vor
     gefälschten Absendern schützt dann nur die DMARC-Prüfung, daher fragt die
     Oberfläche beim Einschalten nach. Nur für kleine Empfängerkreise gedacht.
     Gezählt wird nur ein `dmarc=pass` des eigenen Mailservers: `MAIL_AUTHSERV_ID` in der
     `.env` nennt dessen Kennung (der erste Wert in seinem `Authentication-Results`-Kopf).
     Ohne diese Einstellung geht nichts direkt hinaus, sondern immer mit Bestätigungslink,
     weil den obersten Kopf sonst auch der Absender mitschicken könnte (Audit 03.11. GA-V05).
7. Antwort-an ist der Absender: Antworten der Mitglieder gehen nie an alle.

Im „Von“ jeder Rundschreiben-Mail steht „Person (Verein)“ bzw. „Person (Untereinheit)“,
ohne Konto die Adresse des Absenders; die Adresse selbst bleibt `DEFAULT_FROM_EMAIL`
(nur für sie unterschreibt der Server, sonst scheitert DMARC). Die Fußzeile ist die
des Postausgangs („im Auftrag von … über HUBIplan versandt“, Impressum, Datenschutz),
bei Informationen an Mitglieder ergänzt um den Abmeldelink.

Ohne Sammelpostfach (Testserver) gibt es beim Verteiler den **Probe-Eingang**: als
käme eine Mail von der eigenen Adresse (`INBOUND_SIMULATION`, Standard: an, solange
`INBOUND_IMAP_HOST` leer ist).

Einstellungen (`.env`): `INBOUND_DOMAINS`, `INBOUND_IMAP_HOST`, `INBOUND_IMAP_PORT`
(993, TLS), `INBOUND_IMAP_USER`, `INBOUND_IMAP_PASSWORD`, `INBOUND_IMAP_FOLDER`
(`INBOX`), `MAIL_RATE_PER_HOUR`. Einrichtung auf dem Hestia-Server:
[echtbetrieb.md](echtbetrieb.md#mailverteiler).

### Termine aus dem Mailprogramm

Eine Mail an eine Verteileradresse mit Kalenderteil (iMIP, RFC 6047: `text/calendar` oder
`.ics`-Anhang mit `METHOD:REQUEST`/`CANCEL`) wird kein Rundschreiben, sondern geht an
`events/mail_intake.py` (Lesen und Schreiben der Kalenderteile: `events/imip.py`):

1. Absender braucht `events.manage` für die Einheit des Verteilers (Untereinheit:
   `dept.events.manage`) und muss, falls eingestellt, unter den Absendern stehen.
   „Jeder darf schreiben“ gilt für Termine nicht. Kommt die Einladung von einem Kalenderserver
   (Nextcloud: `noreply@…`), zählt der Organisator, wenn er im Antwort-an steht; direkt
   übernommen wird dann nie.
2. Der Eingang (`InboundMail.event_data`) wartet auf den Bestätigungslink (gleiche Seite wie beim
   Rundschreiben); nur Modus „direkt“ mit DMARC-Pass des Absenders selbst übernimmt sofort.
   PDF-Anhänge liegen bis dahin verschlüsselt unter `events/eingang/`.
3. Übernehmen: Termin über `Event.mail_uid` anlegen, ändern (höhere `SEQUENCE`) oder absagen.
   Sichtbarkeit nach dem Empfängerkreis des Musters: `roles`, `boards`, `departments` → „nur
   Vorstand“ (ohne Zu- und Absagen), sonst „Mitglieder“; nie öffentlich. Serien nur wöchentlich,
   monatlich oder jährlich mit Abstand und Ende.
4. Einladung als Rundschreiben nach dem Muster des Verteilers (bei Mitgliederterminen mit
   `Circular.event`, also mit Rückmeldelink), Videolink aus `CONFERENCE`, `URL`, Ort oder
   Beschreibung (`Event.video_url`), sonst je Verteiler (`event_video`) ein neuer Talk-Raum
   (`oidc.nc_talk`, wo eingerichtet).
5. An den Organisator geht `METHOD:REPLY` „angenommen“ für die Verteileradresse.

Antworten auf HUBIplans eigene Einladungen: Einladungen und Rundschreiben zu Terminen mit Zu- und
Absage tragen einen Kalenderteil (`METHOD:REQUEST`, UID wie im Kalender-Abo) mit dem Organisator
`termin+<Termin>-<Mitgliedschaft>-<HMAC>@<Verteiler-Domain>` (der lokale Teil `termin` ist
reserviert). „Annehmen/Mit Vorbehalt/Ablehnen“ im Mailprogramm schickt `METHOD:REPLY` dorthin;
der Abruf speichert es als Zu- oder Absage (Quelle „Mailprogramm“), wenn Code und Absender zum
Mitglied passen. Ohne Sammelpostfach (`INBOUND_IMAP_HOST`), für Mitglieder mit eigenem
Kalender-Abo und für den Organisator einer Einladung aus dem Mailprogramm gibt es keinen
Kalenderteil.

## An einen Verteiler

Hat die Einheit Verteiler, zeigt „An“ im Rundschreiben nur diese (Ralf 2026-10-31).
Das Rundschreiben merkt sich den Verteiler (`Circular.mailing_list`); Empfängerkreis
und Auswahl kommen aus dessen Muster und werden bei Vorschau und Versand neu
übernommen (`services.apply_list`). Die Filter sind dann ausgeblendet; geändert wird
die Auswahl beim Verteiler. Ohne Verteiler bleibt die freie Auswahl wie bisher.

## Zustellung

Je Rundschreiben (und im Muster eines Verteilers) wählt man die Zustellung:

- **per App, sonst E-Mail** (Standard): Mitglieder mit der HUBIplan-App und Mitteilungen
  bekommen es nur aufs Telefon, alle anderen per Mail (`via_app`).
- **per App und zusätzlich E-Mail**: App-Nutzer bekommen beides (`via_app` + `also_mail`).
  Die zusätzliche Mail zählt zur Stundengrenze.
- **nur per E-Mail**: niemand per App.

Ohne Mailadresse gibt es wie bisher einen Brief (Kurzmitteilung: nur im Mitgliederbereich).

## Glückwünsche (Geburtstag und Jubiläum)

Unter Rundschreiben › Glückwünsche (nur Verein, Recht `circulars.send`) stellt der Vorstand ein,
zu welchen Geburtstagen (keine, besondere, alle; ab einem Alter jedes Jahr) und ob zu
Vereinsjubiläen gratuliert wird (App `greetings`).

- `greetings.tasks.hourly` legt `lead_days` Tage vorher je Tag und Anlass ein Rundschreiben der
  Art `greeting` als Entwurf an (`GreetingBatch`) und gleicht es an, solange es Entwurf ist. Ab
  `send_hour` am Tag (auch noch am Folgetag) versendet er es, außer mit Freigabe (`approval`).
- Empfänger: Filter `members` (genau diese Mitgliedschaften), Werte je Mitglied in `greeting`
  (Platzhalter `{Alter}`, `{Jubiläumsjahre}`); Haushalte werden nicht zusammengefasst.
- Widerspruch: `Membership.greetings_opt_out_at` (Mitgliederbereich, Mitgliedsakte); wer
  widersprochen hat, bekommt weder Mail noch Brief. Ohne Empfänger wird der Tag ausgelassen.
- Glückwünsche stehen nicht in der Liste der Rundschreiben und lassen sich dort nicht ändern;
  Jubiläen nur mit Tag oder Monat (jahresgenaue haben kein Datum), nur die des Vereins.
