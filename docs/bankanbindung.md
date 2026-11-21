# Bankanbindung (FinTS)

Mit der Bankanbindung holt HUBIplan die Umsätze direkt bei der Bank, statt dass die Kasse einen
Kontoauszug als Datei hochlädt ([kontoauszug.md](kontoauszug.md)). Der Weg heißt FinTS (früher
HBCI, „HBCI mit PIN/TAN“) und wird von fast allen deutschen Banken und Sparkassen angeboten.
Dieser Stand umfasst **Bankzugang einrichten und Umsätze abrufen**. Lastschriften und
Überweisungen direkt einreichen folgt in eigenen Schritten; bis dahin bleibt der Weg über die
SEPA-Datei.

Die Bankanbindung ist auf einem neuen Server **aus**. Sie braucht zwei Dinge: die Einstellung
des Betreibers auf dem Server und den Schalter des Vereins.

## Für Betreiber: einschalten

1. **Produkt registrieren.** Die Deutsche Kreditwirtschaft (DK) verlangt, dass jedes Programm,
   das über FinTS mit Banken spricht, registriert ist. Die Registrierung ist kostenlos, das
   Formular steht auf der Seite der DK zu FinTS (Produktregistrierung); die Bearbeitung dauert
   nach Angabe der DK zwei bis drei Wochen. Als Produktkategorie passt „Web-Server“.
2. **Nummer auf dem Server eintragen**, in der `.env`:

   ```sh
   HUBIPLAN_FINTS=1
   HUBIPLAN_FINTS_PRODUKT_ID=<Registrierungsnummer des Betreibers>
   ```

   Danach die Dienste neu erstellen (wie nach jeder Änderung der `.env`). Ohne Nummer bleibt
   die Bankanbindung aus, auch wenn `HUBIPLAN_FINTS=1` gesetzt ist.
3. **Verein schaltet ein:** Einstellungen › Module › Finanzen › „Bankanbindung: Umsätze direkt
   bei der Bank abrufen“. Der Schalter erscheint nur, wenn Schritt 2 erledigt ist.

**Die Registrierungsnummer gehört dem, der sie beantragt hat.** Sie steht deshalb nicht im
Quellcode, in keinem Image und in keiner Beispieldatei, und sie gehört nicht in Issues, Pull
Requests oder Chats. Wer HUBIplan selbst betreibt, registriert sich selbst; die Nummer eines
anderen Betreibers zu verwenden ist nicht erlaubt und kann dazu führen, dass Banken sie
sperren. So hat es die Registrierungsstelle gegenüber anderen quelloffenen Projekten
beschrieben.

Der Server braucht ausgehende HTTPS-Verbindungen zu den Banken (Port 443). HUBIplan spricht
nur `https://`-Adressen an, folgt keinen Weiterleitungen und verbindet sich nicht mit
internen Adressen.

## Rechtliche Einordnung (keine Rechtsberatung)

Wer für andere auf deren Konten zugreift, kann einen Kontoinformationsdienst im Sinne des
Zahlungsdiensteaufsichtsgesetzes (ZAG) erbringen. Das braucht eine Registrierung bei der BaFin
(§ 34 ZAG), das Auslösen von Zahlungen sogar eine Erlaubnis (§ 10 ZAG). Nach unserer Prüfung
gilt, ohne Gewähr:

| Wer betreibt die Instanz | Einordnung |
| --- | --- |
| Der Verein selbst, für die eigenen Konten | kein Zahlungsdienst: der Verein nutzt ein Programm für sich |
| Ein Ehrenamtlicher für den eigenen Verein, unentgeltlich | wohl kein Zahlungsdienst; am saubersten ist der Verein der formale Betreiber |
| Ein Verband oder jemand für mehrere fremde Vereine | Grauzone, vorher bei der BaFin anfragen |
| Ein gewerblicher Hoster für Kunden | Kontoinformationsdienst, Registrierung nötig; die Bankanbindung nicht einschalten oder einen lizenzierten Anbieter nutzen |

Wer HUBIplan gewerblich für andere betreibt, lässt die Bankanbindung aus oder klärt das vorher
mit der BaFin. Der Abruf ist als austauschbare Schicht gebaut (`finance/bankweg.py`), sodass
später weitere Wege dazukommen können, etwa EBICS oder ein lizenzierter
Kontoinformationsdienst.

## Ablauf für die Kasse

Unter **Finanzen › Kontoauszüge** steht die Karte „Umsätze bei der Bank abrufen“ (Recht
`finance.edit`; lesen mit `finance.view`).

1. **Bankzugang hinzufügen:** Bezeichnung, Bankleitzahl, FinTS-Adresse der Bank, Anmeldename
   (und Kunden-ID, falls die Bank eine nennt). Anlegen, Ändern und Löschen eines Zugangs
   verlangen einen frischen zweiten Faktor.
2. **Einrichten:** Mit der PIN meldet sich HUBIplan bei der Bank an, fragt das Freigabeverfahren
   (TAN-Verfahren, bei Bedarf das Gerät) ab und holt die Liste der Konten. Verbunden werden
   die Konten, deren IBAN unter Finanzen › Konten eingetragen ist.
3. **Umsätze abrufen:** PIN eingeben; verlangt die Bank eine Freigabe, TAN eintippen oder in
   der App der Bank bestätigen (HUBIplan fragt dann alle drei Sekunden nach). Abgerufen wird
   seit dem letzten Abruf mit sieben Tagen Überlappung, beim ersten Mal 90 Tage zurück.

Das Ergebnis ist ein Kontoauszug wie aus einer Datei, mit dem Vermerk „Abruf“: dieselben
Vorschläge, derselbe Saldo-Abgleich. Die Antwort der Bank wird unverändert als ZIP mit
Prüfsumme aufbewahrt (GoBD) und liegt dem Datenexport bei. Geliefert wird CAMT (camt.052/053),
wenn die Bank es anbietet, sonst MT940.

**Keine Dubletten:** Jeder Umsatz wird nur einmal gespeichert. Das gilt auch, wenn derselbe
Umsatz schon aus einer hochgeladenen Datei stammt und der Abruf ihn in einem anderen Format
liefert: Gleich ist dann ein Umsatz mit gleichem Tag, Betrag und gleicher Richtung, wenn die
End-to-End-Referenz übereinstimmt oder, ohne Referenz, der Verwendungszweck.

## PIN, TAN und was gespeichert wird

- **Die PIN wird nie gespeichert**, nicht protokolliert und nicht zurückgegeben. Sie kommt mit
  jedem Schritt neu aus dem Browser und lebt nur für die Dauer der Anfrage im Speicher des
  Servers. Einen Abruf ohne anwesende Person (etwa nachts) gibt es deshalb nicht.
- Gespeichert werden je Zugang: Bezeichnung, Bankleitzahl, Adresse, Anmeldename und Kunden-ID
  (verschlüsselt), das gewählte Freigabeverfahren und der Sitzungsstand der Bank (Kennung des
  Kundensystems und Bankparameter, verschlüsselt). Angezeigt werden vom Anmeldenamen nur die
  letzten zwei Zeichen.
- Wartet die Bank auf eine Freigabe, liegt der angehaltene Dialog höchstens fünf Minuten
  verschlüsselt in der Datenbank (Kennung des Dialogs und Zähler, keine PIN). Nach Ende,
  Abbruch oder Ablauf wird er geleert. Fortsetzen darf nur, wer den Vorgang begonnen hat.
- **Schutz vor einer Sperre:** Banken sperren einen Zugang meist nach drei falschen PINs.
  Lehnt die Bank eine Anmeldung ab, verlangt HUBIplan vor dem nächsten Versuch eine
  ausdrückliche Bestätigung; nach der zweiten Ablehnung ruht der Zugang 24 Stunden. Eine
  erfolgreiche Anmeldung setzt den Zähler zurück.
- Je Zugang läuft höchstens ein Vorgang gleichzeitig. Jeder Vorgang steht mit Art, Ergebnis,
  Person und Zeit in der Liste der Bankvorgänge (`/api/orgs/<id>/finance/bank-tasks/`),
  Einrichten und Abruf außerdem im Protokoll.
- Beim Umzug eines Vereins auf eine andere Instanz kommen Bankzugänge nicht mit; sie werden
  am Ziel neu eingerichtet.

## Technik

| Baustein | Ort |
| --- | --- |
| Austauschbare Schicht (Schritte, Fehlerarten) | `backend/finance/bankweg.py` |
| FinTS mit python-fints (LGPL-3.0-or-later) | `backend/finance/fints_weg.py` |
| Ablauf, Sperrschutz, Einlesen | `backend/finance/bank_fetch.py` |
| MT940 lesen | `backend/finance/mt940.py` |
| API | `backend/finance/bank_access_views.py` (`…/finance/bank-access/`, `…/finance/bank-tasks/`) |
| Oberfläche | `frontend/src/pages/finance/BankAccess.tsx` |
| Nachgebaute Bank für Tests | `backend/tests/fints_server.py`, Tests in `backend/tests/test_bankanbindung.py` |

Fehler der Bank kommen als HTTP 409 mit `code`: `pin` (Anmeldung abgelehnt), `pin_retry`
(Bestätigung nötig), `paused` (Zugang ruht), `locked` (bei der Bank gesperrt), `tan` (Freigabe
abgelehnt), `expired`, `busy`, `connection`, `unsupported`, `bank`, `import`.

Getestet ist gegen die nachgebaute Bank. Der Betrieb gegen eine echte Bank setzt die
Registrierungsnummer voraus; Besonderheiten einzelner Banken zeigen sich erst dort.
