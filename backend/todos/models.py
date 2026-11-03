"""Private und ausdrücklich freigegebene Aufgaben im Datenbereich einer Einheit."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone as django_timezone

from core.encfields import EncryptedCharField, EncryptedTextField


class Todo(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="todos",
    )
    title = EncryptedCharField("Titel", max_length=200)
    description = EncryptedTextField("Beschreibung", blank=True)
    due_date = models.DateField("Frist", null=True, blank=True)
    due_time = models.TimeField("Uhrzeit", null=True, blank=True)
    timezone = models.CharField(max_length=64, default="Europe/Berlin")
    due_revision = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=10, default="open", choices=[("open", "Offen"), ("done", "Erledigt")]
    )
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="owned_todos"
    )
    shared = models.BooleanField(default=False)
    origin = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="copies"
    )
    per_unit = models.BooleanField(default=False)
    local_note = EncryptedTextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=django_timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Aufgabe"
        verbose_name_plural = "Aufgaben"
        indexes = [models.Index(fields=["organization", "status", "due_date"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(due_time__isnull=True) | Q(due_date__isnull=False),
                name="todo_time_needs_date",
            )
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from changes.tracking import active

        ctx = active()
        if ctx is not None and ctx.reverts and self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous:
                self.version = max(previous.version, self.version) + 1
                old_due = (previous.due_date, previous.due_time, previous.timezone)
                if old_due != (self.due_date, self.due_time, self.timezone):
                    self.due_revision = max(previous.due_revision, self.due_revision) + 1
            else:
                self.version += 1
                self.due_revision += 1
        super().save(*args, **kwargs)
