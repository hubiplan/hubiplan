"""Datenbankschutz (finance/0024, audit/0008) in Tests gezielt abschalten.

Manche Tests spielen einen Angreifer, der die Datenbank beherrscht, oder setzen die
Protokollkette für eine Migration zurück. Das darf nur ein Superuser der Datenbank
(Testdatenbank: ja; im Echtbetrieb nicht die Anwendung).
"""

from contextlib import contextmanager

from django.db import connection


@contextmanager
def ohne_trigger():
    with connection.cursor() as cur:
        cur.execute("SELECT current_user, session_user")
        role, login = cur.fetchone()
        cur.execute("RESET ROLE")
        cur.execute("SET LOCAL session_replication_role = replica")
        if role != login:
            cur.execute(f'SET ROLE "{role}"')
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute("SET LOCAL session_replication_role = origin")
            if role != login:
                cur.execute(f'SET ROLE "{role}"')


protokoll_offen = ohne_trigger
