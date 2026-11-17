# Rückmeldungen nach Aktionen

Eine bestätigte Änderung braucht eine verständliche Rückmeldung in Deutsch und Englisch.
Erfolg wird erst nach der Serverbestätigung gezeigt. Beim nächsten Versuch wird eine ältere
Bestätigung entfernt; Fehler dürfen keinen alten Erfolg stehen lassen. Der Fokus bleibt im
Arbeitsablauf und wird durch die Meldung nicht übernommen.

## Vorhandene Rückmeldewege

| Bereich | Rückmeldung | Fehler und Wiederholung |
| --- | --- | --- |
| Web-Formulare in Verwaltung, Finanzen, Mitgliedschaften und Einstellungen | `useForm` und `Alert`, `role=status`, atomarer Meldungsinhalt | Feldfehler am Feld, Fehler als `role=alert`, erneutes Speichern |
| Web-Autospeichern, Aufgabenserien, Dokumente und lokale Notizen | bestehende `SaveStatus`-Region: ausstehend, speichert, gespeichert | Fehler, Eingaben erhalten, erneut versuchen oder verwerfen |
| Web-Aktionen mit Rückgängig | `UndoControls` mit Status und eigener Rückgängig-Aktion | API-Fehler und wiederherstellbare Aktion |
| Web-Mitgliederzugang, Ausweise, Foto, Anmeldung, Kalender-Abo, externe Kalender, Versand, Importe und Freigaben | lokale bestätigte Meldung über `Alert`; kein pauschaler Erfolg für Hintergrundanfragen | bestehende Fehlerkanäle und lokale Wiederholung |
| Web-Terminantworten und Standmodus | örtliche Statusregion, bestätigter Zustand beziehungsweise sichtbarer Synchronisierungszustand | Fehler und noch nicht übertragene Daten gesondert |
| Web-2FA und Informations-E-Mails | bereits vorhandene `StatusMessage`-Region wird nach Bestätigung gefüllt | vorheriger Erfolg wird beim nächsten Versuch geleert |
| Android-Profil, Terminantworten, Mitgliederaufgaben und Mitteilungsversand | `StatusNotice`, höfliche native Live-Region | Fehler gesondert dringend; vorheriger Erfolg entfernt |
| Android-Verwaltung, Buchungen, Quittungen und Aufgaben | gemeinsamer Material-`SnackbarHost` mit vorhandenen Rückgängig-Aktionen; Entwurfs- und Synchronisierungszustände zusätzlich sichtbar | fehlgeschlagene Übertragung erhält Entwürfe und bietet den vorgesehenen Rückweg |

Diese Übersicht beschreibt die geprüften Rückmeldewege im Quellcode, nicht einen ausgeführten
Test jeder möglichen Kombination aus Rolle, Aktion und Unterbrechung. Eine reine Navigation,
Auswahl, Downloadöffnung oder automatische Hintergrundabfrage braucht keine zusätzliche
Erfolgsmeldung. Meldungen und fokussierte Abschlussansichten dürfen nicht doppelt angesagt werden.

Die Checkbox für Informations-E-Mails bleibt beim Speichern fokussierbar. Sie kennzeichnet den
laufenden Vorgang und sperrt weitere Änderungen, ohne das native `disabled` kurz einzuschalten;
dies würde den Browserfokus entfernen. Ein bloßes `aria-disabled` reicht nicht: Maus- und
Tastaturaktionen werden während des laufenden Vorgangs auch tatsächlich abgefangen.

## Speichern, Verwerfen, Löschen: ein Modell

Seit dem UX-Audit vom 16.11.2026 (X-05, VW-22, VW-23, VW-26) gilt für die Verwaltung:

| Fall | Regel | Baustein |
|---|---|---|
| Stammdaten ohne Außenwirkung (Organisation, Briefbogen, Mitgliederakte …) | speichert automatisch und zeigt den Stand | `useAutoSave` + `SaveStatus` |
| Außen- oder Rechtewirkung (Farben, Rollen und Rechte, Veröffentlichen, Versand) | Entwurf oder Vorschau, wirksam erst mit genau einem Primärknopf, der die Wirkung nennt („Für alle übernehmen“, „Veröffentlichen“, „Senden“) | `useForm` + `useDraftGuard` |
| Neues anlegen | Formular mit „Speichern“ oder „Anlegen“ und „Abbrechen“ | `useForm`, `useChangesGuard` |
| Dialog mit Eingaben | Esc, „Schließen“ und der Klick daneben fragen nach einer Eingabe „Eingaben verwerfen?“; ohne Eingabe schließen sie sofort | `Modal` (Standard), `beforeClose` für eigene Regeln, `guard={false}` nur für Suchfelder |
| Seite verlassen mit offenen Eingaben | Rückfrage in der App und im Browser | `useDraftGuard`, `useChangesGuard` |
| Löschen, das sich zurücknehmen lässt (Papierkorb, Rückgängig) | ohne Rückfrage, mit Hinweis und „Rückgängig“ | `undo.ts`, siehe [rueckgaengig.md](rueckgaengig.md) |
| Löschen, das sich nicht zurücknehmen lässt | Rückfrage mit Handlungsverb auf dem Knopf und der Folge im Text („lässt sich nicht rückgängig machen“) | `confirmDialog` mit `confirmLabel` |
| Rückfrage, die nichts löscht oder trennt („Jetzt abgleichen?“, „Auf der Webseite zeigen?“) | Knopf nennt die Handlung, nicht rot | `confirmDialog` mit `confirmLabel` (Pflicht) und `danger: false` |
| Formular, das unter einer Liste eingeblendet wird | Fokus im ersten Feld, Escape schließt wie „Abbrechen“ | `useRevealFocus(aktiv, schliessen)` |
| Sitzung läuft ab | Vorwarnung; nach Ablauf bleiben die Eingaben stehen | `SessionWatch` |

Jede Formularseite zeigt entweder den Speicherstand oder genau einen Primärknopf, nie keins von
beiden. Die Apps folgen demselben Modell: Eingaben überstehen Drehen und Unterbrechungen, „Zurück“
fragt bei geänderten Eingaben.

## Technische Prüfungen

Alle Tests werden über `scripts/test.sh` ausgeführt. Webregressionen prüfen erfolgreiche und
fehlgeschlagene Einstellungsänderungen, das Entfernen alter Erfolge und den dauerhaften Statusknoten.
Die bestehenden Formular-, Autospeicher-, Rückgängig- und Terminprüfungen bleiben Bestandteil des
Gesamtlaufs. Android prüft die native Semantik auf dem Gerät; der zusätzliche TalkBack-Test nutzt
einen ausdrücklich freigegebenen eigenen Emulator und protokolliert die Übergabe an eine stumme
Prüfsynthese. Das ist ein Nachweis tatsächlicher Textübergabe, keine akustische Hörprüfung.

Mit Betroffenen zu validieren bleiben Verständlichkeit, angemessenes Timing und die Belastung
durch mehrere Meldungen. Unterschiedliche Browser-/Screenreader-Kombinationen, Unterbrechungen
durch fremde Apps und individuelle TalkBack-Einstellungen brauchen weitere Geräteprüfungen.
