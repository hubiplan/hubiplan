---
key: guide.bank_fetch
titel: Umsätze direkt bei der Bank abrufen
modul: finance
rechte: [finance.edit]
routen: [/finanzen/kontoauszuege]
reihe: 105
stichworte: [Bank, FinTS, HBCI, Umsätze, Abruf, PIN, TAN, Bankzugang, Online-Banking]
---

Statt eine Datei aus dem Online-Banking zu laden, kann HUBIplan die Umsätze selbst bei der Bank holen. Dazu muss die Bankanbindung auf dem Server eingerichtet und unter Einstellungen › Module für den Verein eingeschaltet sein.

## Einmal einrichten

1. Trage unter Finanzen › Konten beim Bankkonto die IBAN ein.
2. Öffne [Finanzen › Kontoauszüge](/finanzen/kontoauszuege) und klicke auf **Bankzugang hinzufügen**.
3. Gib Bezeichnung, Bankleitzahl, die FinTS-Adresse deiner Bank und deinen Anmeldenamen für das Online-Banking ein. Die FinTS-Adresse (auch „HBCI mit PIN/TAN“) nennt die Bank auf ihrer Webseite oder am Telefon.
4. Gib deine PIN ein und klicke auf **Bei der Bank anmelden**. Hat die Bank mehrere Freigabeverfahren, wählst du das, das du auch im Online-Banking nutzt.

HUBIplan verbindet danach die Konten, deren IBAN die Bank zu diesem Zugang nennt.

## Umsätze abrufen

1. Klicke beim Bankzugang auf **Umsätze abrufen** und gib deine PIN ein.
2. Verlangt die Bank eine Freigabe, tippst du die TAN ein oder bestätigst in der App deiner Bank. Bei der Freigabe in der App macht HUBIplan von selbst weiter.
3. Die neuen Umsätze stehen danach als Auszug in der Liste, mit Vorschlägen wie bei einer eingelesenen Datei.

Abgerufen wird seit dem letzten Abruf, beim ersten Mal die letzten 90 Tage. Umsätze, die schon eingelesen sind, auch aus einer Datei, kommen nicht doppelt.

## Deine PIN

Deine PIN gibst du bei jedem Abruf neu ein. HUBIplan speichert sie nicht. Lehnt die Bank die Anmeldung ab, fragt HUBIplan vor dem nächsten Versuch nach; nach zwei Ablehnungen ruht der Zugang 24 Stunden, damit die Bank ihn nicht sperrt.
