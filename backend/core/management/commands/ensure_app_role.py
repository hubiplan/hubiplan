"""Legt die eingeschränkte Datenbankrolle an und vergibt ihre Rechte (idempotent).

Läuft bei jedem Start des Backends nach den Migrationen – so stimmen die Rechte
auch nach einer Wiederherstellung aus einem Backup (das keine Rechte enthält).

Ist ``APP_DB_PASSWORD`` gesetzt, darf sich die Rolle mit diesem Passwort anmelden.
Backend, Worker und Beat verbinden sich dann direkt als hubiplan_app statt als
Datenbank-Superuser (siehe docker-compose.server.yml).

Ist ``BACKUP_DB_PASSWORD`` gesetzt, legt der Befehl zusätzlich die Rolle hubiplan_backup
an: Sie darf nur lesen und meldet sich im Backup-Dienst statt des Superusers an
(Gesamtaudit 08.11., GA8-06).
"""

import os

from django.core.management.base import BaseCommand
from django.db import connection

from core.rls import app_login_sql, backup_role_sql, create_app_role_sql


class Command(BaseCommand):
    help = "Rolle hubiplan_app anlegen und Rechte vergeben (nur PostgreSQL)."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write("Keine PostgreSQL-Datenbank – nichts zu tun.")
            return
        with connection.cursor() as cursor:
            cursor.execute(create_app_role_sql())
            password = os.environ.get("APP_DB_PASSWORD", "")
            if password:
                cursor.execute(app_login_sql(password, connection.connection))
                self.stdout.write("Rolle hubiplan_app darf sich mit Passwort anmelden.")
            backup_password = os.environ.get("BACKUP_DB_PASSWORD", "")
            if backup_password:
                cursor.execute(backup_role_sql(backup_password, connection.connection))
                self.stdout.write("Rolle hubiplan_backup darf nur lesen.")
        self.stdout.write(self.style.SUCCESS("Rechte der Rolle hubiplan_app gesetzt."))
