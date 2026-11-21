"""Sammelbestellungen im Mitgliederbereich und in der App (/api/portal/<Zugang>/orders/…).

Mitglieder sehen die freigegebenen Sammelbestellungen ihres Vereins und ihrer Untereinheiten,
bestellen bis zur Frist und ändern oder ziehen die Bestellung bis dahin zurück. Zahlt der Verein,
sehen sie keine Preise.
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import scope_of, set_rls, user_view

from . import access as order_access
from . import services
from .models import MemberOrder


def portal_access(user, access_id):
    from portal.views import _portal_access

    with user_view(user.pk):
        access = _portal_access(user, access_id)
    set_rls(access.organization_id, user.pk, scope_id=scope_of(access.organization_id))
    if order_access.MODULE not in (access.organization.enabled_modules or []):
        raise NotFound()
    if not access.membership_id or not access.membership.current_period():
        raise NotFound()
    return access


def member_data(campaign, membership_id: int, *, full: bool = False) -> dict:
    prices = not campaign.club_pays
    order = (
        MemberOrder.objects.filter(campaign=campaign, membership_id=membership_id)
        .select_related("invoice")
        .prefetch_related("lines__article")
        .first()
    )
    current = services.state(campaign)
    data = {
        "id": campaign.pk,
        "title": campaign.title,
        "deadline": campaign.deadline,
        "state": current,
        "from": services.owner(campaign),
        "club_pays": campaign.club_pays,
        "ordered": order is not None,
        "can_order": False,
        "order": None,
    }
    if order is not None:
        data["order"] = services.order_data(order, prices=prices)
    if full:
        base = services.campaign_data(campaign, prices=prices)
        data.update(
            {
                "text": campaign.text,
                "articles": base["articles"],
            }
        )
        editable = order is None or (not services.invoiced(order) and not order.handed_out_at)
        data["can_order"] = (
            current == services.OPEN and editable and services.may_order(campaign, membership_id)
        )
    return data


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.access = portal_access(request.user, kwargs["access_id"])
        self.org = self.access.organization

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.setdefault("Cache-Control", "private, no-store")
        return response

    def visible(self):
        return services.visible_for(self.org, self.access.membership_id)

    def campaign(self, pk):
        return get_object_or_404(self.visible(), pk=pk)


class ListView(Base):
    def get(self, request, **kwargs):
        rows = self.visible().order_by("deadline", "pk")
        open_rows = [c for c in rows if services.state(c) == services.OPEN]
        closed = [c for c in rows if services.state(c) != services.OPEN]
        closed.sort(key=lambda c: (c.deadline, c.pk), reverse=True)
        mid = self.access.membership_id
        return Response({"campaigns": [member_data(c, mid) for c in [*open_rows, *closed]]})


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        campaign = self.campaign(pk)
        return Response(member_data(campaign, self.access.membership_id, full=True))


class OrderView(Base):
    """Eigene Bestellung setzen (``lines``: Artikel, Auswahl, Menge; leer = zurückziehen)."""

    @transaction.atomic
    def put(self, request, pk, **kwargs):
        campaign = self.campaign(pk)
        if not services.may_order(campaign, self.access.membership_id):
            raise PermissionDenied()
        note = request.data.get("note")
        services.set_order(
            campaign,
            self.access.membership,
            request.data.get("lines") or [],
            note=str(note) if note is not None else None,
            user=request.user,
        )
        return Response(member_data(campaign, self.access.membership_id, full=True))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        campaign = self.campaign(pk)
        services.set_order(campaign, self.access.membership, [], user=request.user)
        return Response(member_data(campaign, self.access.membership_id, full=True))
