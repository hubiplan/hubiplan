"""Material vor Ort (Anmeldung A6, Konzept 3.11): Namensschild, Tasche, Leihgerät … ausgeben
und, wenn vorgesehen, zurücknehmen. Abgehakt wird in der Verwaltung oder über einen Scan-Link
mit der Station „Ausgabe“ bzw. „Rückgabe“."""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Handout, Material, Participant, Registration

MAX_MATERIALS = 10


def material_data(m: Material) -> dict:
    return {"id": m.pk, "name": m.name, "returnable": m.returnable, "is_active": m.is_active}


def handout_data(h: Handout | None) -> dict | None:
    if h is None:
        return None
    return {"handed_out_at": h.handed_out_at, "returned_at": h.returned_at, "via": h.via}


def board(setup) -> dict:
    """Liste für die Verwaltung: alle Personen verbindlicher Anmeldungen mit Stand je Material."""
    materials = list(setup.materials.filter(is_active=True))
    handouts = {
        (h.material_id, h.participant_id): h for h in Handout.objects.filter(material__setup=setup)
    }
    people = sorted(
        Participant.objects.filter(
            registration__setup=setup,
            registration__status=Registration.Status.REGISTERED,
            status=Participant.Status.ACTIVE,
        ).select_related("registration"),
        key=lambda p: (p.name.casefold(), p.pk),
    )
    return {
        "materials": [material_data(m) for m in materials],
        "rows": [
            {
                "id": p.pk,
                "name": p.name,
                "number": p.registration.display_number,
                "price_name": p.price_name,
                "items": {str(m.pk): handout_data(handouts.get((m.pk, p.pk))) for m in materials},
            }
            for p in people
        ],
        "counts": {
            str(m.pk): {
                "out": sum(1 for (mid, _pid), h in handouts.items() if mid == m.pk),
                "returned": sum(
                    1 for (mid, _pid), h in handouts.items() if mid == m.pk and h.returned_at
                ),
            }
            for m in materials
        },
    }


def apply(material: Material, p: Participant, action: str, *, user=None, via: str = ""):
    """``out`` ausgeben, ``return`` zurücknehmen, ``undo`` letzten Schritt zurücknehmen.
    Liefert (Ergebnis, Handout oder None); Ergebnis ``ok``, ``already`` oder ``not_out``."""
    now = timezone.now()
    h = Handout.objects.select_for_update().filter(material=material, participant=p).first()
    if action == "out":
        if h is not None:
            return "already", h
        h = Handout.objects.create(
            material=material, participant=p, handed_out_at=now, user=user, via=via[:100]
        )
        return "ok", h
    if action == "return":
        if h is None:
            return "not_out", None
        if h.returned_at is not None:
            return "already", h
        h.returned_at = now
        h.save(update_fields=["returned_at"])
        return "ok", h
    # undo: Rückgabe zurücknehmen, sonst die Ausgabe
    if h is None:
        return "not_out", None
    if h.returned_at is not None:
        h.returned_at = None
        h.save(update_fields=["returned_at"])
        return "ok", h
    h.delete()
    return "ok", None


def station(material: Material, returning: bool) -> str:
    if returning:
        return _("Rückgabe: {name}").format(name=material.name)
    return _("Ausgabe: {name}").format(name=material.name)


def card_items(p: Participant) -> list[dict]:
    """Material dieser Person für die Scan-Anzeige."""
    have = {h.material_id: h for h in Handout.objects.filter(participant=p)}
    return [
        {
            "id": m.pk,
            "name": m.name,
            "returnable": m.returnable,
            "handed_out_at": have[m.pk].handed_out_at if m.pk in have else None,
            "returned_at": have[m.pk].returned_at if m.pk in have else None,
        }
        for m in p.registration.setup.materials.filter(is_active=True)
    ]
