"""Ausdrückliche Mitgliederfreigaben; Mitgliedschaft ist kein Verwaltungsrecht."""

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from changes.tracking import active
from core.tenancy import rls_bypass, scope_of, set_rls, tenant_context, user_view
from portal.models import PortalAccess

from .access import Scope, can_delete, visible
from .attachments import AttachmentDetailView, Conflict, attachment_rows, row_data
from .models import Todo, TodoPortalGrant, TodoPortalPublication, TodoSeries
from .views import TodoScopeMixin


def current_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    with tenant_context(access.organization_id, user.pk):
        if not access.membership.current_period():
            raise NotFound()
    return access


def portal_scope(user, access_id):
    access = current_access(user, access_id)
    set_rls(
        access.organization_id,
        user.pk,
        scope_id=scope_of(access.organization_id),
        todo_portal_id=access.pk,
    )
    return access, Scope(access.organization, None, set(), access.pk)


def portal_visible(user, scope):
    access = current_access(user, scope.portal_access_id)
    from members.models import DepartmentMembership, today
    from organizations.tree import with_ancestors

    departments = (
        DepartmentMembership.objects.filter(
            membership_id=access.membership_id, valid_from__lte=today()
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today()))
        .values_list("department_id", flat=True)
    )
    permitted = with_ancestors(scope.org.pk, departments)
    publication_ids = (
        TodoPortalPublication.objects.filter(
            active=True,
            organization=scope.org,
        )
        .filter(Q(mode="offer") | Q(grants__access=access))
        .filter(Q(todo__department__isnull=True) | Q(todo__department_id__in=permitted))
        .values("todo_id")
    )
    return Todo.objects.filter(
        pk__in=publication_ids, organization=scope.org, deleted_at__isnull=True, withdrawn=False
    )


def may_complete(todo, access):
    from .remote import completion_allowed

    pub = todo.portal_publication
    return completion_allowed(todo) and (
        pub.active
        and (
            pub.mode == "offer"
            and pub.claimed_by_id == access.pk
            or pub.mode == "assigned"
            and pub.grants.filter(access=access, can_complete=True).exists()
        )
        and not todo.per_unit
    )


def portal_data(todo, access, scope):
    from .reminders import highlight

    pub = todo.portal_publication
    with attachment_rows(todo, scope) as rows:
        attachments = [
            row_data(a, central, pk, scope)
            for a, central, pk in rows
            if a is None or not a.deleted_at
        ]
    from .remote import file_entries

    attachments += file_entries(todo)
    return {
        "id": todo.pk,
        "title": todo.title,
        "description": todo.description,
        "due_date": todo.due_date,
        "due_time": todo.due_time,
        "timezone": todo.timezone,
        "status": todo.status,
        "version": todo.version,
        "can_complete": may_complete(todo, access),
        "can_claim": pub.mode == "offer" and pub.claimed_by_id is None and todo.status == "open",
        "claimed_by_me": pub.claimed_by_id == access.pk,
        "claimed": pub.claimed_by_id is not None,
        "attachments": attachments,
        **highlight(todo, access.user),
    }


class PortalTaskMixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access, self.scope = portal_scope(request.user, kwargs["access_id"])

    def task(self, request, pk, *, write=False):
        qs = portal_visible(request.user, self.scope)
        if write:
            # Gleiche Sperrreihenfolge wie alle anderen Serienwege.
            candidate = get_object_or_404(qs, pk=pk)
            if candidate.remote_mode == "common" and candidate.remote_origin_id:
                from .models import TodoRemoteTask

                with rls_bypass():
                    TodoRemoteTask.objects.select_for_update().values("pk").get(
                        pk=candidate.remote_origin_id
                    )
            if candidate.series_id:
                with rls_bypass():
                    TodoSeries.objects.defer(
                        "title", "description", "shares", "documents"
                    ).select_for_update().get(pk=candidate.series_id)
            # Ein noch unübernommenes Angebot ist lesbar, aber noch nicht schreibbar.
            # Deshalb nur seine bereits geprüfte Nummer unter der Systemsperre sperren.
            with rls_bypass():
                Todo.objects.only("pk").select_for_update().get(pk=candidate.pk)
        from .remote import refresh_common

        return refresh_common(get_object_or_404(qs, pk=pk))


class PortalTaskListView(PortalTaskMixin, APIView):
    def get(self, request, **kwargs):
        from .remote import fresh_rows

        return Response(
            {
                "items": [
                    portal_data(t, self.access, self.scope)
                    for t in fresh_rows(
                        portal_visible(request.user, self.scope).order_by("due_date", "pk")
                    )
                ]
            }
        )


class MemberChange(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=["open", "done"], required=False)
    action = serializers.ChoiceField(choices=["claim", "release"], required=False)

    def validate(self, attrs):
        if len(attrs) != 2 or bool(attrs.get("status")) == bool(attrs.get("action")):
            raise serializers.ValidationError(gettext("Dafür fehlt dir die Berechtigung."))
        if set(self.initial_data) - {"version", "status", "action"}:
            raise serializers.ValidationError(gettext("Dafür fehlt dir die Berechtigung."))
        return attrs


class PortalTaskDetailView(PortalTaskMixin, APIView):
    def get(self, request, pk, **kwargs):
        from .remote import refresh_common

        return Response(
            portal_data(refresh_common(self.task(request, pk)), self.access, self.scope)
        )

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        values = MemberChange(data=request.data)
        values.is_valid(raise_exception=True)
        values = values.validated_data
        todo = self.task(request, pk, write=True)
        with rls_bypass():
            pub = TodoPortalPublication.objects.select_for_update().get(todo=todo, active=True)
        if values["version"] != todo.version:
            raise Conflict(gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden."))
        action = values.get("action")
        if action:
            if pub.mode != "offer" or todo.status != "open":
                raise PermissionDenied()
            if action == "claim" and pub.claimed_by_id not in (None, self.access.pk):
                raise Conflict(gettext("Diese Aufgabe wurde bereits übernommen."))
            if action == "release" and pub.claimed_by_id != self.access.pk:
                raise PermissionDenied()
            # Nur die gesperrte und oben berechtigte Zuordnungszeile. Kein Inhaltszugriff.
            with rls_bypass():
                pub.claimed_by = self.access if action == "claim" else None
                pub.save(update_fields=["claimed_by"])
                Todo.objects.filter(pk=todo.pk).update(version=todo.version + 1)
            todo.refresh_from_db()
        else:
            if not may_complete(todo, self.access):
                raise PermissionDenied()
            if todo.remote_mode == "common":
                from .remote import complete_common

                todo = complete_common(todo, request.user, values["status"])
                from .sharing import log_change

                log_change(todo, request.user, "update")
                return Response(portal_data(todo, self.access, self.scope))
            todo.status = values["status"]
            todo.done_at = timezone.now() if todo.status == "done" else None
            todo.done_by = request.user if todo.status == "done" else None
            todo.version += 1
            from django.core.exceptions import ValidationError

            try:
                todo.save(update_fields=["status", "done_at", "done_by", "version", "updated_at"])
            except ValidationError as exc:
                raise Conflict(exc.messages) from exc
        ctx = active()
        if ctx:
            ctx.block(gettext("Diese Änderung kann hier nicht zurückgenommen werden."))
        from .sharing import log_change

        log_change(todo, request.user, "update")
        return Response(portal_data(todo, self.access, self.scope))


class PortalTaskFileView(PortalTaskMixin, AttachmentDetailView):
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        # AttachmentDetailView setzt sonst einen Verwaltungskontext.
        APIView.initial(self, request, *args, **kwargs)
        self.access, self.scope = portal_scope(request.user, kwargs["access_id"])


class PortalRemoteFileView(PortalTaskMixin, APIView):
    def get(self, request, pk, att_id, **kwargs):
        from .remote import remote_file

        todo = self.task(request, pk)
        if not todo.remote_origin_id:
            raise PermissionDenied()
        return remote_file(todo, att_id)


def choices(scope):
    org = scope.org
    if not org.member_portal_enabled:
        return []
    from members.models import today

    on = today()
    rows = PortalAccess.objects.filter(organization=org, user__is_active=True).select_related(
        "membership__person"
    )
    if scope.department_id:
        from members.models import DepartmentMembership
        from organizations.tree import UnitTree

        member_ids = (
            DepartmentMembership.objects.filter(
                department_id__in=UnitTree.of(org.pk).subtree(scope.department_id),
                valid_from__lte=on,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on))
            .values("membership_id")
        )
        rows = rows.filter(membership_id__in=member_ids)
    return [
        {"id": p.pk, "name": str(p.membership.person)}
        for p in rows
        if p.membership.current_period(on)
    ]


class PublishInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    active = serializers.BooleanField(default=True)
    mode = serializers.ChoiceField(choices=["assigned", "offer"], default="assigned")
    following = serializers.BooleanField(default=False)
    recipients = serializers.ListField(child=serializers.DictField(), default=list, max_length=1000)


class PublicationView(TodoScopeMixin, APIView):
    def task(self, request, pk):
        todo = get_object_or_404(visible(request.user, self.scope), pk=pk)
        if (
            not can_delete(todo, request.user, self.scope)
            or "todos.edit" not in self.scope.permissions
        ):
            raise PermissionDenied()
        return todo

    def get(self, request, pk, **kwargs):
        todo = self.task(request, pk)
        pub = TodoPortalPublication.objects.filter(todo=todo).first()
        return Response(
            {
                "choices": choices(self.scope),
                "enabled": self.org.member_portal_enabled and self.org.type == "club",
                "active": bool(pub and pub.active),
                "mode": pub.mode if pub else "assigned",
                "following": bool(pub and pub.following),
                "recipients": list(pub.grants.values("access_id", "can_complete")) if pub else [],
                "claimed_by": pub.claimed_by_id if pub else None,
                "version": todo.version,
            }
        )

    @transaction.atomic
    def put(self, request, pk, **kwargs):
        from .series import lock_task
        from .sharing import log_change

        self.task(request, pk)
        todo = lock_task(request.user, self.scope, pk)
        values = PublishInput(data=request.data)
        values.is_valid(raise_exception=True)
        data = values.validated_data
        if data["version"] != todo.version:
            raise Conflict(gettext("Die Aufgabe wurde inzwischen geändert. Bitte neu laden."))
        if todo.per_unit or (data["following"] and not todo.series_id):
            raise PermissionDenied()
        allowed = {r["id"] for r in choices(self.scope)}
        recipients = []
        for row in data["recipients"]:
            aid = row.get("access_id")
            if (
                type(aid) is not int
                or aid not in allowed
                or type(row.get("can_complete", True)) is not bool
            ):
                raise serializers.ValidationError(
                    gettext("Dieser Empfänger hat keinen passenden Zugang.")
                )
            if aid in {r["access_id"] for r in recipients}:
                raise serializers.ValidationError(
                    gettext("Dieser Empfänger ist bereits ausgewählt.")
                )
            recipients.append({"access_id": aid, "can_complete": row.get("can_complete", True)})
        if data["active"] and not self.org.member_portal_enabled:
            raise PermissionDenied()
        pub, _ = TodoPortalPublication.objects.update_or_create(
            todo=todo,
            defaults={
                "organization": self.org,
                "active": data["active"],
                "mode": data["mode"],
                "following": data["following"],
            },
        )
        previous = set(pub.grants.values_list("access_id", flat=True))
        pub.grants.all().delete()
        TodoPortalGrant.objects.bulk_create(
            [TodoPortalGrant(organization=self.org, publication=pub, **r) for r in recipients]
        )
        if pub.mode != "offer" and pub.claimed_by_id:
            pub.claimed_by = None
            pub.save(update_fields=["claimed_by"])
        if pub.active:
            todo.shared = True
        todo.version += 1
        todo.save(update_fields=["shared", "version", "updated_at"])
        ctx = active()
        if ctx:
            ctx.block(gettext("Freigaben lassen sich nicht rückgängig machen."))
        log_change(todo, request.user, "update")
        from .reminders import sync

        sync(todo)
        if pub.active and pub.mode == "assigned":
            for aid in {r["access_id"] for r in recipients} - previous:
                transaction.on_commit(lambda aid=aid: member_notice(todo.pk, aid))
        return self.get(request, pk, **kwargs)


def member_notice(todo_id, access_id):
    with rls_bypass():
        access = PortalAccess.objects.select_related("user").filter(pk=access_id).first()
    if access is None:
        return
    with tenant_context(access.organization_id, access.user_id):
        _member_notice(todo_id, access)


def _member_notice(todo_id, access):
    from core.i18n import language_of, user_language
    from devices.push import send_to_user
    from organizations.addresses import base_url
    from outbox import mail

    from .models import TodoPreference

    access_id = access.pk
    try:
        _, scope = portal_scope(access.user, access_id)
        todo = portal_visible(access.user, scope).filter(pk=todo_id).first()
    except NotFound:
        return
    if todo is None:
        return
    pref, _ = TodoPreference.objects.get_or_create(user=access.user)
    with language_of(access.user):
        title = gettext("Neue Aufgabe: {title}").format(title=todo.title)
        link = f"{base_url(scope.org)}/mein-bereich/aufgaben?zugang={access_id}&aufgabe={todo_id}"
        if pref.share_mail:
            mail.send(
                access.user.email,
                title,
                f"{title}\n{link}",
                organization=todo.organization,
                kind="aufgabe",
                language=user_language(access.user),
                fail_silently=True,
            )
        if pref.share_push:
            try:
                send_to_user(
                    access.user_id,
                    {
                        "v": 1,
                        "t": "todo",
                        "todo": todo_id,
                        "access": access_id,
                        "org": scope.org.pk,
                        "title": title if pref.push_title else gettext("Neue Aufgabe"),
                        "text": str(todo.due_date or ""),
                    },
                )
            except Exception:  # noqa: BLE001 - Push-Fehler verhindern keine gespeicherte Freigabe
                import logging

                logging.getLogger(__name__).exception("Mitglieder-Aufgabenhinweis nicht zugestellt")


def reminder_recipients(todo):
    with rls_bypass():
        pub = TodoPortalPublication.objects.filter(todo=todo, active=True).first()
        if pub is None:
            return {}
        ids = (
            [pub.claimed_by_id]
            if pub.mode == "offer"
            else list(pub.grants.filter(can_complete=True).values_list("access_id", flat=True))
        )
        accesses = list(
            PortalAccess.objects.filter(
                pk__in=[pk for pk in ids if pk], user__is_active=True
            ).select_related("user")
        )
    result = {}
    for access in accesses:
        with tenant_context(todo.organization_id, access.user_id):
            try:
                _, scope = portal_scope(access.user, access.pk)
                if not portal_visible(access.user, scope).filter(pk=todo.pk).exists():
                    continue
            except NotFound:
                continue
            result[access.user_id] = {
                "user": access.user,
                "edit": True,
                "responsible": True,
                "scope": scope,
            }
    return result


def inherit_publication(sender, instance, created=False, raw=False, **kwargs):
    if raw or not created or not instance.series_id or not instance.sequence_no:
        return
    with rls_bypass():
        previous = TodoPortalPublication.objects.filter(
            todo__series_id=instance.series_id,
            todo__sequence_no=instance.sequence_no - 1,
            todo__withdrawn=False,
            active=True,
            following=True,
        ).first()
        if previous is None:
            return
        publication = TodoPortalPublication.objects.create(
            organization=instance.organization,
            todo=instance,
            mode=previous.mode,
            following=True,
        )
        TodoPortalGrant.objects.bulk_create(
            [
                TodoPortalGrant(
                    organization=instance.organization,
                    publication=publication,
                    access_id=grant.access_id,
                    can_complete=grant.can_complete,
                )
                for grant in previous.grants.all()
            ]
        )
        Todo.objects.filter(pk=instance.pk).update(shared=True)
        instance.shared = True
