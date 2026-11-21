"""Sammelbestellungen in der Verwaltung des Vereins (/api/orgs/<Verein>/orders/…)."""

from __future__ import annotations

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.log import diff, record, snapshot

from . import access, services
from .models import MemberOrder, OrderCampaign


def conflict():
    exc = APIException(_("Die Sammelbestellung wurde inzwischen geändert. Bitte neu laden."))
    exc.status_code = 409
    return exc


class Base(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.scope = access.scope_for(request.user, kwargs.get("org_id"))
        self.org = self.scope.org

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response.setdefault("Cache-Control", "private, no-store")
        return response

    def campaigns(self):
        return OrderCampaign.objects.filter(organization=self.org).select_related(
            "department", "organization"
        )

    def campaign(self, pk, *, lock=False):
        qs = self.campaigns()
        if lock:
            qs = qs.select_for_update(of=("self",))
        return get_object_or_404(qs, pk=pk)

    def detail(self, campaign: OrderCampaign) -> dict:
        orders = (
            MemberOrder.objects.filter(campaign=campaign)
            .select_related("membership__person", "invoice")
            .prefetch_related("lines__article")
        )
        rows = sorted(
            (services.order_data(o, admin=True) for o in orders), key=lambda r: r["sort_name"]
        )
        for row in rows:
            row.pop("sort_name", None)
        data = services.campaign_data(campaign)
        data.update(
            {
                "orders": rows,
                "sums": services.sums(campaign),
                "audience": services.audience(campaign).count(),
                "can_edit": self.scope.can_edit,
                "can_invoice": self.scope.can_invoice and not campaign.club_pays,
            }
        )
        return data


class ListView(Base):
    def get(self, request, **kwargs):
        from django.db.models import Count

        rows = self.campaigns().annotate(n=Count("orders"))
        out = []
        for c in rows:
            out.append(
                {
                    "id": c.pk,
                    "title": c.title,
                    "deadline": c.deadline,
                    "state": services.state(c),
                    "unit": c.department.name if c.department_id else "",
                    "club_pays": c.club_pays,
                    "orders": c.n,
                }
            )
        return Response(
            {
                "campaigns": out,
                "can_edit": self.scope.can_edit,
                "can_invoice": self.scope.can_invoice,
                "departments": self.departments(),
                "categories": self.categories(),
            }
        )

    def departments(self) -> list[dict]:
        from organizations.models import Department

        rows = Department.objects.filter(organization=self.org, is_active=True).order_by("name")
        return [{"id": d.pk, "name": d.name} for d in rows]

    def categories(self) -> list[dict]:
        """Kategorien für die Rechnungen (nur mit Recht für Rechnungen)."""
        if not self.scope.can_invoice:
            return []
        from finance.models import Category

        rows = Category.objects.filter(organization=self.org, is_active=True).exclude(
            kind=Category.Kind.EXPENSE
        )
        return [{"id": c.pk, "name": c.name} for c in rows.order_by("name")]

    @transaction.atomic
    def post(self, request, **kwargs):
        access.require_edit(self.scope)
        fields = services.clean_campaign(request.data, self.org)
        if fields["deadline"] < services.today():
            raise ValidationError({"deadline": _("Das Datum liegt in der Vergangenheit.")})
        campaign = OrderCampaign.objects.create(
            organization=self.org, created_by=request.user, **fields
        )
        services.sync_articles(campaign, request.data.get("articles") or [])
        record(self.org, request.user, "create", campaign, diff({}, snapshot(campaign)))
        return Response(self.detail(campaign), status=201)


class DetailView(Base):
    def get(self, request, pk, **kwargs):
        return Response(self.detail(self.campaign(pk)))

    @transaction.atomic
    def patch(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        campaign = self.campaign(pk, lock=True)
        version = request.data.get("version")
        if version is not None and str(version) != str(campaign.version):
            raise conflict()
        before = snapshot(campaign)
        fields = services.clean_campaign(request.data, self.org, partial=True)
        if (
            "department" in fields
            and fields["department"] != campaign.department
            and campaign.orders.exists()
        ):
            raise ValidationError(
                {"department": _("Es gibt schon Bestellungen; die Zielgruppe bleibt.")}
            )
        for key, value in fields.items():
            setattr(campaign, key, value)
        campaign.version += 1
        campaign.save()
        if "articles" in request.data:
            services.sync_articles(campaign, request.data.get("articles"))
        changes = diff(before, snapshot(campaign))
        if changes:
            record(self.org, request.user, "update", campaign, changes)
        return Response(self.detail(campaign))

    @transaction.atomic
    def delete(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        campaign = self.campaign(pk, lock=True)
        record(self.org, request.user, "delete", campaign, diff(snapshot(campaign), {}))
        campaign.delete()
        return Response(status=204)


class PublishView(Base):
    """Freigeben (Mitglieder sehen und bestellen), vorzeitig beenden oder wieder öffnen."""

    @transaction.atomic
    def post(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        campaign = self.campaign(pk, lock=True)
        action = str(request.data.get("action") or "publish")
        before = snapshot(campaign)
        now = timezone.now()
        if action == "publish":
            if not campaign.articles.exists():
                raise ValidationError(_("Bitte zuerst mindestens einen Artikel anlegen."))
            if campaign.deadline < services.today():
                raise ValidationError({"deadline": _("Das Datum liegt in der Vergangenheit.")})
            if campaign.published_at is None:
                campaign.published_at = now
            campaign.closed_at = None
        elif action == "close":
            if campaign.published_at is None:
                raise ValidationError(_("Diese Sammelbestellung ist noch nicht freigegeben."))
            campaign.closed_at = campaign.closed_at or now
        elif action == "reopen":
            if campaign.deadline < services.today():
                raise ValidationError(
                    {"deadline": _("Bitte zuerst die Frist in die Zukunft legen.")}
                )
            campaign.closed_at = None
        else:
            raise ValidationError({"action": "?"})
        campaign.version += 1
        campaign.save()
        record(self.org, request.user, "update", campaign, diff(before, snapshot(campaign)))
        if action == "publish" and campaign.push and campaign.pushed_at is None:
            from .tasks import notify

            pk_ = campaign.pk
            transaction.on_commit(lambda: notify.delay(pk_))
        return Response(self.detail(campaign))


class MembersView(Base):
    """Mitglieder der Zielgruppe suchen (Bestellung für ein Mitglied eintragen)."""

    def get(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        campaign = self.campaign(pk)
        term = str(request.query_params.get("q") or "").strip().lower()
        if len(term) < 2:
            return Response({"members": []})
        rows = []
        for m in services.audience(campaign).select_related("person"):
            name = m.person.display_name
            if term in name.lower() or (m.club_number and term == m.club_number.lower()):
                rows.append(
                    {
                        "id": m.pk,
                        "first_name": m.person.first_name,
                        "last_name": m.person.last_name,
                        "name": name,
                        "number": m.club_number,
                    }
                )
            if len(rows) >= 20:
                break
        return Response({"members": rows})


class OrdersView(Base):
    """Bestellung für ein Mitglied eintragen oder ersetzen (auch nach der Frist)."""

    @transaction.atomic
    def put(self, request, pk, **kwargs):
        access.require_edit(self.scope)
        campaign = self.campaign(pk)
        try:
            membership_id = int(request.data.get("membership"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"membership": _("Bitte ein Mitglied wählen.")}) from exc
        membership = services.audience(campaign).filter(pk=membership_id).first()
        existing = MemberOrder.objects.filter(campaign=campaign, membership_id=membership_id)
        if membership is None:
            # Ausgetreten: vorhandene Bestellung darf die Verwaltung noch ändern
            first = existing.select_related("membership").first()
            if first is None:
                raise ValidationError({"membership": _("Dieses Mitglied gehört nicht dazu.")})
            membership = first.membership
        note = request.data.get("note")
        order = services.set_order(
            campaign,
            membership,
            request.data.get("lines") or [],
            note=str(note) if note is not None else None,
            user=request.user,
            board=True,
        )
        record(
            self.org,
            request.user,
            "update",
            campaign,
            {"order": [None, membership.pk]},
        )
        campaign.refresh_from_db()
        data = self.detail(campaign)
        data["order"] = order.pk if order else None
        return Response(data)


class OrderView(Base):
    @transaction.atomic
    def patch(self, request, pk, order_id, **kwargs):
        """Ausgabe abhaken oder zurücknehmen."""
        access.require_edit(self.scope)
        campaign = self.campaign(pk)
        order = get_object_or_404(
            MemberOrder.objects.select_for_update(of=("self",)), pk=order_id, campaign=campaign
        )
        if "handed_out" in request.data:
            done = services.as_bool(request.data.get("handed_out"))
            order.handed_out_at = (order.handed_out_at or timezone.now()) if done else None
            order.save(update_fields=["handed_out_at", "updated_at"])
        return Response(self.detail(campaign))

    @transaction.atomic
    def delete(self, request, pk, order_id, **kwargs):
        access.require_edit(self.scope)
        campaign = self.campaign(pk)
        order = get_object_or_404(
            MemberOrder.objects.select_related("invoice"), pk=order_id, campaign=campaign
        )
        if services.invoiced(order):
            raise ValidationError(services.INVOICED_TEXT())
        record(self.org, request.user, "update", campaign, {"order": [order.membership_id, None]})
        order.delete()
        return Response(self.detail(campaign))


class InvoicesView(Base):
    @transaction.atomic
    def post(self, request, pk, **kwargs):
        if not self.scope.can_invoice:
            raise PermissionDenied()
        campaign = self.campaign(pk, lock=True)
        raw = request.data.get("orders")
        ids = None
        if raw is not None:
            if not isinstance(raw, list):
                raise ValidationError({"orders": "?"})
            try:
                ids = [int(x) for x in raw]
            except (TypeError, ValueError) as exc:
                raise ValidationError({"orders": "?"}) from exc
        done = services.invoice_orders(campaign, ids, request.user)
        data = self.detail(campaign)
        data["created"] = len(done)
        return Response(data)


class ExportView(Base):
    def get(self, request, pk, **kwargs):
        from .export import xlsx

        campaign = self.campaign(pk)
        content = xlsx(campaign)
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="bestellung-{campaign.pk}.xlsx"'
        return response
