"""Inventar und ausdrückliche Verknüpfungen; keine impliziten Objektfreigaben."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.encfields import EncryptedCharField, EncryptedJSONField, EncryptedTextField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage


def photo_path(instance, filename):
    return f"materials/{instance.organization_id}/{uuid.uuid4().hex}.jpg"


class Scoped(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self._meta.model_name} {self.pk}"


class MaterialItem(Scoped):
    title = EncryptedCharField(_("Bezeichnung"), max_length=200)
    description = EncryptedTextField(_("Kurzbeschreibung"))
    purpose = EncryptedTextField(_("Verwendungszweck"), blank=True)
    location_kind = models.CharField(
        max_length=10,
        choices=[("member", _("Mitglied")), ("address", _("Adresse")), ("unknown", _("Zu klären"))],
    )
    member = models.ForeignKey(
        "members.Membership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="materials",
    )
    address = EncryptedJSONField(default=dict, blank=True)
    location_note = EncryptedCharField(max_length=300, blank=True)
    condition = models.CharField(
        max_length=15,
        default="ready",
        choices=[
            ("ready", _("Einsatzbereit")),
            ("limited", _("Eingeschränkt nutzbar")),
            ("defective", _("Defekt")),
            ("retired", _("Ausgesondert")),
        ],
    )
    condition_note = EncryptedCharField(max_length=500, blank=True)
    version = models.PositiveIntegerField(default=1)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["organization", "department", "deleted_at"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(location_kind="member") | Q(member__isnull=True),
                name="material_member_only_at_member",
            )
        ]

    def __str__(self):
        return self.inventory_number if self.pk else str(_("Material"))

    @property
    def inventory_number(self):
        return f"MAT-{self.pk:06d}"


class MaterialEventLink(Scoped):
    item = models.ForeignKey(MaterialItem, on_delete=models.CASCADE, related_name="event_links")
    event = models.ForeignKey("events.Event", null=True, on_delete=models.SET_NULL)
    kind = models.CharField(
        max_length=12,
        choices=[
            ("event", _("Einzeltermin")),
            ("series", _("Ganze Reihe")),
            ("occurrence", _("Nur dieser Termin")),
            ("exclude", _("Diesen Termin ausschließen")),
        ],
    )
    original_start = models.DateTimeField(null=True, blank=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    note = EncryptedCharField(max_length=300, blank=True)
    # Die Regel beim Zuordnen: Regeländerungen erfordern eine ausdrückliche Bestätigung.
    rule = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "event", "kind", "original_start"],
                condition=Q(event__isnull=False),
                nulls_distinct=False,
                name="material_event_unique",
            ),
            models.CheckConstraint(
                condition=Q(valid_until__isnull=True)
                | Q(valid_from__isnull=True)
                | Q(valid_until__gte=models.F("valid_from")),
                name="material_event_dates",
            ),
        ]


class MaterialTodoLink(Scoped):
    item = models.ForeignKey(MaterialItem, on_delete=models.CASCADE, related_name="todo_links")
    todo = models.ForeignKey("todos.Todo", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "todo"], name="material_todo_unique")
        ]


class MaterialDocumentLink(Scoped):
    item = models.ForeignKey(MaterialItem, on_delete=models.CASCADE, related_name="document_links")
    document = models.ForeignKey("documents.Document", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "document"], name="material_doc_unique")
        ]


class MaterialPhoto(Scoped):
    item = models.ForeignKey(MaterialItem, on_delete=models.CASCADE, related_name="photos")
    file = PrivateFileField(storage=private_storage, upload_to=photo_path)
    size = models.PositiveIntegerField(default=0)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item"], condition=Q(deleted_at__isnull=True), name="material_one_photo"
            )
        ]


class MaterialRevision(Scoped):
    item = models.ForeignKey(MaterialItem, on_delete=models.CASCADE, related_name="revisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=20)
    # Private Verweise erscheinen nie im allgemeinen Änderungsprotokoll.
    data = EncryptedJSONField(default=dict)

    class Meta:
        ordering = ["-pk"]
