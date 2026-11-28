"""Füllt den Demoverein so, dass die Antworten des Bereichs Mitglieder jedes Feld zeigen.

Alles geht über die Schnittstelle, wie es die Web-Oberfläche täte: Ehrung, Haushalt,
Rechnungsanschrift, Austritt, Foto, Organisation als Mitglied mit Ansprechpartner.
"""

from __future__ import annotations

import datetime

from django.test import Client
from django.utils import timezone

JSON = "application/json"


def fuelle(client: Client, club, ids: list[int], melde=None) -> None:
    basis = f"/api/orgs/{club.pk}/"
    heute = timezone.localdate()
    frueher = (heute - datetime.timedelta(days=400)).isoformat()

    def sende(methode: str, pfad: str, daten=None, erwartet=(200, 201), **mehr):
        # Dateien gehen als Formular, alles andere als JSON
        art = (
            {} if mehr.get("format") == "multipart" or methode == "get" else {"content_type": JSON}
        )
        antwort = getattr(client, methode)(basis + pfad, daten, **art)
        if melde:
            melde(methode, pfad, antwort.status_code, antwort.content[:300])
        assert antwort.status_code in erwartet, (pfad, antwort.status_code, antwort.content[:300])
        return antwort.json() if antwort.content else None

    a, b, c, d = ids[:4]
    # Ehrung des Vereins, verliehen mit eigenem Titel
    titel = sende(
        "post", "honorary-titles/", {"name": "Ehrenmitglied", "name_plural": "Ehrenmitglieder"}
    )
    sende(
        "post",
        f"members/{a}/honorary-titles/",
        {
            "title": titel["id"],
            "valid_from": frueher,
            "note": "Beschluss der Versammlung",
            "display_title": "Ehrenhauptmann",
        },
    )
    # eine zweite Ehrung, die schon endete
    sende(
        "post",
        f"members/{b}/honorary-titles/",
        {"title": titel["id"], "valid_from": frueher, "valid_until": heute.isoformat()},
    )
    # Haushalt mit zwei Mitgliedern
    haushalt = sende(
        "post", "households/", {"kind": "family", "name": "Familie Muster", "note": ""}
    )
    for pk in (a, b):
        sende(
            "post",
            f"households/{haushalt['id']}/members/",
            {"membership": pk, "valid_from": frueher},
        )
    # Abweichende Rechnungsanschrift
    sende(
        "put",
        f"members/{a}/billing-address/",
        {
            "name": "Muster GmbH",
            "attention": "Buchhaltung",
            "street": "Musterweg 1",
            "postal_code": "12345",
            "city": "Musterstadt",
            "country": "Deutschland",
            "email": "rechnung@muster.example",
            "order_reference": "B-1",
        },
    )
    # Austritt
    sende(
        "post",
        f"members/{c}/exit/",
        {"exit_date": heute.isoformat(), "exit_reason": "exit", "note": "auf eigenen Wunsch"},
    )
    # Werbung und Glückwünsche abbestellt, Mitgliedsnummer
    sende(
        "patch",
        f"members/{b}/",
        {"info_opt_out": True, "greetings_opt_out": True, "member_number": "M-0002"},
    )
    # Organisation als Mitglied mit Ansprechpartner (verknüpft und frei)
    art = sende("get", "member-types/")[0]["id"]
    firma = sende(
        "post",
        "members/admit/",
        {
            "kind": "organization",
            "last_name": "Bäckerei Muster GmbH",
            "legal_form": "gmbh",
            "size": 12,
            "entry_date": frueher,
            "member_type": art,
            "street": "Musterweg 2",
            "postal_code": "12345",
            "city": "Musterstadt",
            "email": "info@baeckerei-muster.example",
        },
    )
    sende(
        "post",
        f"members/{firma['id']}/contacts/",
        {"member": d, "function": "Geschäftsführung", "is_primary": True, "since": frueher},
    )
    sende(
        "post",
        f"members/{firma['id']}/contacts/",
        {
            "last_name": "Muster",
            "first_name": "Maria",
            "email": "maria@muster.example",
            "phone": "+49 30 1234567",
            "function": "Buchhaltung",
        },
    )
    # Ein Amt in einer Untereinheit endet
    for pk in ids:
        aemter = sende("get", f"members/{pk}/")["department_roles"]
        if aemter:
            sende(
                "patch",
                f"members/{pk}/department-roles/{aemter[0]['id']}/",
                {"valid_until": heute.isoformat()},
            )
            break
    # Ein Mitglied mit Zugang hat sich schon angemeldet
    from accounts.models import User
    from demodaten import korps

    User.objects.filter(email=korps.MEMBER_EMAIL).update(last_login=timezone.now())
    # Foto: vom Vorstand hochgeladen (gleich freigegeben) und eines, das noch zu prüfen ist
    sende("post", f"members/{a}/photo/", {"file": _foto(), "consent": "true"}, format="multipart")
    from members.photo_models import MemberPhoto

    MemberPhoto.objects.create(
        organization=club, membership_id=b, status=MemberPhoto.Status.PENDING, image=_foto()
    )


def _foto():
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    puffer = io.BytesIO()
    Image.new("RGB", (600, 800), (120, 140, 160)).save(puffer, "JPEG")
    return SimpleUploadedFile("foto.jpg", puffer.getvalue(), "image/jpeg")
