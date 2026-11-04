from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import visible
from .models import TodoCleanupSetting, TodoReminderConfig
from .reminders import sync
from .views import TodoScopeMixin


class ReminderInput(serializers.ModelSerializer):
    days = serializers.ListField(
        child=serializers.ChoiceField(choices=[0, 1, 3, 7]), allow_empty=False, max_length=4
    )

    class Meta:
        model = TodoReminderConfig
        fields = ["days", "enabled", "mail", "push"]

    def validate_days(self, value):
        return sorted(set(value))


class ReminderSettingsView(TodoScopeMixin, APIView):
    def get(self, request, pk, **kwargs):
        todo = get_object_or_404(visible(request.user, self.scope), pk=pk)
        config, _ = TodoReminderConfig.objects.get_or_create(
            organization=todo.organization, todo=todo, user=request.user
        )
        return Response(ReminderInput(config).data)

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        from .series import lock_task

        todo = lock_task(request.user, self.scope, pk)
        config, _ = TodoReminderConfig.objects.get_or_create(
            organization=todo.organization, todo=todo, user=request.user
        )
        serializer = ReminderInput(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(revision=config.revision + 1, customized=True)
        sync(todo)
        return Response(ReminderInput(config).data)


class CleanupSettingsView(TodoScopeMixin, APIView):
    def get(self, request, **kwargs):
        setting, _ = TodoCleanupSetting.objects.get_or_create(
            organization=self.org, department_id=self.scope.department_id
        )
        return Response({"purge_done": setting.purge_done})

    def patch(self, request, **kwargs):
        if not {"todos.edit", "roles.edit"} <= self.scope.permissions:
            raise PermissionDenied()
        serializer = CleanupInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        setting, _ = TodoCleanupSetting.objects.get_or_create(
            organization=self.org, department_id=self.scope.department_id
        )
        setting.purge_done = serializer.validated_data["purge_done"]
        setting.save(update_fields=["purge_done"])
        return Response({"purge_done": setting.purge_done})


class CleanupInput(serializers.Serializer):
    purge_done = serializers.BooleanField()
