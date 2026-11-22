---
key: page.settings_api
titel: Einstellungen › API-Zugänge
modul: api
rechte: [api.manage]
routen: [/einstellungen/api]
stichworte:
  [
    API,
    Schnittstelle,
    Schlüssel,
    Verbandssoftware,
    Dachverband,
    fremde Programme,
    Datenaustausch,
    OpenAPI,
    Personendaten,
    Rechtsgrundlage,
    Auftragsverarbeitung,
    Verbandsmeldung,
    Webhook,
    Benachrichtigung,
  ]
---

Mit einem API-Zugang liest ein anderes Programm Daten eurer Einheit, zum Beispiel die Software eures Dachverbands, eine eigene Webseite oder eine Anzeigetafel. Jeder Zugang hat einen eigenen Schlüssel, darf nur lesen, was ihr ankreuzt, und läuft von selbst ab.

Namen, Anschriften und andere Personendaten gibt ein Zugang nur heraus, wenn ihr den Empfänger benennt und die Rechtsgrundlage bestätigt. Bankdaten gibt es nie, und ein Zugang kann nichts ändern. Legt für jedes Programm einen eigenen Zugang an; dann lässt sich einer löschen, ohne die anderen zu stören.

Die Seite gibt es nur, wenn das Modul „API für andere Programme“ eingeschaltet ist und deine Rolle das Zusatzrecht „API-Zugänge verwalten“ hat. Dieses Recht bekommt keine Rolle von selbst.

## Was ein Zugang lesen darf

- Einheit: Name, Anschrift, Kontakt, Logo und die Untereinheiten.
- Termine: Termine mit der Sichtbarkeit „nach außen öffentlich“, auf Wunsch auch die für Mitglieder. Termine „nur Vorstand“, Zu- und Absagen gibt es nie.
- Mitgliederzahlen: Anzahlen zum Stichtag nach Alter, Geschlecht und Untereinheit, keine Personen.
- Vorstand und Ämter: Rollen mit ihrer Funktionsadresse; Namen nur, wenn sie auf eurer öffentlichen Webseite stehen.
- Ergebnisse, Beiträge, Dokumente: nur, was eure Webseite veröffentlicht.

Dazu kommen für Vereine die Bereiche mit Personendaten, siehe nächster Abschnitt.

Ein Bereich erscheint nur, wenn das Modul dazu eingeschaltet ist. Mit **Gilt für** begrenzt ihr einen Zugang auf eine Untereinheit; er sieht dann nur deren Daten.

## Personendaten

Diese Bereiche tragen das Zeichen „Personendaten“ und gibt es nur für Vereine:

- Verbandsmeldung: gemeldete Mitglieder zum Stichtag. Unter **Verbandsmeldung** wählt ihr „nur Zahlen“ (Anzahl nach aktiv, passiv und Geburtsmonat) oder „namentlich“ (dazu Name, Geburtsdatum, Verbandsnummer, Mitgliedsart und Eintritt).
- Mitglieder: immer Name, Titel, Geschlecht, Geburtsdatum und Mitgliedsnummer. Kontakt und Anschrift, Mitgliedschaft und Untereinheiten kommen nur dazu, wenn ihr sie ankreuzt.
- Ehrungen und Qualifikationen: mit Name der Person und Zeitraum. Qualifikationen, bei denen nur die Einsicht vermerkt wird, etwa das Führungszeugnis, gehen nie nach außen.

Nie dabei sind Bankdaten, Bemerkungen, Fotos, Zusatzfelder und Mitglieder, deren Daten nach der Löschfrist gelöscht sind. Mit **Nur aktuelle Mitglieder** und **Nur Volljährige** begrenzt ihr den Zugang weiter.

Für Personendaten verlangt HUBIplan drei Angaben:

- **Empfänger (Geschäftspartner)**: wer die Daten bekommt. Legt ihn vorher unter Verwaltung › Geschäftspartner an.
- **Rechtsgrundlage**: Auftragsverarbeitung, wenn der Empfänger nur in eurem Auftrag arbeitet, etwa ein Dienstleister mit Vertrag nach Art. 28 DSGVO. Übermittlung, wenn der Empfänger selbst über die Daten entscheidet, etwa der Dachverband nach seiner Satzung.
- Die Bestätigung, dass es den Vertrag oder die Rechtsgrundlage gibt. Sie gilt für genau diesen Empfänger; wählt ihr einen anderen, fragt HUBIplan erneut.

Bei Auftragsverarbeitung bekommt der Geschäftspartner die Rolle Auftragsverarbeiter und steht damit im Verzeichnis unter [Datenschutz-Werkzeuge](/dsgvo). Alle mit dem Recht bekommen eine E-Mail, sobald ein Zugang Personendaten herausgibt. HUBIplan ersetzt keine Rechtsberatung: Ob die Weitergabe zulässig ist, entscheidet der Vorstand.

Jeder Abruf von Personendaten wird 90 Tage lang protokolliert. In der Liste steht je Zugang, wie viele Datensätze abgerufen wurden und wann zuletzt.

## Benachrichtigen bei Änderungen

Tragt ihr eine **Adresse für Benachrichtigungen** ein, meldet HUBIplan dem anderen Programm, wenn ein Mitglied aufgenommen oder geändert wird, austritt oder ein Termin sich ändert. Die Nachricht nennt nur die Art der Änderung und eine Kennung, nie Inhalte; das Programm holt die Daten danach mit seinem Schlüssel ab.

Beim ersten Speichern zeigt HUBIplan einmal ein Geheimnis. Damit prüft das andere Programm, dass die Nachricht wirklich von HUBIplan kommt. **Neues Geheimnis erzeugen** ersetzt es, **Probenachricht senden** prüft die Verbindung.

Ist die Adresse nicht erreichbar, versucht HUBIplan es bis zu drei Tage lang erneut. Nach sieben Tagen ohne Erfolg ruhen die Benachrichtigungen, und alle mit dem Recht bekommen eine E-Mail; **Benachrichtigungen wieder einschalten** nimmt sie wieder in Betrieb. Der Zugang selbst gilt weiter.

## Schlüssel und Sicherheit

Der Schlüssel steht genau einmal auf der Seite: nach dem Anlegen und nach **Neuen Schlüssel erzeugen**. HUBIplan speichert ihn nicht lesbar. Gebt ihn auf sicherem Weg weiter, nicht per unverschlüsselter E-Mail. Für beides fragt HUBIplan nach einem frischen Code der Zwei-Faktor-Anmeldung, ebenso wenn ein Zugang neu Personendaten herausgibt oder eine andere Adresse für Benachrichtigungen bekommt.

Nach **Neuen Schlüssel erzeugen** gilt der bisherige Schlüssel noch sieben Tage, damit sich das andere Programm ohne Ausfall umstellen lässt. Ist ein Schlüssel in falsche Hände geraten, löscht den Zugang: Dann gilt er sofort nicht mehr.

Jeder Zugang läuft spätestens nach einem Jahr ab; 30 Tage vorher bekommen alle mit dem Recht eine E-Mail. Mit **Bearbeiten** verlängert ihr ihn. Wird ein Zugang 90 Tage nicht genutzt, schaltet HUBIplan ihn ab; **Wieder einschalten** nimmt ihn wieder in Betrieb.

Unter **Erlaubte Adressen (optional)** lasst ihr Abrufe nur von bestimmten IP-Adressen zu. **Aus fremden Webseiten aufrufbar** ist für Daten gedacht, die ohnehin öffentlich sind, denn der Schlüssel steht dann im Quelltext der Webseite; mit Mitgliederterminen, Mitgliederzahlen oder Personendaten geht es deshalb nicht.

Anlegen, Ändern, Schlüsselwechsel und Löschen stehen im Änderungsprotokoll. Je Zugang sind 600 Abrufe in der Stunde möglich.

## Für Entwickler

Die Adresse der Schnittstelle und die Beschreibung (OpenAPI) stehen oben auf der Seite. Der Schlüssel wird als `Authorization: Bearer hpk_…` mitgeschickt. Fehler kommen als `application/problem+json` mit einem festen `code`.
