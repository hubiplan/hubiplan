# Social-Media-Beiträge auf der Webseite

Konzept: `konzepte/social-media-feed.md` im Projektordner (Stand 30.10.2026).

HUBIplan holt die **eigenen** Beiträge einer Einheit von Instagram (Profikonto) und Facebook
(Seite) serverseitig ab und speichert Text und Bilder selbst. Die Webseite zeigt sie wie jeden
anderen Inhalt von der eigenen Domain: kein Meta-Skript, kein iframe, keine Bilder von
Meta-Servern, keine Cookies.

## Eigene Meta-App je Einheit

Jede Einheit legt auf developers.facebook.com eine eigene App an und trägt App-ID und
App-Geheimnis unter **Webseite › Social Media** ein. Dadurch

- reicht Metas „Standard-Zugriff“ (keine App-Prüfung), weil die App nur eigene Konten liest,
- bleiben Geheimnis, Zugang und Beiträge in der Instanz der Einheit,
- wird niemand außer der Einheit „Developer“ im Sinne der Meta-Plattformbedingungen
  (insbesondere wird der Herausgeber von HUBIplan kein Auftragsverarbeiter).

Weiterleitungsadresse für die App: `<Basis>/api/website/social/callback/`. Die Basis ist die
Vereinsadresse der Einheit, zu der der Kanal gehört (Plattform › Adressen, bei Untereinheiten die
nächsthöhere Einheit mit eigener Adresse); ohne Vereinsadresse `SOCIAL_CALLBACK_BASE` bzw.
`FRONTEND_URL` (Issue #723). Die Anmeldung gilt je Adresse, deshalb verbindet man einen Kanal von
seiner Vereinsadresse aus; von einer anderen Adresse lehnt HUBIplan das Verbinden mit einem
Hinweis ab, und die Rückkehrseite liegt auf der Adresse, über die Meta zurückgeleitet hat.
Webseite › Social Media zeigt die genaue Weiterleitungs-URI und die App-Domain je Kanal zum
Kopieren. Kanäle, die vor der Umstellung schon verbunden waren, behalten die bisherige Adresse
(Feld `redirect_base`, von Migration `website 0056` gesetzt), bis jemand „Vereinsadresse
verwenden“ wählt. Version der Graph-Schnittstelle: `META_GRAPH_VERSION`
(Standard `v26.0`); bei Abkündigung durch Meta in der `.env` anheben.

### Anmeldewege

| Kanal | Weg | Zugang |
|---|---|---|
| Instagram (Standard) | „Unified Login“ / Facebook Login for Business mit **Konfigurations-ID** (`config_id`) | Nutzer-Zugang, Konten aus `me/assigned_instagram_accounts` bzw. den Freigaben (`debug_token` › `granular_scopes`), Beiträge über `graph.facebook.com/{ig-id}/media` |
| Instagram ohne Konfigurations-ID | Facebook-Anmeldung mit Berechtigungen | Seiten-Zugang der Facebook-Seite, an der das Profikonto hängt (`instagram_business_account`) |
| Instagram, alter Weg (Haken „Instagram-Login“) | instagram.com, nur ältere Meta-Apps | 60-Tage-Zugang über `graph.instagram.com`, wird verlängert |
| Facebook-Seite | Facebook-Anmeldung (optional mit Konfigurations-ID) | Seiten-Zugang |

Neue Meta-Apps bieten seit 2026 nur noch „Unified Login“. Konfiguration: Zugriffstoken
„Nutzerzugriffstoken“ (Ablauf „nie“, falls angeboten), Assets nur Instagram-Konten, nur die
Pflicht-Berechtigungen. Ein „Systemnutzer“-Zugang funktioniert im Entwicklungsmodus nicht:
Meta teilt das Konto im Dialog, der Zugang darf es aber nicht lesen (Hubertus, 30.10.2026).
Schlägt das Verbinden fehl, nennt die Meldung, was Meta an jeder Stelle geliefert hat. App-ID und
App-Geheimcode aus App-Einstellungen › Allgemein. Das Instagram-Konto braucht die Rolle
„Instagram-Tester“; Webhooks und App-Review sind nicht nötig (Entwicklungsmodus).

## Ablauf

| Job | Wann | Was |
|---|---|---|
| `website.tasks.sync_social_feeds` | alle 30 min | neueste N Beiträge je Kanal holen, Bilder von `*.cdninstagram.com`/`*.fbcdn.net` laden und neu schreiben (ohne EXIF), bei Meta gelöschte oder herausgerutschte Beiträge löschen |
| `website.tasks.maintain_social_feeds` | täglich | Instagram-Login-Zugang (60 Tage) alle 7 Tage verlängern, sonst Zugang mit `debug_token` prüfen; bei Ablehnung einmal Mail an die Person, die verbunden hat |

- Geheimnis und Zugänge verschlüsselt mit dem `MFA_ENCRYPTION_KEY` (wie 2FA-Geheimnisse).
- Rückleitung von Meta gilt nur für die Person, die das Verbinden gestartet hat, 15 Minuten.
- Videos: nur das Vorschaubild (Musikrechte bei Reels). Geteilte Facebook-Beiträge und Links
  Dritter werden ausgelassen.
- Trennen oder Löschen des Kanals löscht Zugang, Beiträge und Bilder.
- Modus „erst nach Freigabe“: neue Beiträge erscheinen erst nach Klick auf „Freigeben“.
- Alben: bis zu 20 Bilder je Beitrag (Instagram-Karussell, Facebook-Unteranhänge).
- Likes und Kommentarzahl (Schalter je Kanal, aus): kommen mit dem Abruf der Beiträge und
  brauchen keine weitere Berechtigung.
- Kommentartexte (je Kanal „nicht zeigen“ | „erst nach Freigabe“ | „automatisch zeigen“,
  Standard aus): je Beitrag die neuesten 20 Kommentare der obersten Ebene, ohne Antworten.
  Zusätzliche Berechtigung beim Verbinden: Instagram `instagram_manage_comments` (alter Weg
  `instagram_business_manage_comments`), Facebook `pages_read_user_content`; bei einer
  Konfiguration (`config_id`) muss sie dort eingetragen sein. Nach dem Einschalten neu
  verbinden. Namen Dritter auf Facebook nur gekürzt („Erika M.“), auf Instagram der öffentliche
  Benutzername. Ausschalten löscht alle gespeicherten Kommentare des Kanals. Fehlt die
  Berechtigung, laufen die Beiträge weiter, der Kanal zeigt einen Hinweis.

## Öffentliche Schnittstelle

- Info `…/site/v1/<key>/`: `posts` = `{instagram: bool, facebook: bool}` (gibt es sichtbare
  Beiträge), `posts_url`. Seite einer Untereinheit: ebenso `posts`.
- `…/site/v1/<key>/posts/?art=instagram|facebook&anzahl=N&einheit=<slug>`: sichtbare
  Beiträge (neueste zuerst) mit Text, Datum, Link (falls eingeschaltet) und Bildern.
  Mit „Likes und Kommentarzahl zeigen“ zusätzlich `likes` (Instagram: Likes, Facebook:
  Reaktionen; `null`, wenn ausgeblendet) und `comment_count`; mit Kommentaren `comments`
  (`author`, `text`, `published_at`, nur freigegebene).
- `…/site/v1/<key>/posts/images/<key>/[?size=small]`: Bild von dieser Instanz.
- Baustein `posts` („Aktuelles“) schaltet alles ab.

Ausgehende Verbindungen des Workers: `api.instagram.com`, `graph.instagram.com`,
`graph.facebook.com`, `*.cdninstagram.com`, `*.fbcdn.net`.
