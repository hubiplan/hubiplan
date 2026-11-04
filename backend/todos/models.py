"""Private und ausdrücklich freigegebene Aufgaben im Datenbereich einer Einheit."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone as django_timezone

from core.encfields import EncryptedCharField, EncryptedJSONField, EncryptedTextField
from core.privatefiles import PrivateFileField
from exchange.models import private_storage


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
    series = models.ForeignKey(
        "TodoSeries", on_delete=models.CASCADE, null=True, blank=True, related_name="occurrences"
    )
    sequence_no = models.PositiveIntegerField(null=True, blank=True)
    withdrawn = models.BooleanField(default=False)
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
            ),
            models.UniqueConstraint(
                fields=["series"],
                condition=Q(series__isnull=False, status="open", deleted_at__isnull=True),
                name="todo_series_one_open",
            ),
            models.UniqueConstraint(
                fields=["series", "sequence_no"],
                condition=Q(series__isnull=False, deleted_at__isnull=True),
                name="todo_series_sequence_unique",
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from django.db import transaction

        if self.series_id:
            from .series import after_save, before_save

            with transaction.atomic():
                series = TodoSeries.objects.select_for_update().get(pk=self.series_id)
                previous = (
                    type(self).objects.select_for_update().filter(pk=self.pk).first()
                    if self.pk
                    else None
                )
                before_save(self, previous, series)
                self._save(*args, **kwargs)
                after_save(self, previous, series)
        else:
            self._save(*args, **kwargs)

    def _save(self, *args, **kwargs):
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


class TodoSeries(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department", on_delete=models.CASCADE, null=True, related_name="+"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    source_series = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="target_series"
    )
    kind = models.CharField(
        max_length=8,
        default="sequence",
        choices=[("template", "Vorlage"), ("sequence", "Ausgabenfolge")],
    )
    active = models.BooleanField(default=True)
    anchor_date = models.DateField()
    repeat = models.CharField(
        max_length=7,
        choices=[
            ("daily", "täglich"),
            ("weekly", "wöchentlich"),
            ("monthly", "monatlich"),
            ("yearly", "jährlich"),
        ],
    )
    interval = models.PositiveIntegerField(default=1)
    basis = models.CharField(
        max_length=4, default="due", choices=[("due", "Frist"), ("done", "Erledigung")]
    )
    last_day = models.BooleanField(default=False)
    ends_on = models.DateField(null=True, blank=True)
    count = models.PositiveIntegerField(null=True, blank=True)
    title = EncryptedCharField(max_length=200)
    description = EncryptedTextField(blank=True)
    due_time = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="Europe/Berlin")
    shares = EncryptedJSONField(default=list)
    documents = EncryptedJSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(interval__gte=1), name="todo_series_interval_positive"
            )
        ]

    def __str__(self):
        return self.title


class TodoShare(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    role = models.ForeignKey("access.Role", on_delete=models.CASCADE, null=True, blank=True)
    target_org = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="todo_shares"
    )
    target_department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="todo_department_shares",
    )
    level = models.CharField(
        max_length=4, choices=[("view", "Lesen"), ("edit", "Bearbeiten")], default="view"
    )
    responsible = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, role__isnull=True)
                    | Q(user__isnull=True, role__isnull=False)
                ),
                name="todo_share_one_recipient",
            ),
            models.UniqueConstraint(
                fields=["todo", "user", "target_org"],
                condition=Q(user__isnull=False),
                name="todo_share_user_unique",
            ),
            models.UniqueConstraint(
                fields=["todo", "role", "target_org"],
                condition=Q(role__isnull=False),
                name="todo_share_role_unique",
            ),
        ]

    def __str__(self):
        return f"{self.todo_id}: {self.user_id or self.role_id}"


class TodoPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    share_mail = models.BooleanField(default=True)
    share_push = models.BooleanField(default=True)
    reminder_mail = models.BooleanField(default=True)
    reminder_push = models.BooleanField(default=True)
    push_title = models.BooleanField(default=True)
    purge_done = models.BooleanField(default=False)

    def __str__(self):
        return str(self.user_id)


class TodoNotice(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    revision = models.PositiveIntegerField()
    claimed_at = models.DateTimeField(default=django_timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["todo", "user", "revision"], name="todo_notice_once")
        ]

    def __str__(self):
        return f"{self.todo_id}: {self.user_id} ({self.revision})"


def reminder_days():
    return [1]


class TodoReminderConfig(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="reminder_configs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    days = models.JSONField(default=reminder_days)
    enabled = models.BooleanField(default=True)
    mail = models.BooleanField(null=True, default=None)
    push = models.BooleanField(null=True, default=None)
    active = models.BooleanField(default=False)
    customized = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    last_due_revision = models.PositiveIntegerField(default=0)
    enrolled_at = models.DateTimeField(default=django_timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["todo", "user"], name="todo_reminder_config_unique")
        ]

    def __str__(self):
        return f"{self.todo_id}: {self.user_id}"


class TodoReminder(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="reminders")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    due_revision = models.PositiveIntegerField()
    config_revision = models.PositiveIntegerField()
    rule = models.CharField(max_length=24)
    channel = models.CharField(max_length=4, choices=[("mail", "Mail"), ("push", "Push")])
    scheduled_at = models.DateTimeField(db_index=True)
    claimed_at = models.DateTimeField(null=True)
    sent_at = models.DateTimeField(null=True)
    result = models.CharField(max_length=12, default="pending")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["todo", "user", "due_revision", "config_revision", "rule", "channel"],
                name="todo_reminder_attempt_unique",
            )
        ]
        indexes = [models.Index(fields=["result", "scheduled_at"])]

    def __str__(self):
        return f"{self.todo_id}: {self.user_id} {self.rule} {self.channel}"


class TodoCleanupSetting(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department",
        on_delete=models.CASCADE,
        null=True,
        related_name="todo_cleanup_settings",
    )
    purge_done = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(department__isnull=True),
                name="todo_cleanup_root_unique",
            ),
            models.UniqueConstraint(
                fields=["organization", "department"],
                condition=Q(department__isnull=False),
                name="todo_cleanup_department_unique",
            ),
        ]

    def __str__(self):
        return f"{self.organization_id}: {self.department_id or 0}"


def attachment_path(instance, filename):
    import uuid

    return f"todos/{instance.organization_id}/{uuid.uuid4().hex}/{filename}"


class TodoAttachment(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    department = models.ForeignKey(
        "organizations.Department", on_delete=models.CASCADE, null=True, related_name="+"
    )
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="attachments")
    kind = models.CharField(max_length=8, choices=[("file", "Datei"), ("document", "Dokument")])
    file = PrivateFileField(storage=private_storage, upload_to=attachment_path, blank=True)
    document = models.ForeignKey(
        "documents.Document", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    name = EncryptedCharField(max_length=200, blank=True)
    size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    uploaded_at = models.DateTimeField(default=django_timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(kind="file", document__isnull=True) | Q(kind="document", file=""),
                name="todo_attachment_kind",
            )
        ]

    def __str__(self):
        return self.name or str(self.pk)
