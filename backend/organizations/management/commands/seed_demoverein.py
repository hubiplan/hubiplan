"""Zusätzlicher Demoverein für den Testserver: Schützenverein mit Korps (alles erfunden).

    python manage.py seed_demoverein [--password PASSWORT] [--reset-passwords]

Legt „Schützenverein Musterstadt 1823 e.V.“ mit Korps, Zügen, Mitgliedern und Daten für
alle Module an (Inhalt: ``organizations/demo_korps.py``). Wiederholbar; vorhandene Daten
und andere Organisationen (z. B. aus ``seed_testdata``) bleiben unverändert.

Ohne --password wird ein zufälliges Passwort für die neuen Testzugänge erzeugt und einmal
ausgegeben (nicht in Chats kopieren).
Nie auf dem Echtserver ausführen.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import generate_initial_password
from core.tenancy import rls_bypass
from organizations import demo_korps


class Command(BaseCommand):
    help = "Zusätzlichen Demoverein (Schützenverein mit Korps) anlegen."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Passwort für die Testzugänge des Demovereins")
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Passwort auch für bereits vorhandene Testzugänge des Demovereins setzen",
        )

    def handle(self, *args, **options):
        password = options["password"] or generate_initial_password()
        with transaction.atomic(), rls_bypass():
            result = demo_korps.seed(password, reset=options["reset_passwords"])
        self.stdout.write(self.style.SUCCESS(f"Demoverein angelegt: {result['club'].name}"))
        lines = ["Testzugänge:", *(f"  {e}" for e in demo_korps.all_emails())]
        if (result["created"] or options["reset_passwords"]) and not options["password"]:
            lines.append(f"Passwort: {password}")
        elif not options["password"]:
            lines.append("Passwort: unverändert (bestehende Zugänge)")
        self.stdout.write("\n".join(lines))
