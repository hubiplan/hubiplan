"""Zeitleiste: mehrere Bilder je Ereignis (Ralf 02.11.). Aus ``image`` wird ``images``."""

from django.db import migrations


def _convert(entries):
    if not isinstance(entries, list):
        return entries, False
    changed = False
    result = []
    for e in entries:
        if isinstance(e, dict) and "images" not in e:
            image = e.get("image")
            e = {k: v for k, v in e.items() if k != "image"}
            e["images"] = [image] if isinstance(image, int) else []
            changed = True
        result.append(e)
    return result, changed


def forwards(apps, schema_editor):
    for model, fields in (
        ("WebsiteText", ("timeline", "published_timeline")),
        ("WebsiteRevision", ("timeline",)),
    ):
        objects = apps.get_model("website", model).objects
        if model == "WebsiteRevision":
            objects = objects.exclude(timeline=[])
        for obj in objects.iterator():
            update = []
            for field in fields:
                value, changed = _convert(getattr(obj, field))
                if changed:
                    setattr(obj, field, value)
                    update.append(field)
            if update:
                obj.save(update_fields=update)


class Migration(migrations.Migration):
    dependencies = [("website", "0029_zeitleiste_reihenfolge")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
