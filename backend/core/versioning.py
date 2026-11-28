"""Schutz vor gleichzeitigem Bearbeiten: Jede Änderung erhöht ``version``.

Wer einen Datensatz ändert oder löscht, schickt die Fassung mit, die er geladen hat. Hat
inzwischen jemand anderes gespeichert, lehnt der Server mit 409 ab („… wurde inzwischen
geändert. Bitte neu laden.“), statt den fremden Stand stillschweigend zu überschreiben.
Ältere Apps schicken keine Fassung; für sie gilt wie bisher „wer zuletzt speichert, gewinnt“.

Die Fassung zählt nur hoch: Sie steht in ``derived_fields`` des Modells und wird damit weder
protokolliert noch von „Rückgängig“ auf einen alten Wert zurückgesetzt.
"""

from __future__ import annotations

from django.db import models
from rest_framework.exceptions import APIException

MISSING = object()


class Conflict(APIException):
    status_code = 409
    default_code = "conflict"


class Versioned(models.Model):
    """Modell mit Fassung. Jedes Speichern eines vorhandenen Datensatzes zählt hoch."""

    version = models.PositiveIntegerField("Fassung", default=1, db_default=1, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            self.version = (self.version or 0) + 1
            fields = kwargs.get("update_fields")
            # Leere Liste heißt bei Django „nichts speichern“; das bleibt so
            if fields and "version" not in fields:
                kwargs["update_fields"] = [*fields, "version"]
        super().save(*args, **kwargs)


def sent_version(request):
    """Mitgeschickte Fassung aus dem Rumpf (auch bei DELETE) oder ``?version=``."""
    data = request.data
    if hasattr(data, "get") and "version" in data:
        return data.get("version")
    return request.query_params.get("version", MISSING)


def check_version(instance, sent, message) -> None:
    """Lehnt mit 409 ab, wenn ``sent`` nicht die aktuelle Fassung ist.

    Der Aufrufer hat die Zeile gesperrt und frisch gelesen. ``MISSING`` (ältere App) prüft
    nicht. Zahlen aus Formularen und Abfragen kommen als Text; ``True`` zählt nicht als 1.
    """
    if sent is MISSING:
        return
    if isinstance(sent, str) and sent.isdecimal():
        sent = int(sent)
    if type(sent) is not int or sent != instance.version:
        raise Conflict(message)


def check_request(request, instance, message) -> None:
    check_version(instance, sent_version(request), message)
