"""Nextcloud-Konten deaktivieren, wenn der Zugang in HUBIplan endet (und wieder aktivieren).

Grundlage ist dieselbe Prüfung wie bei der Anmeldung (``claims.profile``): Was dort „kein
Zugang“ ergibt, wird in der Nextcloud deaktiviert. Angefasst werden nur Konten, die sich über
HUBIplan angemeldet haben (``Account``); wieder aktiviert nur, was HUBIplan selbst deaktiviert
hat. Die Nextcloud bekommt die Aufträge über ihre Benutzer-Schnittstelle (OCS Provisioning
API) mit einem Dienstkonto, das Gruppen-Admin der Gruppe ``Client.account_group`` ist.

Schutz: Würde ein Abgleich mehr als ``MAX_AT_ONCE`` Konten oder mehr als die Hälfte auf
einmal deaktivieren, hält er an und meldet sich, statt zu handeln.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from django.utils import timezone
from django.utils.translation import gettext, ngettext

from accounts.mfa import decrypt
from audit.log import record
from core import safehttp
from core.tenancy import rls_bypass

from . import claims
from .models import Account, Client

log = logging.getLogger(__name__)

MAX_AT_ONCE = 3
TIMEOUT = 15


class NextcloudError(Exception):
    """Die Nextcloud hat den Auftrag nicht angenommen (Text für die Oberfläche).

    ``code``: Statuscode der OCS-Antwort (oder HTTP-Status), falls bekannt."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def missing_text() -> str:
    """Hinweis zu einem Konto, das die Nextcloud nicht findet. Steht auch in ``Account.error``,
    damit die Mail nur beim ersten Mal kommt und nicht jede Nacht."""
    return gettext(
        "Die Nextcloud findet das Konto nicht. Entweder wurde es dort gelöscht oder es ist "
        "Administrator der Nextcloud (solche Konten darf das Dienstkonto nicht verwalten); dann "
        "ist nichts zu tun. Sonst unter Einstellungen › Nextcloud bei „Bisherige Benutzernamen“ "
        "prüfen, ob der Benutzername stimmt."
    )


def admin_text() -> str:
    """Hinweis zu einem Konto, das Administrator der Nextcloud ist (wie ``missing_text``)."""
    return gettext(
        "Das Konto ist Administrator der Nextcloud. Solche Konten darf das Dienstkonto nicht "
        "verwalten, HUBIplan lässt es deshalb aus. Gruppen und Sperre dieses Kontos bitte in der "
        "Nextcloud von Hand pflegen."
    )


def quiet_texts() -> set[str]:
    """Vermerke, die kein Fehler sind und nur einmal gemeldet werden."""
    return {missing_text(), admin_text()}


def not_found_text(client: Client, nc_user: str) -> str:
    """Die Nextcloud meldet 404/998 für ein Konto: gelöscht oder Administrator?

    Einem Gruppen-Admin antwortet die Nextcloud bei Administratorkonten genauso wie bei
    gelöschten („nicht gefunden“). In der Benutzerliste seiner Gruppen sieht er sie aber."""
    try:
        data = _ocs(client, "GET", "cloud/users", {"search": nc_user})
    except NextcloudError:
        return missing_text()
    users = data.get("users") or []
    if nc_user.casefold() in {str(u).casefold() for u in users}:
        return admin_text()
    return missing_text()


# --- Schnittstelle der Nextcloud ---


def _ocs(client: Client, method: str, path: str, params: dict | None = None) -> dict:
    if not client.service_user or not client.service_password:
        raise NextcloudError(gettext("Dienstkonto und App-Passwort fehlen."))
    auth = f"{client.service_user}:{decrypt(client.service_password, purpose='nextcloud')}"
    query = urlencode({**(params or {}), "format": "json"})
    url = f"{client.base_url.rstrip('/')}/ocs/v2.php/{path}?{query}"
    try:
        resp = safehttp.request(
            method,
            url,
            headers={
                "Authorization": "Basic " + base64.b64encode(auth.encode()).decode(),
                "OCS-APIRequest": "true",
                "Accept": "application/json",
                "Content-Length": "0",
            },
            body=b"" if method != "GET" else None,
            timeout=TIMEOUT,
        )
    except safehttp.SafeHTTPError as exc:
        raise NextcloudError(str(exc)) from exc
    if resp.status == 401:
        raise NextcloudError(gettext("Die Nextcloud lehnt Dienstkonto oder App-Passwort ab."), 401)
    try:
        meta = json.loads(resp.body or b"{}").get("ocs", {})
    except ValueError:
        meta = {}
    code = meta.get("meta", {}).get("statuscode")
    if resp.status == 200 and code in (100, 200):
        return meta.get("data") or {}
    if resp.status == 404 or code in (404, 998):
        raise NextcloudError(gettext("Das Konto gibt es in der Nextcloud nicht (mehr)."), 404)
    if resp.status == 403 or code in (403, 997):
        raise NextcloudError(
            gettext("Das Dienstkonto darf dieses Konto nicht verwalten (Gruppen-Admin?)."), 403
        )
    raise NextcloudError(
        gettext("Die Nextcloud antwortet mit Fehler {status}.").format(status=code or resp.status),
        code or resp.status,
    )


def check_connection(client: Client) -> str:
    """Dienstkonto prüfen; liefert den Anzeigenamen, sonst ``NextcloudError``."""
    data = _ocs(client, "GET", "cloud/user")
    return str(data.get("display-name") or data.get("id") or client.service_user)


def _set_enabled(client: Client, nc_user: str, enabled: bool) -> None:
    verb = "enable" if enabled else "disable"
    _ocs(client, "PUT", f"cloud/users/{quote(nc_user, safe='')}/{verb}")


def disable_deleted(client_id: int, nc_user: str) -> bool:
    """Das HUBIplan-Konto wurde gelöscht: Nextcloud-Konto deaktivieren (nicht löschen;
    Dateien und Freigaben bleiben, bis die Nextcloud-Verwaltung entscheidet). Nur bei Diensten
    mit „Konten automatisch deaktivieren“ (Gesamtaudit 15.11., PF-02)."""
    with rls_bypass():
        client = Client.objects.filter(pk=client_id, manage_accounts=True, is_active=True).first()
    if client is None or not nc_user:
        return False
    try:
        _set_enabled(client, nc_user, False)
    except NextcloudError:
        log.exception("Nextcloud-Konto nach Kontolöschung nicht deaktiviert (Dienst %s)", client_id)
        return False
    return True


# --- Anmeldung merken ---


def remember_login(client: Client, user, prof: claims.Profile) -> None:
    """Nach jeder erfolgreichen Anmeldung: welches Nextcloud-Konto gehört zu wem."""
    nc_user = prof.username or claims.subject(client, user)
    now = timezone.now()
    with rls_bypass():
        account, created = Account.objects.get_or_create(
            client=client,
            user=user,
            defaults={
                "organization_id": client.organization_id,
                "nc_user": nc_user,
                "last_login_at": now,
            },
        )
        if not created:
            account.nc_user = nc_user
            account.last_login_at = now
            # Wer sich anmelden konnte, ist in der Nextcloud wieder aktiv
            account.disabled_by_hubiplan = False
            account.error = ""
            account.save(
                update_fields=["nc_user", "last_login_at", "disabled_by_hubiplan", "error"]
            )


# --- Abgleich ---


@dataclass
class Plan:
    account: Account
    allowed: bool

    @property
    def action(self) -> str:
        """``disable``, ``enable`` oder ``""`` (nichts zu tun)."""
        if not self.allowed and not self.account.disabled_by_hubiplan:
            return "disable"
        if self.allowed and self.account.disabled_by_hubiplan:
            return "enable"
        return ""


def _allowed(client: Client, user) -> bool:
    try:
        claims.profile(client, user)
    except claims.NotAllowed:
        return False
    return True


def plan(client: Client, users: list[int] | None = None) -> list[Plan]:
    """Was ein Abgleich täte (auch für den Probelauf in der Oberfläche)."""
    with rls_bypass():
        qs = Account.objects.filter(client=client).select_related("user")
        if users is not None:
            qs = qs.filter(user_id__in=users)
        # Verwaltungs- und Dienstkonten fasst der Abgleich nie an (Gesamtaudit 15.11., AUTH-07)
        blocked = client.blocked_usernames()
        accounts = [a for a in qs if a.nc_user.lower() not in blocked]
    return [Plan(a, _allowed(client, a.user)) for a in accounts]


def _too_many(client: Client, disabling: int) -> bool:
    if disabling <= 1:
        return False
    with rls_bypass():
        total = Account.objects.filter(client=client).count()
    return disabling > MAX_AT_ONCE or disabling * 2 > total


def sync(client: Client, users: list[int] | None = None, *, confirmed: bool = False) -> dict:
    """Abgleich für einen Dienst (alle oder nur die genannten Benutzer).

    ``confirmed``: von Hand bestätigt (Oberfläche), dann ohne Obergrenze.
    """
    result = {"disabled": 0, "enabled": 0, "errors": 0, "held": False}
    if not client.manage_accounts or not client.is_active:
        return result
    steps = [p for p in plan(client, users) if p.action]
    disabling = sum(1 for p in steps if p.action == "disable")
    now = timezone.now()
    if not confirmed and _too_many(client, disabling):
        message = gettext(
            "Angehalten: {count} Konten wären auf einmal deaktiviert worden. Bitte Rollen "
            "prüfen und unter Einstellungen › Nextcloud den Abgleich bestätigen."
        ).format(count=disabling)
        _finish(client, message, now)
        result["held"] = True
        _notify(client, message, [])
        return result
    done: list[str] = []
    failed: list[str] = []
    for step in steps:
        account = step.account
        enable = step.action == "enable"
        who = f"{account.nc_user} ({account.user.email})"
        try:
            _set_enabled(client, account.nc_user, enable)
        except NextcloudError as exc:
            if exc.code == 404:
                # Gelöscht oder Administrator: kein Fehler, nur beim ersten Mal melden
                note = not_found_text(client, account.nc_user)
                if account.error != note:
                    account.error = note
                    with rls_bypass():
                        account.save(update_fields=["error"])
                    done.append(f"{who}: {note}")
                continue
            account.error = str(exc)[:300]
            with rls_bypass():
                account.save(update_fields=["error"])
            result["errors"] += 1
            failed.append(f"{who}: {exc}")
            continue
        account.disabled_by_hubiplan = not enable
        account.changed_at = now
        account.error = ""
        with rls_bypass():
            account.save(update_fields=["disabled_by_hubiplan", "changed_at", "error"])
            record(
                client.organization,
                None,
                "update",
                account,
                {
                    "Nextcloud-Konto": [
                        "aktiv" if not enable else "deaktiviert",
                        "aktiv" if enable else "deaktiviert",
                    ]
                },
            )
        result["enabled" if enable else "disabled"] += 1
        label = gettext("aktiviert") if enable else gettext("deaktiviert")
        done.append(f"{who}: {label}")
    error = ""
    if result["errors"]:
        error = (
            ngettext(
                "{count} Konto konnte nicht geändert werden.",
                "{count} Konten konnten nicht geändert werden.",
                result["errors"],
            ).format(count=result["errors"])
            + " "
            + "; ".join(failed)
        )
    _finish(client, error, now)
    if done or error:
        _notify(client, error, done)
    return result


def sync_user(user_id: int) -> None:
    """Nach einer Änderung an Rollen oder Konto: alle Dienste dieses Benutzers abgleichen."""
    with rls_bypass():
        clients = list(
            Client.objects.filter(
                manage_accounts=True, is_active=True, accounts__user_id=user_id
            ).distinct()
        )
    for client in clients:
        sync(client, [user_id])


def sync_all() -> None:
    with rls_bypass():
        clients = list(Client.objects.filter(manage_accounts=True, is_active=True))
    for client in clients:
        try:
            sync(client)
        except Exception:  # ein Dienst darf die anderen nicht aufhalten
            log.exception("Nextcloud-Abgleich %s fehlgeschlagen", client.pk)


def _finish(client: Client, error: str, now) -> None:
    client.sync_error = error[:500]
    client.synced_at = now
    with rls_bypass():
        Client.objects.filter(pk=client.pk).update(sync_error=client.sync_error, synced_at=now)


def _notify(client: Client, error: str, done: list[str], *, what: str = "accounts") -> None:
    """E-Mail an alle, die Rollen der Einheit festlegen und besetzen."""
    from access.catalog import ROLES_MANAGE, effective
    from access.models import RoleAssignment
    from outbox.mail import send

    org = client.organization
    with rls_bypass():
        assignments = (
            RoleAssignment.objects.active()
            .filter(organization=org, user__isnull=False, user__is_active=True)
            .select_related("role", "user")
        )
        to = sorted(
            {a.user.email for a in assignments if ROLES_MANAGE in effective(a.role.permissions)}
        )
    if not to:
        return
    if what == "groups":
        subject = gettext("Nextcloud „{name}“: Gruppen abgeglichen").format(name=client.name)
        intro = gettext(
            "HUBIplan hat die Gruppen in der Nextcloud „{name}“ ({host}) mit den Rollen "
            "abgeglichen."
        )
    else:
        subject = gettext("Nextcloud „{name}“: Konten abgeglichen").format(name=client.name)
        intro = gettext(
            "HUBIplan hat die Konten in der Nextcloud „{name}“ ({host}) mit den Rollen abgeglichen."
        )
    lines = [
        intro.format(name=client.name, host=client.host),
        "",
        *done,
    ]
    if error:
        lines += ["", error]
    lines += [
        "",
        gettext("Einzelheiten stehen unter Einstellungen › Nextcloud und im Änderungsprotokoll."),
    ]
    send(
        to, subject, "\n".join(lines) + "\n", organization=org, kind="nextcloud", fail_silently=True
    )
