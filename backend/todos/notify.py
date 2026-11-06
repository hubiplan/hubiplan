import logging

from celery import shared_task
from django.db import transaction
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User
from core.i18n import language_of, user_language
from core.tenancy import rls_bypass, tenant_context
from devices.push import send_to_user
from organizations.addresses import base_url
from outbox import mail

from .access import scope_for, visible
from .models import Todo, TodoNotice, TodoPreference

logger = logging.getLogger(__name__)


def schedule_shared(todo, user_ids, *, include_creator=False):
    for user_id in sorted(set(user_ids) - (set() if include_creator else {todo.created_by_id})):
        transaction.on_commit(
            lambda uid=user_id: notify_shared.delay(todo.pk, uid, todo.version), robust=True
        )


@shared_task
def notify_shared(todo_id, user_id, revision):
    with rls_bypass():
        todo = Todo.objects.filter(pk=todo_id, shared=True, deleted_at__isnull=True).first()
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if todo is None or user is None:
            return
        preferences, _ = TodoPreference.objects.get_or_create(user=user)
        units = {
            (todo.organization_id, todo.department_id),
            *todo.shares.values_list("target_org_id", "target_department_id"),
        }
    selected = None
    for org_id, dept_id in sorted(units, key=lambda item: (item[0], item[1] or 0)):
        with tenant_context(org_id, user.pk):
            try:
                scope = scope_for(user, org_id, dept_id)
            except (NotFound, PermissionDenied):
                continue
            if visible(user, scope).filter(pk=todo.pk).exists():
                selected = (org_id, dept_id)
                break
    if selected is None:
        return
    with tenant_context(selected[0], user.pk):
        try:
            scope = scope_for(user, selected[0], selected[1])
        except (NotFound, PermissionDenied):
            return
        if not visible(user, scope).filter(pk=todo.pk).exists():
            return
        with rls_bypass():
            _, created = TodoNotice.objects.get_or_create(
                organization=todo.organization,
                todo=todo,
                user=user,
                revision=revision,
            )
        if not created:
            return
        with language_of(user):
            title = gettext("Neue Aufgabe: {title}").format(title=todo.title)
            unit = (
                f"abteilung={scope.department_id}"
                if scope.department_id
                else f"einheit={scope.org.pk}"
            )
            link = f"{base_url(scope.org)}/aufgaben?aufgabe={todo.pk}&{unit}"
            if preferences.share_mail:
                mail.send(
                    user.email,
                    title,
                    f"{title}\n{link}",
                    organization=todo.organization,
                    kind="aufgabe",
                    language=user_language(user),
                    fail_silently=True,
                )
            if preferences.share_push:
                try:
                    send_to_user(
                        user.pk,
                        {
                            "v": 1,
                            "t": "todo",
                            "todo": todo.pk,
                            "org": scope.org.pk,
                            "department": scope.department_id,
                            "title": title if preferences.push_title else gettext("Neue Aufgabe"),
                            "text": str(todo.due_date or ""),
                        },
                    )
                except Exception:  # noqa: BLE001 - Kanalfehler dürfen Speichern nicht verhindern
                    logger.exception("Aufgabenhinweis konnte nicht zugestellt werden")
