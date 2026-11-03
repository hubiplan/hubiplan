import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User
from core.i18n import language_of, user_language
from core.tenancy import rls_bypass, tenant_context
from devices.push import send_to_user
from outbox import mail

from .access import scope_for, visible
from .models import Todo, TodoPreference

logger = logging.getLogger(__name__)


def schedule_shared(todo, user_ids):
    for user_id in sorted(set(user_ids) - {todo.created_by_id}):
        transaction.on_commit(lambda uid=user_id: notify_shared.delay(todo.pk, uid), robust=True)


@shared_task
def notify_shared(todo_id, user_id):
    with rls_bypass():
        todo = Todo.objects.filter(pk=todo_id, shared=True, deleted_at__isnull=True).first()
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if todo is None or user is None:
            return
        preferences, _ = TodoPreference.objects.get_or_create(user=user)
    with tenant_context(todo.organization_id, user.pk):
        try:
            scope = scope_for(user, todo.organization_id, todo.department_id)
        except (NotFound, PermissionDenied):
            return
        if not visible(user, scope).filter(pk=todo.pk).exists():
            return
        with language_of(user):
            title = gettext("Neue Aufgabe: {title}").format(title=todo.title)
            link = f"{settings.FRONTEND_URL}/aufgaben?aufgabe={todo.pk}"
            if preferences.share_mail:
                mail.send(user.email, title, f"{title}\n{link}", organization=todo.organization,
                          kind="aufgabe", language=user_language(user), fail_silently=True)
            if preferences.share_push:
                try:
                    send_to_user(user.pk, {"v": 1, "t": "todo", "todo": todo.pk,
                        "org": todo.organization_id, "department": todo.department_id,
                        "title": title if preferences.push_title else gettext("Neue Aufgabe"),
                        "text": str(todo.due_date or "")})
                except Exception:  # noqa: BLE001 - Kanalfehler dürfen Speichern nicht verhindern
                    logger.exception("Aufgabenhinweis konnte nicht zugestellt werden")
