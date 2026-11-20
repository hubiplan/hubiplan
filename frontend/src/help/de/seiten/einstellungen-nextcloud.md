---
key: page.settings_nextcloud
titel: Einstellungen › Nextcloud
rechte: [org.edit]
routen: [/einstellungen/nextcloud]
siehe: [guide.account_create]
stichworte: [Nextcloud, Anmeldung, Dateiablage, Kalender, CalDAV]
---

Hier verbindet ihr die Nextcloud eures Vereins mit HUBIplan, sodass sich Mitglieder dort mit ihrem HUBIplan-Konto anmelden können.

Mit **Konten automatisch deaktivieren** schaltet HUBIplan das Nextcloud-Konto ab, sobald jemand bei euch keinen Zugang mehr hat, zum Beispiel weil die Rolle endet. Sitzungen und Sync-Apps werden dabei abgemeldet, die Dateien bleiben. Bekommt die Person wieder eine Rolle, wird das Konto wieder eingeschaltet. Dafür braucht es in der Nextcloud ein eigenes Dienstkonto mit App-Passwort. Mit **Verbindung prüfen** testet ihr es.

Unter „Konten über HUBIplan“ seht ihr, wer sich schon über HUBIplan angemeldet hat und was der nächste Abgleich täte. Hält der Abgleich an, weil zu viele Konten auf einmal betroffen wären, prüft die Rollen und bestätigt dann mit **Jetzt abgleichen**.

## Termine im Kalender der Nextcloud

Unter **Termine in den Kalender der Nextcloud** schreibt HUBIplan eure Termine in den Kalender der Nextcloud. Es gibt zwei Kalender: **Termine für Mitglieder** mit allem, was jedes Mitglied sieht, und **Termine „nur Vorstand“**. Jeder Kalender wird nur zum Lesen für eine Gruppe freigegeben, voreingestellt „Mitglieder“ und „Vorstand“. Wer in der Gruppe ist, sieht ihn in der Kalender-App der Nextcloud und auf dem Handy.

Bearbeitet werden die Termine weiter in HUBIplan. Alle 15 Minuten schreibt HUBIplan Änderungen nach, mit **Kalender jetzt abgleichen** sofort. Dafür braucht es Dienstkonto und App-Passwort. Schaltet ihr einen Kalender aus, verschwindet er auch in der Nextcloud. Den Vorstandskalender gebt bitte nur für eine Gruppe frei, in der allein der Vorstand ist.

## Im Einzelnen

Unter **Gruppen für einzelne Rollen anpassen** legt ihr fest, in welche Nextcloud-Gruppen eine Rolle kommt, zum Beispiel „1. Kassierer“ und „2. Kassierer“ beide in „Kassierer“. Mehrere Gruppen trennt ihr mit Komma. Ohne Eintrag heißt die Gruppe wie die Rolle. Benennt ihr eine Rolle um, bleibt die Zuordnung erhalten.

Wie lange man angemeldet bleibt, bestimmt die Nextcloud selbst. Üblich sind bis zu 24 Stunden ohne Aktivität und bis zu 15 Tage mit „angemeldet bleiben“; Sync-Apps bleiben dauerhaft verbunden. Endet der Zugang bei HUBIplan, scheitert ohne automatisches Deaktivieren nur die nächste Anmeldung. Laufende Sitzungen und Sync-Apps beendet erst das automatische Deaktivieren oder ein Abschalten des Kontos in der Nextcloud.

„Nur mit PKCE (S256)“ ist von Anfang an eingeschaltet und schützt den Anmeldecode. Die Nextcloud-App „user_oidc“ nutzt PKCE von selbst. Ausschalten musst du es nur für ältere Anwendungen, die PKCE nicht können.

Die Konten „admin“, „root“, „administrator“ und das Dienstkonto lassen sich nie zuordnen, auch nicht über „Bisherige Benutzernamen“. Steht dort schon eine solche Zeile, zeigt die Seite sie rot an; sie wirkt nicht und sollte entfernt werden. Änderungen an Benutzernamen und Gruppen für Rollen verlangen eine frische Bestätigung mit dem zweiten Faktor, und alle mit dem Recht, Rollen zu verwalten, bekommen einen Hinweis per Mail.
