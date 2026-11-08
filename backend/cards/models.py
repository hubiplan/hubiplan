"""Digitaler Mitgliedsausweis: QR-Code mit zufälligem Schlüssel je Mitgliedschaft.

Der QR-Code enthält nur einen Link mit einem zufälligen, nicht erratbaren
Schlüssel, keine Mitgliedsnummer. Wer ihn scannt, sieht eine öffentliche Seite
mit Name, Foto (nur mit Einwilligung), aktuellem Status, Verein und Abteilung.

Der Ausweis muss jederzeit neu gedruckt und im Mitgliederbereich angezeigt werden
können. Deshalb liegt der Schlüssel verschlüsselt mit dem Schlüssel des Vereins vor;
gesucht wird über seinen Hash (Gesamtaudit 08.11., F-04). Wer nur die Datenbank liest,
kann damit keine Ausweisseite öffnen. Neu erzeugen ersetzt den Schlüssel (alte Ausdrucke
werden ungültig), Sperren macht ihn ungültig, bis der Ausweis wieder freigegeben wird.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models

from core.encfields import EncryptedCharField


def new_token() -> str:
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class MemberCard(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        verbose_name="Verein",
        on_delete=models.CASCADE,
        related_name="+",
    )
    membership = models.OneToOneField(
        "members.Membership", on_delete=models.CASCADE, related_name="card"
    )
    token = EncryptedCharField(max_length=64, default=new_token)
    token_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Zeitpunkt des aktuellen Schlüssels (beim Neu-Erzeugen aktualisiert)
    issued_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField("gesperrt am", null=True, blank=True)
    # Anbieter -> Objekt-ID -> zuletzt übertragener Inhalts-Hash. Keine Wallet-Schlüssel.
    wallet_passes = models.JSONField(default=dict, db_default={}, blank=True)

    class Meta:
        verbose_name = "Mitgliedsausweis"
        verbose_name_plural = "Mitgliedsausweise"

    def __str__(self) -> str:
        return f"Mitgliedsausweis {self.membership_id}"

    def save(self, *args, **kwargs):
        self.token_hash = hash_token(self.token) if self.token else None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "token" in update_fields:
            kwargs["update_fields"] = {*update_fields, "token_hash"}
        super().save(*args, **kwargs)

    @property
    def url(self) -> str:
        from organizations.addresses import base_url

        return f"{base_url(self.organization)}/ausweis/{self.token}"
