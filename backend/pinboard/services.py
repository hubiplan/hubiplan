"""Pinnwand: Beiträge anlegen, Fotos, wer was sieht, Zähler „neu“, Aufräumen."""

from __future__ import annotations

import datetime
import io

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from PIL import Image
from rest_framework.exceptions import ValidationError

from core.tenancy import rls_bypass

from .models import MAX_PHOTOS, MAX_TEXT, Notice, NoticePhoto, NoticeSeen

# Ohne „Anzeigen bis“ bleibt ein Beitrag so lange stehen, angeheftete bis zum Lösen
KEEP = datetime.timedelta(days=365)
# So lange nach „Anzeigen bis“ sieht die Verwaltung den Beitrag noch, dann wird er gelöscht
AFTER = datetime.timedelta(days=30)
# Höchstens so viele Beiträge im Mitgliederbereich
MEMBER_LIMIT = 50


def today() -> datetime.date:
    return timezone.localdate()


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "on", "yes", "ja"}


def owner(notice: Notice) -> str:
    return notice.department.name if notice.department_id else notice.organization.name


def clean_fields(data, *, partial=False) -> dict:
    """Text, Anheften und „Anzeigen bis“ aus JSON oder Formulardaten prüfen."""
    out: dict = {}
    if not partial or "text" in data:
        text = str(data.get("text") or "").strip()
        if not text:
            raise ValidationError({"text": _("Bitte einen Text eingeben.")})
        if len(text) > MAX_TEXT:
            raise ValidationError({"text": _("Höchstens {n} Zeichen.").format(n=MAX_TEXT)})
        out["text"] = text
    if not partial or "pinned" in data:
        out["pinned"] = as_bool(data.get("pinned"))
    if not partial or "visible_until" in data:
        raw = data.get("visible_until") or None
        day = None
        if raw:
            try:
                day = parse_date(str(raw))
            except ValueError:
                day = None
            if day is None:
                raise ValidationError({"visible_until": _("Bitte ein gültiges Datum wählen.")})
            if day < today():
                raise ValidationError({"visible_until": _("Das Datum liegt in der Vergangenheit.")})
        out["visible_until"] = day
    return out


def author_name(user, org) -> str:
    """Name unter dem Beitrag: Person der Mitgliedschaft im Verein, sonst Name des Kontos."""
    from portal.models import PortalAccess

    with rls_bypass():
        access = (
            PortalAccess.objects.filter(user=user, organization=org, contact_person__isnull=True)
            .select_related("membership__person")
            .first()
        )
        if access and access.membership_id:
            person = access.membership.person
            name = f"{person.first_name} {person.last_name}".strip()
            if name:
                return name[:200]
    name = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return name[:200]


# --- Fotos ---


def image_content(upload, request=None) -> tuple[ContentFile, int, int]:
    from materials.services import image_content as clean

    content = clean(upload, request)
    with Image.open(io.BytesIO(content.read())) as img:
        width, height = img.size
    content.seek(0)
    return ContentFile(content.read(), name="pinnwand.jpg"), width, height


def add_photos(notice: Notice, uploads, request=None) -> None:
    from django.core.exceptions import ValidationError as DjangoValidationError

    from documents.services import check_budget

    uploads = [u for u in uploads or [] if u]
    if not uploads:
        return
    have = notice.photos.count()
    if have + len(uploads) > MAX_PHOTOS:
        raise ValidationError({"photos": _("Höchstens {n} Fotos je Beitrag.").format(n=MAX_PHOTOS)})
    position = have
    for upload in uploads:
        content, width, height = image_content(upload, request)
        try:
            check_budget(notice.organization, content.size)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        photo = NoticePhoto(
            organization=notice.organization,
            notice=notice,
            position=position,
            size=content.size,
            width=width,
            height=height,
        )
        try:
            photo.file.save("pinnwand.jpg", content, save=False)
            photo.save()
        except Exception:
            if photo.file:
                photo.file.storage.delete(photo.file.name)
            raise
        position += 1


def photo_deleted(sender, instance, **kwargs):
    storage, name = instance.file.storage, instance.file.name
    if name:
        transaction.on_commit(lambda: storage.delete(name))


# --- Daten ---


def notice_data(notice: Notice, prefix: str, *, can_edit: bool = False) -> dict:
    return {
        "id": notice.pk,
        "text": notice.text,
        "unit": notice.department.name if notice.department_id else "",
        "department": notice.department_id,
        "from": owner(notice),
        "author": notice.author,
        "pinned": notice.pinned,
        "visible_until": notice.visible_until,
        "created_at": notice.created_at,
        "edited_at": notice.edited_at,
        "pushed": notice.pushed_at is not None,
        "push": notice.push,
        "expired": bool(notice.visible_until and notice.visible_until < today()),
        "version": notice.version,
        "can_edit": can_edit,
        "photos": [
            {
                "id": p.pk,
                "url": f"{prefix}{notice.pk}/photos/{p.pk}/",
                "width": p.width,
                "height": p.height,
            }
            for p in notice.photos.all()
        ],
    }


def active(qs, on: datetime.date | None = None):
    on = on or today()
    return qs.filter(Q(visible_until__isnull=True) | Q(visible_until__gte=on))


def member_department_ids(org, membership_id: int) -> list[int]:
    """Untereinheiten des Mitglieds samt den Einheiten darüber."""
    from members.models import DepartmentMembership
    from organizations.tree import with_ancestors

    on = today()
    ids = list(
        DepartmentMembership.objects.filter(membership_id=membership_id, valid_from__lte=on)
        .exclude(valid_until__lt=on)
        .values_list("department_id", flat=True)
    )
    return sorted(with_ancestors(org.pk, ids) or ids)


def visible_for(org, membership_id: int):
    """Beiträge, die ein Mitglied sieht: Verein und eigene Untereinheiten, noch aktuell."""
    depts = member_department_ids(org, membership_id)
    qs = Notice.objects.filter(organization=org).filter(
        Q(department__isnull=True) | Q(department_id__in=depts)
    )
    return active(qs).select_related("department", "organization").prefetch_related("photos")


def seen_at(membership_id: int):
    row = NoticeSeen.objects.filter(membership_id=membership_id).first()
    return row.seen_at if row else None


def new_count(org, membership_id: int) -> int:
    """Beiträge seit dem letzten Lesen (beim ersten Mal: der letzten 14 Tage)."""
    since = seen_at(membership_id) or timezone.now() - datetime.timedelta(days=14)
    return visible_for(org, membership_id).filter(created_at__gt=since).count()


def mark_seen(org, membership_id: int) -> None:
    NoticeSeen.objects.update_or_create(
        membership_id=membership_id,
        defaults={"organization": org, "seen_at": timezone.now()},
    )


def recipients(notice: Notice) -> list[int]:
    from circulars.recipients import club_base

    return list(
        club_base(notice.organization, notice.department)
        .order_by()
        .values_list("pk", flat=True)
        .distinct()
    )


def purge_due(now: datetime.datetime | None = None) -> int:
    """Abgelaufene Beiträge nach 30 Tagen löschen, nicht angeheftete ohne Datum nach einem Jahr."""
    now = now or timezone.now()
    day = timezone.localdate(now)
    with rls_bypass():
        qs = Notice.objects.filter(
            Q(visible_until__lt=day - AFTER)
            | Q(visible_until__isnull=True, pinned=False, created_at__lt=now - KEEP)
        )
        n = 0
        for notice in qs.iterator():
            notice.delete()
            n += 1
    return n
