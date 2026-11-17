---
key: page.settings_data_transfer
titel: Einstellungen › Datenübernahme
rechte: [data.export, export.run]
routen: [/einstellungen/datenuebernahme]
stichworte: [Export, Sicherung, Umzug, JSON]
---

Mit dem vollständigen Export nehmt ihr alle Daten der Einheit als Datei mit, etwa für einen Umzug auf eine andere HUBIplan-Instanz oder als eigene Sicherung. Der Import spielt eine solche Datei ein. Bewahrt die Datei sicher auf, sie enthält personenbezogene Daten.

Neue Exporte kennzeichnen ihr Rechteformat ausdrücklich. Bei Dateien ohne diese Angabe und mit mehrdeutigen Codes muss die ursprüngliche
Bedeutung ausdrücklich ausgewählt werden. **Erneut prüfen** zeigt die danach
wirksamen Rollenrechte. Diese sind vor der Übernahme ausdrücklich zu bestätigen.
Das historische Format umfasst die früheren Foto-/Ausweis-/Zugangsdatenrechte.
Neu exportierte schmale Leserechte bleiben schmal. Unbekannte Formate werden abgelehnt.
URLs müssen HTTP(S)-Adressen sein. Bei aktiviertem Virenscanner wird jede tatsächlich
übernommene innere Datei einzeln geprüft, auch wenn das äußere Archiv zu groß für
den Uploadscan war. Bei verpflichtender Prüfung sind fehlender Scanner und zu große
innere Dateien ein Abbruchgrund; ein Fehler verhindert den Datenimport.

Eine Untereinheit aus einer Datei einzulesen braucht neben „Einstellungen“ die Bearbeitungsrechte der Bereiche, die die Datei enthält, etwa „Mitglieder bearbeiten“ für Mitgliedschaften oder „Ablage bearbeiten“ für Ordner und Dokumente. Fehlt eines, nennt die Prüfung die fehlenden Rechte. Alle Zeilen der Datei müssen zur neuen Untereinheit gehören; die Satzung aus der Datei kommt nicht mit, sie gehört dem Verein. Import, Export einer Untereinheit und Kopplungen im Verbund verlangen eine frische Bestätigung mit dem zweiten Faktor.
