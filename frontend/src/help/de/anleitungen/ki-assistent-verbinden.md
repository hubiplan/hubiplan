---
key: guide.mcp_connect
titel: KI-Assistenten mit HUBIplan verbinden
routen: [/mein-konto/app]
reihe: 50
stichworte: [KI, Claude, ChatGPT, MCP, Assistent, Webseite, Entwurf, Texte schreiben]
---

Ein KI-Assistent wie Claude oder ChatGPT kann die Webseite deiner Einheit lesen und Texte als Entwurf schreiben oder überarbeiten. Veröffentlicht wird nur in HUBIplan, von einem Menschen. Der Assistent darf nie mehr als du selbst; Mitgliederdaten, Mails und Zahlungen gibt es über ihn nicht.

Einmal vorab (Vorstand oder Rollenverwaltung):

1. Schalte unter [Einstellungen › Module](/einstellungen/module) das Modul „KI-Assistenten“ ein. Es braucht die Webseite.
2. Gib unter [Einstellungen › Rollen und Rechte](/einstellungen/rollen) der passenden Rolle das Zusatzrecht „KI-Assistenten verbinden“.
3. Wer verbinden will, braucht die Zwei-Faktor-Anmeldung (Mein Konto › Anmeldung & Sicherheit).

Verbinden:

1. Öffne [Mein Konto › App & andere Instanzen](/mein-konto/app) und kopiere die Adresse unter „KI-Assistenten“, z. B. `https://verein.example.org/api/mcp/verein/`.
2. Trage sie im Assistenten als neue Verbindung ein (je nach Assistent „Connector“, „Integration“ oder „MCP-Server“).
3. Der Assistent öffnet HUBIplan im Browser. Melde dich mit Passwort und Code an, wähle die Einheit und klicke auf **Erlauben**.

Achte vor dem Erlauben auf die Adresse unter „Die Freigabe geht an“: Dorthin gehen deine Rechte. Den Namen des Assistenten kann sich jeder selbst geben. Warnt HUBIplan, dass die Adresse zu keinem bekannten Assistenten gehört, erlaube nur, wenn du die Verbindung gerade selbst eingerichtet hast. Kam der Link per Mail oder Nachricht, klicke auf **Ablehnen**.

Danach kannst du im Assistenten z. B. schreiben: „Überarbeite den Text ‚Über uns‘ unserer Webseite und mach ihn freundlicher.“ Der Assistent speichert den Entwurf und gibt dir einen Link zur Vorschau. Gefällt dir das Ergebnis, veröffentlichst du es in HUBIplan unter Webseite. Jede Änderung steht im Änderungsprotokoll mit „KI-Assistent“ und lässt sich rückgängig machen.

Bei jeder neuen Verbindung bekommst du eine Mail. Eine Verbindung gilt höchstens 30 Tage und endet nach 14 Tagen ohne Nutzung, ebenso wenn du dein Passwort änderst oder das Recht wegfällt. Trennen kannst du sie jederzeit unter [Mein Konto › App & andere Instanzen](/mein-konto/app) mit **Trennen**.

Was du dem Assistenten schreibst und was er liest, geht an seinen Anbieter. Schreibe dort keine vertraulichen Daten hinein. Ohne Anmeldung kann ein Assistent unter `/api/mcp/` nur die Hilfe von HUBIplan lesen.
