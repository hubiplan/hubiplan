"""Kachel „Zu erledigen“: offene Mitgliedsanträge."""

from __future__ import annotations

from django.utils.translation import gettext

from access.catalog import MEMBERS_EDIT, MEMBERS_VIEW

LIMIT = 10


def application_tasks(user, org, perms: set[str]) -> list[dict]:
    from . import rules, services
    from .models import Application, ApplicationForm

    if MEMBERS_VIEW not in perms or not org.keeps_members:
        return []
    form = ApplicationForm.objects.filter(organization=org).first()
    if form is None:
        return []
    rule = form.rule or {}
    edit = MEMBERS_EDIT in perms
    approver = rules.may_approve(rule, rules.user_roles(user, org), perms)
    if not (edit or approver):
        return []
    qs = (
        Application.objects.filter(organization=org, status__in=Application.OPEN_STATES)
        .prefetch_related("approvals")
        .order_by("created_at")
    )
    items = []
    for app in qs[: LIMIT * 3]:
        state = services.state(app, form)
        mine = any(a.user_id == user.pk for a in app.approvals.all())
        if app.status == "unsigned":
            detail = gettext("wartet auf Unterschrift")
        elif app.status == "query":
            detail = gettext("Rückfrage läuft")
        elif state.disputed:
            detail = gettext("Ablehnung liegt vor")
        elif not state.met:
            if approver and not mine:
                detail = gettext("deine Zustimmung fehlt")
            elif not edit:
                continue
            else:
                detail = gettext("wartet auf Zustimmungen")
        elif edit:
            detail = gettext("bereit zur Aufnahme")
        else:
            continue
        items.append(
            {
                "kind": "application",
                "kind_label": gettext("Mitgliedsantrag"),
                "title": app.display_name,
                "detail": detail,
                "created_at": app.created_at,
                "link": f"/mitglieder/antraege/{app.pk}",
                "ref": app.pk,
            }
        )
        if len(items) >= LIMIT:
            break
    return items
