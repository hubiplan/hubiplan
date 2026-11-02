"""Migrationen hängen nur von festen Vorgängern ab.

``__latest__`` zeigt immer auf die jeweils neueste Migration einer App. Kommt dort eine neue
hinzu, hinge eine längst angewendete Migration plötzlich von ihr ab, und ``migrate`` bricht
auf jedem bestehenden Server mit InconsistentMigrationHistory ab (Rollout 02.11.). Tests mit
leerer Datenbank merken das nicht, deshalb diese Prüfung.
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def test_kein_latest_in_migrationen():
    found = [
        str(path.relative_to(BACKEND))
        for path in BACKEND.glob("*/migrations/*.py")
        if "__latest__" in path.read_text(encoding="utf-8")
    ]
    assert found == []
