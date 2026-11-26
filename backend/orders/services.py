"""Sammelbestellungen: Prüfen, Bestellen bis zur Frist, Summen, Rechnungen, Aufräumen."""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from core.tenancy import rls_bypass

from .models import (
    MAX_ARTICLES,
    MAX_QUANTITY,
    MAX_VARIANTS,
    MemberOrder,
    MemberOrderLine,
    OrderArticle,
    OrderCampaign,
)

ZERO = Decimal("0.00")
# So lange nach der Frist sehen Mitglieder eine Sammelbestellung ohne eigene Bestellung noch
MEMBER_AFTER = datetime.timedelta(days=30)
# So lange nach der Frist bleiben Sammelbestellungen samt Bestellungen, dann werden sie gelöscht
KEEP = datetime.timedelta(days=730)
# Zahlungsziel der Rechnungen
DUE_DAYS = 14

DRAFT, OPEN, CLOSED = "draft", "open", "closed"


def today() -> datetime.date:
    return timezone.localdate()


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "on", "yes", "ja"}


def state(campaign: OrderCampaign, on: datetime.date | None = None) -> str:
    if campaign.published_at is None:
        return DRAFT
    if campaign.closed_at is not None or campaign.deadline < (on or today()):
        return CLOSED
    return OPEN


def money(value) -> str | None:
    """Betrag für die Oberfläche als Text mit zwei Stellen (wie die Serializer)."""
    return None if value is None else f"{Decimal(value):.2f}"


def owner(campaign: OrderCampaign) -> str:
    return campaign.department.name if campaign.department_id else campaign.organization.name


# --- Eingaben prüfen ---


def _text(data, key: str, length: int, *, required: bool = False, label: str = "") -> str:
    value = str(data.get(key) or "").strip()
    if required and not value:
        raise ValidationError({key: label or _("Bitte ausfüllen.")})
    if len(value) > length:
        raise ValidationError({key: _("Höchstens {n} Zeichen.").format(n=length)})
    return value


def _price(raw, key: str = "price") -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw).replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError({key: _("Bitte einen Betrag eingeben.")}) from exc
    if value < 0 or value >= Decimal("100000000"):
        raise ValidationError({key: _("Bitte einen Betrag eingeben.")})
    return value


def _positive(raw, key: str) -> int | None:
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({key: _("Bitte eine ganze Zahl eingeben.")}) from exc
    if value < 1 or value > 100000:
        raise ValidationError({key: _("Bitte eine Zahl ab 1 eingeben.")})
    return value


def _variants(raw) -> list[str]:
    if isinstance(raw, str):
        raw = raw.split(",")
    out: list[str] = []
    for item in raw or []:
        value = str(item or "").strip()[:60]
        if value and value not in out:
            out.append(value)
    if len(out) > MAX_VARIANTS:
        raise ValidationError({"variants": _("Höchstens {n} Auswahlwerte.").format(n=MAX_VARIANTS)})
    return out


def clean_campaign(data, org, *, partial: bool = False) -> dict:
    """Titel, Beschreibung, Frist, Zielgruppe, „Verein zahlt“ und Kategorie prüfen."""
    out: dict = {}
    if not partial or "title" in data:
        out["title"] = _text(
            data, "title", 200, required=True, label=_("Bitte einen Titel eingeben.")
        )
    if not partial or "text" in data:
        out["text"] = _text(data, "text", 4000)
    if not partial or "deadline" in data:
        raw = data.get("deadline") or ""
        try:
            day = parse_date(str(raw)) if raw else None
        except ValueError:
            day = None
        if day is None:
            raise ValidationError({"deadline": _("Bitte ein gültiges Datum wählen.")})
        out["deadline"] = day
    if not partial or "club_pays" in data:
        out["club_pays"] = as_bool(data.get("club_pays"))
    if not partial or "push" in data:
        out["push"] = as_bool(data.get("push"))
    if not partial or "department" in data:
        raw = data.get("department") or None
        department = None
        if raw not in (None, "", "null"):
            from organizations.models import Department

            try:
                department = Department.objects.filter(pk=int(raw), organization=org).first()
            except (TypeError, ValueError):
                department = None
            if department is None:
                raise ValidationError({"department": _("Diese Untereinheit gibt es nicht.")})
        out["department"] = department
    if not partial or "payment_category" in data:
        raw = data.get("payment_category") or None
        category = None
        if raw not in (None, "", "null"):
            from finance.models import Category

            try:
                category = Category.objects.filter(pk=int(raw), organization=org).first()
            except (TypeError, ValueError):
                category = None
            if category is None:
                raise ValidationError({"payment_category": _("Diese Kategorie gibt es nicht.")})
        out["payment_category"] = category
    return out


def clean_article(row: dict, index: int) -> dict:
    if not isinstance(row, dict):
        raise ValidationError({"articles": _("Ungültiger Artikel.")})
    name = str(row.get("name") or "").strip()
    if not name:
        raise ValidationError(
            {"articles": _("Artikel {n}: Bitte einen Namen eingeben.").format(n=index + 1)}
        )
    return {
        "name": name[:100],
        "text": str(row.get("text") or "").strip()[:300],
        "price": _price(row.get("price")),
        "variants": _variants(row.get("variants")),
        "variant_label": str(row.get("variant_label") or "").strip()[:40],
        "max_per_member": _positive(row.get("max_per_member"), "max_per_member"),
        "max_total": _positive(row.get("max_total"), "max_total"),
        "position": index,
    }


def sync_articles(campaign: OrderCampaign, rows) -> None:
    """Artikel wie übergeben: vorhandene (mit ``id``) ändern, neue anlegen, fehlende löschen.

    Bestellte Artikel lassen sich nicht löschen, und ihre bestellten Varianten bleiben."""
    if not isinstance(rows, list):
        raise ValidationError({"articles": _("Ungültige Artikelliste.")})
    if len(rows) > MAX_ARTICLES:
        raise ValidationError({"articles": _("Höchstens {n} Artikel.").format(n=MAX_ARTICLES)})
    existing = {a.pk: a for a in campaign.articles.all()}
    keep: set[int] = set()
    for index, row in enumerate(rows):
        fields = clean_article(row, index)
        pk = row.get("id")
        if pk:
            try:
                article = existing[int(pk)]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValidationError({"articles": _("Ungültiger Artikel.")}) from exc
            used = set(
                article.lines.exclude(variant="").values_list("variant", flat=True).distinct()
            )
            missing = used - set(fields["variants"])
            if missing:
                raise ValidationError(
                    {
                        "articles": _(
                            "{name}: {values} ist schon bestellt und bleibt in der Auswahl."
                        ).format(name=fields["name"], values=", ".join(sorted(missing)))
                    }
                )
            if article.lines.filter(variant="").exists() and fields["variants"]:
                raise ValidationError(
                    {
                        "articles": _(
                            "{name} ist schon ohne Auswahl bestellt; bitte einen neuen Artikel "
                            "anlegen."
                        ).format(name=fields["name"])
                    }
                )
            for key, value in fields.items():
                setattr(article, key, value)
            article.save()
            keep.add(article.pk)
        else:
            article = OrderArticle.objects.create(
                organization=campaign.organization, campaign=campaign, **fields
            )
            keep.add(article.pk)
    for pk, article in existing.items():
        if pk in keep:
            continue
        if article.lines.exists():
            raise ValidationError(
                {
                    "articles": _("{name} ist schon bestellt und lässt sich nicht löschen.").format(
                        name=article.name
                    )
                }
            )
        article.delete()


# --- Wer bestellen darf ---


def audience(campaign: OrderCampaign):
    """Aktuelle Mitglieder des Vereins oder der Untereinheit (samt Einheiten darunter)."""
    from circulars.recipients import club_base

    return club_base(campaign.organization, campaign.department)


def member_department_ids(org, membership_id: int) -> list[int]:
    from pinboard.services import member_department_ids as ids

    return ids(org, membership_id)


def visible_for(org, membership_id: int):
    """Sammelbestellungen, die ein Mitglied sieht: veröffentlicht, für den Verein oder eine
    eigene Untereinheit (samt Einheiten darüber), offen, kürzlich beendet oder mit eigener
    Bestellung."""
    depts = member_department_ids(org, membership_id)
    own = MemberOrder.objects.filter(membership_id=membership_id).values("campaign_id")
    return (
        OrderCampaign.objects.filter(organization=org, published_at__isnull=False)
        .filter(Q(department__isnull=True) | Q(department_id__in=depts) | Q(pk__in=own))
        .filter(Q(deadline__gte=today() - MEMBER_AFTER) | Q(pk__in=own))
        .select_related("department", "organization")
    )


def may_order(campaign: OrderCampaign, membership_id: int) -> bool:
    return audience(campaign).filter(pk=membership_id).exists()


def open_count(org, membership_id: int) -> int:
    """Offene Sammelbestellungen ohne eigene Bestellung (Hinweis im Mitgliederbereich)."""
    rows = visible_for(org, membership_id).filter(closed_at__isnull=True, deadline__gte=today())
    return rows.exclude(orders__membership_id=membership_id).count()


# --- Bestellen ---


def INVOICED_TEXT() -> str:  # noqa: N802
    return _(
        "Für diese Bestellung gibt es schon eine Rechnung. Bitte zuerst die Rechnung stornieren."
    )


def invoiced(order: MemberOrder) -> bool:
    inv = order.invoice
    return inv is not None and inv.status != "cancelled"


def _lock(campaign: OrderCampaign) -> None:
    OrderCampaign.objects.select_for_update().filter(pk=campaign.pk).values_list("pk").first()


def clean_lines(campaign: OrderCampaign, rows) -> list[tuple[OrderArticle, str, int]]:
    if not isinstance(rows, list):
        raise ValidationError({"lines": _("Ungültige Bestellung.")})
    articles = {a.pk: a for a in campaign.articles.all()}
    merged: dict[tuple[int, str], int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError({"lines": _("Ungültige Bestellung.")})
        try:
            article = articles[int(row.get("article"))]
            quantity = int(row.get("quantity") or 0)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError({"lines": _("Diesen Artikel gibt es nicht.")}) from exc
        if quantity == 0:
            continue
        if quantity < 0 or quantity > MAX_QUANTITY:
            raise ValidationError(
                {"lines": _("Bitte eine Menge von 1 bis {n} angeben.").format(n=MAX_QUANTITY)}
            )
        variant = str(row.get("variant") or "").strip()
        if article.variants:
            if variant not in article.variants:
                raise ValidationError(
                    {
                        "lines": _("{name}: Bitte {label} wählen.").format(
                            name=article.name, label=article.variant_label or _("eine Auswahl")
                        )
                    }
                )
        else:
            variant = ""
        key = (article.pk, variant)
        merged[key] = merged.get(key, 0) + quantity
    out = []
    for (article_id, variant), quantity in merged.items():
        out.append((articles[article_id], variant, quantity))
    return out


def _check_limits(campaign, order_id, lines) -> None:
    per_article: dict[int, int] = {}
    for article, _variant, quantity in lines:
        per_article[article.pk] = per_article.get(article.pk, 0) + quantity
    for article_id, quantity in per_article.items():
        article = next(a for a, _v, _q in lines if a.pk == article_id)
        if article.max_per_member and quantity > article.max_per_member:
            raise ValidationError(
                {
                    "lines": _("{name}: höchstens {n} Stück je Mitglied.").format(
                        name=article.name, n=article.max_per_member
                    )
                }
            )
        if article.max_total:
            others = (
                MemberOrderLine.objects.filter(article=article)
                .exclude(order_id=order_id)
                .aggregate(s=Sum("quantity"))["s"]
                or 0
            )
            if others + quantity > article.max_total:
                left = max(article.max_total - others, 0)
                raise ValidationError(
                    {
                        "lines": _("{name}: nur noch {n} Stück verfügbar.").format(
                            name=article.name, n=left
                        )
                    }
                )


@transaction.atomic
def set_order(
    campaign: OrderCampaign,
    membership,
    rows,
    *,
    note: str | None = None,
    user=None,
    board: bool = False,
) -> MemberOrder | None:
    """Bestellung eines Mitglieds ersetzen. Leere Bestellung: zurückziehen (löschen).

    Mitglieder nur, solange die Sammelbestellung offen ist; die Verwaltung auch danach.
    Nach einer Rechnung oder Ausgabe ändert nur noch die Verwaltung (nach Storno)."""
    _lock(campaign)
    campaign.refresh_from_db()
    current = state(campaign)
    if current == DRAFT and not board:
        raise ValidationError(_("Diese Sammelbestellung ist noch nicht freigegeben."))
    if current == CLOSED and not board:
        raise ValidationError(_("Die Bestellfrist ist abgelaufen."))
    order = (
        MemberOrder.objects.select_for_update(of=("self",))
        .select_related("invoice")
        .filter(campaign=campaign, membership=membership)
        .first()
    )
    if order is not None and invoiced(order):
        raise ValidationError(INVOICED_TEXT())
    if order is not None and order.handed_out_at and not board:
        raise ValidationError(_("Diese Bestellung wurde schon ausgegeben."))
    lines = clean_lines(campaign, rows)
    if note is not None and len(note) > 500:
        raise ValidationError({"note": _("Höchstens {n} Zeichen.").format(n=500)})
    if not lines:
        if order is not None:
            order.delete()
        return None
    _check_limits(campaign, order.pk if order else None, lines)
    if order is None:
        order = MemberOrder.objects.create(
            organization=campaign.organization,
            campaign=campaign,
            membership=membership,
            note=(note or "").strip(),
            entered_by=user if board else None,
        )
    else:
        if note is not None:
            order.note = note.strip()
        if board:
            order.entered_by = user
        order.invoice = None
        order.save()
        order.lines.all().delete()
    MemberOrderLine.objects.bulk_create(
        MemberOrderLine(
            organization=campaign.organization,
            order=order,
            article=article,
            variant=variant,
            quantity=quantity,
        )
        for article, variant, quantity in lines
    )
    return order


# --- Beträge und Summen ---


def order_total(order: MemberOrder) -> Decimal | None:
    """Summe der Preise; ``None``, wenn kein bestellter Artikel einen Preis hat."""
    total, priced = ZERO, False
    for line in order.lines.all():
        if line.article.price is not None:
            priced = True
            total += line.article.price * line.quantity
    return total if priced else None


def sums(campaign: OrderCampaign) -> list[dict]:
    """Summen je Artikel und Auswahl in der Reihenfolge der Artikel und Auswahlwerte."""
    rows = (
        MemberOrderLine.objects.filter(order__campaign=campaign)
        .values("article_id", "variant")
        .annotate(quantity=Sum("quantity"))
    )
    by = {(r["article_id"], r["variant"]): r["quantity"] for r in rows}
    out = []
    for article in campaign.articles.all():
        values = article.variants or [""]
        extra = sorted({v for (a, v) in by if a == article.pk} - set(values))
        variants = []
        for variant in [*values, *extra]:
            quantity = by.get((article.pk, variant), 0)
            if quantity or variant in values:
                variants.append({"variant": variant, "quantity": quantity})
        total = sum(v["quantity"] for v in variants)
        out.append(
            {
                "article": article.pk,
                "name": article.name,
                "variant_label": article.variant_label,
                "variants": variants,
                "quantity": total,
                "amount": money(article.price * total) if article.price is not None else None,
            }
        )
    return out


# --- Daten für die Oberfläche ---


def article_data(article: OrderArticle, *, prices: bool = True, ordered: int | None = None) -> dict:
    data = {
        "id": article.pk,
        "name": article.name,
        "text": article.text,
        "price": money(article.price) if prices else None,
        "variants": list(article.variants or []),
        "variant_label": article.variant_label,
        "max_per_member": article.max_per_member,
        "max_total": article.max_total,
    }
    if ordered is not None and article.max_total:
        data["left"] = max(article.max_total - ordered, 0)
    return data


def ordered_counts(campaign: OrderCampaign) -> dict[int, int]:
    rows = (
        MemberOrderLine.objects.filter(order__campaign=campaign)
        .values("article_id")
        .annotate(s=Sum("quantity"))
    )
    return {r["article_id"]: r["s"] for r in rows}


def campaign_data(campaign: OrderCampaign, *, prices: bool = True) -> dict:
    counts = ordered_counts(campaign)
    return {
        "id": campaign.pk,
        "title": campaign.title,
        "text": campaign.text,
        "deadline": campaign.deadline,
        "state": state(campaign),
        "department": campaign.department_id,
        "unit": campaign.department.name if campaign.department_id else "",
        "from": owner(campaign),
        "club_pays": campaign.club_pays,
        "payment_category": campaign.payment_category_id,
        "push": campaign.push,
        "pushed": campaign.pushed_at is not None,
        "published_at": campaign.published_at,
        "closed_at": campaign.closed_at,
        "version": campaign.version,
        "articles": [
            article_data(a, prices=prices, ordered=counts.get(a.pk, 0))
            for a in campaign.articles.all()
        ],
    }


def line_data(line: MemberOrderLine, *, prices: bool = True) -> dict:
    price = line.article.price if prices else None
    return {
        "article": line.article_id,
        "name": line.article.name,
        "variant": line.variant,
        "quantity": line.quantity,
        "price": money(price),
        "amount": money(price * line.quantity) if price is not None else None,
    }


def order_data(order: MemberOrder, *, prices: bool = True, admin: bool = False) -> dict:
    lines = list(order.lines.select_related("article").all())
    total = order_total(order) if prices else None
    inv = order.invoice
    data = {
        "id": order.pk,
        "lines": [line_data(line, prices=prices) for line in lines],
        "note": order.note,
        "total": money(total),
        "handed_out": order.handed_out_at is not None,
        "handed_out_at": order.handed_out_at,
        "updated_at": order.updated_at,
        "invoice": (
            {
                "id": inv.pk,
                "number": inv.display_number,
                "status": inv.status,
                "total": money(inv.total),
                "outstanding": money(inv.outstanding),
            }
            if inv is not None and inv.status != "cancelled"
            else None
        ),
    }
    if admin:
        person = order.membership.person
        data.update(
            {
                "membership": order.membership_id,
                "name": person.display_name,
                "sort_name": f"{person.last_name} {person.first_name}".strip().lower(),
                "number": order.membership.club_number,
                "entered_by_board": order.entered_by_id is not None,
            }
        )
    return data


# --- Rechnungen ---


def payment_category(campaign: OrderCampaign):
    from billing.services import settings_for

    return campaign.payment_category or settings_for(campaign.organization).category


def create_invoice(order: MemberOrder, user=None):
    """Rechnung über die Artikel mit Preis, gleich festgeschrieben. Mitglieder mit gültigem
    Lastschriftmandat erscheinen damit im nächsten Lastschriftlauf, sonst wird überwiesen."""
    from billing import services as billing
    from billing.models import Invoice, InvoiceLine

    campaign = order.campaign
    org = order.organization
    on = today()
    cat = payment_category(campaign)
    vat_percent = None
    if org.vat_enabled and cat is not None and cat.vat_rate:
        from finance.models import VatRate

        if cat.vat_rate == VatRate.STANDARD:
            vat_percent = Decimal("19.00")
        elif cat.vat_rate == VatRate.REDUCED:
            vat_percent = Decimal("7.00")
    invoice = Invoice.objects.create(
        organization=org,
        recipient_kind=Invoice.Recipient.MEMBER,
        membership=order.membership,
        payment_category=cat,
        date=on,
        due_date=on + datetime.timedelta(days=DUE_DAYS),
        subject=_("Bestellung {title}").format(title=campaign.title)[:200],
        note=_("Bitte bei der Überweisung die Rechnungsnummer angeben."),
        created_by=user,
        **billing.member_recipient(org, order.membership),
    )
    position = 0
    for line in order.lines.select_related("article").all():
        price = line.article.price
        if not price:
            continue
        position += 1
        InvoiceLine.objects.create(
            organization=org,
            invoice=invoice,
            position=position,
            text=f"{line.quantity} × {campaign.title}: {line.article.name}"[:200],
            detail=(
                f"{line.article.variant_label or _('Auswahl')}: {line.variant}"
                if line.variant
                else ""
            )[:200],
            amount=price * line.quantity,
            vat_rate=vat_percent,
        )
    billing.finalize(invoice)
    order.invoice = invoice
    order.save(update_fields=["invoice", "updated_at"])
    return invoice


def invoice_orders(campaign: OrderCampaign, order_ids, user=None) -> list[MemberOrder]:
    """Rechnungen für die gewählten Bestellungen (``None``: alle ohne Rechnung) anlegen."""
    if campaign.club_pays:
        raise ValidationError(_("Bei dieser Sammelbestellung zahlt der Verein; keine Rechnungen."))
    qs = (
        MemberOrder.objects.filter(campaign=campaign)
        .select_related("invoice", "membership__person", "campaign", "organization")
        .prefetch_related("lines__article")
    )
    if order_ids is not None:
        qs = qs.filter(pk__in=order_ids)
    done = []
    for order in qs.select_for_update(of=("self",)):
        if invoiced(order):
            continue
        total = order_total(order)
        if not total:
            continue
        create_invoice(order, user)
        done.append(order)
    return done


# --- Aufräumen ---


def forget_membership(membership) -> None:
    MemberOrder.objects.filter(membership=membership).delete()


def purge_due(now: datetime.datetime | None = None) -> int:
    """Sammelbestellungen zwei Jahre nach der Frist löschen (Rechnungen bleiben in den Finanzen)."""
    day = timezone.localdate(now or timezone.now())
    n = 0
    with rls_bypass():
        for campaign in OrderCampaign.objects.filter(deadline__lt=day - KEEP).iterator():
            campaign.delete()
            n += 1
    return n
