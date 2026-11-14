"""Räume in Orten: Gebäude mit Anschrift, darunter Räume.

Bestehende Orte wie „Bürgerhaus, Saal“ und „Bürgerhaus, Schießstand“ mit derselben
Anschrift werden zu einem Ort „Bürgerhaus“ mit den Räumen „Saal“ und „Schießstand“
zusammengeführt (mindestens zwei Räume). Die Nummern der Räume bleiben, damit
Verweise (Abschnitt „Anfahrt“ der Webseite) weiter stimmen. Termine tragen eine Kopie
von Ort und Anschrift und ändern sich nicht.
"""

from collections import defaultdict

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q

SEP = ", "


def _same(values):
    values = list(values)
    return values[0] if values and all(v == values[0] for v in values) else None


def merge_rooms(apps, schema_editor):
    from core.tenancy import rls_bypass

    with rls_bypass():
        _merge_rooms(apps)


def _merge_rooms(apps):
    Place = apps.get_model("places", "Place")
    groups = defaultdict(list)
    for place in Place.objects.filter(parent__isnull=True).order_by("pk"):
        if SEP not in place.name:
            continue
        building, room = place.name.split(SEP, 1)
        building, room = building.strip(), room.strip()
        if not building or not room:
            continue
        key = (place.organization_id, building.lower(), place.address.strip().lower())
        groups[key].append((place, building, room))
    for (org_id, _name, _address), rows in groups.items():
        if len(rows) < 2:
            continue
        places = [p for p, _b, _r in rows]
        name = rows[0][1]
        existing = Place.objects.filter(
            organization_id=org_id, parent__isnull=True, name__iexact=name
        ).first()
        if existing is not None and existing.address.strip().lower() not in (
            "",
            places[0].address.strip().lower(),
        ):
            continue  # gleichnamiger Ort an anderer Anschrift: nichts anfassen
        directions = _same(p.directions.strip() for p in places)
        point = _same((p.latitude, p.longitude) for p in places)
        if point is None:
            point = next(
                ((p.latitude, p.longitude) for p in places if p.latitude is not None),
                (None, None),
            )
        if existing is None:
            existing = Place.objects.create(
                organization_id=org_id,
                name=name,
                address=places[0].address.strip(),
                directions=directions or "",
                latitude=point[0],
                longitude=point[1],
                is_active=any(p.is_active for p in places),
                created_by_id=places[0].created_by_id,
            )
        else:
            if not existing.address.strip():
                existing.address = places[0].address.strip()
            if not existing.directions.strip() and directions:
                existing.directions = directions
            if existing.latitude is None and point[0] is not None:
                existing.latitude, existing.longitude = point
            if any(p.is_active for p in places):
                existing.is_active = True
            existing.save()
        for place, _building, room in rows:
            place.parent = existing
            place.name = room
            place.address = ""
            place.latitude = None
            place.longitude = None
            if directions is not None or place.directions.strip() == existing.directions.strip():
                place.directions = ""
            place.save()


def split_rooms(apps, schema_editor):
    from core.tenancy import rls_bypass

    Place = apps.get_model("places", "Place")
    with rls_bypass():
        rooms = list(Place.objects.filter(parent__isnull=False).select_related("parent"))
    for room in rooms:
        building = room.parent
        room.name = f"{building.name}{SEP}{room.name}"[:200]
        room.address = building.address
        room.latitude, room.longitude = building.latitude, building.longitude
        room.directions = "\n".join(
            x for x in (building.directions.strip(), room.directions.strip()) if x
        )[:1000]
        room.parent = None
        with rls_bypass():
            room.save()


class Migration(migrations.Migration):

    dependencies = [
        ("places", "0001_orte"),
    ]

    operations = [
        migrations.AddField(
            model_name="place",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rooms",
                to="places.place",
                verbose_name="Gebäude",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="place",
            name="ort_name_je_org",
        ),
        migrations.AddConstraint(
            model_name="place",
            constraint=models.UniqueConstraint(
                condition=Q(parent__isnull=True),
                fields=("organization", "name"),
                name="ort_name_je_org",
            ),
        ),
        migrations.AddConstraint(
            model_name="place",
            constraint=models.UniqueConstraint(
                condition=Q(parent__isnull=False),
                fields=("parent", "name"),
                name="raum_name_je_ort",
            ),
        ),
        migrations.RunPython(merge_rooms, split_rooms),
    ]
