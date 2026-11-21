"""Gruppen der Nextcloud laufend mit den Rollen in HUBIplan abgleichen.

Die App ``user_oidc`` setzt Gruppen nur beim Anmelden. Endet eine Rolle, das Konto bleibt aber
aktiv (andere Rolle, Mitgliederzugang), behielt die Person bisher die Gruppe samt Gruppenordnern
und geteilten Kalendern, mit Sync-Apps unbegrenzt. Dieser Abgleich setzt die Gruppen nach jeder
Änderung an Rollen, Ämtern oder Mitgliedschaft und jede Nacht, mit derselben Berechnung wie das
Token (``claims.profile``).

Geändert werden nur Gruppen aus ``Client.managed_groups`` (Liste der Einheit und Kontengruppe),
nur bei Konten, die sich über HUBIplan angemeldet haben, nie ``admin`` und nie Verwaltungs- oder
Dienstkonten. Das Dienstkonto muss Gruppen-Admin dieser Gruppen sein (OCS Provisioning API).
Wer keinen Zugang mehr hat, verliert alle abgeglichenen Gruppen außer der Kontengruppe, damit das
Dienstkonto das Konto weiter verwalten kann.

Schutz wie beim Kontenabgleich: Würden mehr als ``MAX_AT_ONCE`` Konten (oder mehr als die Hälfte)
auf einmal Gruppen verlieren, hält der Abgleich an, bis jemand ihn auf der Seite bestätigt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import quote

from django.utils import timezone
from django.utils.translation import gettext, ngettext

from audit.log import record
from core.tenancy import rls_bypass

from . import claims
from .models import Account, Client
from .nc_accounts import MAX_AT_ONCE, NextcloudError, _notify, _ocs, missing_text

log = logging.getLogger(__name__)


@dataclass
class GroupPlan:
    account: Account
    current: list[str] = field(default_factory=list)
    wanted: list[str] = field(default_factory=list)
    error: str = ""
    # Das Konto gibt es in der Nextcloud nicht (mehr): kein Fehler des Abgleichs, nichts zu tun
    missing: bool = False

    @property
    def add(self) -> list[str]:
        return [g for g in self.wanted if g not in self.current]

    @property
    def remove(self) -> list[str]:
        return [g for g in self.current if g not in self.wanted]


def wanted_groups(client: Client, user) -> list[str]:
    """Abgeglichene Gruppen, die der Benutzer haben soll (Reihenfolge wie im Token)."""
    managed = {g.casefold(): g for g in client.managed_groups()}
    try:
        groups = claims.profile(client, user).groups
    except claims.NotAllowed:
        # Ohne Zugang nur die Kontengruppe: Sie hält das Konto in der Hand des Dienstkontos
        groups = [client.account_group] if client.account_group else []
    out = []
    for g in groups:
        name = managed.get(" ".join(str(g).split()).casefold())
        if name and name not in out:
            out.append(name)
    return out


def current_groups(client: Client, nc_user: str) -> list[str]:
    """Abgeglichene Gruppen, in denen das Konto heute ist (soweit das Dienstkonto sie sieht)."""
    data = _ocs(client, "GET", f"cloud/users/{quote(nc_user, safe='')}/groups")
    managed = {g.casefold(): g for g in client.managed_groups()}
    out = []
    for g in data.get("groups") or []:
        name = managed.get(str(g).casefold())
        if name and name not in out:
            out.append(name)
    return out


def plan(client: Client, users: list[int] | None = None) -> list[GroupPlan]:
    """Was ein Abgleich täte; fragt die Nextcloud nach den heutigen Gruppen jedes Kontos."""
    with rls_bypass():
        qs = Account.objects.filter(client=client).select_related("user")
        if users is not None:
            qs = qs.filter(user_id__in=users)
        blocked = client.blocked_usernames()
        accounts = [a for a in qs if a.nc_user.lower() not in blocked]
    plans = []
    for account in accounts:
        p = GroupPlan(account, wanted=wanted_groups(client, account.user))
        try:
            p.current = current_groups(client, account.nc_user)
        except NextcloudError as exc:
            p.wanted = []
            if exc.code == 404:
                p.missing = True
            else:
                p.error = str(exc)[:300]
        plans.append(p)
    return plans


def missing_admin(client: Client) -> list[str]:
    """Abgeglichene Gruppen, für die das Dienstkonto kein Gruppen-Admin ist (soweit die
    Nextcloud das dem Dienstkonto verrät; sonst leer)."""
    try:
        data = _ocs(client, "GET", "cloud/user")
    except NextcloudError:
        return []
    sub = data.get("subadmin")
    if not isinstance(sub, list):
        return []
    have = {str(g).casefold() for g in sub}
    return [g for g in client.managed_groups() if g.casefold() not in have]


def _too_many(client: Client, losing: int) -> bool:
    if losing <= 1:
        return False
    with rls_bypass():
        total = Account.objects.filter(client=client).count()
    return losing > MAX_AT_ONCE or losing * 2 > total


def _change(client: Client, nc_user: str, group: str, add: bool) -> None:
    path = f"cloud/users/{quote(nc_user, safe='')}/groups"
    try:
        _ocs(client, "POST" if add else "DELETE", path, {"groupid": group})
    except NextcloudError as exc:
        if exc.code == 102:
            raise NextcloudError(
                gettext("Die Gruppe „{group}“ gibt es in der Nextcloud nicht.").format(group=group),
                102,
            ) from exc
        if exc.code in (103, 104, 403):
            raise NextcloudError(
                gettext("Das Dienstkonto ist nicht Gruppen-Admin von „{group}“.").format(
                    group=group
                ),
                104,
            ) from exc
        raise


def sync(client: Client, users: list[int] | None = None, *, confirmed: bool = False) -> dict:
    """Gruppen für einen Dienst abgleichen (alle Konten oder nur die genannten Benutzer).

    ``confirmed``: von Hand bestätigt (Oberfläche), dann ohne Obergrenze."""
    result = {"added": 0, "removed": 0, "errors": 0, "missing": 0, "held": False}
    if not client.sync_groups or not client.is_active or not client.managed_groups():
        return result
    plans = plan(client, users)
    now = timezone.now()
    losing = sum(1 for p in plans if p.remove)
    if not confirmed and _too_many(client, losing):
        message = gettext(
            "Angehalten: {count} Konten hätten auf einmal Gruppen verloren. Bitte Rollen prüfen "
            "und unter Einstellungen › Nextcloud den Gruppenabgleich bestätigen."
        ).format(count=losing)
        _finish(client, message, now)
        result["held"] = True
        _notify(client, message, [], what="groups")
        return result
    done: list[str] = []
    gone = missing_text()
    for p in plans:
        who = f"{p.account.nc_user} ({p.account.user.email})"
        if p.missing:
            result["missing"] += 1
            # Nur beim ersten Mal melden, nicht jede Nacht wieder
            if p.account.error != gone:
                p.account.error = gone
                with rls_bypass():
                    p.account.save(update_fields=["error"])
                done.append(f"{who}: {gone}")
            continue
        if p.account.error == gone:
            p.account.error = ""
            with rls_bypass():
                p.account.save(update_fields=["error"])
        if p.error:
            p.error = f"{who}: {p.error}"[:300]
            result["errors"] += 1
            continue
        changes = [(g, True) for g in p.add] + [(g, False) for g in p.remove]
        for group, add in changes:
            try:
                _change(client, p.account.nc_user, group, add)
            except NextcloudError as exc:
                p.error = f"{who}: {exc}"[:300]
                result["errors"] += 1
                continue
            result["added" if add else "removed"] += 1
            with rls_bypass():
                record(
                    client.organization,
                    None,
                    "update",
                    p.account,
                    {
                        gettext("Gruppe „{group}“").format(group=group): [
                            gettext("nein") if add else gettext("ja"),
                            gettext("ja") if add else gettext("nein"),
                        ]
                    },
                )
            if add:
                label = gettext("in „{group}“ aufgenommen").format(group=group)
            else:
                label = gettext("aus „{group}“ entfernt").format(group=group)
            done.append(f"{who}: {label}")
    error = ""
    if result["errors"]:
        errors = sorted({p.error for p in plans if p.error})
        error = (
            ngettext(
                "{count} Gruppenänderung ging nicht.",
                "{count} Gruppenänderungen gingen nicht.",
                result["errors"],
            ).format(count=result["errors"])
            + " "
            + "; ".join(errors)
        )
    _finish(client, error, now)
    if done or error:
        _notify(client, error, done, what="groups")
    return result


def _finish(client: Client, error: str, now) -> None:
    client.groups_error = error[:500]
    client.groups_synced_at = now
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(
            groups_error=client.groups_error, groups_synced_at=now
        )


def sync_user(user_id: int) -> None:
    """Nach einer Änderung an Rollen oder Konto: alle Dienste dieses Benutzers abgleichen."""
    with rls_bypass():
        clients = list(
            Client.objects.filter(
                sync_groups=True, is_active=True, accounts__user_id=user_id
            ).distinct()
        )
    for client in clients:
        sync(client, [user_id])


def sync_all() -> None:
    with rls_bypass():
        clients = list(Client.objects.filter(sync_groups=True, is_active=True))
    for client in clients:
        try:
            sync(client)
        except Exception:  # ein Dienst darf die anderen nicht aufhalten
            log.exception("Nextcloud-Gruppenabgleich %s fehlgeschlagen", client.pk)
