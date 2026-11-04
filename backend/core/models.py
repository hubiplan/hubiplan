import uuid

from django.db import models


class DataKey(models.Model):
    """Datenschlüssel eines Vereins, verpackt von der Schlüsselquelle (core.crypto).

    Ohne RLS: Die Zeile ist ohne Hauptschlüssel wertlos, und Systemaufgaben müssen
    Dateien aller Vereine lesen können. Wird der Verein gelöscht, fällt die Zeile mit
    weg; seine verschlüsselten Daten sind dann nicht mehr lesbar (Krypto-Schreddern).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+"
    )
    # Bestehende Schlüssel bleiben aktiv; auch Inserts älterer Fassungen erhalten
    # den DB-Default. Weitere Generationen legt diese Vorbereitung noch nicht an.
    is_active = models.BooleanField(default=True, db_default=True)
    # "<Quelle>:<Version>:<Daten>", z. B. "file:1:…"
    wrapped = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    rewrapped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Datenschlüssel"
        verbose_name_plural = "Datenschlüssel"
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(is_active=True),
                name="core_datakey_ein_aktiver",
            ),
        ]

    def __str__(self) -> str:
        return f"Datenschlüssel {self.pk} ({self.organization_id})"


class DataKeyRotation(models.Model):
    """Wiederaufnehmbarer Betriebsauftrag; enthält nur Kennungen, keine Nutzdaten.

    Wie DataKey ohne RLS: Der Verwaltungsbefehl arbeitet über Organisationsgrenzen
    hinweg und muss auch falsch zugeordnete Schlüsselverweise erkennen können.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    target_key = models.OneToOneField(DataKey, on_delete=models.RESTRICT, related_name="+")
    source_key_ids = models.JSONField(default=list)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    phase = models.CharField(max_length=20, default="database")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(completed_at__isnull=True),
                name="core_ein_offener_schluesselwechsel",
            ),
        ]

    def __str__(self):
        return f"Schlüsselwechsel {self.pk} ({self.organization_id})"
