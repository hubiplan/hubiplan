"""Passwort-Hash mit Argon2id (RFC 9106).

Werte nach der zweiten Empfehlung von RFC 9106 (64 MiB, 3 Durchläufe, 4 Fäden): hart gegen
Grafikkarten, aber mit wenig genug Speicher, dass mehrere gleichzeitige Anmeldungen in das
Speicherlimit des Backend-Containers passen. Djangos Vorgabe (100 MiB, 8 Fäden) wäre dafür zu
groß. Wer die Werte später anhebt, braucht nichts weiter zu tun: Django rechnet beim nächsten
Anmelden neu (``must_update``).
"""

from django.contrib.auth.hashers import Argon2PasswordHasher


class Argon2idHasher(Argon2PasswordHasher):
    time_cost = 3
    memory_cost = 64 * 1024  # KiB
    parallelism = 4
