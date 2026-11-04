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
