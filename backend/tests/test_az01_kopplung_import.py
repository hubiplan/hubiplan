# ruff: noqa: F401, F811  (Fixtures aus test_datatransfer)
"""Kopplungen im Import (Gesamtaudit 15.11., AZ-01, Fachfrage FF-19).

Ein Dachverband legte über eine bearbeitete Vereinsdatei eine Gegenstelle mit frei
gewählter Adresse und Schlüsseln und eine aktive Kopplung an, auch bei abgeschaltetem
Verbund. Jetzt übernimmt nur die Plattform Kopplungen, prüft die Gegenstelle über ihre
Selbstauskunft und lässt jede Kopplung ruhen, bis ein Vorstand den Fingerabdruck bestätigt.
Abgeschalteter Verbund versendet nichts. Erfundene Daten (example.invalid).
"""

import io
import json
import uuid
import zipfile

import pytest

from core.tenancy import rls_bypass
from organizations.models import Organization, PlatformSettings
from peering import services, transport
from peering.models import Coupling, Message, Peer

from .factories import give_role, make_user
from .test_datatransfer import _eager, _on_commit_now, club_c, export, types, upload

pytestmark = pytest.mark.django_db
FREMD = "https://fremd.example.invalid"
SCHLUESSEL = {"public_key": "A" * 43, "enc_public_key": "B" * 43}


def _with_peering(content: bytes, peering: list) -> bytes:
    if content[:2] == b"PK":
        src = zipfile.ZipFile(io.BytesIO(content))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as dst:
            for name in src.namelist():
                data = src.read(name)
                if name == "export.json":
                    doc = json.loads(data)
                    doc["organization"]["peering"] = peering
                    data = json.dumps(doc).encode()
                dst.writestr(name, data)
        return out.getvalue()
    doc = json.loads(content)
    doc["organization"]["peering"] = peering
    return json.dumps(doc).encode()


def _peering(instance_id: str) -> list:
    return [
        {
            "direction": "parent",
            "state": "active",
            "remote_uuid": str(uuid.uuid4()),
            "peer": {"instance_id": instance_id, "base_url": FREMD, **SCHLUESSEL},
            "placeholder": {"name": "Ferner Musterverband"},
            "packets": {"unit": "on", "members": "b"},
        }
    ]


def _nichts_angelegt(instance_id: str) -> None:
    with rls_bypass():
        assert not Peer.objects.filter(instance_id=instance_id).exists()
        assert not Organization.objects.filter(name="Ferner Musterverband").exists()
        assert not Message.objects.exists()


def _platform_admin():
    admin = make_user(f"plattform-{uuid.uuid4().hex[:6]}@example.org")
    give_role(admin, Organization.platform())
    return admin


def _run(c, base, job):
    assert c.post(f"{base}/datatransfer/imports/{job['id']}/run/").status_code == 200
    job = c.get(f"{base}/datatransfer/imports/{job['id']}/").json()
    assert job["status"] == "done", job
    return job


def _warnings(job) -> str:
    return " ".join((job.get("preview") or {}).get("warnings") or [])


def test_dachverband_uebernimmt_keine_kopplung(api, orgs, club_c, board_c):
    content, _ = export(api(board_c), f"/api/orgs/{club_c['club'].pk}")
    instance_id = str(uuid.uuid4())
    board_fed = make_user("verband-az01@example.org")
    give_role(board_fed, orgs["federation"])
    c = api(board_fed)
    base = f"/api/orgs/{orgs['federation'].pk}"
    job = upload(c, base, _with_peering(content, _peering(instance_id)), name="Eingelesen")
    assert "nur die Plattform" in _warnings(job)
    job = _run(c, base, job)
    _nichts_angelegt(instance_id)
    with rls_bypass():
        new_club = Organization.objects.get(pk=job["result_organization"]["id"])
        assert not Coupling.objects.filter(local_unit=new_club).exists()


@pytest.mark.parametrize("fehler", ["unerreichbar", "andere_schluessel"])
def test_plattform_uebergeht_ungepruefte_gegenstelle(
    api, orgs, club_c, board_c, monkeypatch, fehler
):
    instance_id = str(uuid.uuid4())

    def fake_info(base_url):
        if fehler == "unerreichbar":
            raise transport.PeerError("Selbstauskunft nicht abrufbar (HTTP 502).")
        return {
            "instance_id": instance_id,
            "base_url": base_url,
            "public_key": "C" * 43,
            "enc_public_key": "B" * 43,
            "fingerprint": "1" * 40,
        }

    monkeypatch.setattr(transport, "fetch_info", fake_info)
    content, _ = export(api(board_c), f"/api/orgs/{club_c['club'].pk}")
    c = api(_platform_admin())
    job = upload(c, "/api/platform", _with_peering(content, _peering(instance_id)))
    assert "ruhen, bis ein Vorstand" in _warnings(job)
    _run(c, "/api/platform", job)
    _nichts_angelegt(instance_id)


def test_plattform_kopplung_ruht_bis_zur_bestaetigung(api, orgs, club_c, board_c, monkeypatch):
    instance_id = str(uuid.uuid4())
    monkeypatch.setattr(
        transport,
        "fetch_info",
        lambda base_url: {
            "instance_id": instance_id,
            "base_url": base_url,
            **SCHLUESSEL,
            "fingerprint": "2" * 40,
        },
    )
    content, _ = export(api(board_c), f"/api/orgs/{club_c['club'].pk}")
    c = api(_platform_admin())
    job = _run(
        c,
        "/api/platform",
        upload(c, "/api/platform", _with_peering(content, _peering(instance_id))),
    )
    with rls_bypass():
        new_club = Organization.objects.get(pk=job["result_organization"]["id"])
        coupling = Coupling.objects.get(local_unit=new_club)
        assert coupling.state == Coupling.State.MOVING
        assert coupling.options["move"]["import"] is True
        assert coupling.options["move"]["fingerprint"] == "2" * 40
        assert coupling.options["move"]["previous"] == Coupling.State.ACTIVE
        # Bis zur Bestätigung geht nichts hinaus, nichts herein, kein Abgleich
        monkeypatch.setattr(transport, "call", lambda *a, **k: pytest.fail("Gegenstelle angefragt"))
        platform = PlatformSettings.load()
        platform.peering_enabled = True  # auch bei eingeschaltetem Verbund
        platform.save()
        assert services.sync(coupling) == 0
        services.deliver(coupling.pk)
        assert services.reconcile(coupling) == []
        with pytest.raises(services.Refused) as refused:
            services._receive(
                coupling, {"kind": "unit", "seq": 1, "msg_id": str(uuid.uuid4()), "data": {}}
            )
        assert refused.value.status == 423
        assert not Message.objects.filter(coupling=coupling).exists()


def test_abgeschalteter_verbund_versendet_nichts(orgs, monkeypatch):
    settings = PlatformSettings.load()
    assert not settings.peering_enabled
    with rls_bypass():
        peer = Peer.objects.create(
            instance_id=uuid.uuid4(), base_url=FREMD, fingerprint="3" * 40, **SCHLUESSEL
        )
        placeholder = services._placeholder(
            "Ferner Musterverband", parent=Organization.platform(), type_="federation"
        )
        coupling = Coupling.objects.create(
            local_unit=orgs["a"],
            remote_unit=placeholder,
            remote_uuid=uuid.uuid4(),
            peer=peer,
            direction=Coupling.Direction.PARENT,
            state=Coupling.State.ACTIVE,
            packets={"unit": "on"},
        )
        msg = Message.objects.create(
            coupling=coupling, direction=Message.Direction.OUT, seq=1, kind="unit"
        )
    calls = []
    monkeypatch.setattr(transport, "call", lambda *a, **k: calls.append(a) or {})
    monkeypatch.setattr(transport, "_http", lambda *a, **k: calls.append(a))
    with rls_bypass():
        assert services.sync(coupling) == 0
        services.sync_all()
        services.deliver_due()
        services.deliver(coupling.pk)
        services.reconcile_all()
        msg.refresh_from_db()
    assert calls == []
    assert msg.state == Message.State.QUEUED
    assert Message.objects.filter(coupling=coupling).count() == 1
