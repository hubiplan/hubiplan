# Releases

HUBIplan wird laufend aus `main` weiterentwickelt. Ein **Release** ist ein geprüfter,
benannter Stand von `main` mit Versionsnummer, Git-Tag und Änderungshinweisen auf Deutsch
und Englisch. Für die Webseite (`hubiplan-website`) gilt dasselbe mit eigener Zählung.

## Versionsnummern

`JJJJ.MM.N`: Jahr, Monat, laufende Nummer im Monat ab 0, z. B. `2026.11.0`, `2026.11.1`,
`2026.12.0`. Die Nummer sagt, wie alt eine Fassung ist. Schnittstellen haben eigene
Versionen (`api_version` für die App, `/api/public/site/v1/` für die Webseite); innerhalb
einer Schnittstellenversion kommt nur Neues hinzu.

Die laufende Fassung zeigt ihre Version auf `/lizenz` und in `GET /api/app/v1/instance/`
(`version`). `deploy/deploy.sh` bildet sie aus den Git-Tags:

| Ausgerollt | Version |
| --- | --- |
| Release-Tag `v2026.11.0` | `2026.11.0` |
| drei Commits nach `v2026.11.0` | `2026.11.0+3.0a5d21e` |
| noch kein Release | nur der Commit, z. B. `0a5d21e` |

Auch Stände zwischen zwei Releases dürfen ausgerollt werden, wenn sie lokal getestet sind.

## Änderungshinweise

Jeder Pull Request füllt in der Vorlage den Abschnitt **„Für die Änderungshinweise“** aus:
ein bis drei Sätze für Vereinsvorstände auf Deutsch und Englisch, die Art (`neu`,
`verbessert`, `behoben`, `sicherheit`, `betrieb`) und ob Migrationen dabei sind und der
Rückweg möglich bleibt. Nicht sichtbare Änderungen bekommen „–“.

Aus diesen Abschnitten entstehen [CHANGELOG.md](../CHANGELOG.md) und
[CHANGELOG.en.md](../CHANGELOG.en.md), das neueste Release oben.

In HUBIplan stehen beide Dateien unter **Hilfe › Neuigkeiten** (`/hilfe/neuigkeiten`) in der
Sprache der Oberfläche; `deploy/web.Dockerfile` legt sie dafür unter `/lizenzen/` ab. Läuft ein
Release (Version ohne `+…`), sehen alle mit Rechten in einer Einheit einmal je Browser den Hinweis
„HUBIplan wurde auf Version … aktualisiert · Das ist neu“. Zwischenstände lösen ihn nicht aus.

## Ein Release anlegen

Wann ein Release kommt, entscheidet der Betreuer. Ablauf im Klon (in WSL):

1. `git fetch origin --tags` (in WSL vorher im Windows-Checkout ebenfalls).
2. `scripts/release.sh entwurf` trägt die Hinweise aller PRs seit dem letzten Release in
   beide Changelogs ein und schlägt die nächste Nummer vor (`--version` für eine andere).
   PRs findet es über „(#12)“ im Squash-Commit oder „Merge pull request #12“. PRs ohne
   Abschnitt übernimmt es mit ihrem Titel und meldet sie.
3. Entwurf lesen und glätten, als PR „Release 2026.11.0“ mergen, und zwar per **Squash**
   (ein einzelner Commit, sonst erkennt Schritt 4 ihn nicht als reinen Changelog-Commit).
4. `scripts/test.sh <Merge-Commit>`: Ändert der Commit gegenüber dem getesteten Vorgänger
   nur die beiden Changelogs, gilt er sofort als getestet (kein neuer Testlauf).
5. Auf den Testserver ausrollen wie immer.
6. `scripts/release.sh taggen` prüft:
   - der Stand ist lokal getestet,
   - er enthält das vorige Release (kein Rückschritt),
   - der Testserver läuft diesen Stand, einen Nachfolger oder denselben Code
     (liest `/opt/hubiplan/.fassung` per SSH, `DEPLOY_KEY` wie bei `deploy.sh`;
     `--ohne-testserver` überspringt das),
   - beide Changelogs haben einen vollständigen Abschnitt für die Version.

   Danach zeigt es die Release-Notizen und legt nach Rückfrage mit `gh release create`
   den Tag `v2026.11.0` und das GitHub-Release an (`GH=` für einen anderen Pfad zu `gh`).
7. `git fetch origin --tags`, dann `deploy/deploy.sh v2026.11.0` auf den Echtserver.

Für die Webseite dieselben Schritte im Klon von `hubiplan-website` mit
`~/hubiplan/scripts/release.sh`.

## Migrationen und Rückweg

`deploy/zurueck.sh` tauscht Code und Images, angewendete Migrationen bleiben. Damit das
sicher ist, bleiben Migrationen **eine Fassung lang abwärtsverträglich**: Neue Spalten sind
nullable oder haben einen Standardwert; Spalten und Tabellen werden erst im nächsten Release
entfernt oder umbenannt. Geht das nicht, steht im PR „Rückweg möglich: nein“, und das Release
bekommt oben den Hinweis, vorher eine Sicherung anzulegen.

## Rollout-Protokoll

`deploy/deploy.sh` schreibt je Lauf eine Zeile nach `/opt/hubiplan.protokoll` (neben dem
Programmordner): Zeit (UTC), Commit, Version und Ergebnis (`ausgerollt`,
`fehlgeschlagen (…)`); `deploy/zurueck.sh` vermerkt `zurueck`.

```bash
tail /opt/hubiplan.protokoll
```
