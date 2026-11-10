# Lizenzen

HUBIplan steht unter der **AGPL-3.0-or-later** ([LICENSE](../LICENSE)). Dieses Dokument
beschreibt, wie HUBIplan die Pflichten aus der eigenen Lizenz und aus den Lizenzen der
verwendeten Bibliotheken erfüllt. Es beruht auf den Lizenzaudits vom 29.10.2026, 31.10.2026 und
10.11.2026 (Berichte im Projektordner unter `audit/`) und ist keine anwaltliche Prüfung.

## Was die Nutzer sehen

Jede Seite hat in der Fußzeile den Link **„Lizenzen“** (`/lizenz`). Dort stehen:

| Datei | Inhalt | Woher |
|---|---|---|
| `/lizenzen/LICENSE.txt` | Volltext der AGPL | `LICENSE` im Repo, kopiert in `deploy/web.Dockerfile` |
| `/lizenzen/drittanbieter.txt` | Lizenztexte aller Bibliotheken im Browser-Code | beim Bauen erzeugt, `frontend/lizenzen/` |

**Quellcode für Nutzer (AGPL § 13):** Das Repository ist öffentlich auf GitHub
(`https://github.com/hubiplan/hubiplan`). Die Seite `/lizenz` verlinkt den Quellcode der
laufenden Fassung: `deploy/server-setup.sh` legt beim Ausrollen den Commit aus `.fassung`
als `/lizenzen/fassung.txt` ins Web-Image, die Seite verlinkt dann
`…/tree/<commit>`. Ohne diese Datei (Entwicklung) verlinkt sie das Repository. Wer eine
veränderte Fassung betreibt, setzt `HUBIPLAN_SOURCE_URL` in der `.env` des Servers (wird als
Build-Argument an `deploy/web.Dockerfile` gereicht) auf sein eigenes öffentliches Repository
mit genau dem laufenden Stand; ohne Angabe gilt `https://github.com/hubiplan/hubiplan`.

## Browser-Code (Frontend)

Im Browser landen Kopien der Bibliotheken. MIT, ISC und BSD verlangen, dass ihre
Lizenztexte jede Kopie begleiten. Deshalb:

- `frontend/lizenzen/plugin.ts` sammelt beim Bauen (`vite build`) alle Module, die
  tatsächlich im Bundle stecken, und schreibt die Lizenztexte der zugehörigen Pakete nach
  `lizenzen/drittanbieter.txt`. Fehlt für ein Paket der Lizenztext, bricht der Build ab.
  Verschachtelte Pakete (z. B. `markdown-it/node_modules/entities` 4.5.0 neben `entities`
  8.1.0 auf oberster Ebene) liest das Plugin aus ihrem eigenen Ordner, damit Version und
  Lizenztext zur gebündelten Kopie passen (Lizenzaudit 31.10., L07).
- `frontend/lizenzen/zusatz.txt` ergänzt Code, den Pakete selbst übernommen haben und
  dessen Lizenz nicht im Paket liegt: Nayuki-QR-Generator in qrcode.react, Modernizr in
  normalize-wheel, Oxc-/Babel-Hilfsfunktionen in react-easy-crop. Dazu die Vorlage für
  den Bildzuschnitt. Die Symbole der Oberfläche sind seit 2026-10-29 selbst gezeichnet
  (vorher Feather-ähnlich).

**Neue Frontend-Abhängigkeit:** Nach dem Bauen `dist/lizenzen/drittanbieter.txt` ansehen.
Steht im Paket ein Hinweis auf übernommenen Fremdcode (README, Quellkommentare,
„This product bundles …“), den Text in `zusatz.txt` ergänzen.

**Dateien des Servers im Browser:** Unter `/static/` liefert das Backend nur die Dateien der
Django-Verwaltung aus (`/admin`, jQuery, Select2, XRegExp mit ihren Lizenzdateien daneben).
Die HTML-Ansicht von Django REST framework (Browsable API) ist aus, die API antwortet nur mit
JSON; ihre Dateien (Bootstrap, jQuery, Font Awesome mit OFL-Schriften) sammelt
`backend/Dockerfile` mit `collectstatic --ignore rest_framework` gar nicht erst ein
(Lizenzaudit 31.10., L06). Wer die HTML-Ansicht wieder einschaltet, muss deren
Lizenzhinweise mitliefern.

Schriften: Text und Bedienung nutzen die Systemschriften. Nur der Schriftzug „HUBIplan“ im
Logo nutzt die Schrift Outfit (SIL OFL 1.1), zwei Schnitte als Dateien in
`frontend/src/assets/fonts/`; der Lizenztext steht in `frontend/lizenzen/zusatz.txt`.

## Server (Backend und Dienste)

Die Server-Images werden nur selbst betrieben (Test- und Produktionsserver) und **nicht an andere
weitergegeben**. Ohne Weitergabe verlangen die Lizenzen der Server-Bibliotheken keine
Lizenztexte oder Quellcode-Angebote an die Nutzer. Das ändert sich, wenn Images oder
Installationspakete an Dritte gehen (siehe unten).

| Komponente | Lizenz | Hinweis |
|---|---|---|
| Django, Django REST framework, drf-spectacular, dj-database-url, Celery | BSD-3-Clause | |
| django-allauth, redis (Python-Client), gunicorn, whitenoise, openpyxl | MIT | |
| python-dateutil | Apache-2.0 oder BSD-3-Clause | |
| reportlab | BSD | Bringt Schriftdateien mit eigenen Lizenzen mit (Adobe-/Monotype-Typ-1, Vera, DarkGarden); die PDFs von HUBIplan verwenden nur die PDF-Standardschriften (Helvetica, Times) und betten keine Schriftdatei ein |
| Pillow | MIT-CMU | Enthält native Bibliotheken (FreeType, libjpeg, libtiff u. a.) mit eigenen Lizenzen |
| verovio | LGPL-3.0-only | Notensatz für MusicXML/MEI/ABC (PDF, MIDI); dynamisch geladene native Bibliothek, austauschbar per `pip`; bringt Notenschriften (Leipzig, Bravura u. a.) unter der SIL Open Font License mit, die nur als Pfade in SVG/PDF landen |
| svglib | LGPL-3.0-or-later | wandelt das SVG von Verovio in reportlab-Zeichnungen; nutzt lxml (BSD-3-Clause), cssselect2 und tinycss2 (BSD-3-Clause) |
| pypdfium2 | Apache-2.0 oder BSD-3-Clause | Bringt PDFium (BSD-3-Clause, Teile Apache-2.0) als native Bibliothek mit; dient nur dem Vorschaubild der Satzung auf der Webseite |
| psycopg, psycopg-binary | LGPL-3.0 | Enthält libpq (PostgreSQL-Lizenz) und OpenSSL (Apache-2.0) |
| PostgreSQL 18 | PostgreSQL License | |
| Redis 8 (Server) | RSALv2 oder SSPLv1 oder AGPLv3, nach Wahl | HUBIplan nutzt Redis unverändert und nur intern als Warteschlange und Zwischenspeicher, unter der **AGPLv3**. Redis wird nicht als eigener Dienst angeboten. |
| Caddy | Apache-2.0 | |
| KoSIT Validator 1.6.3 und Prüfkonfiguration XRechnung 3.0.2 (2026-08-31) | Apache-2.0 für die KoSIT-Projekte | Unveränderte offizielle Veröffentlichungen, beim Image-Bau mit festen SHA-256-Prüfsummen installiert. [Validator-Lizenz](https://github.com/itplr-kosit/validator/blob/v1.6.3/LICENSE), [Konfigurationslizenz](https://github.com/itplr-kosit/validator-configuration-xrechnung/blob/v2026-08-31/LICENSE). Das Regelpaket und das Standalone-JAR enthalten zusätzlich fremde Schemas, Regelwerke und Java-Bibliotheken; bei Weitergabe deren jeweilige Hinweise mitliefern. |
| OpenJDK (Debian `default-jre-headless`) | GPL-2.0 mit Classpath Exception | Separater Java-Prozess für die XML-Prüfung; Debian-Copyright-Dateien bleiben im Image. Bei Image-Weitergabe auch die Pflichten für die enthaltene Laufzeit beachten. |
| factur-x 7.9, pypdf, iso4217 | BSD | Konvertierung und Einbettung des CII-XML; Lizenztexte verbleiben in den installierten Python-Paketen. |
| lxml | BSD mit Hinweisen für libxml2/libxslt | XML-Schema-Prüfung und Serialisierung; native Komponenten mit eigenen Copyright-Hinweisen. |
| python-stdnum | LGPL-2.1-or-later | Validierung von Kennungen als Abhängigkeit von factur-x. |
| Ghostscript (Debian) | AGPL-3.0 | Unveränderter separater Prozess für PDF/A-3. Enthaltene Schrift- und ICC-Profildateien behalten ihre jeweiligen Hinweise. Bei Weitergabe des Images vollständige Lizenz-/Quellcodepflichten beachten. |
| veraPDF 1.30.3 | MPL-2.0 oder GPL-3.0-or-later | Unveränderter offizieller CLI-Validator, Installer mit SHA-256 geprüft; Lizenztexte bleiben in der Installation. Enthaltene Java-Abhängigkeiten haben eigene Hinweise. |
| Hestia-Vorlagen `deploy/hestia/app-8110.*` | GPL-3.0 | Aufgebaut nach den Standardvorlagen von HestiaCP 1.9.4 (Commit `aae8b2b`), als solche gekennzeichnet mit Änderungsvermerk und Datum der letzten Änderung (GPL § 5a, bei jeder Änderung anpassen); GPL-Volltext in `deploy/hestia/LICENSE-GPL-3.0.txt`. Die Vorlagen bleiben GPL-3.0; GPL-3.0 und AGPL-3.0 dürfen kombiniert werden (jeweils § 13) |
| Häufige Passwörter | BSD-3-Clause (Django) | Djangos `CommonPasswordValidator` mit der Liste aus Django. Die frühere NCSC-Liste (über SecLists) ist seit 10.11.2026 entfernt, weil die Rechte an der ursprünglichen Sammlung nicht belegt waren (Audit 10.11., L05) |
| SEPA-Schema `backend/music/schemas/pain.001.001.09.xsd` | ISO 20022 Nutzungsbedingungen | Unverändertes ISO-20022-Originalschema zur Prüfung der Auszahlungsdatei. Die strengeren Regeln der Deutschen Kreditwirtschaft (GBIC 5) prüft `music.payouts.dk_rules` im eigenen Code; die DK-Schemadatei ist seit 10.11.2026 entfernt, weil eine Erlaubnis zur Weitergabe fehlte (Audit 10.11., L04) |

Das Server-Image enthält nur die Laufzeit-Abhängigkeiten (`requirements.txt`). Test-Werkzeuge
(`requirements-dev.txt`: pytest, ruff) baut nur `scripts/test.sh` mit
`--build-arg REQUIREMENTS=requirements-dev.txt` dazu.

**API-Dokumentation:** Die Swagger-Oberfläche unter `/api/docs/` lädt Code von einem CDN
(swagger-ui-dist 5.29.5, Apache-2.0, feste Version). Im Server-Betrieb ist sie aus
(`DJANGO_API_DOCS_ENABLED=false` in `docker-compose.server.yml`); das Schema unter
`/api/schema/` bleibt für Angemeldete.

## Falls Images oder Pakete weitergegeben werden

Wer HUBIplan als fertiges Image oder Installationspaket an andere gibt (z. B. einen anderen
Verein, der selbst betreibt), muss vorher am konkreten Image prüfen:

1. Stückliste (SBOM) aller Python-, nativen und Betriebssystem-Pakete mit Versionen.
2. Lizenztexte und NOTICE-Dateien aller enthaltenen Pakete beilegen.
3. psycopg, verovio und svglib (LGPL-3.0): Lizenztexte GPL und LGPL beilegen, Quellcode der Bibliothek
   anbieten, Austausch der Bibliothek ermöglichen.
4. Pillow: Hinweise der nativen Bibliotheken (FreeType, IJG, libtiff) beilegen.
5. Nicht benutzte Schriftdateien von reportlab entfernen oder ihre Lizenz belegen.
6. Den Quellcode von HUBIplan zum Image mitgeben (AGPL §§ 4–6).
7. `.dockerignore` hält `.env`, Schlüssel und Laufzeitdaten aus den Images heraus.

## Offene Punkte außerhalb des Codes

Diese Fragen aus dem Lizenzaudit lassen sich nicht im Code lösen:

- **Rechtekette:** Ralf Philipsen ist der einzige menschliche Mitwirkende, ohne Mitarbeitende
  oder Auftragnehmer; der Code entsteht zu großen Teilen mit Claude. Offen ist nur, welches
  Claude-Produkt mit welcher Vertragsfassung im Entwicklungszeitraum galt (Audit 31.10., L13).
- **Quellcode-Angebot (AGPL §§ 4–6, 13):** für Online-Nutzer erledigt (Link auf `/lizenz`,
  siehe oben). Zusätzlich nötig, sobald
  ein anderer als der Rechteinhaber eine Instanz betreibt (z. B. ein Verein selbst), Images
  weitergegeben werden oder die App verteilt wird. Dann je ausgelieferter Fassung die passende
  Quelle mit Bauskripten, ohne Geheimnisse und Vereinsdaten (Audit 31.10., L03).
- **Passwortliste und SEPA-Schema:** Seit 10.11.2026 ersetzt (siehe Tabelle). Ältere
  Fassungen in der Git-Geschichte enthalten die NCSC-Liste und die DK-Schemadatei noch.
- **Beiträge aus Instagram/Facebook:** HUBIplan kopiert Texte und Bilder auf die Webseite
  (Bilder neu gespeichert, ohne eingebettete Angaben). Die Verbindung gibt keine Rechte an
  fremden Bildern oder Musik; der Hinweis steht in der Einrichtung (Audit 31.10., L10).
- **Inhalte der Vereine:** Fotos, Logos, Wappen und Texte laden die Vereine selbst hoch.
  Die Upload-Felder weisen darauf hin, dass die Erlaubnis der Urheber nötig ist.
- **Marken:** Keine Recherche zu „HUBIplan“ oder dem H-Logo (Audit 10.11., L14). Vor
  weiterer Werbung recherchiert der Herausgeber bei DPMA und EUIPO (Entscheidung 10.11.2026).
- **Android-App:** eigenes Repository `hubiplan-android` mit eigener Lizenzseite in der App
  und Beschreibung in dessen `docs/lizenzen.md`. Die Variante `play` enthält Google-Bausteine
  unter proprietären SDK-Bedingungen und bleibt unveröffentlicht (Audit 31.10., L02).
