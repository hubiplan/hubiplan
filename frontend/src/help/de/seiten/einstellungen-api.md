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
  ]
---

Mit einem API-Zugang liest ein anderes Programm Daten eurer Einheit, zum Beispiel die Software eures Dachverbands, eine eigene Webseite oder eine Anzeigetafel. Jeder Zugang hat einen eigenen Schlüssel, darf nur lesen, was ihr ankreuzt, und läuft von selbst ab.

Über diese Zugänge gibt es keine Namen, Anschriften oder Bankdaten einzelner Mitglieder, und ein Zugang kann nichts ändern. Legt für jedes Programm einen eigenen Zugang an; dann lässt sich einer löschen, ohne die anderen zu stören.

Die Seite gibt es nur, wenn das Modul „API für andere Programme“ eingeschaltet ist und deine Rolle das Zusatzrecht „API-Zugänge verwalten“ hat. Dieses Recht bekommt keine Rolle von selbst.

## Was ein Zugang lesen darf

- Einheit: Name, Anschrift, Kontakt, Logo und die Untereinheiten.
- Termine: Termine mit der Sichtbarkeit „nach außen öffentlich“, auf Wunsch auch die für Mitglieder. Termine „nur Vorstand“, Zu- und Absagen gibt es nie.
- Mitgliederzahlen: Anzahlen zum Stichtag nach Alter, Geschlecht und Untereinheit, keine Personen.
- Vorstand und Ämter: Rollen mit ihrer Funktionsadresse; Namen nur, wenn sie auf eurer öffentlichen Webseite stehen.
- Ergebnisse, Beiträge, Dokumente: nur, was eure Webseite veröffentlicht.

Ein Bereich erscheint nur, wenn das Modul dazu eingeschaltet ist. Mit **Gilt für** begrenzt ihr einen Zugang auf eine Untereinheit; er sieht dann nur deren Daten.

## Schlüssel und Sicherheit

Der Schlüssel steht genau einmal auf der Seite: nach dem Anlegen und nach **Neuen Schlüssel erzeugen**. HUBIplan speichert ihn nicht lesbar. Gebt ihn auf sicherem Weg weiter, nicht per unverschlüsselter E-Mail. Für beides fragt HUBIplan nach einem frischen Code der Zwei-Faktor-Anmeldung.

Nach **Neuen Schlüssel erzeugen** gilt der bisherige Schlüssel noch sieben Tage, damit sich das andere Programm ohne Ausfall umstellen lässt. Ist ein Schlüssel in falsche Hände geraten, löscht den Zugang: Dann gilt er sofort nicht mehr.

Jeder Zugang läuft spätestens nach einem Jahr ab; 30 Tage vorher bekommen alle mit dem Recht eine E-Mail. Mit **Bearbeiten** verlängert ihr ihn. Wird ein Zugang 90 Tage nicht genutzt, schaltet HUBIplan ihn ab; **Wieder einschalten** nimmt ihn wieder in Betrieb.

Unter **Erlaubte Adressen (optional)** lasst ihr Abrufe nur von bestimmten IP-Adressen zu. **Aus fremden Webseiten aufrufbar** ist für Daten gedacht, die ohnehin öffentlich sind, denn der Schlüssel steht dann im Quelltext der Webseite; mit Mitgliederterminen oder Mitgliederzahlen geht es deshalb nicht.

Anlegen, Ändern, Schlüsselwechsel und Löschen stehen im Änderungsprotokoll. Je Zugang sind 600 Abrufe in der Stunde möglich.

## Für Entwickler

Die Adresse der Schnittstelle und die Beschreibung (OpenAPI) stehen oben auf der Seite. Der Schlüssel wird als `Authorization: Bearer hpk_…` mitgeschickt. Fehler kommen als `application/problem+json` mit einem festen `code`.
