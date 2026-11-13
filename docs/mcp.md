# KI-Schnittstelle (MCP)

Über das **Model Context Protocol** (MCP) kann ein KI-Assistent (Claude, ChatGPT, ein lokales
Modell …) Werkzeuge von HUBIplan aufrufen. Konzept mit allen Stufen: `konzepte/mcp-schnittstelle.md`
im Projektordner. Umgesetzt sind **Stufe 0** (die HUBIplan-Hilfe, ohne Anmeldung und ohne
Vereinsdaten, `/api/mcp/`) und **Stufe 1a mit W1** (Anmeldung nach OAuth 2.1, Webseite der
verbundenen Einheit lesen und als Entwurf bearbeiten, `/api/mcp/verein/`), siehe unten.

## Adresse und Einrichtung

`https://<Instanz>/api/mcp/`, Transport „Streamable HTTP“. Im KI-Assistenten als eigenen
MCP-Server bzw. Connector mit dieser Adresse eintragen, ohne Anmeldung. Caddy leitet `/api/*`
schon ans Backend weiter; eine eigene Regel ist nicht nötig.

Beide Adressen (`/api/mcp/` und `/api/mcp/verein/`) antworten auch ohne Schrägstrich am Ende
direkt, ohne Weiterleitung. claude.ai prüft eine Connector-Adresse ohne Schrägstrich und bricht
bei 301 mit „Nicht gefunden“ ab.

Der Betreiber schaltet die Schnittstelle mit `HUBIPLAN_MCP_HILFE=false` ab (dann 404).
Standard: an, weil nur die ohnehin öffentliche Hilfe (Quelltext unter AGPL) herausgeht.

## Werkzeuge

Alle nur lesend (`readOnlyHint`), ohne Nebenwirkung, ohne Datenbankabfrage. `sprache` ist
`de` (Standard) oder `en`; Antworten und Hinweise kommen in dieser Sprache.

| Werkzeug | Eingaben | Antwort |
|---|---|---|
| `hilfe_suchen` | `frage` (bis 200 Zeichen), `sprache`, `anzahl` (1–10, Standard 5) | Treffer mit Titel, Name, Adresse `/hilfe/<Name>` und erstem Absatz |
| `hilfe_lesen` | `name` (z. B. `passwort-aendern`, `seite/mein-konto`; auch der `key`), `sprache` | ganzer Text als Markdown mit Adresse |
| `hilfe_uebersicht` | `art` (`anleitungen` oder `seiten`), `sprache` | alle Titel mit Namen |
| `begriff_erklaeren` | `begriff`, `sprache` | bis zu drei Einträge aus dem Glossar (Begriffe und Entscheidungen) mit Beispiel |

Die Suche wertet Wörter im Titel (6), in den Stichworten (4) und im Text (1); Anleitungen stehen
bei gleicher Wertung vor Seitenhilfen. Platzhalter wie `{pl}` sind mit den Standardwörtern
gefüllt („Abteilungen“), Bildschirmfotos durch ihren Alternativtext ersetzt („(Bild: …)“).
Links im Text (`/mitglieder`) sind Seiten der Instanz. Hinweise und Ansprechpartner der
Einheit („Hinweise bei uns“, „Wer hilft bei uns?“) gehören zu Vereinsdaten und fehlen.

## Protokoll

- JSON-RPC 2.0 über `POST`, je Anfrage genau eine JSON-Antwort (kein Ereignisstrom, keine
  Sitzung, kein `Mcp-Session-Id`). `GET` und `DELETE`: 405.
- Methoden: `initialize`, `ping`, `tools/list`, `tools/call`; Benachrichtigungen (ohne `id`)
  bekommen `202` ohne Inhalt. Andere Methoden: `-32601`, unbekanntes Werkzeug: `-32602`,
  Stapel (Liste von Nachrichten): `-32600`.
- Fassungen `2025-11-25`, `2025-06-18`, `2025-03-26`; eine unbekannte Fassung beim
  `initialize` wird mit der neuesten beantwortet, ein unbekannter Kopf
  `MCP-Protocol-Version` mit 400.
- Fehler eines Werkzeugs (fehlende Eingabe, unbekannte Anleitung) kommen als Ergebnis mit
  `isError: true` und erklärendem Text, damit der Assistent sich korrigieren kann.
- Ein Werkzeug liefert Text oder eine fertige Liste von Inhaltsteilen (`bild_ansehen`: ein
  `image`-Teil mit JPEG in Base64 und ein `text`-Teil).

## Schutz

- `Origin` muss fehlen oder die eigene Adresse sein (sonst 403): Gegen DNS-Rebinding, wie die
  Spezifikation verlangt. KI-Dienste schicken keinen `Origin`.
- Höchstens 120 Anfragen je Minute und Adresse (429), Anfragen bis 64 KB (413).
- `Cache-Control: no-store`, keine Anmeldung, keine Cookies nötig.

## Hilfe im Backend

Das Backend wird ohne `frontend/` gebaut. Deshalb liegt die Hilfe als Kopie in
`backend/mcpserver/hilfe.json`: die Markdown-Dateien aus `frontend/src/help/de|en` und die
Begriffe und Entscheidungen der Lernhilfen (`frontend/src/learning/content.ts`, englisch über
`learning/en.json`). Erzeugen im Ordner `frontend`:

```bash
node scripts/mcp-hilfe.mjs
```

`src/test/McpHilfe.test.ts` schlägt fehl, wenn die Kopie nicht mehr zur Hilfe passt.
Code: `backend/mcpserver/` (`help_index.py` lesen und suchen, `tools.py` Werkzeuge,
`protocol.py` JSON-RPC, `views.py` Adresse), Tests `backend/tests/test_mcp_hilfe.py`.

## Stufe 1a: Anmeldung (`/api/mcp/verein/`)

Ohne Schlüssel antwortet `/api/mcp/verein/` mit 401 und
`WWW-Authenticate: Bearer resource_metadata="https://<Instanz>/.well-known/oauth-protected-resource/api/mcp/verein"`.
Ein Assistent nach MCP-Spezifikation meldet sich damit selbst an:

| Schritt | Adresse | Inhalt |
|---|---|---|
| Ressource (RFC 9728) | `/.well-known/oauth-protected-resource/api/mcp/verein` | `authorization_servers: [https://<Instanz>/api/mcp/oauth]` |
| Anmeldedienst (RFC 8414) | `/.well-known/oauth-authorization-server/api/mcp/oauth`, auch `/api/mcp/oauth/.well-known/openid-configuration` | Adressen unten |
| Selbstanmeldung (RFC 7591) | `POST /api/mcp/oauth/register` (JSON) | `client_id` `hpmc_…`, kein Geheimnis (`token_endpoint_auth_method: none`) |
| Zustimmung | Seite `/ki/verbinden` (Oberfläche), dahinter `GET/POST /api/mcp/oauth/authorize/` | Code 60 s, einmal |
| Schlüssel | `POST /api/mcp/oauth/token` (Formular) | `authorization_code` mit PKCE S256, `refresh_token` |
| Widerruf (RFC 7009) | `POST /api/mcp/oauth/revoke` | `token=hpm_…` oder `hpmr_…` |

Caddy leitet `/.well-known/oauth-protected-resource*`, `/.well-known/oauth-authorization-server*`
und `/.well-known/openid-configuration/api/mcp/oauth` ans Backend (`deploy/caddy/site.caddy`).
Alle Adressen gehen von der aufgerufenen Adresse der Instanz aus (`organizations.addresses.base_url`).

Regeln:

- Rückleitung: `https://…`, `http://127.0.0.1|localhost|[::1]` (Port darf wechseln, RFC 8252) oder
  ein eigenes Schema eines Programms; nie `javascript:`, `data:`, `file:`, kein Fragment.
  Nicht genutzte Selbstanmeldungen räumt HUBIplan nach einem Tag weg; höchstens 20 je Stunde
  und Adresse.
- Zustimmen kann nur, wer mit **zweitem Faktor** angemeldet ist (`amr` enthält `mfa`) und in der
  gewählten Einheit das Modul **„KI-Assistenten“** (`mcp`, braucht „Webseite“, standardmäßig aus)
  und das Zusatzrecht **`mcp.connect`** hat. Die Seite zeigt groß den Host der Rückleitung (dort
  landet die Freigabe), den selbst gewählten Namen des Assistenten nur nachrangig, Bereiche und
  einen Hinweis zum Datenschutz. Gehört der Host zu keinem bekannten Assistenten
  (`HUBIPLAN_MCP_BEKANNTE_ASSISTENTEN`, Standard `claude.ai,claude.com`, Endungen zählen mit),
  warnt sie vor einer Täuschung; ebenso bei einem Programm auf dem eigenen Rechner.
- Bereiche: `webseite.lesen`, `webseite.entwurf` (schließt lesen ein). Die Hilfe ist immer dabei.
  `verein.erscheinungsbild` gibt es nur, wenn die Person es auf der Seite eigens anhakt (nicht
  vorangekreuzt), auch wenn der Assistent danach fragt; die Seite schickt den Haken als `extra` mit.
- Zugriffsschlüssel `hpm_…` 1 Stunde, Erneuerung `hpmr_…` dreht sich bei jeder Nutzung; die
  Verbindung (`McpGrant`) gilt höchstens 30 Tage und endet nach 14 Tagen ohne Nutzung. Wer
  einen alten Erneuerungsschlüssel noch einmal benutzt, beendet die Verbindung (Kopie). In der
  Datenbank stehen nur SHA-256-Prüfsummen.
- Bei **jeder Anfrage** gilt live: Konto aktiv, `auth_version` unverändert (Passwort geändert,
  überall abgemeldet: Verbindung endet), zweiter Faktor eingerichtet, Modul an, `mcp.connect` in
  der Einheit. Höchstens 300 Anfragen je Stunde und Verbindung.
- Jede neue Verbindung: Mail an das Konto (Art „Sicherheit“) und Eintrag im Änderungsprotokoll
  der Einheit. Liste und **Trennen** unter Mein Konto › App & andere Instanzen
  (`GET /api/me/mcp/`, `DELETE /api/me/mcp/<id>/`).
- Der Betreiber schaltet Stufe 1a mit `HUBIPLAN_MCP=false` für die ganze Instanz ab (404).

## W1: Werkzeuge der Webseite

Die Werkzeuge rufen dieselben Ansichten wie die Oberfläche auf (`website.views`,
`website.content_views`, intern mit der Person der Verbindung). Rechte, Prüfungen, RLS,
Änderungsprotokoll und Rückgängig sind dieselben; das Protokoll nennt „KI-Assistent (<Name>)“.
Die Einheit kommt immer aus der Verbindung, nie aus den Eingaben.

| Werkzeug | Bereich | Was |
|---|---|---|
| `webseite_ansehen` | lesen | Zustand, Adresse, Menü, Bausteine, offener Entwurf |
| `webseite_texte` | lesen | alle Texte mit Nummer, Art, Titel, Stand |
| `webseite_text_lesen` | lesen | `nummer` → Titel, Markdown und Bild (samt Karussell) im Entwurf, veröffentlichter Stand |
| `webseite_bilder` | lesen | Bilder mit Markdown-Zeile `![…](bild:…)` |
| `startseite_ansehen` | lesen | Abschnitte der Startseite im Entwurf mit Art und Inhalt |
| `webseite_pruefen` | lesen | Prüfpunkte (Impressum, Datenschutz) und offene Entwürfe |
| `webseite_vorschau` | lesen | kurz gültiger Link zur Vorschau mit allen Entwürfen |
| `webseite_text_aendern` | entwurf | `nummer`, `titel`, `text`, `bild` (Bildnummer oder `null`), `bilder`, `bilder_takt`, `bilder_zufall` (Karussell der Begrüßung bzw. Untereinheit) → Entwurf des Textes; Hinweis bei Bildern ohne Alternativtext |
| `webseite_textseite_anlegen` | entwurf | `titel`, `adresse`, `text`, `bild` → neue, unveröffentlichte Textseite |
| `startseite_abschnitt_aendern` | entwurf | `schluessel`, `inhalt` (nur geänderte Felder) → Entwurf; Aufbau, Reihenfolge, Aussehen bleiben |

Bewusst nicht: Veröffentlichen, Zustand, Domains, Kontaktnachrichten, Löschen.

## W2/W3: Gestaltung, Menü, Bilder, Beitragsentwürfe

Gestaltung, Menü und Aufbau der Startseite gehen über `PUT website/` mit `{"draft": …}` und
brauchen „Webseite verwalten“; Bilder und Beitragsentwürfe „Inhalte bearbeiten“. Das Menü
(`menu`, `block_names`, `menu_links`, `menu_button`, seit Webseite #75 auch `menu_places`) gehört seit W2 zu `DRAFT_FIELDS`, auch in
der Oberfläche; die Häkchen der Bausteine (`blocks`) und die Hinweisleiste bleiben sofort
wirksam. `clean_draft` prüft die vier Menüfelder zusammen.

| Werkzeug | Bereich | Was |
|---|---|---|
| `webseite_gestaltung_ansehen` | lesen | Design, Farbrollen, Palette, Stilregler, Darstellung, Kopfbild mit erlaubten Werten |
| `webseite_gestaltung_aendern` | entwurf | `design`, `stil`, `farben`, `darstellung`, `kopfbild`, `kopfbild_schmal` (Handyfassung unter 600 px); nur Angegebenes ändert sich, `null` setzt zurück |
| `webseite_menue_ansehen` | lesen | Menübaum im Entwurf mit Namen, Links, Knopf |
| `webseite_menue_aendern` | entwurf | `reihenfolge`, `namen`, `links`, `neu` (Überschrift/Link), `knopf`, `fuss` (Platz im Fuß) |
| `startseite_bausteine` | lesen | Abschnittsarten mit Feldern, Aussehen, `home_choices` |
| `startseite_aufbau_aendern` | entwurf | `neu`, `reihenfolge`, `an`, `aus`, `aussehen`, `entfernen` (nur eigene Abschnitte) |
| `bilder_suchen` | lesen | Suche über Bildunterschrift, Alternativtext, Datei, Untereinheit |
| `bild_ansehen` | lesen | kleine Fassung (640 px, JPEG) als Bildinhalt; Hinweis: keine Personen erkennen |
| `bild_beschreiben` | entwurf | Alternativtext, Bildunterschrift; bei benutzten Bildern nur leere Felder füllen |
| `bild_hochladen_vorbereiten` | entwurf | Hochladelink (30 Minuten, 20 Bilder) |
| `bild_von_adresse` | entwurf | Bild von einem freigegebenen Server, `quelle` Pflicht |
| `social_beitrag_entwerfen` | entwurf | Text (2200 Zeichen), bis 10 Bilder, Kanal → `SocialDraft` |
| `social_entwuerfe` | lesen | Entwürfe, offene zuerst |

**Hochladelink** (`ImageUploadLink`): Nur der SHA-256 des Schlüssels liegt in der Datenbank.
`/bilder-hochladen/<schlüssel>` ist eine Seite ohne Anmeldung; sie spricht
`/api/public/website-images/<schlüssel>/` (GET Angaben, POST ein Bild, je IP begrenzt). Der
Link endet nach Ablauf, voll, mit stillgelegter Einheit, abgeschaltetem Modul oder inaktivem
Konto. Jedes Bild belegt erst einen Platz und wird dann wie jeder Upload geprüft (Größe,
Format, Pixel, Metadaten entfernt); scheitert es, zählt es nicht. Angelegt werden die Bilder im
Namen der Person, die den Link erzeugt hat.

**Bild per Adresse**: `Website.image_hosts` (Webseite › Internetadresse, höchstens 10 Rechnernamen, keine
IP-Adressen). Nur `https`, genauer Rechnername, Abruf über `core.safehttp` (keine internen
Adressen, keine Weiterleitungen, höchstens 15 MB, 15 s), Inhaltstyp JPG/PNG/WebP. Die Quelle
steht danach in der Bildunterschrift.

**Beitragsentwürfe** (`SocialDraft`): Unter Webseite › Social Media mit „Text kopieren“, Bildern
zum Speichern, „Als erledigt markieren“ und „Löschen“. HUBIplan postet nichts bei Meta; die
Adressen liegen unter dem Modul „Social Media“.

Neue Tabellen mit RLS (Migration `website/0046`). Hochladelinks und Beitragsentwürfe gehen nicht
in den Datenumzug.

## Erscheinungsbild (Bereich `verein.erscheinungsbild`)

Ralf 13.11.2026: Das Erscheinungsbild der Einheit hat keinen Entwurf, Änderungen gelten sofort
(HUBIplan und Webseite) und lassen sich im Änderungsprotokoll zurücknehmen. Eigener Bereich
`verein.erscheinungsbild` (nur mit eigenem Haken beim Verbinden, keine Vorgabe; ältere
Verbindungen neu verbinden),
Recht `theme.edit`, Ansichten `ThemeView` (PATCH `theme/`) und `OrganizationLogoView`/
`OrganizationLogoDarkView` (Formular mit Datei über `ClubContext.call(..., multipart=…)`).

| Werkzeug | Bereich | Was |
|---|---|---|
| `erscheinungsbild_ansehen` | lesen | Palette (Platz 0–5), Verläufe, Farbrollen, Logo gesetzt |
| `erscheinungsbild_aendern` | erscheinungsbild | `hauptfarbe`/`zweitfarbe` {farbe, name, verwendung}, `weitere_farben` und `verlaeufe` (ersetzen), `farbrollen` (ergänzen, `null` entfernt), `farbrollen_in_hubiplan` |
| `logo_aus_bild` | erscheinungsbild | Bild der Bilderverwaltung als Logo oder Dunkel-Logo, optional Hintergrund entfernen |

Code: `mcpserver/oauth.py` (Anmeldung), `auth.py` (Schlüssel prüfen), `club.py` (Werkzeuge W1),
`club_design.py` (W2/W3), `club_theme.py` (Erscheinungsbild), `website/upload_views.py` (Hochladelink, Bild per Adresse),
`oauth_views.py`, `models.py`; Tests `backend/tests/test_mcp_verein.py`, `test_mcp_webseite_w2.py`, `test_mcp_erscheinungsbild.py`,
`frontend/src/test/McpConnect.test.tsx`.
