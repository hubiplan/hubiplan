"""Einheiten in zwei Stufen löschen (Gesamtaudit 10.11., F02).

1. **Stilllegen und Löschung vormerken** (Plattform): Die Einheit und alle Untereinheiten
   darunter werden stillgelegt, niemand kommt mehr hinein, die Daten bleiben. Solange die
   Vormerkung gilt, lässt sich die Einheit nicht wieder einschalten; die Plattform kann die
   Vormerkung zurücknehmen.
2. **Endgültig löschen** (Plattform, zweite Bestätigung): frühestens ``WAIT_DAYS`` Tage nach
   der Vormerkung und erst nach Ablauf der Aufbewahrungsfristen aller Geschäftsjahre
   (§ 147 AO, ``finance.retention``; Löschsperren verlängern), mit Namen, Passwort und ggf.
   Code sowie der Angabe, wer die Fristen bestätigt hat. Untereinheiten werden mit gelöscht.

Jede endgültige Löschung steht zusätzlich auf der Löschliste (``members.loeschliste``);
spielt jemand ein älteres Backup ein, wird die Einheit erneut gelöscht.
"""

import datetime
import logging

from django.apps import apps
from django.db import models, transaction
from django.db.models import Max, Min
from django.db.models.deletion import Collector
from django.utils import timezone
from django.utils.translation import gettext
from rest_framework import serializers

from core.files import delete_on_commit
from core.tenancy import rls_bypass
from finance import gobd

from .models import Organization

logger = logging.getLogger(__name__)

# Mindestabstand zwischen Vormerkung und endgültigem Löschen (Versehen fällt auf)
WAIT_DAYS = 30


class ErasureCollector(Collector):
    """Allow protected references only between rows being explicitly erased."""

    def __init__(self, roots):
        super().__init__(using="default")
        self.roots = roots

    def can_fast_delete(self, objs, from_field=None):
        # Visit file fields and deletion signals on every row.
        return False

    def related_objects(self, related_model, related_fields, objs):
        related = super().related_objects(related_model, related_fields, objs)
        if any(field.remote_field.on_delete is models.PROTECT for field in related_fields):
            owned = self.roots.get(related_model)
            if owned is not None:
                # These rows are collected separately. Other tenants' protected
                # references still abort the entire transaction.
                related = related.exclude(pk__in=owned.values("pk"))
        return related


def _today() -> datetime.date:
    return timezone.localdate()


def subtree(org) -> list[Organization]:
    """``org`` und alle Untereinheiten darunter, Eltern vor Kindern."""
    from .tree import UnitTree

    if org.type == Organization.Type.UNIT:
        ids = UnitTree.of(org.organization_id).subtree(org.pk)[1:]
    else:
        ids = UnitTree.of(org.pk).ordered()
    units = Organization.objects.in_bulk(ids)
    return [org, *(units[pk] for pk in ids if pk in units)]


def _finance_dates(org) -> tuple[datetime.date | None, datetime.date | None]:
    """Frühester und spätester Tag mit Finanzdaten der Einheit (eigener Datenbereich)."""
    from billing.models import DebitRun, Dunning, IncomingInvoice, Invoice
    from finance import bank_originals
    from finance.models import (
        Booking,
        CashCount,
        CashReceipt,
        Donation,
        DonationStatement,
        ReserveMovement,
    )
    from music.models import EngagementDocument, PayoutRun, PerformanceAccount

    sources = [
        (Booking, "date"),
        (Invoice, "date"),
        (Dunning, "date"),
        (DebitRun, "collection_date"),
        (IncomingInvoice, "created_at__date"),
        (CashCount, "date"),
        (CashReceipt, "receipt_date"),
        (Donation, "date"),
        (DonationStatement, "issued_on"),
        (ReserveMovement, "date"),
        (EngagementDocument, "created_at__date"),
        (PayoutRun, "execution_date"),
        (PerformanceAccount, "date"),
    ]
    days: list[datetime.date] = []
    for model, field in sources:
        found = model._base_manager.filter(organization=org).aggregate(
            first=Min(field), last=Max(field)
        )
        days.extend(d for d in found.values() if d)
    statements = (
        bank_originals.queryset(org)
        .exclude(source="")
        .aggregate(first=Min("original_first_day"), last=Max("original_last_day"))
    )
    days.extend(d for d in statements.values() if d)
    days = [d.date() if isinstance(d, datetime.datetime) else d for d in days]
    if not days:
        return None, None
    return min(days), max(days)


def retention(org) -> dict:
    """Bis wann Bücher und Belege der Einheit und ihrer Untereinheiten aufzubewahren sind.

    ``until`` ist der erste Tag, an dem alle Fristen abgelaufen sind (``None``: keine
    Finanzdaten). ``holds`` nennt Geschäftsjahre mit Löschsperre."""
    from finance.models import YearClosing
    from finance.retention import due_dates

    until: datetime.date | None = None
    holds: list[dict] = []
    with rls_bypass():
        for unit in subtree(org):
            first, last = _finance_dates(unit)
            years = set(
                YearClosing.objects.filter(organization=unit).values_list("year", flat=True)
            )
            if first and last:
                years |= set(range(unit.fiscal_year_of(first), unit.fiscal_year_of(last) + 1))
            for year in sorted(years):
                documents_from, records_from = due_dates(unit, year)
                end = max(documents_from, records_from)
                until = end if until is None else max(until, end)
            for closing in YearClosing.objects.filter(organization=unit).exclude(retention_hold=""):
                holds.append({"unit": unit.name, "year": unit.fiscal_label(closing.year)})
    return {"until": until, "holds": holds}


def erase_state(org) -> dict:
    """Stand für die Plattform: vorgemerkt seit, frühestens löschbar ab, was noch fehlt."""
    kept = retention(org)
    requested = org.erase_requested_at
    wait_until = (
        timezone.localdate(requested) + datetime.timedelta(days=WAIT_DAYS) if requested else None
    )
    today = _today()
    possible_from = max(d for d in (wait_until, kept["until"]) if d) if wait_until else None
    blockers: list[str] = []
    if org.type == Organization.Type.PLATFORM or org.is_remote:
        blockers.append(gettext("Diese Einheit kann nicht gelöscht werden."))
    elif Organization.objects.filter(parent=org).exclude(type=Organization.Type.UNIT).exists():
        blockers.append(gettext("Bitte zuerst alle zugehörigen Vereine löschen oder umhängen."))
    if requested is None:
        blockers.append(gettext("Die Löschung ist noch nicht vorgemerkt."))
    elif wait_until and today < wait_until:
        blockers.append(gettext("Frühestens {n} Tage nach der Vormerkung.").format(n=WAIT_DAYS))
    if kept["until"] and today < kept["until"]:
        blockers.append(gettext("Die Aufbewahrungsfristen laufen noch."))
    if kept["holds"]:
        blockers.append(gettext("Für einzelne Geschäftsjahre gilt eine Löschsperre."))
    return {
        "requested_at": requested,
        "requested_by": (
            org.erase_requested_by.get_full_name() or org.erase_requested_by.email
            if org.erase_requested_by
            else ""
        ),
        "wait_days": WAIT_DAYS,
        "wait_until": wait_until,
        "retention_until": kept["until"],
        "holds": kept["holds"],
        "has_finance": kept["until"] is not None,
        "possible_from": possible_from,
        "blockers": blockers,
        "can_erase": not blockers,
    }


@transaction.atomic
def request_erase(org, actor) -> None:
    """Stufe 1: Einheit und Untereinheiten stilllegen, Löschung vormerken."""
    from audit.log import record

    with rls_bypass():
        org = Organization.objects.select_for_update().get(pk=org.pk)
        if org.type == Organization.Type.PLATFORM or org.is_remote:
            raise serializers.ValidationError(gettext("Diese Einheit kann nicht gelöscht werden."))
        if org.erase_requested_at:
            return
        now = timezone.now()
        was_active = org.is_active
        org.erase_requested_at = now
        org.erase_requested_by = actor
        org.is_active = False
        # save() legt Untereinheiten mit still (activity.cascade_active)
        org.save(update_fields=["erase_requested_at", "erase_requested_by", "is_active"])
        ids = [unit.pk for unit in subtree(org)[1:]]
        Organization.objects.filter(pk__in=ids, is_active=True).update(
            is_active=False, inactive_by_parent=True
        )
        Organization.objects.filter(pk__in=ids, erase_requested_at__isnull=True).update(
            erase_requested_at=now, erase_requested_by=actor
        )
    changes = {"Löschung vorgemerkt": [None, timezone.localtime(now).strftime("%d.%m.%Y")]}
    if was_active:
        changes["aktiv"] = [True, False]
    record(Organization.platform(), actor, "update", org, changes)
    record(org, actor, "update", org, changes)


@transaction.atomic
def withdraw_erase(org, actor) -> None:
    """Vormerkung zurücknehmen; die Einheit bleibt stillgelegt, bis sie jemand einschaltet."""
    from audit.log import record

    with rls_bypass():
        org = Organization.objects.select_for_update().get(pk=org.pk)
        if org.erase_requested_at is None:
            return
        ids = [unit.pk for unit in subtree(org)]
        Organization.objects.filter(pk__in=ids, erase_requested_at=org.erase_requested_at).update(
            erase_requested_at=None, erase_requested_by=None
        )
    changes = {
        "Löschung vorgemerkt": [
            timezone.localtime(org.erase_requested_at).strftime("%d.%m.%Y"),
            None,
        ]
    }
    record(Organization.platform(), actor, "update", org, changes)
    record(org, actor, "update", org, changes)


def _erase_one(org) -> None:
    """Eine Einheit ohne Einheiten darunter mit allen ihren Daten löschen."""
    if Organization.objects.filter(parent=org).exists():
        raise serializers.ValidationError(
            gettext("Bitte zuerst alle untergeordneten Einheiten löschen oder umhängen.")
        )
    roots = {Organization: Organization.objects.filter(pk=org.pk)}
    owners = {}
    for model in apps.get_models():
        if model is Organization or model._meta.proxy or not model._meta.managed:
            continue
        fields = {
            field.name: field for field in model._meta.fields if field.related_model is Organization
        }
        if "organization" in fields:
            owned = models.Q(organization=org)
            if "scope" in fields and fields["organization"].null:
                owned |= models.Q(organization__isnull=True, scope=org)
        elif "scope" in fields:
            owned = models.Q(scope=org)
        else:
            continue
        roots[model] = model._base_manager.filter(owned)
        owners[model] = set(roots[model].values_list("pk", flat=True))
    collector = ErasureCollector(roots)
    try:
        for rows in roots.values():
            collector.collect(rows, fail_on_restricted=False)
        for model, instances in collector.data.items():
            if model in owners and any(instance.pk not in owners[model] for instance in instances):
                raise serializers.ValidationError(
                    gettext("Andere Einheiten verweisen auf diese Daten. Löschen nicht möglich.")
                )
        # RESTRICT checks are deferred until every owned row is collected.
        for model, instances in collector.data.items():
            collector.clear_restricted_objects_from_set(model, instances)
        for qs in collector.fast_deletes:
            collector.clear_restricted_objects_from_queryset(qs.model, qs)
        if any(
            objs for fields in collector.restricted_objects.values() for objs in fields.values()
        ):
            raise serializers.ValidationError(
                gettext("Andere Einheiten verweisen auf diese Daten. Löschen nicht möglich.")
            )
        for model, instances in collector.data.items():
            fields = [f for f in model._meta.fields if isinstance(f, models.FileField)]
            for instance in instances:
                delete_on_commit(*(getattr(instance, f.name) for f in fields))
        gobd.release_unit(org.pk)
        collector.delete()
    except (models.ProtectedError, models.RestrictedError) as exc:
        raise serializers.ValidationError(
            gettext("Andere Einheiten verweisen auf diese Daten. Löschen nicht möglich.")
        ) from exc


@transaction.atomic
def erase_organization(org, actor, *, confirmed_by: str = "", listed: bool = False) -> None:
    """Stufe 2: Einheit mit allen Untereinheiten und Daten endgültig löschen.

    ``listed``: erneutes Löschen nach dem Einspielen eines älteren Backups (Löschliste);
    dann gelten Vormerkung und Fristen schon als geprüft."""
    from audit.log import record
    from members import loeschliste

    with rls_bypass():
        org = Organization.objects.select_for_update().get(pk=org.pk)
        if org.type == Organization.Type.PLATFORM or org.is_remote:
            raise serializers.ValidationError(gettext("Diese Einheit kann nicht gelöscht werden."))
        if not listed:
            state = erase_state(org)
            if not state["can_erase"]:
                raise serializers.ValidationError(" ".join(state["blockers"]))
        units = subtree(org)
        erased = []
        for unit in reversed(units):  # Kinder vor Eltern
            erased.append((unit.pk, unit.name, unit.created_at))
            _erase_one(unit)
    for pk, _name, created in erased:
        loeschliste.note_unit(pk, created)
    org.pk = erased[-1][0]
    changes = {"Einheit": [f"{erased[-1][1]} ({erased[-1][0]})", None]}
    if len(erased) > 1:
        changes["Untereinheiten"] = [", ".join(f"{n} ({pk})" for pk, n, _c in erased[:-1]), None]
    if confirmed_by:
        changes["Fristen bestätigt von"] = [None, confirmed_by]
    if listed:
        changes["Löschliste"] = [None, "erneut gelöscht"]
    record(Organization.platform(), actor, "delete", org, changes)


def reapply(entries: list[dict]) -> int:
    """Löschliste: nach einem eingespielten Backup wieder vorhandene Einheiten erneut löschen."""
    from django.utils.dateparse import parse_datetime

    count = 0
    # Neueste zuerst wäre falsch: Untereinheiten stehen vor ihrer Einheit in der Liste
    for item in entries:
        created = parse_datetime(item.get("c") or "")
        with rls_bypass():
            org = Organization.objects.filter(pk=item["e"]).first()
        if org is None or created is None or org.created_at != created:
            continue
        try:
            erase_organization(org, None, listed=True)
        except serializers.ValidationError:
            logger.exception("Löschliste: Einheit %s nicht erneut löschbar", item["e"])
            from core.alarm import send_alert

            send_alert(
                "Löschliste: Einheit nicht erneut löschbar",
                [
                    f"Die Einheit {item['e']} ist nach dem Einspielen wieder da und ließ sich "
                    "nicht automatisch löschen. Bitte in der Plattform-Verwaltung prüfen."
                ],
            )
            continue
        count += 1
    return count
