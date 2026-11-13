---
key: guide.mcp_connect
titel: KI-Assistenten mit HUBIplan verbinden
routen: [/mein-konto/app]
reihe: 50
stichworte:
  [
    KI,
    Claude,
    ChatGPT,
    MCP,
    Assistent,
    Webseite,
    Entwurf,
    Texte schreiben,
    Gestaltung,
    Menü,
    Bilder hochladen,
    Alternativtext,
    Instagram,
    Facebook,
  ]
---

Ein KI-Assistent wie Claude oder ChatGPT kann die Webseite deiner Einheit lesen und als Entwurf bearbeiten: Texte, Startseite, Gestaltung und Menü. Veröffentlicht wird nur in HUBIplan, von einem Menschen. Der Assistent darf nie mehr als du selbst; Mitgliederdaten, Mails und Zahlungen gibt es über ihn nicht.

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

Was der Assistent außerdem kann:

- Gestaltung, Menü und Startseite: Design, Farben, Feinabstimmung und Kopfbild wählen, das Menü ordnen (Überschriften, Links nach außen, Knopf) und eigene Abschnitte der Startseite anlegen, verschieben oder ausblenden. Das braucht das Recht „Webseite verwalten“ und landet im Entwurf. Bausteine ein- oder ausschalten geht nur in HUBIplan.
- Titelbild und Bilderkarussell: Der Assistent kann das große Bild oben auf der Startseite (Bild oder Bilderkarussell der Begrüßung) und das Bild oben auf einer Textseite setzen, z. B. „Nimm das neue Foto vom Festzug als Titelbild“. Auch das landet im Entwurf. Fehlt dem Bild ein Alternativtext, weist er darauf hin.
- Bilder hochladen: Schreib z. B. „Ich will Fotos vom Schützenfest hochladen“. Der Assistent gibt dir einen Link, der 30 Minuten für bis zu 20 Bilder gilt. Öffne ihn auf Handy oder PC und wähle die Fotos; sie gehen direkt an HUBIplan, nicht über den Chat, und landen unter Webseite › Bilder.
- Bilder beschreiben: Der Assistent sieht die Bilder klein und schlägt Alternativtext und Bildunterschrift vor. Bei Bildern, die schon auf der Webseite stehen, ergänzt er nur fehlende Texte; vorhandene änderst du selbst. Personen erkennt oder benennt er nicht.
- Bilder per Adresse: Von Servern, die ihr unter [Webseite › Internetadresse](/webseite/domain) bei „Bilder für KI-Assistenten“ freigebt (etwa die Nextcloud des Vereins), holt HUBIplan ein Bild selbst. Die Quelle kommt in die Bildunterschrift. Ohne Eintrag geht das nicht.
- Erscheinungsbild: Farben mit Namen und Verwendung, weitere Farben, Verläufe, Farbrollen und das Logo (aus einem Bild unter Webseite › Bilder) ändern. Das gilt sofort für HUBIplan und die Webseite, es gibt keinen Entwurf; der Assistent fragt vorher nach. Zurücknehmen lässt sich jede Änderung im Änderungsprotokoll mit „Rückgängig“. Diese Freigabe ist nicht von selbst dabei: Hake beim Verbinden unter „Zusätzlich erlauben“ das Erscheinungsbild an. Es braucht außerdem das Recht für das Erscheinungsbild.
- Beiträge für Instagram oder Facebook: Der Assistent legt Text und Bilder als Entwurf unter [Webseite › Social Media](/webseite/beitraege) ab. Dort kopierst du den Text, speicherst die Bilder und postest selbst; HUBIplan veröffentlicht nichts bei Meta.

Neue Bilder sind erst öffentlich, wenn sie in einem veröffentlichten Text oder Abschnitt stehen.

Bei jeder neuen Verbindung bekommst du eine Mail. Eine Verbindung gilt höchstens 30 Tage und endet nach 14 Tagen ohne Nutzung, ebenso wenn du dein Passwort änderst oder das Recht wegfällt. Trennen kannst du sie jederzeit unter [Mein Konto › App & andere Instanzen](/mein-konto/app) mit **Trennen**.

Was du dem Assistenten schreibst und was er liest, geht an seinen Anbieter. Schreibe dort keine vertraulichen Daten hinein. Ohne Anmeldung kann ein Assistent unter `/api/mcp/` nur die Hilfe von HUBIplan lesen.
