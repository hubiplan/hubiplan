"""Vorbereitung beim Start des Backends in einem Prozess: Migrationen, Datenbankrolle und
Löschliste. Früher drei getrennte ``manage.py``-Aufrufe; jeder lud Django neu und kostete
beim Ausrollen ein paar Sekunden mehr Ausfallzeit (konzepte/ausfallzeiten-ausrollen.md).

Läuft als Tabelleneigentümer (``docker-entrypoint.sh`` setzt die Umgebung).
"""

import os

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Migrationen anwenden, Rolle hubiplan_app einrichten, Löschliste anwenden."

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)
        call_command("migrate", interactive=False, verbosity=verbosity)
        call_command("ensure_app_role", verbosity=verbosity)
        # Erledigte Löschungen erneut anwenden (nach dem Einspielen eines älteren Backups)
        if os.environ.get("LOESCHLISTE_PATH"):
            call_command("loeschliste_anwenden", verbosity=verbosity)
