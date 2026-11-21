"""Bankweg FinTS (HBCI mit PIN und TAN) über die Bibliothek python-fints.

Grundsätze (konzepte „FinTS-Integration“):

- Die PIN kommt mit jedem Schritt vom Nutzer und wird nie gespeichert, auch nicht im
  angehaltenen Dialog. Deshalb hält dieses Modul den Dialog selbst an (``_pause``) statt mit
  ``pause_dialog`` der Bibliothek: Deren Abbild enthält die PIN und die gesendeten Nachrichten.
- Die Registrierungsnummer des Produkts steht nur in der Einstellung des Servers
  (``HUBIPLAN_FINTS_PRODUKT_ID``), nie im Quellcode.
- Verbunden wird über ``core.safehttp``: nur https, keine internen Adressen, keine
  Weiterleitungen.
"""

from __future__ import annotations

import base64
import datetime
import logging
from contextlib import contextmanager

from django.conf import settings
from django.utils.translation import gettext

from core import safehttp

from .bankweg import BankError, Bankweg, Step, fints_available

logger = logging.getLogger(__name__)
# Die Bibliothek protokolliert Nachrichten auf DEBUG; das bleibt aus
logging.getLogger("fints").setLevel(logging.WARNING)

MAX_RESPONSE = 20 * 1024 * 1024
PRODUCT_VERSION = "1"
ONE_STEP = "999"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def check_url(url: str) -> str:
    """FinTS-Adresse prüfen: https, öffentlich erreichbar."""
    import urllib.parse

    url = (url or "").strip()
    parts = urllib.parse.urlsplit(url)
    allow_http = settings.FINTS_ALLOW_INTERNAL
    if parts.scheme not in (("https", "http") if allow_http else ("https",)):
        raise BankError("connection", gettext("Die FinTS-Adresse muss mit https:// beginnen."))
    if not parts.hostname or parts.username or parts.password:
        raise BankError("connection", gettext("Die FinTS-Adresse ist ungültig."))
    return url


def _connection(url: str):
    from fints.connection import FinTSHTTPSConnection
    from fints.exceptions import FinTSConnectionError
    from fints.message import FinTSInstituteMessage

    class SafeConnection(FinTSHTTPSConnection):
        def __init__(self, url):  # keine requests-Sitzung
            self.url = url

        def send(self, msg):
            try:
                response = safehttp.request(
                    "POST",
                    self.url,
                    headers={"Content-Type": "text/plain"},
                    body=base64.b64encode(msg.render_bytes()),
                    timeout=30,
                    deadline=90,
                    max_body=MAX_RESPONSE,
                    allow_internal=settings.FINTS_ALLOW_INTERNAL,
                    allow_http=settings.FINTS_ALLOW_INTERNAL,
                )
            except safehttp.SafeHTTPError as exc:
                raise FinTSConnectionError(str(exc)) from exc
            if response.status < 200 or response.status > 299:
                raise FinTSConnectionError(f"Status {response.status}")
            if len(response.body) > MAX_RESPONSE:
                raise FinTSConnectionError("Antwort zu groß")
            try:
                raw = base64.b64decode(response.body.decode("iso-8859-1"))
            except ValueError as exc:
                raise FinTSConnectionError("Antwort nicht lesbar") from exc
            return FinTSInstituteMessage(segments=raw)

    return SafeConnection(url)


class FinTSWeg(Bankweg):
    key = "fints"
    label = "FinTS"

    def available(self) -> bool:
        return fints_available()

    # --- Schritte ---

    def start(self, access, secret: str, job: dict) -> Step:
        with self._errors() as bank_messages:
            client = self._client(access, secret, access.state, bank_messages)
            early = self._choose_mechanism(client, access, job)
            if early is not None:
                return early
            ctx = {"job": job, "pos": 0, "out": {}, "sepa": []}
            return self._run(client, ctx, bank_messages)

    def resume(self, access, secret: str, dialog: dict, tan: str) -> Step:
        with self._errors() as bank_messages:
            client = self._client(access, secret, dialog["client"], bank_messages)
            return self._run(client, dialog["ctx"], bank_messages, paused=dialog, tan=tan)

    # --- Aufbau ---

    def _client(self, access, pin: str, state: str, bank_messages: list):
        from fints.client import FinTS3PinTanClient

        if not self.available():
            raise BankError(
                "unsupported", gettext("FinTS ist auf diesem Server nicht eingerichtet.")
            )
        if not pin:
            raise BankError("pin", gettext("Bitte die PIN eingeben."))
        url = check_url(access.url)
        client = FinTS3PinTanClient(
            access.bank_code,
            access.login,
            pin,
            url,
            customer_id=access.customer_id or None,
            tan_medium=access.tan_medium or None,
            from_data=_unb64(state) if state else None,
            product_id=settings.FINTS_PRODUCT_ID,
            product_version=PRODUCT_VERSION,
        )
        client.connection = _connection(url)

        def remember(_segment, response):
            # Meldungen der Bank (ohne Geheimnisse) für die Fehlermeldung
            if response.code and response.code[0] == "9":
                bank_messages.append((response.code, str(response.text or "")[:200]))

        client.add_response_callback(remember)
        return client

    def _choose_mechanism(self, client, access, job: dict) -> Step | None:
        """TAN-Verfahren festlegen. Liefert einen Schritt, wenn der Nutzer wählen muss."""
        wanted = job.get("mechanism") or access.tan_mechanism
        if job["kind"] != "setup":
            if not client.get_current_tan_mechanism():
                raise BankError(
                    "unsupported", gettext("Bitte den Bankzugang zuerst fertig einrichten.")
                )
            return None
        client.fetch_tan_mechanisms()
        mechanisms = client.get_tan_mechanisms()
        choices = [
            {"id": key, "name": str(getattr(value, "name", "") or key)}
            for key, value in mechanisms.items()
            if key != ONE_STEP
        ]
        if wanted and wanted in mechanisms:
            client.set_tan_mechanism(wanted)
        elif len(choices) == 1:
            client.set_tan_mechanism(choices[0]["id"])
        elif len(choices) > 1:
            return Step(
                done=True,
                result={"need": "mechanism", "mechanisms": choices},
                state=_b64(client.deconstruct(including_private=True)),
            )
        else:
            client.set_tan_mechanism(ONE_STEP)
        current = client.get_current_tan_mechanism()
        job["_mechanism"] = current
        job["_mechanism_name"] = next((c["name"] for c in choices if c["id"] == current), "")
        medium = job.get("medium") or access.tan_medium
        if medium:
            client.selected_tan_medium = medium
        elif current in mechanisms and client.is_tan_media_required():
            _usage, media = client.get_tan_media()
            names = [str(m.tan_medium_name) for m in media if getattr(m, "tan_medium_name", "")]
            if len(names) == 1:
                client.selected_tan_medium = names[0]
            elif names:
                return Step(
                    done=True,
                    result={
                        "need": "medium",
                        "media": names,
                        "mechanism": current,
                        "mechanisms": choices,
                    },
                    state=_b64(client.deconstruct(including_private=True)),
                )
        job["_medium"] = client.selected_tan_medium or ""
        return None

    # --- Ablauf ---

    def _ops(self, job: dict) -> list[tuple]:
        ops: list[tuple] = [("init",), ("accounts",)]
        if job["kind"] == "fetch":
            for index, _account in enumerate(job["accounts"]):
                ops += [("tx", index), ("balance", index)]
        return ops

    def _run(self, client, ctx: dict, bank_messages: list, paused=None, tan: str = "") -> Step:
        from fints.client import NeedRetryResponse, NeedTANResponse

        ops = self._ops(ctx["job"])
        pos = ctx["pos"]
        waiting = None
        with self._dialog(client, paused) as dialog:
            if paused is not None:
                self._prime(client, ops[pos], ctx)
                challenge = NeedRetryResponse.from_data(_unb64(paused["tan"]))
                # Die Bibliothek speichert das Kennzeichen nicht mit
                challenge.decoupled = bool(paused["decoupled"])
                value = client.send_tan(challenge, "" if challenge.decoupled else (tan or ""))
                have = True
            else:
                value, have = None, False
            while pos < len(ops):
                if not have:
                    value = self._call(client, ops[pos], ctx)
                have = False
                if isinstance(value, NeedTANResponse):
                    waiting = value
                    ctx["pos"] = pos
                    break
                if isinstance(value, NeedRetryResponse):
                    raise BankError(
                        "unsupported",
                        gettext("Die Bank verlangt eine Bestätigung, die HUBIplan nicht kennt."),
                    )
                self._fail_on_bank_error(bank_messages)
                self._store(ops[pos], value, ctx)
                pos += 1
            state = self._pause(dialog) if waiting is not None else None
        client_state = _b64(client.deconstruct(including_private=True))
        if waiting is not None:
            image = ""
            if waiting.challenge_matrix:
                mime, data = waiting.challenge_matrix
                if mime in {"image/png", "image/jpeg", "image/gif"}:
                    image = f"data:{mime};base64,{_b64(data)}"
            return Step(
                done=False,
                challenge=str(waiting.challenge or "")[:1000],
                decoupled=bool(waiting.decoupled),
                image=image,
                dialog={
                    "dialog": state,
                    "tan": _b64(waiting.get_data()),
                    "decoupled": bool(waiting.decoupled),
                    "ctx": ctx,
                    "client": client_state,
                },
            )
        out = ctx["out"]
        job = ctx["job"]
        if job["kind"] == "setup":
            out["mechanism"] = job.get("_mechanism", "")
            out["mechanism_name"] = job.get("_mechanism_name", "")
            out["medium"] = job.get("_medium", "")
        return Step(done=True, result=out, state=client_state)

    def _fail_on_bank_error(self, bank_messages: list) -> None:
        if not bank_messages:
            return
        code, text = bank_messages[-1]
        del bank_messages[:]
        kind = "tan" if code in {"9941", "9951"} else "bank"
        raise BankError(
            kind,
            gettext("Die Bank meldet: {text} ({code})").format(text=text or "Fehler", code=code),
        )

    @contextmanager
    def _dialog(self, client, paused):
        """Stehender Dialog: neu (mit Anmeldung) oder fortgesetzt. Endet beim Verlassen,
        außer er wurde mit ``_pause`` angehalten."""
        if paused is None:
            with client:
                yield client._standing_dialog
            return
        from fints.message import MessageDirection

        data = paused["dialog"]
        dialog = client._new_dialog()
        dialog.dialog_id = data["id"]
        dialog.next_message_number = {
            MessageDirection.FROM_CUSTOMER: int(data["out"]),
            MessageDirection.FROM_INSTITUTE: int(data["in"]),
        }
        dialog.open = True
        dialog.need_init = False
        dialog.lazy_init = False
        client._standing_dialog = dialog
        # Wie nach einer Anmeldung: Fehler gelten nicht mehr als Erstkontakt
        client._bootstrap_mode = False
        try:
            with dialog:
                yield dialog
        finally:
            client._standing_dialog = None

    def _pause(self, dialog) -> dict:
        """Dialog anhalten, ohne PIN und ohne Nachrichten (anders als ``pause_dialog``)."""
        from fints.message import MessageDirection

        data = {
            "id": dialog.dialog_id,
            "out": dialog.next_message_number[MessageDirection.FROM_CUSTOMER],
            "in": dialog.next_message_number[MessageDirection.FROM_INSTITUTE],
        }
        dialog.paused = True
        return data

    # --- einzelne Aufträge ---

    def _sepa(self, ctx: dict, index: int):
        from fints.models import SEPAAccount

        wanted = ctx["job"]["accounts"][index]["iban"]
        for row in ctx["sepa"]:
            if row[0] == wanted:
                return SEPAAccount(*row)
        raise BankError(
            "bank",
            gettext("Das Konto {iban} gehört nicht zu diesem Bankzugang.").format(iban=wanted),
        )

    def _tx_plan(self, client, ctx: dict, index: int):
        """Auftrag für Umsätze: bevorzugt CAMT, sonst MT940."""
        from fints.formals import SupportedMessageTypes
        from fints.segments.statement import HKCAZ1, HKKAZ5, HKKAZ6, HKKAZ7

        account = self._sepa(ctx, index)
        spec = ctx["job"]["accounts"][index]
        start = datetime.date.fromisoformat(spec["from"])
        end = datetime.date.fromisoformat(spec["to"])
        hicazs = client.bpd.find_segment_first("HICAZS")
        if hicazs is not None:
            hkcaz = client._find_highest_supported_command(HKCAZ1)
            formats = list(hicazs.parameter.supported_camt_formats)

            def factory(touchdown):
                return hkcaz(
                    account=hkcaz._fields["account"].type.from_sepa_account(account),
                    all_accounts=False,
                    date_start=start,
                    date_end=end,
                    touchdown_point=touchdown,
                    supported_camt_messages=SupportedMessageTypes(formats),
                )

            def processor(responses):
                files = []
                for seg in responses:
                    files += [bytes(x) for x in seg.statement_booked.camt_statements]
                return {"camt": files}

            return factory, processor, "HICAZ"
        hkkaz = client._find_highest_supported_command(HKKAZ5, HKKAZ6, HKKAZ7)

        def factory(touchdown):
            return hkkaz(
                account=hkkaz._fields["account"].type.from_sepa_account(account),
                all_accounts=False,
                date_start=start,
                date_end=end,
                touchdown_point=touchdown,
            )

        def processor(responses):
            return {"mt940": b"".join(bytes(seg.statement_booked) for seg in responses)}

        return factory, processor, "HIKAZ"

    def _prime(self, client, op: tuple, ctx: dict) -> None:
        """Nach dem Fortsetzen: Zustand wiederherstellen, den die Bibliothek für das
        Weiterlesen der Umsätze im Client hält."""
        if op[0] != "tx":
            return
        factory, processor, name = self._tx_plan(client, ctx, op[1])
        client._touchdown_responses = []
        client._touchdown_counter = 1
        client._touchdown = None
        client._touchdown_dialog = client._standing_dialog
        client._touchdown_segment_factory = factory
        client._touchdown_response_processor = processor
        client._touchdown_args = (name,)
        client._touchdown_kwargs = {}

    def _call(self, client, op: tuple, ctx: dict):
        from fints.exceptions import FinTSUnsupportedOperation

        kind = op[0]
        if kind == "init":
            return client.init_tan_response
        if kind == "accounts":
            return client.get_sepa_accounts()
        if kind == "tx":
            factory, processor, name = self._tx_plan(client, ctx, op[1])
            return client._fetch_with_touchdowns(client._standing_dialog, factory, processor, name)
        if kind == "balance":
            try:
                return client.get_balance(self._sepa(ctx, op[1]))
            except FinTSUnsupportedOperation:
                return None
        raise AssertionError(kind)

    def _store(self, op: tuple, value, ctx: dict) -> None:
        kind = op[0]
        out = ctx["out"]
        if kind == "accounts":
            ctx["sepa"] = [list(a) for a in (value or [])]
            out["accounts"] = [{"iban": a.iban, "bic": a.bic or ""} for a in (value or [])]
        elif kind == "tx":
            entry = {"iban": ctx["job"]["accounts"][op[1]]["iban"], "camt": [], "mt940": ""}
            if value and value.get("camt"):
                entry["camt"] = [_b64(x) for x in value["camt"]]
            if value and value.get("mt940"):
                entry["mt940"] = _b64(value["mt940"])
            out.setdefault("statements", []).append(entry)
        elif kind == "balance":
            entry = out["statements"][-1]
            if value is not None and getattr(value, "amount", None) is not None:
                entry["balance"] = str(value.amount.amount)
                entry["balance_date"] = value.date.isoformat() if value.date else ""

    # --- Fehler ---

    @contextmanager
    def _errors(self):
        from fints import exceptions as fx

        bank_messages: list = []

        def bank_text() -> str:
            if not bank_messages:
                return ""
            code, text = bank_messages[-1]
            return f" ({text} [{code}])" if text else f" [{code}]"

        try:
            yield bank_messages
        except BankError:
            raise
        except fx.FinTSClientPINError as exc:
            raise BankError(
                "pin",
                gettext("Die Bank hat die Anmeldung abgelehnt. Bitte Anmeldename und PIN prüfen.")
                + bank_text(),
            ) from exc
        except fx.FinTSClientTemporaryAuthError as exc:
            raise BankError(
                "locked",
                gettext(
                    "Der Zugang ist bei der Bank vorläufig gesperrt. Bitte im Online-Banking "
                    "der Bank entsperren."
                ),
            ) from exc
        except fx.FinTSConnectionError as exc:
            raise BankError(
                "connection",
                gettext("Die Bank ist nicht erreichbar: {reason}").format(reason=str(exc)[:200]),
            ) from exc
        except fx.FinTSUnsupportedOperation as exc:
            raise BankError(
                "unsupported", gettext("Die Bank bietet das für diesen Zugang nicht an.")
            ) from exc
        except fx.FinTSSCARequiredError as exc:
            raise BankError(
                "bank", gettext("Die Bank verlangt eine neue Freigabe. Bitte erneut abrufen.")
            ) from exc
        except Exception as exc:  # noqa: BLE001 - Bibliothek wirft auch einfache Exceptions
            # Weder Ausnahmetext noch Nachricht protokollieren: Sie können Kontodaten enthalten
            logger.warning("FinTS-Vorgang fehlgeschlagen: %s", exc.__class__.__name__)
            raise BankError(
                "bank",
                gettext("Der Vorgang bei der Bank ist fehlgeschlagen.") + bank_text(),
            ) from exc
