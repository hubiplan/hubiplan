"""Umzug einer Einheit auf eine andere Instanz (Verbund, Konzept 9.2).

1. Die Einheit exportiert ihre Daten mit der Datenübernahme (``datatransfer``). Die
   Datei enthält ihre offenen Kopplungen (Gegenstelle, Freigaben, Platzhalter), aber
   keine Schlüssel dieser Instanz.
2. Auf der neuen Instanz wird die Datei eingelesen. Die feste Kennung der Einheit
   bleibt, die Kopplungen entstehen dort neu.
3. Die alte Instanz meldet allen Gegenstellen den Umzug, unterschrieben mit ihrem
   Schlüssel. Die Gegenstellen prüfen die neue Instanz über ihre Selbstauskunft und
   halten die Kopplung an („Umzug angekündigt“). Erst wenn dort ein Vorstand den
   Fingerabdruck der neuen Instanz bestätigt, geht es weiter und die Stände gehen neu
   hinaus. Sonst könnte eine gehackte alte Instanz alle Daten still umlenken.
4. Die alte Instanz führt die Kopplungen danach als „umgezogen“ und nimmt keine
   Pakete mehr an. Die Einheit kann dort gelöscht werden.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from . import identity, services, transport
from .models import Coupling, Peer, RemoteMember

log = logging.getLogger(__name__)

OPEN = (Coupling.State.ACTIVE, Coupling.State.PAUSED)


# --- Export und Import ---


def dump_couplings(org) -> list[dict]:
    """Offene Kopplungen einer Einheit für die Exportdatei."""
    result = []
    for c in Coupling.objects.filter(local_unit=org, state__in=OPEN).select_related(
        "peer", "remote_unit"
    ):
        ph = c.remote_unit
        result.append(
            {
                "direction": c.direction,
                "state": c.state,
                "remote_uuid": str(c.remote_uuid),
                "packets": c.packets or {},
                "remote_packets": c.remote_packets or {},
                "options": c.options or {},
                "version": c.version,
                "peer": {
                    "instance_id": str(c.peer.instance_id),
                    "base_url": c.peer.base_url,
                    "public_key": c.peer.public_key,
                    "enc_public_key": c.peer.enc_public_key,
                    "fingerprint": c.peer.fingerprint,
                    "versions": c.peer.versions,
                    "country": c.peer.country,
                },
                # Platzhalter: unten (Kopplung nach oben) steht er nicht im Baum der Datei
                "placeholder": {"id": ph.pk, "name": ph.name, "type": ph.type},
            }
        )
        if c.direction == Coupling.Direction.PARENT:
            # Verbandsnummern je Mitgliedschaft: so erkennt der Dachverband die Personen
            # nach dem Umzug wieder (die Mitgliedschaften bekommen dort neue Nummern)
            result[-1]["numbers"] = {
                str(mid): number
                for mid, number in RemoteMember.objects.filter(
                    coupling=c, number__isnull=False, membership__isnull=False
                ).values_list("membership_id", "number")
            }
    return result


def _verified_info(peer_data: dict) -> dict:
    """Selbstauskunft der Gegenstelle aus der Datei holen; sie muss zur Datei passen.

    Gesamtaudit 15.11., AZ-01: Adresse und Schlüssel der Gegenstelle kamen ungeprüft aus der
    Datei. Jetzt gilt nur, was die Instanz unter dieser Adresse selbst meldet."""
    base_url = transport.normalize_url(str(peer_data.get("base_url") or ""))
    transport.check_host(base_url)
    info = transport.fetch_info(base_url)
    if (
        str(info["instance_id"]) != str(peer_data.get("instance_id"))
        or info["public_key"] != peer_data.get("public_key")
        or info["enc_public_key"] != peer_data.get("enc_public_key")
    ):
        raise transport.PeerError(gettext("Die Instanz meldet andere Schlüssel als die Datei."))
    return info


def load_couplings(org, items: list, ids_of_orgs: dict, warn, membership_id=None) -> int:
    """Kopplungen aus einer Exportdatei auf dieser Instanz anlegen (nur Plattform-Import).

    Gesamtaudit 15.11., AZ-01, Fachfrage FF-19: Die Gegenstelle wird über ihre
    Selbstauskunft geprüft, und jede Kopplung wartet wie bei einem angekündigten Umzug, bis
    ein Vorstand den Fingerabdruck bestätigt, den die andere Seite mitteilt. Bis dahin geht
    nichts hinaus und nichts herein. Übergangene Kopplungen hinterlassen nichts."""
    from organizations.models import Organization

    count = 0
    for item in items or []:
        try:
            peer_data = item["peer"]
            direction = item["direction"]
            remote_uuid = item["remote_uuid"]
            if direction not in Coupling.Direction.values or not isinstance(peer_data, dict):
                raise KeyError("direction")
        except (KeyError, TypeError):
            warn(gettext("Eine Kopplung in der Datei ist unvollständig und wurde übergangen."))
            continue
        name = str((item.get("placeholder") or {}).get("name", ""))
        if str(peer_data.get("instance_id")) == identity.identity().instance_id:
            warn(
                gettext(
                    "Die Kopplung mit „{name}“ läuft auf dieser Instanz und wurde übergangen."
                ).format(name=name)
            )
            continue
        known = Peer.objects.filter(instance_id=peer_data.get("instance_id")).first()
        if known is not None and (
            known.public_key != peer_data.get("public_key")
            or known.enc_public_key != peer_data.get("enc_public_key")
        ):
            warn(
                gettext("{url} ist hier mit einem anderen Schlüssel bekannt; übergangen.").format(
                    url=known.base_url
                )
            )
            continue
        try:
            info = _verified_info(peer_data)
        except (transport.PeerError, ValidationError) as exc:
            warn(
                gettext("Kopplung mit „{name}“ übergangen: {reason}").format(
                    name=name, reason="; ".join(getattr(exc, "messages", [str(exc)]))
                )
            )
            continue
        ph_info = item.get("placeholder") or {}
        if direction == Coupling.Direction.CHILD:
            placeholder = ids_of_orgs.get(ph_info.get("id"))
            if placeholder is None or not placeholder.is_remote:
                warn(
                    gettext("Platzhalter für „{name}“ fehlt; Kopplung übergangen.").format(
                        name=name
                    )
                )
                continue
        elif Coupling.objects.filter(
            local_unit=org, direction=Coupling.Direction.PARENT, state__in=OPEN
        ).exists():
            warn(gettext("Es gibt hier schon eine Einheit darüber; Kopplung übergangen."))
            continue
        previous = item.get("state") if item.get("state") in OPEN else Coupling.State.ACTIVE
        options = dict(item.get("options") or {}) if isinstance(item.get("options"), dict) else {}
        options["move"] = {
            "from": "",
            "import": True,
            "base_url": info["base_url"],
            "instance_id": str(info["instance_id"]),
            "public_key": info["public_key"],
            "enc_public_key": info["enc_public_key"],
            "fingerprint": info["fingerprint"],
            "country": str(info.get("country", ""))[:10],
            "versions": info.get("versions") or [1],
            "previous": previous,
            "at": timezone.now().isoformat(),
        }
        try:
            with transaction.atomic():
                peer = services._store_peer(info)
                if direction == Coupling.Direction.PARENT:
                    placeholder = services._placeholder(
                        str(ph_info.get("name") or "Ferne Einheit"),
                        parent=Organization.platform(),
                        type_=Organization.Type.FEDERATION,
                    )
                coupling = Coupling.objects.create(
                    local_unit=org,
                    remote_unit=placeholder,
                    remote_uuid=remote_uuid,
                    peer=peer,
                    direction=direction,
                    state=Coupling.State.MOVING,
                    packets=item.get("packets") or {},
                    remote_packets=item.get("remote_packets") or {},
                    options=options,
                    version=int(item.get("version") or 1),
                    activated_at=timezone.now(),
                )
                if direction == Coupling.Direction.PARENT and membership_id is not None:
                    for old, number in (item.get("numbers") or {}).items():
                        try:
                            new = membership_id(int(old))
                            number = int(number)
                        except (TypeError, ValueError):
                            continue
                        if new:
                            RemoteMember.objects.create(
                                coupling=coupling, uid=f"m{new}", membership_id=new, number=number
                            )
                services._audit(
                    coupling,
                    None,
                    f"Aus Datei übernommen: {peer.base_url} "
                    "(wartet auf Bestätigung des Fingerabdrucks)",
                )
        except ValidationError as exc:
            warn(
                gettext("Kopplung mit „{name}“ übergangen: {reason}").format(
                    name=name, reason="; ".join(exc.messages)
                )
            )
            continue
        count += 1
    return count


# --- Umzug melden (alte Instanz) ---


def inspect_target(base_url: str) -> dict:
    """Neue Instanz prüfen: Selbstauskunft mit Fingerabdruck zum Abgleich."""
    info = transport.fetch_info(base_url)
    if str(info["instance_id"]) == identity.identity().instance_id:
        raise ValidationError(gettext("Das ist diese Instanz."))
    return info


def announce(org, base_url: str, fingerprint: str, user) -> dict:
    """Allen Gegenstellen den Umzug melden. Danach gelten die Kopplungen hier als umgezogen."""
    info = inspect_target(base_url)
    if fingerprint.replace(" ", "").upper() != info["fingerprint"].replace(" ", "").upper():
        raise ValidationError(gettext("Der Fingerabdruck passt nicht zur neuen Instanz."))
    couplings = list(Coupling.objects.filter(local_unit=org, state__in=OPEN).select_related("peer"))
    if not couplings:
        raise ValidationError(gettext("Diese Einheit hat keine aktiven Kopplungen."))
    done, failed = 0, []
    for coupling in couplings:
        payload = services._envelope(
            coupling,
            "unit.moved",
            {
                "base_url": info["base_url"],
                "instance_id": str(info["instance_id"]),
                "public_key": info["public_key"],
                "enc_public_key": info["enc_public_key"],
            },
            seq=coupling.out_seq + 1,
        )
        try:
            transport.call(services.keys_of(coupling.peer), "/api/peering/v1/inbox/", payload)
        except transport.PeerError as exc:
            failed.append(f"{coupling.remote_unit.name}: {exc}")
            continue
        with transaction.atomic():
            locked = Coupling.objects.select_for_update().get(pk=coupling.pk)
            locked.state = Coupling.State.MOVED
            locked.ended_at = timezone.now()
            locked.options = {**(locked.options or {}), "moved_to": info["base_url"]}
            locked.save(update_fields=["state", "ended_at", "options"])
            services._audit(locked, user, f"Umzug nach {info['base_url']} gemeldet")
        done += 1
    return {"done": done, "failed": failed}


# --- Umzug übernehmen (Gegenstelle) ---


def verify_moved(data: dict) -> dict:
    """Verify the announced identity before taking a global reception-budget lock."""
    info = transport.fetch_info(str(data.get("base_url", "")))
    if (
        str(info["instance_id"]) != str(data.get("instance_id"))
        or info["public_key"] != data.get("public_key")
        or info["enc_public_key"] != data.get("enc_public_key")
    ):
        raise ValidationError(gettext("Die neue Instanz meldet andere Schlüssel als angekündigt."))
    if str(info["instance_id"]) == identity.identity().instance_id:
        raise ValidationError(gettext("Die neue Instanz ist diese Instanz selbst."))
    return info


def receive_moved(coupling: Coupling, data: dict, *, verified_info=None) -> None:
    """Gegenstelle: Umzug erst nach lokaler Bestätigung (``confirm_move``)."""
    info = verify_moved(data) if verified_info is None else verified_info
    options = dict(coupling.options or {})
    previous = options.get("move", {}).get("previous") or coupling.state
    if previous not in OPEN:
        previous = Coupling.State.ACTIVE
    options["move"] = {
        "from": coupling.peer.base_url,
        "base_url": info["base_url"],
        "instance_id": str(info["instance_id"]),
        "public_key": info["public_key"],
        "enc_public_key": info["enc_public_key"],
        "fingerprint": info["fingerprint"],
        "country": str(info.get("country", ""))[:10],
        "versions": info.get("versions") or [1],
        "previous": previous,
        "at": timezone.now().isoformat(),
    }
    coupling.options = options
    coupling.state = Coupling.State.MOVING
    coupling.save(update_fields=["options", "state"])
    services._audit(
        coupling,
        None,
        f"Umzug angekündigt: {coupling.peer.base_url} → {info['base_url']} "
        "(wartet auf Bestätigung)",
    )
    pk = coupling.pk
    transaction.on_commit(lambda: services._notify_move(pk))
    from core.alarm import send_alert

    lines = [
        f"Kopplung {pk}: {options['move']['from']} → {options['move']['base_url']}",
        "Die Kopplung ruht, bis ein Vorstand den Fingerabdruck bestätigt.",
    ]
    transaction.on_commit(lambda: send_alert("Verbund: Umzug einer Gegenstelle angekündigt", lines))


def _norm(fingerprint: str) -> str:
    return "".join(str(fingerprint or "").split()).upper()


def confirm_move(coupling: Coupling, fingerprint: str, user) -> Coupling:
    """Vorstand bestätigt den Umzug mit dem Fingerabdruck, den die andere Seite mitteilt."""
    with transaction.atomic():
        coupling = Coupling.objects.select_for_update().select_related("peer").get(pk=coupling.pk)
        pending = (coupling.options or {}).get("move")
        if coupling.state != Coupling.State.MOVING or not pending:
            raise ValidationError(gettext("Für diese Kopplung ist kein Umzug angekündigt."))
        if not fingerprint or _norm(fingerprint) != _norm(pending["fingerprint"]):
            raise ValidationError(
                gettext(
                    "Der Fingerabdruck passt nicht zur neuen Instanz. Bitte nicht bestätigen "
                    "und bei der anderen Seite nachfragen."
                )
            )
        # Frisch prüfen: meldet die neue Adresse noch dieselben Schlüssel?
        try:
            info = transport.fetch_info(pending["base_url"])
        except transport.PeerError as exc:
            raise ValidationError(
                gettext("Die neue Instanz antwortet nicht: {exc}").format(exc=exc)
            ) from exc
        if (
            str(info["instance_id"]) != pending["instance_id"]
            or info["public_key"] != pending["public_key"]
            or info["enc_public_key"] != pending["enc_public_key"]
        ):
            raise ValidationError(gettext("Die neue Instanz meldet inzwischen andere Schlüssel."))
        peer = services._store_peer(info)
        old = coupling.peer.base_url
        options = dict(coupling.options or {})
        options.pop("move", None)
        coupling.options = options
        coupling.peer = peer
        coupling.state = pending.get("previous") or Coupling.State.ACTIVE
        coupling.in_seq = 0
        coupling.sent_hashes = {}
        coupling.last_error = ""
        coupling.error_since = None
        coupling.save(
            update_fields=[
                "options",
                "peer",
                "state",
                "in_seq",
                "sent_hashes",
                "last_error",
                "error_since",
            ]
        )
        services._audit(coupling, user, f"Umzug bestätigt: {old} → {peer.base_url}")
        pk = coupling.pk
        transaction.on_commit(lambda: services.sync(Coupling.objects.get(pk=pk)))
    return coupling


def decline_move(coupling: Coupling, user) -> None:
    """Umzug ablehnen: Die Kopplung wird gelöst (die alte Instanz nimmt ohnehin nichts mehr an)."""
    if coupling.state != Coupling.State.MOVING:
        raise ValidationError(gettext("Für diese Kopplung ist kein Umzug angekündigt."))
    services.end(coupling, user, reason="gelöst (Umzug abgelehnt)", notify=False)
