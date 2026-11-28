"""Webseite › Aktuelles: eigene Beiträge verwalten (#707).

Recht wie bei den Texten: „Inhalte der Webseite bearbeiten“ oder „Webseite verwalten“.
Änderungen gehen in den Entwurf; „Veröffentlichen“ macht sie auf der Webseite sichtbar."""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot
from core.versioning import lock_and_check

from . import news, services
from .content_views import _ContentMixin
from .news_models import NewsPost


def _invalid(exc: news.Invalid) -> ValidationError:
    return ValidationError({exc.field: [exc.message]})


class NewsListView(_ContentMixin, APIView):
    """GET: alle eigenen Beiträge, neueste zuerst · POST: neuer Beitrag (Entwurf)."""

    def get(self, request, org_id: int):
        website = self.website()
        posts = NewsPost.objects.filter(website=website).select_related("department")
        units = [
            {"id": u.pk, "name": u.name}
            for u in services.units_below(website.organization).order_by("name")
        ]
        return Response({"posts": [news.admin_data(p) for p in posts], "units": units})

    @transaction.atomic
    def post(self, request, org_id: int):
        website = self.website()
        try:
            post = news.create(website, request.data, request.user)
        except news.Invalid as exc:
            raise _invalid(exc) from exc
        record(self.org, request.user, "create", post, {"Beitrag": [None, str(post)]})
        return Response(news.admin_data(post), status=status.HTTP_201_CREATED)


# Gleichzeitiges Bearbeiten (core/versioning.py)
NEWS_STALE = gettext_lazy("Der Beitrag wurde inzwischen geändert. Bitte neu laden.")


class _NewsMixin(_ContentMixin):
    def news_post(self) -> NewsPost:
        return get_object_or_404(
            NewsPost.objects.select_related("department", "website"),
            website=self.website(),
            pk=self.kwargs["pk"],
        )


class NewsDetailView(_NewsMixin, APIView):
    """GET/PUT: Entwurf · DELETE: Beitrag löschen."""

    def get(self, request, org_id: int, pk: int):
        return Response(news.admin_data(self.news_post()))

    @transaction.atomic
    def put(self, request, org_id: int, pk: int):
        post = self.news_post()
        lock_and_check(request, post, NEWS_STALE)
        before = snapshot(post)
        try:
            changed = news.apply(post, request.data)
        except news.Invalid as exc:
            raise _invalid(exc) from exc
        if changed:
            post.updated_by = request.user
            post.save()
            changes = diff(before, snapshot(post))
            changes.pop("updated_by", None)
            if changes:
                record(self.org, request.user, "update", post, changes)
        return Response(news.admin_data(post))

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        post = self.news_post()
        lock_and_check(request, post, NEWS_STALE)
        record(self.org, request.user, "delete", post, {"Beitrag": [str(post), None]})
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NewsPublishView(_NewsMixin, APIView):
    """POST: Entwurf veröffentlichen · DELETE: Veröffentlichung zurücknehmen."""

    @transaction.atomic
    def post(self, request, org_id: int, pk: int):
        post = self.news_post()
        lock_and_check(request, post, NEWS_STALE)
        post.publish(request.user)
        record(self.org, request.user, "update", post, {"veröffentlicht": [None, str(post)]})
        return Response(news.admin_data(post))

    @transaction.atomic
    def delete(self, request, org_id: int, pk: int):
        post = self.news_post()
        lock_and_check(request, post, NEWS_STALE)
        if post.is_published:
            post.unpublish(request.user)
            record(self.org, request.user, "update", post, {"veröffentlicht": [str(post), None]})
        return Response(news.admin_data(post))
