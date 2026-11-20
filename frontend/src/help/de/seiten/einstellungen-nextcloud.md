---
key: page.settings_nextcloud
titel: Einstellungen › Nextcloud
rechte: [org.edit]
routen: [/einstellungen/nextcloud]
siehe: [guide.account_create]
stichworte: [Nextcloud, Anmeldung, Dateiablage, Kalender, CalDAV, Gruppen, Gruppenordner]
---

Hier verbindet ihr die Nextcloud eures Vereins mit HUBIplan, sodass sich Mitglieder dort mit ihrem HUBIplan-Konto anmelden können.

Mit **Konten automatisch deaktivieren** schaltet HUBIplan das Nextcloud-Konto ab, sobald jemand bei euch keinen Zugang mehr hat, zum Beispiel weil die Rolle endet. Sitzungen und Sync-Apps werden dabei abgemeldet, die Dateien bleiben. Bekommt die Person wieder eine Rolle, wird das Konto wieder eingeschaltet. Dafür braucht es in der Nextcloud ein eigenes Dienstkonto mit App-Passwort. Mit **Verbindung prüfen** testet ihr es.

Unter „Konten über HUBIplan“ seht ihr, wer sich schon über HUBIplan angemeldet hat und was der nächste Abgleich täte. Hält der Abgleich an, weil zu viele Konten auf einmal betroffen wären, prüft die Rollen und bestätigt dann mit **Jetzt abgleichen**.

## Gruppen laufend abgleichen

Die Nextcloud übernimmt Gruppen sonst nur beim Anmelden. Sync-Apps auf Handy und Rechner melden sich nie neu an: Wer eine Rolle abgibt, aber weiter ein Konto hat, behielte die Gruppe, etwa „Kassierer“, mit allen Gruppenordnern. Mit **Gruppen laufend abgleichen** setzt HUBIplan die Gruppen gleich nach jeder Änderung an Rollen, Ämtern oder Untereinheiten und jede Nacht.

Tragt unter **Gruppen, die HUBIplan abgleicht** ein, welche Gruppen HUBIplan setzen und entfernen darf, zum Beispiel „Vorstand, Mitglieder, Kassierer“. Die Gruppe der Konten über HUBIplan gehört immer dazu. Gruppen, die ihr von Hand pflegt, und „admin“ fasst HUBIplan nie an. Das Dienstkonto muss in der Nextcloud Gruppen-Admin jeder dieser Gruppen sein.

Mit **Gruppen vergleichen** seht ihr vorher, wer in welche Gruppe kommt und wer aus welcher herausfällt; das ändert noch nichts. Würden mehr als drei Konten auf einmal Gruppen verlieren, hält der Abgleich an und alle, die Rollen verwalten, bekommen eine Mail. Prüft dann die Rollen und bestätigt mit **Gruppen jetzt abgleichen**. Dateien gehen dabei nie verloren, nur der Zugriff auf die Ordner der Gruppe.

## Dateien in der Nextcloud

Mit **In Nextcloud ablegen** erscheint neben Kassenbericht, Steuerauswertung, Kassenzählung, Protokoll, Beschlussbuch und Dokumenten ein Knopf **In Nextcloud ablegen**. Die Datei landet in einem Ordner des Dienstkontos: „Vorstand“, „Kasse“ oder „Mitglieder“ unter dem **Ordner im Dienstkonto** (voreingestellt „HUBIplan“). Jeder Ordner ist nur zum Lesen an eine Gruppe freigegeben, voreingestellt „Vorstand“, „Kassierer“ und „Mitglieder“. Nichts wird überschrieben; gibt es den Namen schon, hängt HUBIplan eine Nummer an.

Jede Datei bekommt beim Ablegen eine Art, und danach richtet sich, wie lange sie in der Nextcloud bleibt: Beschlüsse und Grundlagen sowie Planung und Statistik ohne Personen dauerhaft, Kassen- und Steuerunterlagen 10 Jahre und Meldungen an Verbände 6 Jahre nach Jahresende, personenbezogene Listen 3 Monate, Sonstiges 2 Jahre. Unter **Fristen je Art anpassen** stellt ihr das anders ein. Nach Ablauf löscht HUBIplan die Datei in den Papierkorb des Dienstkontos. Listen mit Personendaten legt HUBIplan nur nach ausdrücklicher Bestätigung ab und nie in den Ordner „Mitglieder“.

Bedenkt: In der Nextcloud gelten Verschlüsselung, Rechte und Protokoll von HUBIplan nicht. Wer eine Sync-App nutzt, hat die Dateien auch auf seinem Gerät.

Mit **Ordner zum Übernehmen** erscheint beim Hochladen von Dokumenten, Bildern der Webseite, Anhängen an Terminen und Rundschreiben und Belegen ein Knopf **Aus Nextcloud**. Gebt dafür in der Nextcloud einen Ordner an das Dienstkonto frei, zum Beispiel „An HUBIplan“, und tragt seinen Namen hier ein. HUBIplan holt eine Kopie und prüft sie wie jede hochgeladene Datei; in der Nextcloud bleibt alles, wie es ist. Wer in HUBIplan Dateien hochladen darf, sieht alles in diesem Ordner.

## Termine im Kalender der Nextcloud

Unter **Termine in den Kalender der Nextcloud** schreibt HUBIplan eure Termine in den Kalender der Nextcloud. Es gibt zwei Kalender: **Termine für Mitglieder** mit allem, was jedes Mitglied sieht, und **Termine „nur Vorstand“**. Jeder Kalender wird nur zum Lesen für eine Gruppe freigegeben, voreingestellt „Mitglieder“ und „Vorstand“. Wer in der Gruppe ist, sieht ihn in der Kalender-App der Nextcloud und auf dem Handy.

Bearbeitet werden die Termine weiter in HUBIplan. Alle 15 Minuten schreibt HUBIplan Änderungen nach, mit **Kalender jetzt abgleichen** sofort. Dafür braucht es Dienstkonto und App-Passwort. Schaltet ihr einen Kalender aus, verschwindet er auch in der Nextcloud. Den Vorstandskalender gebt bitte nur für eine Gruppe frei, in der allein der Vorstand ist.

## Im Einzelnen

Unter **Gruppen für einzelne Rollen anpassen** legt ihr fest, in welche Nextcloud-Gruppen eine Rolle kommt, zum Beispiel „1. Kassierer“ und „2. Kassierer“ beide in „Kassierer“. Mehrere Gruppen trennt ihr mit Komma. Ohne Eintrag heißt die Gruppe wie die Rolle. Benennt ihr eine Rolle um, bleibt die Zuordnung erhalten.

Wie lange man angemeldet bleibt, bestimmt die Nextcloud selbst. Üblich sind bis zu 24 Stunden ohne Aktivität und bis zu 15 Tage mit „angemeldet bleiben“; Sync-Apps bleiben dauerhaft verbunden. Endet der Zugang bei HUBIplan, scheitert ohne automatisches Deaktivieren nur die nächste Anmeldung. Laufende Sitzungen und Sync-Apps beendet erst das automatische Deaktivieren oder ein Abschalten des Kontos in der Nextcloud.

„Nur mit PKCE (S256)“ ist von Anfang an eingeschaltet und schützt den Anmeldecode. Die Nextcloud-App „user_oidc“ nutzt PKCE von selbst. Ausschalten musst du es nur für ältere Anwendungen, die PKCE nicht können.

Die Konten „admin“, „root“, „administrator“ und das Dienstkonto lassen sich nie zuordnen, auch nicht über „Bisherige Benutzernamen“. Steht dort schon eine solche Zeile, zeigt die Seite sie rot an; sie wirkt nicht und sollte entfernt werden. Änderungen an Benutzernamen und Gruppen für Rollen verlangen eine frische Bestätigung mit dem zweiten Faktor, und alle mit dem Recht, Rollen zu verwalten, bekommen einen Hinweis per Mail.
