#!/usr/bin/env python3
"""Rückweg-Prüfung der Migrationen (Gesamtaudit 15.11., PF-06, Fachfrage FF-40).

Regel (docs/releases.md): Migrationen bleiben eine Fassung lang abwärtsverträglich. Nach dem
Ausrollen muss die vorige Fassung auf dem neuen Schema noch laufen, denn ``deploy/zurueck.sh``
tauscht nur Code und Images, angewendete Migrationen bleiben.

Geprüft werden die Migrationen, die seit einem Vergleichsstand neu sind, gegen zwei Maßstäbe:

- ``release``: seit dem letzten Release-Tag (Rückweg fremder Betreiber von Release zu Release),
- ``main``: seit der Basis des Zweigs bzw. dem vorigen main-Stand (Rückweg auf Servern, die
  jeden main-Stand ausrollen).

Jeder Maßstab lässt sich abschalten: ``MIGRATIONSPRUEFUNG_RELEASE=0`` bzw.
``MIGRATIONSPRUEFUNG_MAIN=0``. Den Vergleichsstand für ``main`` gibt ``MIGRATIONSPRUEFUNG_BASIS``
vor (sonst: merge-base mit main, bei einem Stand auf main dessen erster Elternteil).

Gemeldet wird:

- ``AddField`` auf einer Tabelle, die es vorher schon gab, ohne ``null=True`` und ohne
  ``db_default`` im Endstand (ein Django-``default`` gilt nur im neuen Code; die alte Fassung
  lässt die Spalte beim Einfügen weg -> IntegrityError),
- ``RemoveField``, ``RenameField``, ``RenameModel``, ``DeleteModel`` auf vorher vorhandenen
  Modellen (alter Code liest/schreibt sie noch),
- ``RunSQL`` mit Zeilenschutz, Triggern oder Constraints auf vorher vorhandenen Tabellen
  (``ROW LEVEL SECURITY``, ``CREATE POLICY``, ``CREATE TRIGGER``, ``ADD CONSTRAINT``): Der
  alte Code kennt die Regel nicht.

Ausnahme mit Begründung: Kommentar ``# rueckweg-ok: <Grund>`` in der Migrationsdatei. Dann
gehört in den PR „Rückweg möglich: nein“ bzw. die Begründung, warum der alte Code
nicht betroffen ist. Bekannte ältere Fälle stehen in ``scripts/migrationen-bekannt.txt``.

Aufruf: ``scripts/pruefe-migrationen.py <Commit>`` im Repository; Rückgabewert 1 bei Funden.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Im Repository aufrufen (scripts/test.sh: aus dem Klon, das Skript aus dem geprüften Stand)
ROOT = Path(os.environ.get("MIGRATIONSPRUEFUNG_REPO") or os.getcwd())
KNOWN = "scripts/migrationen-bekannt.txt"
SQL_RULES = re.compile(
    r"ROW\s+LEVEL\s+SECURITY|CREATE\s+POLICY|CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER|ADD\s+CONSTRAINT",
    re.IGNORECASE,
)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


def git_ok(*args: str) -> bool:
    return (
        subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).returncode
        == 0
    )


@dataclass
class Finding:
    path: str
    line: int
    text: str

    def key(self) -> str:
        return f"{self.path}:{self.text}"


def _kw(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _const(node, default=None):
    return node.value if isinstance(node, ast.Constant) else default


def _field_nullable(field: ast.AST) -> tuple[bool, bool, bool]:
    """(null=True, db_default gesetzt, ManyToMany) eines Feld-Aufrufs."""
    if not isinstance(field, ast.Call):
        return True, True, False  # unbekannt: nicht melden
    name = field.func.attr if isinstance(field.func, ast.Attribute) else getattr(field.func, "id", "")
    many = "ManyToMany" in name
    null = _const(_kw(field, "null"), False) is True
    db_default = _kw(field, "db_default") is not None
    # Fremdschlüssel/OneToOne ohne null: ebenfalls NOT NULL
    return null, db_default, many


def _operations(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "operations" for t in node.targets
        ):
            if isinstance(node.value, ast.List | ast.Tuple):
                yield from node.value.elts


def _op_name(op) -> str:
    if isinstance(op, ast.Call):
        f = op.func
        return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
    return ""


def _str(op: ast.Call, name: str, pos: int | None = None) -> str:
    node = _kw(op, name)
    if node is None and pos is not None and len(op.args) > pos:
        node = op.args[pos]
    value = _const(node, "")
    return value.lower() if isinstance(value, str) else ""


def _sql_text(op: ast.Call) -> str:
    parts = []
    for node in [*op.args, *(kw.value for kw in op.keywords)]:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                parts.append(sub.value)
    return "\n".join(parts)


def new_migrations(base: str, head: str) -> list[str]:
    out = git(
        "diff", "--name-only", "--diff-filter=A", base, head, "--", "backend/*/migrations/*.py"
    )
    return sorted(p for p in out.splitlines() if not p.endswith("__init__.py"))


def check(base: str, head: str) -> list[Finding]:
    files = new_migrations(base, head)
    created: set[tuple[str, str]] = set()  # in diesen Migrationen neu angelegte Modelle
    added: dict[tuple[str, str, str], tuple[str, int, ast.AST]] = {}
    findings: list[Finding] = []
    parsed = []
    for path in files:
        source = git("show", f"{head}:{path}")
        if "rueckweg-ok:" in source:
            continue
        app = path.split("/")[1]
        tree = ast.parse(source)
        parsed.append((path, app, tree, source))
        for op in _operations(tree):
            if isinstance(op, ast.Call) and _op_name(op) == "CreateModel":
                created.add((app, _str(op, "name", 0)))
    for path, app, tree, _source in parsed:
        for op in _operations(tree):
            if not isinstance(op, ast.Call):
                continue  # z. B. *liste: nicht statisch auswertbar
            name = _op_name(op)
            line = getattr(op, "lineno", 0)
            model = _str(op, "model_name", 0)
            old = (app, model) not in created
            if name == "AddField" and old:
                field = _kw(op, "field") or (op.args[2] if len(op.args) > 2 else None)
                added[(app, model, _str(op, "name", 1))] = (path, line, field)
            elif name == "AlterField":
                # Nur für Spalten, die in diesen Migrationen neu sind: Endstand zählt. Ob ein
                # AlterField eine ältere Spalte erst NOT NULL macht, ist ohne den vorigen
                # Stand nicht sicher zu erkennen (fast immer ändert es nur den Typ).
                key = (app, model, _str(op, "name", 1))
                field = _kw(op, "field") or (op.args[2] if len(op.args) > 2 else None)
                if key in added:
                    added[key] = (added[key][0], added[key][1], field)
            elif name in ("RemoveField", "RenameField") and old:
                findings.append(Finding(path, line, f"{name} {model}: alter Code nutzt die Spalte"))
            elif name in ("RenameModel", "DeleteModel"):
                target = _str(op, "old_name", 0) if name == "RenameModel" else _str(op, "name", 0)
                if (app, target) not in created:
                    findings.append(Finding(path, line, f"{name} {target}: alter Code nutzt die Tabelle"))
            elif name == "RunSQL":
                sql = _sql_text(op)
                if SQL_RULES.search(sql):
                    tables = set(re.findall(r"\b([a-z_]+_[a-z_0-9]+)\b", sql))
                    if not any(f"{a}_{m}" in tables for a, m in created):
                        findings.append(
                            Finding(path, line, "RunSQL: Zeilenschutz/Trigger/Constraint auf bestehender Tabelle")
                        )
    for (_app, model, field_name), (path, line, field) in added.items():
        null, db_default, many = _field_nullable(field)
        if not (null or db_default or many):
            findings.append(
                Finding(path, line, f"AddField {model}.{field_name}: NOT NULL ohne db_default")
            )
    return sorted(findings, key=lambda f: (f.path, f.line))


def known(head: str) -> set[str]:
    """Bekannte ältere Fälle aus dem geprüften Stand (``Pfad:Meldung`` je Zeile)."""
    if not git_ok("cat-file", "-e", f"{head}:{KNOWN}"):
        return set()
    return {
        line.split("  #", 1)[0].strip()
        for line in git("show", f"{head}:{KNOWN}").splitlines()
        if line.strip() and not line.startswith("#")
    }


def bases(head: str) -> list[tuple[str, str]]:
    result = []
    if os.environ.get("MIGRATIONSPRUEFUNG_RELEASE", "1") != "0":
        tags = git("tag", "--merged", head, "--sort=-creatordate", "--list", "v*").split()
        if tags:
            result.append(("release", tags[0]))
    if os.environ.get("MIGRATIONSPRUEFUNG_MAIN", "1") != "0":
        base = os.environ.get("MIGRATIONSPRUEFUNG_BASIS", "")
        if not base:
            # refs/test-main/main: von scripts/test.sh --main geholt (aktueller main)
            for ref in ("refs/test-main/main", "refs/remotes/origin/main", "refs/heads/main"):
                if git_ok("rev-parse", "--verify", "--quiet", ref):
                    base = git("merge-base", head, ref).strip()
                    break
            if base and base == git("rev-parse", head).strip():
                # Stand liegt auf main: mit dem vorigen main-Stand vergleichen
                base = git("rev-parse", f"{head}^1").strip()
        if base:
            result.append(("main", base))
    return result


def main() -> int:
    if sys.argv[1:2] == ["--selbsttest"]:
        return selftest()
    head = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    ignore = known(head)
    failed = 0
    checked = []
    for label, base in bases(head):
        findings = [f for f in check(base, head) if f.key() not in ignore]
        checked.append(f"{label} {base[:12]}")
        for f in findings:
            print(f"Rückweg ({label} {base[:12]}): {f.path}:{f.line}: {f.text}")
        failed += len(findings)
    if failed:
        print(
            "Migrationen: Rückweg auf die vorige Fassung bricht (docs/releases.md, „Migrationen "
            "und Rückweg“). Spalte nullable oder mit db_default anlegen, Entfernen erst eine "
            "Fassung später; bewusste Ausnahme mit „# rueckweg-ok: <Grund>“ in der Migration."
        )
        return 1
    print("Migrationen: Rückweg ok (" + (", ".join(checked) or "kein Vergleichsstand") + ")")
    return 0


def selftest() -> int:
    """Prüfung an einem erfundenen Repository (Regressionstest, ohne Datenbank)."""
    import tempfile

    global ROOT
    files_base = {
        "backend/club/migrations/0001_initial.py": (
            "operations = [migrations.CreateModel(name='Team', fields=[])]"
        ),
    }
    files_head = {
        "backend/club/migrations/0002_pflicht.py": "operations = [migrations.AddField("
        "model_name='team', name='motto', field=models.CharField(max_length=10, default=''))]",
        "backend/club/migrations/0003_vorgabe.py": "operations = [migrations.AddField("
        "model_name='team', name='aktiv', field=models.BooleanField(default=True, "
        "db_default=True))]",
        "backend/club/migrations/0004_weg.py": "operations = [migrations.RemoveField("
        "model_name='team', name='alt')]",
        "backend/club/migrations/0005_neu.py": "operations = [migrations.CreateModel("
        "name='Liga', fields=[]), migrations.AddField(model_name='liga', name='name', "
        "field=models.CharField(max_length=10))]",
        "backend/club/migrations/0006_ausnahme.py": "# rueckweg-ok: erfundener Grund\n"
        "operations = [migrations.RemoveField(model_name='team', name='alt2')]",
        "backend/club/migrations/0007_spaeter.py": "operations = [migrations.AddField("
        "model_name='team', name='farbe', field=models.CharField(max_length=10)), "
        "migrations.AlterField(model_name='team', name='farbe', "
        "field=models.CharField(max_length=10, db_default='rot'))]",
        "backend/club/migrations/0008_rls.py": "operations = [migrations.RunSQL("
        "'ALTER TABLE club_team ENABLE ROW LEVEL SECURITY')]",
    }
    with tempfile.TemporaryDirectory(dir=os.environ.get("TESTPLATZ_TMP") or None) as tmp:
        ROOT = Path(tmp)
        env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.org",
               "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.org"}

        def commit(files, message):
            for name, text in files.items():
                path = ROOT / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            subprocess.run(["git", "-C", tmp, "add", "-A"], check=True, env=env)
            subprocess.run(
                ["git", "-C", tmp, "commit", "-qm", message], check=True, env=env
            )
            return git("rev-parse", "HEAD").strip()

        subprocess.run(["git", "init", "-q", tmp], check=True, env=env)
        base = commit(files_base, "Basis")
        head = commit(files_head, "Neu")
        found = {(Path(f.path).name, f.text.split(":")[0]) for f in check(base, head)}
    expected = {
        ("0002_pflicht.py", "AddField team.motto"),
        ("0004_weg.py", "RemoveField team"),
        ("0008_rls.py", "RunSQL"),
    }
    if found != expected:
        print(f"Selbsttest Migrationsprüfung FEHLGESCHLAGEN: {sorted(found)}")
        return 1
    print("Selbsttest Migrationsprüfung: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
