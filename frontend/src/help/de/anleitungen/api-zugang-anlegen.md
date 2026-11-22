---
key: guide.api_access_create
titel: Einem anderen Programm einen API-Zugang geben
modul: api
rechte: [api.manage]
routen: [/einstellungen/api]
stichworte:
  [API, Schlüssel, Verbandssoftware, Dachverband, Schnittstelle, eigene Webseite, Datenaustausch]
---

1. Öffne [Einstellungen › API-Zugänge](/einstellungen/api) und klicke auf **Zugang anlegen**.
2. Gib einen **Name** ein, am besten den des Programms, und trage **Empfänger** und **Zweck** ein.
3. Soll der Zugang nur eine Untereinheit sehen, wähle sie unter **Gilt für**.
4. Kreuze unter **Was der Zugang lesen darf** nur an, was das Programm wirklich braucht.
5. Prüfe das Datum **Gültig bis** und klicke auf **Zugang anlegen**.
6. Bestätige mit einem Code der Zwei-Faktor-Anmeldung, wenn HUBIplan danach fragt.
7. Klicke auf **Schlüssel kopieren** und gib den Schlüssel auf sicherem Weg an den Empfänger weiter.

Der Schlüssel steht nur jetzt auf der Seite. Geht er verloren, hilft **Neuen Schlüssel erzeugen**; der bisherige gilt dann noch sieben Tage. Der Empfänger braucht außerdem die Adresse der Schnittstelle, die oben auf der Seite steht.

Soll das Programm Mitglieder, Ehrungen, Qualifikationen oder die namentliche Verbandsmeldung lesen, wählst du zusätzlich den **Empfänger (Geschäftspartner)** und die **Rechtsgrundlage** und bestätigst sie. Lege den Empfänger vorher unter [Verwaltung › Geschäftspartner](/geschaeftspartner) an. Soll das Programm von Änderungen erfahren, trage eine **Adresse für Benachrichtigungen** ein; das Geheimnis dazu steht wie der Schlüssel nur einmal auf der Seite.

Fehlt der Menüpunkt, ist das Modul „API für andere Programme“ unter [Einstellungen › Module](/einstellungen/module) aus oder deiner Rolle fehlt das Zusatzrecht „API-Zugänge verwalten“ ([Rollen und Rechte](/einstellungen/rollen)).
