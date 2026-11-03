"""Kalenderregeln, aktuelle Empfänger und einmalige Versandversuche je Kanal."""

import datetime
import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, PermissionDenied

from core.i18n import language_of, user_language
from core.tenancy import rls_bypass, tenant_context
from devices.push import send_to_user
from outbox import mail

from .access import Scope, scope_for, visible
from .models import Todo, TodoPreference, TodoReminder, TodoReminderConfig
from .sharing import participants

logger = logging.getLogger(__name__)


def local_time(day, time, zone):
    """Erste Ausprägung bei doppelter, nächste gültige bei fehlender Ortszeit."""
    local = datetime.datetime.combine(day, time, ZoneInfo(zone)).replace(fold=0)
    return local.astimezone(datetime.UTC).astimezone(ZoneInfo(zone))


def deadline(todo):
    if todo.due_date is None:
        return None
    day = todo.due_date
    if todo.due_time is None:
        day += datetime.timedelta(days=1)
    return local_time(day, todo.due_time or datetime.time(), todo.timezone)


def overdue(todo, now=None):
    due = deadline(todo)
    return due is not None and (now or timezone.now()) >= due


def times(todo, days):
    if todo.due_date is None:
        return []
    result = []
    for offset in sorted(set(days)):
        if todo.due_time is None:
            at = local_time(
                todo.due_date - datetime.timedelta(days=offset), datetime.time(8), todo.timezone
            )
        else:
            at = deadline(todo).astimezone(datetime.UTC) - datetime.timedelta(days=offset)
        result.append((f"before:{offset}", at))
    next_day = todo.due_date + datetime.timedelta(days=1)
    result.append(("overdue_once", local_time(next_day, datetime.time(8), todo.timezone)))
    # Zusammenfallende Zeitpunkte ergeben je Kanal nur einen Versuch.
    unique = {}
    for rule, at in result:
        unique.setdefault(at.astimezone(datetime.UTC), rule)
    return [(rule, at) for at, rule in unique.items()]


def current_recipients(todo):
    if todo.deleted_at or todo.status != "open":
        return {}
    scopes = {(todo.organization_id, todo.department_id)}
    if todo.shared:
        scopes.update(todo.shares.values_list("target_org_id", "target_department_id"))
    eligible = {}
    for org_id, dept_id in scopes:
        from organizations.models import Organization

        org = Organization.objects.get(pk=org_id)
        with tenant_context(org_id):
            if todo.shared:
                people = participants(todo, Scope(org, dept_id, set()))
            elif todo.owner_id:
                people = {todo.owner_id: {"user": todo.owner, "edit": True, "responsible": True}}
            else:
                people = {}
        for uid, person in people.items():
            user = person["user"]
            if not user.is_active:
                continue
            with tenant_context(org_id, uid):
                try:
                    scope = scope_for(user, org_id, dept_id)
                except (NotFound, PermissionDenied):
                    continue
                if not visible(user, scope).filter(pk=todo.pk).exists():
                    continue
            entry = eligible.setdefault(uid, {**person, "scope": scope})
            entry["responsible"] |= person["responsible"]
            entry["edit"] |= person["edit"]
    responsible = any(row["responsible"] for row in eligible.values())
    return {
        uid: row
        for uid, row in eligible.items()
        if row["responsible"] or (not responsible and row["edit"])
    }


@transaction.atomic
def sync(todo, now=None):
    now = now or timezone.now()
    with rls_bypass():
        todo = Todo.objects.select_for_update().get(pk=todo.pk)
    recipients = current_recipients(todo) if todo.due_date else {}
    with rls_bypass():
        stale = todo.reminder_configs.filter(active=True).exclude(user_id__in=recipients)
        stale.update(active=False)
        todo.reminders.filter(result="pending").exclude(user_id__in=recipients).update(
            result="cancelled"
        )
        for uid, entry in recipients.items():
            config, _ = TodoReminderConfig.objects.get_or_create(
                organization=todo.organization,
                todo=todo,
                user_id=uid,
            )
            if not config.active:
                config.active = True
                config.revision += 1
                config.enrolled_at = now
            config.last_due_revision = todo.due_revision
            config.save()
            todo.reminders.filter(user_id=uid, result="pending").exclude(
                due_revision=todo.due_revision,
                config_revision=config.revision,
            ).update(result="cancelled")
            if not config.enabled:
                todo.reminders.filter(user_id=uid, result="pending").update(result="cancelled")
                continue
            preferences, _ = TodoPreference.objects.get_or_create(user_id=uid)
            channels = {
                "mail": config.mail if config.mail is not None else preferences.reminder_mail,
                "push": config.push if config.push is not None else preferences.reminder_push,
            }
            for rule, at in times(todo, config.days):
                if at < now:
                    continue
                for channel, enabled in channels.items():
                    if enabled:
                        TodoReminder.objects.get_or_create(
                            organization=todo.organization,
                            todo=todo,
                            user_id=uid,
                            due_revision=todo.due_revision,
                            config_revision=config.revision,
                            rule=rule,
                            channel=channel,
                            defaults={"scheduled_at": at},
                        )


def highlight(todo, user, now=None):
    now = now or timezone.now()
    if not todo.due_date:
        return {"overdue": False, "highlight": False, "due_label": gettext("ohne Frist")}
    config = TodoReminderConfig.objects.filter(todo=todo, user=user).first()
    days = config.days if config else [1]
    planned = times(todo, days or [0])
    active = now >= min(at for _, at in planned)
    late = overdue(todo, now)
    today = now.astimezone(ZoneInfo(todo.timezone)).date()
    if late:
        label = gettext("Überfällig")
    elif todo.due_date == today:
        label = gettext("Heute fällig")
    elif todo.due_date == today + datetime.timedelta(days=1):
        label = gettext("Fällig morgen")
    else:
        label = str(todo.due_date)
    return {"overdue": late, "highlight": active, "due_label": label}


def deliver(pk, now=None):
    now = now or timezone.now()
    with transaction.atomic(), rls_bypass():
        item = TodoReminder.objects.filter(pk=pk).first()
        if item is None:
            return False
        todo = Todo.objects.select_for_update().filter(pk=item.todo_id).first()
        item = TodoReminder.objects.select_for_update().get(pk=pk)
        if item.claimed_at or item.result != "pending" or item.scheduled_at > now:
            return False
        item.claimed_at = now
        item.result = "skipped"
        entry = current_recipients(todo).get(item.user_id) if todo else None
        config = TodoReminderConfig.objects.filter(
            todo_id=item.todo_id, user_id=item.user_id
        ).first()
        preferences, _ = TodoPreference.objects.get_or_create(user_id=item.user_id)
        allowed = bool(
            entry
            and config
            and config.active
            and config.enabled
            and item.due_revision == todo.due_revision
            and item.config_revision == config.revision
        )
        if allowed:
            override = getattr(config, item.channel)
            allowed = (
                override
                if override is not None
                else getattr(preferences, f"reminder_{item.channel}")
            )
            allowed = allowed and (
                item.rule == "overdue_once" or int(item.rule.split(":")[1]) in config.days
            )
            if item.rule == "overdue_once":
                allowed = allowed and now.astimezone(
                    ZoneInfo(todo.timezone)
                ).date() == todo.due_date + datetime.timedelta(days=1)
            elif overdue(todo, now):
                allowed = bool(
                    todo.due_time
                    and item.rule == "before:0"
                    and now <= item.scheduled_at + datetime.timedelta(minutes=5)
                )
        item.save(update_fields=["claimed_at", "result"])
    if not allowed:
        return False
    # Die Beanspruchung ist vor dem externen Versand dauerhaft gespeichert.
    user = entry["user"]
    with tenant_context(entry["scope"].org.pk, user.pk):
        try:
            scope = scope_for(user, entry["scope"].org.pk, entry["scope"].department_id)
            current = (
                visible(user, scope)
                .filter(pk=todo.pk, status="open", due_revision=item.due_revision)
                .first()
            )
        except (NotFound, PermissionDenied):
            return False
        if current is None:
            return False
        with language_of(user):
            title = gettext("Erinnerung: {title}").format(title=current.title)
            text = gettext("Frist: {date}").format(date=current.due_date)
            link = f"{settings.FRONTEND_URL}/aufgaben?aufgabe={current.pk}"
            try:
                if item.channel == "mail":
                    sent = mail.send(
                        user.email,
                        title,
                        f"{title}\n{text}\n{link}",
                        organization=current.organization,
                        kind="aufgabe",
                        language=user_language(user),
                        fail_silently=True,
                    )
                else:
                    sent = (
                        send_to_user(
                            user.pk,
                            {
                                "v": 1,
                                "t": "todo",
                                "todo": current.pk,
                                "org": scope.org.pk,
                                "department": scope.department_id,
                                "title": title
                                if preferences.push_title
                                else gettext("Aufgabenerinnerung"),
                                "text": text,
                            },
                        )
                        > 0
                    )
            except Exception:  # noqa: BLE001 - jedes Transportmittel unabhängig behandeln
                logger.exception("Aufgabenerinnerung konnte nicht zugestellt werden")
                sent = False
    with rls_bypass():
        TodoReminder.objects.filter(pk=pk).update(
            result="sent" if sent else "failed", sent_at=now if sent else None
        )
    return sent


def run(now=None):
    now = now or timezone.now()
    with rls_bypass():
        tasks = list(
            Todo.objects.filter(status="open", deleted_at__isnull=True, due_date__isnull=False)
        )
        for todo in tasks:
            sync(todo, now)
        ids = list(
            TodoReminder.objects.filter(
                result="pending", claimed_at__isnull=True, scheduled_at__lte=now
            ).values_list("pk", flat=True)
        )
    return sum(deliver(pk, now) for pk in ids)
