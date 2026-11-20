"""Pinnwand: kurze Meldungen an die Mitglieder (Lückenliste 20.11.2026, Punkt A3).

Ein Beitrag gehört zum Verein oder zu einer Untereinheit (Spalte ``department``). Ihn sehen
alle aktuellen Mitglieder des Vereins bzw. der Untereinheit (samt Untereinheiten darunter) im
Mitgliederbereich und in der App. Kein Chat: Mitglieder lesen nur; schreiben darf, wer das
Recht ``pinboard.edit`` hat. Auf Wunsch geht beim Anlegen ein Push an die Apps, nie eine Mail.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedTextField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage

MAX_TEXT = 2000
MAX_PHOTOS = 6


def photo_path(instance, filename):
    return f"pinboard/{instance.organization_id}/{uuid.uuid4().hex}.jpg"


class Notice(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )
    text = EncryptedTextField(_("Text"))
    # Oben angeheftet, bis jemand es löst
    pinned = models.BooleanField(default=False)
    # Ab dem Tag danach nicht mehr im Mitgliederbereich (leer: bis zum Aufräumen)
    visible_until = models.DateField(_("Anzeigen bis"), null=True, blank=True)
    # Push an die Apps beim Anlegen gewünscht und wann er rausging
    push = models.BooleanField(default=False)
    pushed_at = models.DateTimeField(null=True, blank=True)
    # Name unter dem Beitrag (Person beim Anlegen), damit Mitglieder wissen, wer schreibt
    author = EncryptedCharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-pinned", "-created_at", "-pk"]
        indexes = [models.Index(fields=["organization", "department", "created_at"])]

    def __str__(self):
        return f"notice {self.pk}"


class NoticePhoto(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name="photos")
    position = models.PositiveSmallIntegerField(default=0)
    file = PrivateFileField(storage=private_storage, upload_to=photo_path)
    size = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"notice photo {self.pk}"


class NoticeSeen(models.Model):
    """Bis wann ein Mitglied die Pinnwand gelesen hat (Zähler „neu“)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    membership = models.ForeignKey("members.Membership", on_delete=models.CASCADE, related_name="+")
    seen_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["membership"], name="pinboard_seen_once"),
        ]

    def __str__(self):
        return f"seen {self.pk}"
