"""Tägliche Prüfung der Protokollketten (Finanzamt-Prüfung C3)."""

from celery import shared_task

from core.tenancy import rls_bypass


@shared_task
def check_chains() -> int:
    """Versiegelt liegen gebliebene Einträge, prüft jede Kette und meldet Brüche."""
    from core.alarm import send_alert

    from .chain import seal, verify
    from .models import AuditCheck, AuditEntry

    with rls_bypass():
        # order_by(): sonst stünde die Standardsortierung im DISTINCT (Einheit je Eintrag)
        # Auch Organisationen mit früherem Prüfergebnis: sonst fiele das Löschen aller
        # Einträge nicht auf (Gesamtaudit 01.11., GA-F06)
        org_ids = sorted(
            set(AuditEntry.objects.order_by().values_list("organization_id", flat=True).distinct())
            | set(AuditCheck.objects.values_list("organization_id", flat=True))
        )
        before = {
            c.organization_id: c.ok for c in AuditCheck.objects.filter(organization_id__in=org_ids)
        }
    broken = []
    for org_id in org_ids:
        seal(org_id)
        result = verify(org_id)
        if not result["ok"] and before.get(org_id, True):
            broken.append((org_id, result["problems"]))
    if broken:
        from organizations.models import Organization

        with rls_bypass():
            names = dict(
                Organization.objects.filter(pk__in=[o for o, _ in broken]).values_list("pk", "name")
            )
        lines = []
        for org_id, problems in broken:
            lines.append(f"{names.get(org_id, org_id)}:")
            lines.extend(f"  {p}" for p in problems)
        send_alert("Änderungsprotokoll wurde verändert", lines)
    return len(org_ids)


def _auditors(org) -> list:
    """Kassenprüfer: Kasse lesen, aber nicht bearbeiten."""
    from access.catalog import FINANCE_EDIT, FINANCE_VIEW, effective
    from access.models import RoleAssignment

    users: dict[int, object] = {}
    rights: dict[int, set] = {}
    for a in (
        RoleAssignment.objects.active().filter(organization=org).select_related("role", "user")
    ):
        if a.user_id and a.user.is_active and a.user.email:
            users[a.user_id] = a.user
            rights.setdefault(a.user_id, set()).update(effective(a.role.permissions))
    return [
        users[uid]
        for uid, perms in rights.items()
        if FINANCE_VIEW in perms and FINANCE_EDIT not in perms
    ]


@shared_task(soft_time_limit=1500, time_limit=1560)
def mail_heads() -> int:
    """Wöchentlich den Kettenkopf an die Kassenprüfer (Gesamtaudit 05.11. GA-08, F-06).

    Die Zeile „STEMPEL ORG NUMMER PRÜFSUMME“ lässt sich später mit
    ``manage.py kettenkoepfe_pruefen`` gegen die Datenbank prüfen. So fällt eine
    nachträgliche Änderung auch auf, wenn Backups fehlen."""
    from django.utils import timezone, translation
    from django.utils.translation import gettext, gettext_noop

    from core.i18n import user_language
    from organizations.models import Organization
    from outbox import mail

    from .models import AuditCheck

    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    sent = 0
    with rls_bypass():
        heads = list(
            AuditCheck.objects.filter(head_seq__isnull=False)
            .exclude(head_hash="")
            .values_list("organization_id", "head_seq", "head_hash")
        )
        orgs = Organization.objects.in_bulk([org_id for org_id, _, _ in heads])
        for org_id, seq, digest in heads:
            org = orgs.get(org_id)
            if org is None or org.is_remote:
                continue
            line = f"{stamp} {org_id} {seq} {digest}"
            for user in _auditors(org):
                language = user_language(user)
                with translation.override(language):
                    subject = gettext(gettext_noop("Prüfsumme des Änderungsprotokolls: {org}"))
                    body = gettext(
                        gettext_noop(
                            "Diese Mail bekommen alle, die die Kasse von {org} prüfen dürfen.\n\n"
                            "Stand des Änderungsprotokolls (Eintrag Nr. {seq}):\n\n{line}\n\n"
                            "Bitte diese Mail aufbewahren. Mit der Zeile lässt sich später "
                            "nachweisen, dass Buchungen und Protokoll seitdem nicht verändert "
                            "wurden (Betreiber: manage.py kettenkoepfe_pruefen)."
                        )
                    )
                if mail.send(
                    user.email,
                    subject.format(org=org.name),
                    body.format(org=org.name, seq=seq, line=line),
                    organization=org,
                    kind="kettenkopf",
                    language=language,
                    fail_silently=True,
                ):
                    sent += 1
    return sent
