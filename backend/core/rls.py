"""SQL-Bausteine für Row-Level Security, genutzt von den Migrationen."""

import re

APP_ROLE = "hubiplan_app"
# Nur für pg_dump im Backup-Dienst: liest alles, schreibt nichts (Gesamtaudit 08.11., GA8-06)
BACKUP_ROLE = "hubiplan_backup"

ORG = "NULLIF(current_setting('app.org_id', true), '')::bigint"
USER = "NULLIF(current_setting('app.user_id', true), '')::bigint"
BYPASS = "current_setting('app.bypass_rls', true) = 'on'"
SCOPE = "NULLIF(current_setting('app.scope_id', true), '')::bigint"


def create_app_role_sql() -> str:
    """Eingeschränkte Rolle ohne Superuser- und BYPASSRLS-Recht anlegen."""
    return f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
        END IF;
    END $$;
    GRANT {APP_ROLE} TO CURRENT_USER;
    GRANT USAGE ON SCHEMA public TO {APP_ROLE};
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE};
    """


def app_login_sql(password: str, connection) -> str:
    """Rolle hubiplan_app mit Passwort anmeldefähig machen (ohne Superuser-Rechte).

    Im Echtbetrieb meldet sich die Anwendung direkt als hubiplan_app an. So kann
    auch Schadcode in der Anwendung die Rolle nicht per ``RESET ROLE`` verlassen.
    """
    from psycopg import sql

    return (
        sql.SQL(
            "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}"
        )
        .format(sql.Identifier(APP_ROLE), sql.Literal(password))
        .as_string(connection)
    )


def backup_role_sql(password: str, connection) -> str:
    """Rolle hubiplan_backup: Anmeldung mit Passwort, nur Lesen, RLS-Umgehung für pg_dump.

    pg_dump bricht bei Tabellen mit RLS ab, wenn die Rolle sie nicht umgehen darf. Die Rolle
    bekommt deshalb BYPASSRLS, aber über ``pg_read_all_data`` nur Leserechte, keine
    Superuser-Rechte und kein Recht, Rollen oder Datenbanken anzulegen.
    """
    from psycopg import sql

    role = sql.Identifier(BACKUP_ROLE)
    return (
        sql.SQL(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {name}) THEN
                    CREATE ROLE {role} NOLOGIN;
                END IF;
            END $$;
            ALTER ROLE {role} WITH LOGIN NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE
                NOREPLICATION NOINHERIT PASSWORD {password};
            ALTER ROLE {role} SET default_transaction_read_only = on;
            GRANT pg_read_all_data TO {role} WITH INHERIT TRUE;
            """
        )
        .format(name=sql.Literal(BACKUP_ROLE), role=role, password=sql.Literal(password))
        .as_string(connection)
    )


def enable_rls_sql(table: str, extra_using: str = "") -> str:
    """RLS für eine mandantenbezogene Tabelle (Spalte organization_id)."""
    using = f"organization_id = {ORG} OR {BYPASS}"
    if extra_using:
        using = f"{using} OR {extra_using}"
    return f"""
    ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation ON {table};
    CREATE POLICY tenant_isolation ON {table}
        USING ({using})
        WITH CHECK (organization_id = {ORG} OR {BYPASS});
    """


def disable_rls_sql(table: str) -> str:
    return f"""
    DROP POLICY IF EXISTS tenant_isolation ON {table};
    ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
    """


def enable_policy_sql(table: str, using: str, check: str | None = None) -> str:
    """RLS mit frei formulierter Regel (z. B. Verbandsbereich statt Organisation)."""
    return f"""
    ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS tenant_isolation ON {table};
    CREATE POLICY tenant_isolation ON {table}
        USING (({using}) OR {BYPASS})
        WITH CHECK (({check or using}) OR {BYPASS});
    """


# Heutiges Datum für Zeilenschutzregeln, in der Zeitzone der Anwendung (settings.TIME_ZONE).
# ``CURRENT_DATE`` richtet sich nach der Zeitzone der DB-Sitzung, und die ist bei Django mit
# USE_TZ immer UTC. Zwischen Mitternacht und 1 Uhr (Sommerzeit 2 Uhr) lag die Datenbank damit
# einen Tag hinter ``timezone.localdate()``. Regeln vergleichen Zeiträume deshalb mit HEUTE.
HEUTE = "public.hubiplan_heute()"
_CURRENT_DATE = re.compile(r"\bcurrent_date\b", re.IGNORECASE)
_HEUTE = re.compile(r"(?:public\.)?hubiplan_heute\(\)")


def heute_funktionen_sql(zeitzone: str) -> str:
    """``hubiplan_datum(zeitpunkt)`` und ``hubiplan_heute()`` anlegen."""
    if not re.fullmatch(r"[A-Za-z0-9_+\-/]+", zeitzone):
        raise ValueError(f"Ungültige Zeitzone: {zeitzone!r}")
    return f"""
    CREATE OR REPLACE FUNCTION public.hubiplan_datum(zeitpunkt timestamptz) RETURNS date
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
        SELECT (zeitpunkt AT TIME ZONE '{zeitzone}')::date
    $$;
    CREATE OR REPLACE FUNCTION public.hubiplan_heute() RETURNS date
    LANGUAGE sql STABLE PARALLEL SAFE AS $$
        SELECT public.hubiplan_datum(now())
    $$;
    """


def heute_umstellen(schema_editor, tabellen: str, funktionen: tuple[str, ...], vor: bool):
    """``CURRENT_DATE`` in bestehenden Regeln und Funktionen durch HEUTE ersetzen (oder zurück).

    ``tabellen`` ist ein LIKE-Muster (z. B. ``todos\\_%``), ``funktionen`` sind Namen in public.

    Die Regeln werden aus ``pg_policies`` gelesen und mit ``ALTER POLICY`` geändert, die
    Funktionen über ``pg_get_functiondef`` neu angelegt. Rechte und Eigentümer bleiben dabei
    erhalten; sonst ändert sich nichts.
    """

    def tauschen(text: str) -> str:
        return _CURRENT_DATE.sub(HEUTE, text) if vor else _HEUTE.sub("CURRENT_DATE", text)

    with schema_editor.connection.cursor() as cur:
        cur.execute(
            "SELECT tablename, policyname, qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename LIKE %s",
            [tabellen],
        )
        regeln = cur.fetchall()
        cur.execute(
            "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = ANY(%s)",
            [list(funktionen)],
        )
        definitionen = [zeile[0] for zeile in cur.fetchall()]
    for tabelle, regel, using, check in regeln:
        teile = []
        if using and tauschen(using) != using:
            teile.append(f"USING ({tauschen(using)})")
        if check and tauschen(check) != check:
            teile.append(f"WITH CHECK ({tauschen(check)})")
        if teile:
            # Ohne Parameter, damit ein ``%`` im Regeltext keine Platzhalter auslöst
            schema_editor.execute(f'ALTER POLICY "{regel}" ON {tabelle} ' + " ".join(teile), None)
    for definition in definitionen:
        if tauschen(definition) != definition:
            schema_editor.execute(tauschen(definition), None)
