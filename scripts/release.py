#!/usr/bin/env python3
"""Releases von HUBIplan und der Webseite (docs/releases.md). Aufruf über scripts/release.sh.

    release.sh entwurf [Ref]   Änderungshinweise seit dem letzten Release in CHANGELOG.md und
                               CHANGELOG.en.md eintragen (Entwurf zum Lesen und Glätten)
    release.sh taggen  [Ref]   Prüfen und das Release anlegen: Tag v<Version> und GitHub-Release

Läuft im Klon des jeweiligen Repos (hubiplan oder hubiplan-website). Ref ist ohne Angabe
origin/main. Ralf entscheidet, wann ein Release kommt: „taggen“ nur auf sein Wort.
"""

# ruff: noqa: S603, S607  (git, gh und ssh mit festen Argumenten)

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MARKE = "<!-- Neue Versionen hier einfügen (scripts/release.sh) -->"
DATEIEN = {"de": "CHANGELOG.md", "en": "CHANGELOG.en.md"}
ARTEN = {
    # Art aus dem PR: (Überschrift de, Überschrift en)
    "sicherheit": ("Sicherheit", "Security"),
    "neu": ("Neu", "New"),
    "verbessert": ("Verbessert", "Improved"),
    "behoben": ("Behoben", "Fixed"),
    "betrieb": ("Für Betreiber", "For operators"),
}
PRODUKT = {"hubiplan": "HUBIplan", "hubiplan-website": "HUBIplan-Webseite"}
SERVER_DIR = {"hubiplan": "/opt/hubiplan", "hubiplan-website": "/opt/hubiplan-website"}
VERSION_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d+$")


def fehler(text: str) -> None:
    print(f"Abbruch: {text}", file=sys.stderr)
    sys.exit(1)


def git(*args: str, check: bool = True) -> str:
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        fehler(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout.strip() if res.returncode == 0 else ""


def ist_vorfahr(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b]).returncode == 0


def repo_name() -> str:
    name = Path(git("rev-parse", "--show-toplevel")).name
    if name not in PRODUKT:
        fehler(f"unbekanntes Repository „{name}“ (erwartet: {', '.join(PRODUKT)}).")
    return name


def letzter_tag(ref: str) -> str:
    return git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", ref, check=False)


def naechste_version(heute: datetime.date) -> str:
    monat = f"{heute.year}.{heute.month}"
    nummern = [
        int(t.rsplit(".", 1)[1])
        for t in git("tag", "--list", f"v{monat}.*").split()
        if VERSION_RE.match(t[1:])
    ]
    return f"{monat}.{max(nummern) + 1 if nummern else 0}"


def pr_nummern(von: str, bis: str) -> list[int]:
    bereich = f"{von}..{bis}" if von else bis
    nummern = []
    for zeile in git("log", "--first-parent", "--reverse", "--format=%s", bereich).splitlines():
        # Squash: „Titel (#12)“; Merge-Commit: „Merge pull request #12 from …“
        m = re.search(r"\(#(\d+)\)\s*$", zeile) or re.match(r"Merge pull request #(\d+)\b", zeile)
        if m and int(m.group(1)) not in nummern:
            nummern.append(int(m.group(1)))
    return nummern


def gh(*args: str) -> str:
    befehl = os.environ.get("GH", "gh")
    res = subprocess.run([befehl, *args], capture_output=True, text=True)
    if res.returncode != 0:
        fehler(f"{befehl} {' '.join(args[:3])} …: {res.stderr.strip()}")
    return res.stdout


def hinweise_aus_pr(body: str) -> dict[str, str]:
    """Abschnitt „Für die Änderungshinweise“ der PR-Vorlage lesen."""
    m = re.search(r"^##\s*Für die Änderungshinweise\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    if not m:
        return {}
    teil = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)
    werte: dict[str, str] = {}
    for zeile in teil.splitlines():
        z = re.match(r"^\s*-\s*(de|en|Art|Migration)\s*:\s*(.*)$", zeile, re.I)
        if z:
            werte[z.group(1).lower()] = z.group(2).strip()
    return werte


def leer(text: str) -> bool:
    return text.strip() in {"", "–", "-", "—"}


def entwurf(args: argparse.Namespace) -> None:
    repo = repo_name()
    ref = git("rev-parse", "--verify", f"{args.ref}^{{commit}}")
    vorher = letzter_tag(ref)
    version = args.version or naechste_version(datetime.date.today())
    if not VERSION_RE.match(version):
        fehler(f"Version „{version}“ hat nicht die Form JJJJ.MM.N.")
    if git("tag", "--list", f"v{version}"):
        fehler(f"Tag v{version} gibt es schon.")

    gruppen: dict[str, dict[str, list[str]]] = {"de": {}, "en": {}}
    ohne_hinweis, kein_rueckweg = [], []
    for nr in pr_nummern(vorher, ref):
        daten = json.loads(
            gh("pr", "view", str(nr), "--repo", f"hubiplan/{repo}", "--json", "title,body")
        )
        h = hinweise_aus_pr(daten.get("body") or "")
        if not h:
            ohne_hinweis.append(nr)
            h = {"de": daten["title"], "en": f"(Englisch fehlt) {daten['title']}"}
        if leer(h.get("de", "")) and leer(h.get("en", "")):
            continue
        art = (h.get("art") or "verbessert").split()[0].lower()
        art = art if art in ARTEN else "verbessert"
        for sprache in ("de", "en"):
            text = h.get(sprache) or f"(fehlt) {h.get('de', '')}"
            gruppen[sprache].setdefault(art, []).append(f"- {text} (#{nr})")
        if re.search(r"rückweg möglich\s*:\s*nein", h.get("migration", ""), re.I):
            kein_rueckweg.append(nr)

    # Neue Migrationen seit dem letzten Release (ohne Release: seit dem leeren Stand)
    basis = vorher or git("hash-object", "-t", "tree", "/dev/null")
    neu = git("diff", "--name-only", "--diff-filter=A", basis, ref).splitlines()
    migrationen = [d for d in neu if re.search(r"/migrations/\d{4}_.*\.py$", d)]

    heute = datetime.date.today().isoformat()
    for sprache, datei in DATEIEN.items():
        zeilen = [f"## {version} ({heute})", ""]
        if kein_rueckweg:
            zeilen += [
                "> **Kein Rückweg über deploy/zurueck.sh – vorher eine Sicherung anlegen.**"
                if sprache == "de"
                else "> **No way back via deploy/zurueck.sh – make a backup first.**",
                "",
            ]
        for art, (titel_de, titel_en) in ARTEN.items():
            punkte = gruppen[sprache].get(art)
            if punkte:
                zeilen += [f"### {titel_de if sprache == 'de' else titel_en}", "", *punkte, ""]
        if migrationen:
            zeilen += [
                f"{'Datenbank-Migrationen' if sprache == 'de' else 'Database migrations'}: "
                f"{len(migrationen)}",
                "",
            ]
        pfad = Path(datei)
        alt = pfad.read_text(encoding="utf-8") if pfad.exists() else ""
        if MARKE not in alt:
            fehler(f"{datei}: Marke „{MARKE}“ fehlt.")
        pfad.write_text(
            alt.replace(MARKE, MARKE + "\n\n" + "\n".join(zeilen).rstrip() + "\n", 1),
            encoding="utf-8",
        )

    print(f"Entwurf für {PRODUKT[repo]} {version} (seit {vorher or 'Anfang'}) eingetragen.")
    if ohne_hinweis:
        print(
            "Ohne Abschnitt „Für die Änderungshinweise“ (Titel übernommen, bitte glätten): "
            + ", ".join(f"#{n}" for n in ohne_hinweis)
        )
    if kein_rueckweg:
        print("Kein Rückweg laut PR: " + ", ".join(f"#{n}" for n in kein_rueckweg))
    print(f"Weiter: CHANGELOG.md und CHANGELOG.en.md lesen, als PR „Release {version}“ mergen,")
    print("scripts/test.sh auf dem Merge-Commit (geht ohne neuen Lauf), dann release.sh taggen.")


def abschnitt(text: str, version: str) -> str:
    m = re.search(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def oberste_version(text: str) -> str:
    m = re.search(r"^## (\d{4}\.\d{1,2}\.\d+)\b", text, re.M)
    return m.group(1) if m else ""


def testserver_fassung(repo: str) -> str:
    datei = Path(
        os.environ.get("HUBIPLAN_TESTSERVER_FILE", Path.home() / ".config/hubiplan/testserver")
    )
    try:
        host = datei.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        fehler(f"kein Testserver in {datei} (oder --ohne-testserver).")
    ssh = [os.environ.get("SSH", "ssh"), "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if os.environ.get("DEPLOY_KEY"):
        ssh += ["-i", os.path.expanduser(os.environ["DEPLOY_KEY"]), "-o", "IdentitiesOnly=yes"]
    res = subprocess.run(
        [*ssh, host, f"cat {SERVER_DIR[repo]}/.fassung"], capture_output=True, text=True, timeout=60
    )
    if res.returncode != 0:
        fehler(f"Testserver nicht lesbar: {res.stderr.strip()} (DEPLOY_KEY gesetzt?)")
    return res.stdout.strip()


def nur_aenderungshinweise(a: str, b: str) -> bool:
    dateien = set(git("diff", "--name-only", a, b).splitlines())
    return dateien <= set(DATEIEN.values())


def taggen(args: argparse.Namespace) -> None:
    repo = repo_name()
    ref = git("rev-parse", "--verify", f"{args.ref}^{{commit}}")
    kurz = ref[:7]
    de = git("show", f"{ref}:CHANGELOG.md", check=False)
    en = git("show", f"{ref}:CHANGELOG.en.md", check=False)
    version = oberste_version(de)
    if not version:
        fehler(f"CHANGELOG.md in {kurz} nennt keine Version. Erst release.sh entwurf.")
    tag = f"v{version}"
    if git("tag", "--list", tag):
        fehler(f"{tag} gibt es schon. Neue Änderungen brauchen einen neuen Entwurf.")
    text_de, text_en = abschnitt(de, version), abschnitt(en, version)
    if (
        not text_de
        or not text_en
        or "(fehlt)" in text_de + text_en
        or "(Englisch fehlt)" in text_en
    ):
        fehler(f"Änderungshinweise für {version} fehlen oder sind unvollständig (de und en).")

    # 1. Lokal getestet (gleicher Tree wie in scripts/test.sh vermerkt)
    umgebung = "HUBIPLAN_TESTED_FILE" if repo == "hubiplan" else "HUBIPLAN_WEBSITE_TESTED_FILE"
    state = Path(os.environ.get(umgebung, Path.home() / f".local/state/{repo}/tested-trees"))
    tree = git("rev-parse", f"{ref}^{{tree}}")
    try:
        getestet = any(z.startswith(tree + " ") for z in state.read_text().splitlines())
    except OSError:
        getestet = False
    if not getestet:
        fehler(f"{kurz} ist nicht lokal getestet. Erst scripts/test.sh {kurz}.")

    # 2. Kein Rückschritt gegenüber dem neuesten Release
    alle = git("tag", "--list", "v[0-9]*", "--sort=-v:refname").split()
    vorher = alle[0] if alle else ""
    if vorher and not ist_vorfahr(vorher, ref):
        fehler(f"{kurz} enthält das neueste Release {vorher} nicht (wäre ein Rückschritt).")

    # 3. Auf dem Testserver gelaufen (dieser Stand, ein Nachfolger oder derselbe Code)
    if args.ohne_testserver:
        print("Warnung: Testserver nicht geprüft (--ohne-testserver).")
    else:
        test_sha = testserver_fassung(repo)
        if not re.fullmatch(r"[0-9a-f]{40}", test_sha):
            fehler(f"Testserver meldet keine Fassung ({test_sha!r}).")
        bekannt = bool(
            git("rev-parse", "--verify", "--quiet", f"{test_sha}^{{commit}}", check=False)
        )
        if not bekannt:
            fehler(f"Testserver-Fassung {test_sha[:7]} fehlt im Klon (git fetch).")
        if not (ist_vorfahr(ref, test_sha) or nur_aenderungshinweise(test_sha, ref)):
            fehler(
                f"Testserver läuft {test_sha[:7]}, nicht {kurz} oder ein Nachfolger. "
                "Erst auf den Testserver ausrollen."
            )
        print(f"Testserver: {test_sha[:7]} ok")

    notizen = f"{text_de}\n\n---\n\n**English**\n\n{text_en}\n"
    print(f"\n{PRODUKT[repo]} {version} auf {kurz} (vorher: {vorher or 'kein Release'})\n")
    print(notizen)
    if not args.ja:
        antwort = input(f"Release {tag} jetzt bei GitHub anlegen? [j/N] ").strip().lower()
        if antwort not in {"j", "ja"}:
            print("Nichts angelegt.")
            return
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(notizen)
    try:
        url = gh(
            "release",
            "create",
            tag,
            "--repo",
            f"hubiplan/{repo}",
            "--target",
            ref,
            "--title",
            f"{PRODUKT[repo]} {version}",
            "--notes-file",
            f.name,
        )
    finally:
        os.unlink(f.name)
    print(url.strip())
    print(f"Fertig. Tag holen: git fetch origin --tags. Ausrollen: deploy/deploy.sh {tag}")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="release.sh", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="befehl", required=True)
    e = sub.add_parser("entwurf", help="Änderungshinweise eintragen")
    e.add_argument("ref", nargs="?", default="origin/main")
    e.add_argument("--version", help="statt der nächsten Nummer im laufenden Monat")
    t = sub.add_parser("taggen", help="Release anlegen (Tag und GitHub-Release)")
    t.add_argument("ref", nargs="?", default="origin/main")
    t.add_argument("--ohne-testserver", action="store_true")
    t.add_argument("--ja", action="store_true", help="ohne Rückfrage")
    args = p.parse_args()
    entwurf(args) if args.befehl == "entwurf" else taggen(args)


if __name__ == "__main__":
    main()
