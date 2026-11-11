---
key: guide.two_factor
titel: Zwei-Faktor-Anmeldung einrichten
routen: [/mein-konto/anmeldung]
reihe: 20
stichworte: [2FA, Authenticator, Handy, Code, TOTP, Sicherheit]
---

Du brauchst eine Authenticator-App auf dem Handy, z. B. FreeOTP, Aegis oder Google Authenticator.

1. Öffne [Anmeldung & Sicherheit](/mein-konto/anmeldung) unter **Mein Konto**.
2. Scanne im Abschnitt **Zwei-Faktor-Anmeldung** den QR-Code mit der App.
3. Trage den **Code aus der App** ein, dazu **Dein Passwort zur Bestätigung**.
4. Klicke auf **Aktivieren**.
5. Bewahre die angezeigten **Wiederherstellungscodes** sicher auf, z. B. ausgedruckt. Jeder Code
   hilft einmal, falls das Handy fehlt.

![Abschnitt „Zwei-Faktor-Anmeldung“ mit QR-Code](bild:konto-zwei-faktor)

Vereinslogo in der App: Der QR-Code enthält das Logo deines Vereins. Manche Apps wie FreeOTP
zeigen es als Symbol an. Andere, etwa Google Authenticator, Microsoft Authenticator, 2FAS oder
Aegis, zeigen stattdessen die Anfangsbuchstaben. In Aegis kannst du beim Eintrag ein eigenes Bild
wählen, in 2FAS Buchstaben und Farbe ändern. Ein schon eingerichteter Eintrag ändert sich erst, wenn du die
Zwei-Faktor-Anmeldung neu einrichtest.

## Heikle Aktionen bestätigen

Für einige Aktionen fragt HUBIplan noch einmal nach einem aktuellen Code aus der App, wenn
der letzte Code älter als 10 Minuten ist: vollständige Exporte und Ausgliedern, Rollen vergeben
oder ihre Rechte erweitern, die Zwei-Faktor-Anmeldung einer anderen Person zurücksetzen, den
QR-Code für die HUBIplan-App erzeugen und endgültiges Löschen (Verein, ehemaliges Mitglied,
Name in der Chronik). Ein Wiederherstellungscode geht auch, mit eingerichtetem
Passkey auch der Passkey (siehe „Mit Passkey anmelden“). Wer die Zwei-Faktor-Anmeldung noch
nicht eingerichtet hat, bestätigt in der Übergangsfrist mit dem Passwort.

Die Plattform-Verwaltung hat keine Übergangsfrist: Ohne Zwei-Faktor-Anmeldung ruhen ihre
Rechte, bis du sie hier einrichtest. Vorstand und Kasse haben 14 Tage Zeit; die Frist steht oben
auf jeder Seite.
