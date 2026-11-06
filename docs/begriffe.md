# Begriffe in Oberfläche, App und Hilfe

Ein Begriff, eine Bezeichnung: Web-Oberfläche, Android-App und Hilfe verwenden dieselben Wörter
für dieselbe Sache. Die englischen Entsprechungen stehen in [glossar-en.md](glossar-en.md).

## Regeln

- **Menüpunkt = Überschrift.** Ein Unterpunkt in der Seitenleiste heißt genauso wie die
  Überschrift der Seite. Die Überschrift nennt die Unterseite, darüber steht klein der Bereich
  (`SectionTitle` in `frontend/src/components/ui.tsx`); der Browser-Tab heißt
  „Unterseite · Bereich“.
- **Menüpfade in Texten** schreiben wir als „Bereich › Punkt“ mit den Wörtern aus dem Menü.
  `frontend/src/test/Hilfe.test.tsx` prüft das für die Hilfe.
- **Eigene Bezeichnungen des Vereins** (z. B. Korps, Zug, Sparte) ersetzen „Untereinheit“ überall.
  Hat ein Verein mehrere Ebenen, nennt jede Ebene ihre eigene Bezeichnung; gezählt wird je Ebene
  („7 Korps · 15 Züge“).
- **Modul-Einstellungen** heißen in jedem Bereich „Einrichtung“ und stehen als letzter Unterpunkt.
  „Einstellungen“ ist nur der Bereich für die ganze Einheit.
- Links werden nie unterstrichen; sie sind an Farbe und Schriftstärke erkennbar.

## Verbindliche Begriffe

| Sache | Begriff (Web, App, Hilfe) | Englisch | Nicht verwenden |
|---|---|---|---|
| Nachrichten des Vereins an Mitglieder | **Mitteilungen** (Mitgliedersicht) | Messages | „Schreiben“ |
| Verfassen und Versenden im Vorstand | **Rundschreiben** (Verwaltung) | Circulars | – |
| Eigenes Benutzerkonto | **Mein Konto** | My account | „Konto“ allein |
| Bereich des Mitglieds (auch in der Einheitenwahl) | **Mein Bereich** | My area | „Meine Daten“ als Bereichsname |
| Gespeicherte eigene Angaben | **Meine Daten** (Unterpunkt) | My data | „Profil“ für Vereinsdaten |
| Anmeldedaten und Name der Person | **Profil** (Mein Konto) | Profile | – |
| Mitgliedsausweis | **Ausweis**, Aktion „Ausweis zeigen“ | Card, “Show ID card” | „Mitgliedskarte“ |
| App koppeln | **Mein Konto › App & andere Instanzen** | My account › App & other instances | „App auf dem Telefon“ als Pfad |
| Anmeldung, 2FA, Passwort | **Mein Konto › Anmeldung & Sicherheit** | My account › Sign-in & security | – |
| Einrichtung eines Moduls | **Einrichtung** | Setup | „Einstellungen“ im Modul |
| Kasse und Buchungen | **Finanzen › Kassenbuch** | Finances › Cash book | „Kasse“ als Bereichsname |
| Rechnungen an Mitglieder | **Finanzen › Rechnungen** | Finances › Invoices | „Beiträge“ als Menüpunkt |
| Wechsel zwischen Untereinheiten | **Wechselanfragen** | Change requests | „Anfragen“ allein in Überschriften |
| Von Mitgliedern gemeldete Änderungen | **Änderungsmeldungen** | Change notices | – |
| Material, Infrastruktur und Belegung zusammen (Seitenleiste) | **Material & Räume** mit **Material**, **Räume und Anlagen**, **Belegung** | Equipment & rooms with Equipment, Rooms and facilities, Bookings | drei eigene Hauptpunkte |
| Wettbewerbstitel und ihre Träger (Wettbewerbe) | **Titel und Sieger** | Titles and winners | „Titel und Würden“ als Menüpunkt |
| König, Prinz und andere Würden (Mitglieder) | **Würdenträger** | Title holders | Würden an zwei Stellen pflegen |
| Wechselanfragen und Änderungsmeldungen zusammen | **Mitglieder › Änderungen und Wechsel** | Members › Changes and transfers | „Anfragen“ als Menüpunkt |
| Blättern in Listen | **Vorherige Seite / Nächste Seite** | Previous page / Next page | „Zurück / Weiter“ |
| Aufgabe für Mitglieder | **Aufgabe** | Task | „To-do“ |
| Funktion in einer Einheit (Kassierer, Zugführer), mit oder ohne Rechte | **Rolle** | Role | „Funktion“ in der Oberfläche |
| Was eine Rolle darf; Seite in den Einstellungen | **Rechte**, **Einstellungen › Rollen und Rechte** | Permissions, Settings › Roles and permissions | „Rechte für Zugänge“, „Rollen & Benutzer“ |
| Person hat eine Rolle von … bis … | **Amtszeit**; Handlungen **besetzen** und **beenden** | Term of office; assign, end | „Zuordnung“, „zuordnen“, „vergeben“ |
| Anmeldung einer Person (E-Mail, Passwort, Zwei-Faktor) | **Konto** | Account | „Benutzer“, „Benutzerkonto“ |
| Konto darf in den Mitgliederbereich | **Mitgliederbereich freigeschaltet**; **freischalten**, **sperren** | Member area enabled; enable, block | „Zugang“ allein |
| Rolle mit allen Rechten in einer Untereinheit | **Leitung**, Handlung **Leitung besetzen** | Head, Assign head | „Verwalter“ |
| Was auf eine Entscheidung oder Handlung wartet (Startseite, App) | **Zu erledigen** | To do | „Offene Punkte“, „Offene Aufgaben“ dafür |
| Rechnungen im App-Bereich Verwaltung | **Rechnungen** | Invoices | „Beiträge“ |
| Buchungen im App-Bereich Verwaltung | **Kassenbuch** | Cash book | „Kasse“ |
| Geburtstage und Jubiläen der nächsten Wochen | **Jubiläen und Geburtstage** | Anniversaries and birthdays | „Anlässe“ |

## Pflege

- Neue Begriffe hier eintragen, bevor sie in Web, App und Hilfe auftauchen.
- Die App folgt dieser Liste (`hubiplan-android`, `app/src/main/assets/texte/`).
