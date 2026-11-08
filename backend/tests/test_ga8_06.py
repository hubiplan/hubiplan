"""Gesamtaudit 08.11.2026, GA8-06: Leserolle für das Backup, RLS für kontobezogene Tabellen."""

import pytest
from django.db import DatabaseError, ProgrammingError, connection, transaction

from accounts.models import StoredSignature
from core.rls import BACKUP_ROLE, backup_role_sql
from core.tenancy import rls_bypass, set_rls
from letterhead.models import LetterheadChoice

from .verbund_netz import app_role

pytestmark = pytest.mark.django_db

LINE = {"width": 600, "height": 200, "strokes": [[[10, 100], [200, 40], [400, 160], [590, 90]]]}
JSON = "application/json"


def _fails(sql: str, params=None) -> bool:
    try:
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, params)
    except DatabaseError:
        return True
    return False


def _backup_role():
    # Rollen gelten für den ganzen Datenbankserver; parallele Testläufe legen sie evtl.
    # gleichzeitig an. Ein zweiter Versuch findet sie dann vor.
    for attempt in range(2):
        try:
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(backup_role_sql("nur-ein-test", connection.connection))
            return
        except (ProgrammingError, DatabaseError):
            if attempt:
                raise


def test_backup_rolle_liest_alles_und_schreibt_nichts(orgs):
    from .factories import make_member

    make_member(orgs["a"], "Erika", "Muster")
    make_member(orgs["b"], "Max", "Muster")
    _backup_role()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolcanlogin, rolinherit "
            "FROM pg_roles WHERE rolname = %s",
            [BACKUP_ROLE],
        )
        assert cur.fetchone() == (False, True, False, False, True, False)
        cur.execute(
            "SELECT array_agg(b.rolname ORDER BY b.rolname) FROM pg_auth_members m "
            "JOIN pg_roles r ON r.oid = m.member JOIN pg_roles b ON b.oid = m.roleid "
            "WHERE r.rolname = %s",
            [BACKUP_ROLE],
        )
        assert cur.fetchone()[0] == ["pg_read_all_data"]
        cur.execute("SELECT count(*) FROM members_membership")
        total = cur.fetchone()[0]
    assert total > 0
    try:
        with connection.cursor() as cur:
            cur.execute(f"SET ROLE {BACKUP_ROLE}")
            # Ohne Organisationskontext: alle Zeilen (pg_dump braucht die RLS-Umgehung)
            cur.execute("SELECT count(*) FROM members_membership")
            assert cur.fetchone()[0] == total
        assert _fails("DELETE FROM members_membership")
        assert _fails("UPDATE organizations_organization SET name = name")
        assert _fails("CREATE TABLE ga8_06_fremd (x int)")
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")


@pytest.mark.parametrize("model", [StoredSignature, LetterheadChoice])
def test_kontobezogene_zeilen_nur_fuer_das_eigene_konto(orgs, board_a, board_b, model):
    if model is StoredSignature:
        rows = {u: dict(user=u, strokes=LINE) for u in (board_a, board_b)}
    else:
        ctx = f"org:{orgs['a'].pk}"
        rows = {u: dict(user=u, unit=orgs["a"], context=ctx) for u in (board_a, board_b)}
    with rls_bypass():
        objs = {u: model.objects.create(**data) for u, data in rows.items()}
    table = model._meta.db_table
    with app_role():
        set_rls(orgs["a"].pk, board_a.pk)
        assert list(model.objects.values_list("pk", flat=True)) == [objs[board_a].pk]
        assert (
            model.objects.filter(pk=objs[board_b].pk).update(updated_at=objs[board_b].updated_at)
            == 0
        )
        assert model.objects.filter(pk=objs[board_b].pk).delete()[0] == 0
        # Zeile für ein fremdes Konto anlegen oder umhängen: abgewiesen
        assert _fails(
            f"UPDATE {table} SET user_id = %s WHERE id = %s",  # noqa: S608 (Modelltabelle)
            [board_b.pk, objs[board_a].pk],
        )
        set_rls(None, None)
        assert model.objects.count() == 0
        set_rls(None, None, bypass=True)
        assert model.objects.count() == 2
        set_rls(None, None)


def test_unterschrift_und_briefvorlage_api_unter_rls(orgs, board_a, board_b, api):
    with app_role():
        a, b = api(board_a), api(board_b)
        assert a.put("/api/me/signature/", LINE, content_type=JSON).status_code == 200
        assert b.get("/api/me/signature/").json()["signature"] is None
        assert a.get("/api/me/signature/").json()["signature"] is not None
        assert b.delete("/api/me/signature/").status_code == 204
        assert a.get("/api/me/signature/").json()["signature"] is not None
        assert a.get("/api/me/letterheads/").status_code == 200
    with rls_bypass():
        assert StoredSignature.objects.filter(user=board_a).exists()


def test_konto_loeschen_entfernt_eigene_zeilen(orgs, board_a):
    with rls_bypass():
        StoredSignature.objects.create(user=board_a, strokes=LINE)
        LetterheadChoice.objects.create(user=board_a, unit=orgs["a"], context="org:1")
        board_a.delete()
        assert not StoredSignature.objects.exists()
        assert not LetterheadChoice.objects.exists()
