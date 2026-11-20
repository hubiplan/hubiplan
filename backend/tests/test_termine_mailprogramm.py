"""Termine aus dem Mailprogramm: Einladungen an Verteiler werden Termine (events/mail_intake.py),
Antworten auf HUBIplans Einladungen werden Zu- und Absagen (W1b). Alle Daten erfunden."""
# ruff: noqa: F811  (Fixtures als Parameter)

import datetime
from email.message import EmailMessage
from unittest import mock

import pytest
from django.test import Client
from django.utils import timezone

from circulars import inbound, services
from circulars.models import Circular, CircularRecipient, InboundMail
from events import imip, mail_intake, rsvp
from events.models import Event, EventResponse
from outbox.models import OutgoingMail

from .factories import make_user
from .test_m12_events import (  # noqa: F401  (Fixtures)
    JSON,
    cal,
    private_root,
    zug,
    zug2,
)
from .test_mailverteiler import DOMAIN, PDF, base, create_list, members  # noqa: F401

pytestmark = pytest.mark.django_db

ORGANIZER = "vorstand-a@example.org"
UID = "040000008200E00074C5B7101A82E008000000001234@example.org"


@pytest.fixture(autouse=True)
def verteiler_settings(settings, private_root):
    settings.INBOUND_DOMAINS = [DOMAIN]
    settings.INBOUND_SIMULATION = True
    settings.INBOUND_IMAP_HOST = ""
    settings.MAIL_RATE_PER_HOUR = 0
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.EMAIL_BACKEND = "outbox.backend.OutboxBackend"


def ics(
    method: str = "REQUEST",
    *,
    uid: str = UID,
    sequence: int = 0,
    start: str = "20991203T193000",
    end: str = "20991203T213000",
    summary: str = "Vorstandssitzung",
    location: str = "Vereinsheim",
    description: str = "Tagesordnung folgt.",
    organizer: str = ORGANIZER,
    attendee: str = f"alle@{DOMAIN}",
    extra: str = "",
) -> str:
    """Einladung wie aus Outlook (Windows-Zeitzone, Zeilen mit CRLF)."""
    lines = [
        "BEGIN:VCALENDAR",
        f"METHOD:{method}",
        "PRODID:Microsoft Exchange Server 2010",
        "VERSION:2.0",
        "BEGIN:VEVENT",
        f"ORGANIZER;CN=Anna Vorstand:mailto:{organizer}",
        f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee}",
        f"DESCRIPTION;LANGUAGE=de-DE:{description}",
        f"UID:{uid}",
        f"SUMMARY;LANGUAGE=de-DE:{summary}",
        f"DTSTART;TZID=W. Europe Standard Time:{start}",
        f"DTEND;TZID=W. Europe Standard Time:{end}",
        f"SEQUENCE:{sequence}",
        f"LOCATION;LANGUAGE=de-DE:{location}",
        *([extra] if extra else []),
        "BEGIN:VALARM",
        "TRIGGER:-PT15M",
        "ACTION:DISPLAY",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def invitation(
    calendar: str,
    sender: str = ORGANIZER,
    to: str = f"alle@{DOMAIN}",
    subject: str = "Einladung: Vorstandssitzung",
    pdf: bytes | None = None,
    **headers,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"Anna Vorstand <{sender}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{abs(hash((sender, to, subject, calendar)))}@example.org>"
    for name, value in headers.items():
        msg[name.replace("_", "-")] = value
    msg.set_content("Tagesordnung folgt.")
    method = "REQUEST"
    for line in calendar.splitlines():
        if line.startswith("METHOD:"):
            method = line[7:]
    msg.add_alternative(calendar, subtype="calendar", params={"method": method})
    if pdf is not None:
        msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="Tagesordnung.pdf")
    return msg.as_bytes()


def confirm_url(entry: InboundMail) -> str:
    return f"/api/public/circulars/confirm/{inbound.confirm_token(entry)}/"


def last_note(user, prefix: str = "") -> OutgoingMail:
    mails = OutgoingMail.objects.filter(kind="verteiler", to__contains=user.email)
    if prefix:
        mails = mails.filter(subject__startswith=prefix)
    return mails.latest("created_at")


class TestLesen:
    def test_outlook_einladung(self):
        found = imip.read(
            ics(description="Bitte pünktlich.\\nhttps://cloud.example.org/call/ab12cd34")
        )
        assert found.method == "REQUEST" and found.uid == UID and found.sequence == 0
        assert found.organizer == ORGANIZER and found.title == "Vorstandssitzung"
        local = timezone.localtime(found.starts_at)
        assert (local.hour, local.minute) == (19, 30)
        assert found.ends_at - found.starts_at == datetime.timedelta(hours=2)
        assert found.video_url == "https://cloud.example.org/call/ab12cd34"
        assert found.location == "Vereinsheim"

    def test_nextcloud_talk_link_als_ort(self):
        found = imip.read(ics(location="https://cloud.example.org/index.php/call/xy98zz77"))
        assert found.video_url == "https://cloud.example.org/index.php/call/xy98zz77"
        assert found.location == ""

    def test_konferenz_feld(self):
        extra = "CONFERENCE;VALUE=URI;FEATURE=VIDEO:https://meet.jit.si/Musterverein-Sitzung"
        assert imip.read(ics(extra=extra)).video_url == "https://meet.jit.si/Musterverein-Sitzung"

    def test_videolinks_anderer_dienste(self):
        assert imip.video_link("Teams: https://teams.microsoft.com/l/meetup-join/abc") == (
            "https://teams.microsoft.com/l/meetup-join/abc"
        )
        assert imip.video_link("(https://zoom.us/j/123456).") == "https://zoom.us/j/123456"
        assert imip.video_link("https://www.example.org/anfahrt") == ""

    def test_ganztaegig_und_ohne_ende(self):
        cal = ics().replace(
            "DTSTART;TZID=W. Europe Standard Time:20991203T193000", "DTSTART;VALUE=DATE:20991203"
        )
        cal = cal.replace("DTEND;TZID=W. Europe Standard Time:20991203T213000\r\n", "")
        found = imip.read(cal)
        assert found.all_day and found.starts_at == found.ends_at

    def test_serie_mit_ausnahmen_abgewiesen(self):
        second = ics(extra="RECURRENCE-ID:20991210T193000").split("BEGIN:VEVENT", 1)[1]
        cal = ics(extra="RRULE:FREQ=WEEKLY").replace(
            "END:VCALENDAR", "BEGIN:VEVENT" + second.rsplit("END:VCALENDAR", 1)[0] + "END:VCALENDAR"
        )
        with pytest.raises(imip.NotUsable):
            imip.read(cal)

    def test_antwortcode(self):
        code = imip.reply_code(12, 345)
        assert imip.parse_reply_code(code) == (12, 345)
        assert imip.parse_reply_code(code[:-1] + ("0" if code[-1] != "0" else "1")) is None
        assert imip.parse_reply_code("12-346-" + code.rsplit("-", 1)[1]) is None
        assert len(f"termin+{imip.reply_code(10**11, 10**11)}") <= 64


class TestEinladungAnVerteiler:
    def test_bestaetigen_legt_termin_an_und_laedt_ein(
        self, cal, board_a, members, api, django_capture_on_commit_callbacks
    ):
        create_list(api(board_a), base(cal["a"]))
        with django_capture_on_commit_callbacks(execute=True):
            entry = inbound.process_message(
                invitation(
                    ics(description="Bitte zusagen.\\nhttps://cloud.example.org/call/ab12cd34"),
                    pdf=PDF,
                )
            )
        assert entry.status == InboundMail.Status.WAITING and entry.user == board_a
        assert entry.circular_id is None and entry.event_data["action"] == "new"
        assert not Event.objects.filter(mail_uid=UID).exists()
        note = last_note(board_a, "Bitte bestätigen")
        assert "/rundschreiben/bestaetigen/" in note.body and "Vorstandssitzung" in note.body
        public = Client()
        data = public.get(confirm_url(entry)).json()
        assert data["event"]["title"] == "Vorstandssitzung"
        assert data["event"]["attachments"] == ["Tagesordnung.pdf"]
        assert data["event"]["options"] == {
            "rsvp_possible": True,
            "rsvp": True,
            "video_possible": False,
            "video": False,
        }
        assert data["event"]["visibility"] == "members"
        with django_capture_on_commit_callbacks(execute=True):
            resp = public.post(confirm_url(entry), {"action": "send"}, content_type=JSON)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["status"] == "sent" and resp.json()["event"]["event_url"]
        event = Event.objects.get(mail_uid=UID)
        assert event.visibility == Event.Visibility.MEMBERS and event.rsvp_enabled
        assert event.created_by == board_a and event.mail_organizer == ORGANIZER
        assert event.video_url == "https://cloud.example.org/call/ab12cd34"
        assert [a.name for a in event.attachments.all()] == ["Tagesordnung.pdf"]
        circular = Circular.objects.get(event=event)
        assert circular.status == Circular.Status.SENT
        assert CircularRecipient.objects.filter(circular=circular).count() == 2
        sent = OutgoingMail.objects.filter(kind="rundschreiben")
        assert sent.count() == 2
        assert "Video: https://cloud.example.org/call/ab12cd34" in sent.first().body
        assert "Zu- oder absagen" in sent.first().body
        # Organisator bekommt „angenommen“ (sein Kalender zeigt es) und das Ergebnis
        assert OutgoingMail.objects.filter(to=ORGANIZER, subject__startswith="Angenommen:").exists()
        done = last_note(board_a, "Termin angelegt")
        assert "Videoraum: https://cloud.example.org/call/ab12cd34" in done.body
        # Zweiter Klick tut nichts
        resp = public.post(confirm_url(entry), {"action": "send"}, content_type=JSON)
        assert resp.status_code == 400
        assert Event.objects.filter(mail_uid=UID).count() == 1

    def test_aenderung_und_absage(
        self, cal, board_a, members, api, django_capture_on_commit_callbacks
    ):
        create_list(api(board_a), base(cal["a"]))
        entry = inbound.process_message(invitation(ics()))
        mail_intake.apply(entry, rsvp=False)
        event = Event.objects.get(mail_uid=UID)
        assert not event.rsvp_enabled and event.changed_at is None
        # Gleiche Fassung noch einmal: keine Änderung
        again = inbound.process_message(invitation(ics(), subject="Nochmal"))
        assert again.status == InboundMail.Status.REJECTED and again.reason == "Keine Änderung."
        # Neue Zeit
        changed = inbound.process_message(
            invitation(
                ics(sequence=1, start="20991204T190000", end="20991204T210000"),
                subject="Geändert: Vorstandssitzung",
            )
        )
        assert changed.status == InboundMail.Status.WAITING
        assert changed.event_data["action"] == "update"
        with django_capture_on_commit_callbacks(execute=True):
            mail_intake.apply(changed)
        event.refresh_from_db()
        assert timezone.localtime(event.starts_at).day == 4 and event.changed_at is not None
        assert Circular.objects.filter(event=event, subject__startswith="Geändert:").exists()
        # Ältere Fassung kommt zu spät: abgewiesen
        late = inbound.process_message(invitation(ics(sequence=0, summary="Alt"), subject="Alt"))
        assert late.status == InboundMail.Status.REJECTED
        # Absage
        cancel = inbound.process_message(
            invitation(ics("CANCEL", sequence=2), subject="Abgesagt: Vorstandssitzung")
        )
        assert cancel.event_data["action"] == "cancel"
        mail_intake.apply(cancel)
        event.refresh_from_db()
        assert event.is_cancelled
        assert Circular.objects.filter(event=event, subject__startswith="Abgesagt:").exists()

    def test_neuere_einladung_ersetzt_wartende(self, cal, board_a, members, api):
        create_list(api(board_a), base(cal["a"]))
        first = inbound.process_message(invitation(ics()))
        second = inbound.process_message(invitation(ics(sequence=1, summary="Neu"), subject="B"))
        first.refresh_from_db()
        assert first.status == InboundMail.Status.REJECTED and "neuere" in first.reason
        assert second.status == InboundMail.Status.WAITING
        resp = Client().post(confirm_url(first), {"action": "send"}, content_type=JSON)
        assert resp.status_code == 400

    def test_absage_vor_uebernahme(self, cal, board_a, members, api):
        create_list(api(board_a), base(cal["a"]))
        first = inbound.process_message(invitation(ics()))
        cancel = inbound.process_message(invitation(ics("CANCEL", sequence=1), subject="Ab"))
        first.refresh_from_db()
        assert first.status == InboundMail.Status.REJECTED
        assert cancel.status == InboundMail.Status.REJECTED
        assert not Event.objects.filter(mail_uid=UID).exists()

    def test_vorstandsverteiler_nur_vorstand_ohne_rueckmeldung(
        self, cal, board_a, members, api, django_capture_on_commit_callbacks
    ):
        c = api(board_a)
        data = create_list(c, base(cal["a"]), name="Vorstand", local_part="vorstand")
        resp = c.patch(
            f"{base(cal['a'])}{data['pattern_id']}/",
            {"audience": "roles", "filters": {}},
            content_type=JSON,
        )
        assert resp.status_code == 200, resp.json()
        entry = inbound.process_message(invitation(ics(), to=f"vorstand@{DOMAIN}"))
        options = Client().get(confirm_url(entry)).json()["event"]["options"]
        assert options["rsvp_possible"] is False
        with django_capture_on_commit_callbacks(execute=True):
            mail_intake.apply(entry, rsvp=True)
        event = Event.objects.get(mail_uid=UID)
        assert event.visibility == Event.Visibility.BOARD and not event.rsvp_enabled
        circular = Circular.objects.get(subject__contains="Vorstandssitzung")
        assert circular.event_id is None and circular.audience == "roles"
        assert circular.status == Circular.Status.SENT

    def test_nextcloud_von_noreply_mit_antwort_an(self, cal, board_a, members, api, settings):
        settings.MAIL_AUTHSERV_ID = "mx.example.org"
        create_list(api(board_a), base(cal["a"]), mode="direct")
        entry = inbound.process_message(
            invitation(
                ics(location="https://cloud.example.org/call/nc11talk"),
                sender="noreply@cloud.example.org",
                Reply_To=ORGANIZER,
                Authentication_Results="mx.example.org; dkim=pass; dmarc=pass",
            )
        )
        # Konto des Organisators, aber nicht direkt: die Mail kam nicht von ihm selbst
        assert entry.user == board_a and entry.status == InboundMail.Status.WAITING
        assert entry.event_data["video_url"] == "https://cloud.example.org/call/nc11talk"

    def test_direkt_mit_dmarc(
        self, cal, board_a, members, api, settings, django_capture_on_commit_callbacks
    ):
        settings.MAIL_AUTHSERV_ID = "mx.example.org"
        create_list(api(board_a), base(cal["a"]), mode="direct")
        with django_capture_on_commit_callbacks(execute=True):
            entry = inbound.process_message(
                invitation(
                    ics(),
                    Authentication_Results="mx.example.org; spf=pass; dkim=pass; dmarc=pass",
                )
            )
        assert entry.status == InboundMail.Status.SENT and entry.event_id
        assert last_note(board_a, "Termin angelegt")

    def test_fremde_und_offene_verteiler(self, cal, board_a, members, api):
        create_list(api(board_a), base(cal["a"]), open_senders=True)
        entry = inbound.process_message(
            invitation(ics(organizer="fremd@example.net"), sender="fremd@example.net")
        )
        assert entry.status == InboundMail.Status.REJECTED
        assert not OutgoingMail.objects.filter(to__contains="fremd@example.net").exists()
        assert not Event.objects.exists()

    def test_nur_terminrecht(self, cal, board_a, members, api):
        from .factories import give_role

        create_list(api(board_a), base(cal["a"]))
        writer = make_user("schreiber@example.org")
        give_role(writer, cal["a"], name="Rundschreiben", permissions=["circulars.send"])
        entry = inbound.process_message(
            invitation(ics(organizer=writer.email), sender=writer.email)
        )
        assert entry.status == InboundMail.Status.REJECTED
        assert "keine Termine" in entry.reason

    def test_unbekannte_serie_mit_grund(self, cal, board_a, members, api):
        create_list(api(board_a), base(cal["a"]))
        entry = inbound.process_message(invitation(ics(extra="RRULE:FREQ=MONTHLY;BYDAY=2TU")))
        assert entry.status == InboundMail.Status.REJECTED
        assert "Serie" in last_note(board_a, "Nicht übernommen").body

    def test_woechentliche_serie(self, cal, board_a, members, api):
        create_list(api(board_a), base(cal["a"]))
        entry = inbound.process_message(
            invitation(ics(extra="RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=TH;UNTIL=20991231T225959Z"))
        )
        assert entry.status == InboundMail.Status.WAITING
        mail_intake.apply(entry, rsvp=True)
        event = Event.objects.get(mail_uid=UID)
        assert event.repeat == "weekly" and event.repeat_interval == 2
        assert event.repeat_until == datetime.date(2099, 12, 31) and not event.rsvp_enabled

    def test_outlook_winmail(self, cal, board_a, members, api):
        create_list(api(board_a), base(cal["a"]))
        msg = EmailMessage()
        msg["From"] = board_a.email
        msg["To"] = f"alle@{DOMAIN}"
        msg["Subject"] = "Besprechung"
        msg["Message-ID"] = "<tnef@example.org>"
        msg["Content-Class"] = "urn:content-classes:calendarmessage"
        msg.set_content("x")
        msg.add_attachment(
            b"x\x9f>", maintype="application", subtype="ms-tnef", filename="winmail.dat"
        )
        entry = inbound.process_message(msg.as_bytes())
        assert entry.status == InboundMail.Status.REJECTED
        assert "winmail.dat" in last_note(board_a, "Nicht übernommen").body

    def test_verwerfen_loescht_anhaenge(self, cal, board_a, members, api):
        from exchange.models import private_storage

        create_list(api(board_a), base(cal["a"]))
        entry = inbound.process_message(invitation(ics(), pdf=PDF))
        path = entry.event_data["files"][0]["path"]
        assert private_storage().exists(path)
        resp = Client().post(confirm_url(entry), {"action": "discard"}, content_type=JSON)
        assert resp.status_code == 200 and resp.json()["status"] == "rejected"
        assert not private_storage().exists(path)
        assert not Event.objects.exists()

    def test_einstellungen_am_verteiler(self, cal, board_a, api):
        c = api(board_a)
        data = create_list(c, base(cal["a"]))
        assert data["event_rsvp"] is True and data["event_video"] is False
        url = f"{base(cal['a'])}lists/{data['id']}/"
        resp = c.patch(url, {"event_video": True, "event_rsvp": False}, content_type=JSON)
        assert resp.status_code == 200
        detail = c.get(url).json()
        assert detail["event_video"] is True and detail["event_rsvp"] is False
        assert detail["talk_available"] is False

    def test_termin_reserviert(self, cal, board_a, api):
        resp = api(board_a).post(
            f"{base(cal['a'])}lists/", {"name": "T", "local_part": "termin"}, content_type=JSON
        )
        assert resp.status_code == 400

    def test_videoraum_wenn_kein_link(
        self, cal, board_a, members, api, django_capture_on_commit_callbacks
    ):
        c = api(board_a)
        data = create_list(c, base(cal["a"]))
        c.patch(f"{base(cal['a'])}lists/{data['id']}/", {"event_video": True}, content_type=JSON)
        entry = inbound.process_message(invitation(ics()))
        with (
            mock.patch.object(mail_intake, "talk_available", return_value=True),
            mock.patch.object(
                mail_intake, "create_room", return_value="https://cloud.example.org/call/neu12345"
            ) as room,
            django_capture_on_commit_callbacks(execute=True),
        ):
            assert Client().get(confirm_url(entry)).json()["event"]["options"]["video"] is True
            mail_intake.apply(entry)
        room.assert_called_once()
        body = OutgoingMail.objects.filter(kind="rundschreiben").first().body
        assert "Video: https://cloud.example.org/call/neu12345" in body
        assert "https://cloud.example.org/call/neu12345" in last_note(board_a, "Termin").body


class TestAnnehmenImMailprogramm:
    @pytest.fixture
    def event(self, cal, board_a):
        return Event.objects.create(
            organization=cal["a"],
            title="Sommerfest",
            starts_at=timezone.now() + datetime.timedelta(days=30),
            ends_at=timezone.now() + datetime.timedelta(days=30, hours=4),
            visibility=Event.Visibility.MEMBERS,
            rsvp_enabled=True,
            rsvp_maybe=True,
        )

    def reply_mail(self, sender: str, code: str, partstat: str = "ACCEPTED") -> bytes:
        cal = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "METHOD:REPLY",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "UID:1-20991203T183000Z@hubiplan.example.org",
                f"ATTENDEE;PARTSTAT={partstat}:mailto:{sender}",
                "END:VEVENT",
                "END:VCALENDAR",
                "",
            ]
        )
        return invitation(cal, sender=sender, to=f"termin+{code}@{DOMAIN}", subject="Zusage")

    def test_kalenderteil_und_antwort(self, cal, members, event, settings):
        settings.INBOUND_IMAP_HOST = "imap.example.org"
        anna = members["anna"]
        address = rsvp.email_of(anna)
        part = mail_intake.calendar_for(event, anna.pk, address, "Anna")
        assert part is not None and part[1] == "REQUEST"
        assert (
            "ORGANIZER;CN=" in part[0] and f"termin+{imip.reply_code(event.pk, anna.pk)}" in part[0]
        )
        assert f"mailto:{address}" in part[0] and "RSVP=TRUE" in part[0]
        # Zusage aus dem Mailprogramm
        code = imip.reply_code(event.pk, anna.pk)
        entry = inbound.process_message(self.reply_mail(address, code))
        assert entry.status == InboundMail.Status.SENT, entry.reason
        response = EventResponse.objects.get(event=event, membership=anna)
        assert response.status == "yes" and response.source == EventResponse.Source.MAIL
        # Vielleicht, dann Absage
        inbound.process_message(self.reply_mail(address, code, "TENTATIVE"))
        response.refresh_from_db()
        assert response.status == "maybe"
        inbound.process_message(self.reply_mail(address, code, "DECLINED"))
        response.refresh_from_db()
        assert response.status == "no"

    def test_falscher_code_oder_absender(self, cal, members, event, settings):
        settings.INBOUND_IMAP_HOST = "imap.example.org"
        anna, bernd = members["anna"], members["bernd"]
        address = rsvp.email_of(anna)
        bad = imip.reply_code(event.pk, anna.pk)[:-1] + "0"
        entry = inbound.process_message(self.reply_mail(address, bad))
        assert entry.status == InboundMail.Status.REJECTED
        # Code von Anna, Antwort von Bernd
        code = imip.reply_code(event.pk, anna.pk)
        entry = inbound.process_message(self.reply_mail(rsvp.email_of(bernd), code))
        assert entry.status == InboundMail.Status.REJECTED
        assert not EventResponse.objects.exists()

    def test_ohne_postfach_oder_mit_abo_kein_kalenderteil(self, cal, members, event, settings):
        anna = members["anna"]
        address = rsvp.email_of(anna)
        assert mail_intake.calendar_for(event, anna.pk, address, "") is None  # kein Postfach
        settings.INBOUND_IMAP_HOST = "imap.example.org"
        event.mail_organizer = address
        assert mail_intake.calendar_for(event, anna.pk, address, "") is None  # Organisator
        event.mail_organizer = ""
        event.rsvp_enabled = False
        assert mail_intake.calendar_for(event, anna.pk, address, "") is None  # ohne Rückmeldung

    def test_rundschreiben_zum_termin_traegt_kalenderteil(self, cal, members, event, settings):
        settings.INBOUND_IMAP_HOST = "imap.example.org"
        circular = Circular.objects.create(
            organization=cal["a"], subject="Sommerfest", body="Hallo", event=event
        )
        recipient = CircularRecipient(
            organization=cal["a"],
            circular=circular,
            membership=members["anna"],
            email=rsvp.email_of(members["anna"]),
        )
        part = services.calendar_part(recipient, circular)
        assert part is not None and "METHOD:REQUEST" in part[0]
