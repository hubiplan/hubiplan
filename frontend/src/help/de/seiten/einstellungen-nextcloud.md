---
key: page.settings_nextcloud
titel: Einstellungen › Nextcloud
bereich: einstellungen
rechte: [org.edit]
routen: [/einstellungen/nextcloud]
stichworte: [Nextcloud, Anmeldung, Dateiablage]
---

Hier verbindet ihr die Nextcloud eures Vereins mit HUBIplan, sodass sich Mitglieder dort mit ihrem HUBIplan-Konto anmelden können.

Mit **Konten automatisch deaktivieren** schaltet HUBIplan das Nextcloud-Konto ab, sobald jemand bei euch keinen Zugang mehr hat, zum Beispiel weil die Rolle endet. Sitzungen und Sync-Apps werden dabei abgemeldet, die Dateien bleiben. Bekommt die Person wieder eine Rolle, wird das Konto wieder eingeschaltet. Dafür braucht es in der Nextcloud ein eigenes Dienstkonto mit App-Passwort. Mit **Verbindung prüfen** testet ihr es.

Unter „Konten über HUBIplan“ seht ihr, wer sich schon über HUBIplan angemeldet hat und was der nächste Abgleich täte. Hält der Abgleich an, weil zu viele Konten auf einmal betroffen wären, prüft die Rollen und bestätigt dann mit **Jetzt abgleichen**.

Unter **Gruppen für einzelne Rollen anpassen** legt ihr fest, in welche Nextcloud-Gruppen eine Rolle kommt, zum Beispiel „1. Kassierer“ und „2. Kassierer“ beide in „Kassierer“. Mehrere Gruppen trennt ihr mit Komma. Ohne Eintrag heißt die Gruppe wie die Rolle. Benennt ihr eine Rolle um, bleibt die Zuordnung erhalten.

Wie lange man angemeldet bleibt, bestimmt die Nextcloud selbst. Üblich sind bis zu 24 Stunden ohne Aktivität und bis zu 15 Tage mit „angemeldet bleiben“; Sync-Apps bleiben dauerhaft verbunden. Endet der Zugang bei HUBIplan, scheitert ohne automatisches Deaktivieren nur die nächste Anmeldung. Laufende Sitzungen und Sync-Apps beendet erst das automatische Deaktivieren oder ein Abschalten des Kontos in der Nextcloud.

„Nur mit PKCE (S256)“ ist von Anfang an eingeschaltet und schützt den Anmeldecode. Die Nextcloud-App „user_oidc“ nutzt PKCE von selbst. Ausschalten musst du es nur für ältere Anwendungen, die PKCE nicht können.
