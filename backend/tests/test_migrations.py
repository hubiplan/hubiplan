"""Modelle und Migrationen stimmen überein."""

import io

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_keine_fehlenden_migrationen():
    out = io.StringIO()
    try:
        call_command("makemigrations", check=True, dry_run=True, stdout=out)
    except SystemExit as exc:  # makemigrations --check beendet sich mit Code 1
        pytest.fail(f"Fehlende Migrationen:\n{out.getvalue()}\n{exc}")


def test_migrationstests_sind_markiert():
    """Wer hin- und zurückmigriert, trägt @pytest.mark.migration.

    scripts/test.sh lässt diese Tests aus, wenn Migrationen und Migrationstests schon
    einmal grün waren. Fehlt die Markierung, liefe der Test zwar immer, die Ersparnis
    ginge aber verloren, und der Schlüssel für das Auslassen kennte die Datei nicht.
    """
    import ast
    from pathlib import Path

    fehlend = []
    for datei in sorted(Path(__file__).parent.glob("test_*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.FunctionDef) or not knoten.name.startswith("test"):
                continue
            nutzt = any(
                isinstance(n, ast.Name) and n.id == "MigrationExecutor" for n in ast.walk(knoten)
            )
            markiert = any("mark.migration" in ast.unparse(d) for d in knoten.decorator_list)
            if nutzt and not markiert:
                fehlend.append(f"{datei.name}::{knoten.name}")
    assert not fehlend, f"@pytest.mark.migration fehlt: {fehlend}"
