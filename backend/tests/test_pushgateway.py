"""Android-App, Schritt A6: Push-Gateway für die Play-Fassung (FCM) und Google-Push in HUBIplan."""
# ruff: noqa: F811  (Fixtures aus test_m12_events als Parameter)

import base64
import io
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from devices import webpush
from devices.models import Device
from pushgateway import app as gw

from .test_app_devices import APP, app
from .test_app_push import (  # noqa: F401  (Fixtures)
    Receiver,
    allow_endpoint,
    anna,
    b64,
    push_outbox,
)
from .test_m12_events import JSON, cal  # noqa: F401

GATEWAY = "https://push.hubiplan.example"
TOKEN = "fcm-token_" + "x" * 40
ENDPOINT = f"{GATEWAY}/fcm/{TOKEN}"


def rsa_credentials() -> dict:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "project_id": "hubiplan-test",
        "client_email": "gateway@hubiplan-test.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.example/token",
        "_key": key,
    }


class GoogleFake:
    """Ersetzt http_post: Anmeldung und FCM-Versand."""

    def __init__(self):
        self.calls = []
        self.fcm_answer = (200, {"name": "projects/x/messages/1"})

    def __call__(self, url, headers, body):
        self.calls.append({"url": url, "headers": headers, "body": body})
        if url.endswith("/token"):
            return 200, {"access_token": "ya29.test", "expires_in": 3600}
        return self.fcm_answer

    @property
    def messages(self):
        return [json.loads(c["body"]) for c in self.calls if "fcm.googleapis.com" in c["url"]]


@pytest.fixture
def google(monkeypatch):
    fake = GoogleFake()
    monkeypatch.setattr(gw, "http_post", fake)
    return fake


@pytest.fixture
def creds():
    return rsa_credentials()


@pytest.fixture
def gateway(google, creds):
    data = {k: v for k, v in creds.items() if not k.startswith("_")}
    return gw.Gateway(GATEWAY, gw.Fcm(data), rate=3)


@pytest.fixture
def vapid(settings, tmp_path):
    settings.PUSH_VAPID_KEY_FILE = str(tmp_path / "vapid.json")
    webpush.reset_cache()
    return webpush


def push_request(body=None, *, endpoint=ENDPOINT, urgency="high", auth=None):
    body = body if body is not None else webpush.encrypt(b'{"t":"sync"}', *_receiver_keys())
    return {
        "content-encoding": "aes128gcm",
        "urgency": urgency,
        "ttl": "86400",
        "authorization": auth if auth is not None else webpush.vapid_header(endpoint),
    }, body


def _receiver_keys():
    r = Receiver()
    return r.p256dh, b64(r.auth)


class TestVapidPruefung:
    def test_gueltig(self, vapid):
        key = gw.check_vapid(vapid.vapid_header(ENDPOINT), GATEWAY)
        assert key == vapid.vapid_public_key()

    def test_andere_adresse(self, vapid):
        with pytest.raises(gw.Rejected):
            gw.check_vapid(vapid.vapid_header("https://andere.example/x"), GATEWAY)

    def test_abgelaufen(self, vapid):
        old = vapid.vapid_header(ENDPOINT, now=time.time() - 13 * 3600)
        with pytest.raises(gw.Rejected):
            gw.check_vapid(old, GATEWAY)

    def test_signatur_falsch(self, vapid):
        header = vapid.vapid_header(ENDPOINT)
        token = header.split("t=")[1].split(",")[0]
        head, body, sig = token.split(".")
        forged = header.replace(token, f"{head}.{body}.{b64(b'0' * 64)}")
        with pytest.raises(gw.Rejected):
            gw.check_vapid(forged, GATEWAY)
        with pytest.raises(gw.Rejected):
            gw.check_vapid("Bearer abc", GATEWAY)


@pytest.mark.parametrize("head", ["null", "[]", '"x"', "1"])
@pytest.mark.parametrize("part", ["head", "claims"])
def test_vapid_ohne_objekt_gibt_401(vapid, head, part):
    """Audit 02.11., PG-F01: JSON-Liste oder Zahl statt Objekt → 401, kein Serverfehler."""
    header = vapid.vapid_header(ENDPOINT)
    token = header.split("t=")[1].split(",")[0]
    h, c, sig = token.split(".")
    if part == "head":
        h = b64(head.encode())
    else:
        c = b64(head.encode())
    with pytest.raises(gw.Rejected) as exc:
        gw.check_vapid(header.replace(token, f"{h}.{c}.{sig}"), GATEWAY)
    assert exc.value.status == 401


class TestGateway:
    def test_reicht_an_fcm_weiter(self, vapid, gateway, google, creds):
        headers, body = push_request()
        status, _ = gateway.handle("POST", f"/fcm/{TOKEN}", headers, body)
        assert status == 201
        token_call, send_call = google.calls
        # Anmeldung mit vom Dienstkonto signiertem JWT (RS256)
        assertion = dict(x.split("=") for x in token_call["body"].decode().split("&"))["assertion"]
        head, claims, sig = assertion.split(".")
        creds["_key"].public_key().verify(
            base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)),
            f"{head}.{claims}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        assert send_call["url"].endswith("/projects/hubiplan-test/messages:send")
        assert send_call["headers"]["Authorization"] == "Bearer ya29.test"
        msg = google.messages[0]["message"]
        assert msg["token"] == TOKEN
        assert base64.b64decode(msg["data"]["b"]) == body
        assert msg["android"] == {"priority": "HIGH", "ttl": "86400s"}
        # Zugriffstoken wird wiederverwendet
        gateway.handle("POST", f"/fcm/{TOKEN}", *push_request(urgency="normal"))
        assert len([c for c in google.calls if c["url"].endswith("/token")]) == 1
        assert google.messages[1]["message"]["android"]["priority"] == "NORMAL"

    def test_unbekanntes_geraet(self, vapid, gateway, google):
        google.fcm_answer = (
            404,
            {"error": {"details": [{"errorCode": "UNREGISTERED"}]}},
        )
        assert gateway.handle("POST", f"/fcm/{TOKEN}", *push_request())[0] == 410

    def test_ablehnungen(self, vapid, gateway, google):
        path = f"/fcm/{TOKEN}"
        headers, body = push_request()
        assert gateway.handle("POST", path, headers, b"x" * (gw.MAX_BODY + 1))[0] == 413
        other = {**headers, "content-encoding": "aesgcm"}
        assert gateway.handle("POST", path, other, body)[0] == 415
        assert gateway.handle("POST", path, {**headers, "authorization": ""}, body)[0] == 401
        assert gateway.handle("POST", "/fcm/kurz", headers, body)[0] == 404
        assert gateway.handle("GET", path, headers, body)[0] == 405
        assert gateway.handle("POST", "/anderes", headers, body)[0] == 404
        assert google.messages == []

    def test_begrenzung_je_absender(self, vapid, gateway):
        statuses = [gateway.handle("POST", f"/fcm/{TOKEN}", *push_request())[0] for _ in range(4)]
        assert statuses == [201, 201, 201, 429]

    def test_ohne_dienstkonto(self, vapid):
        g = gw.Gateway(GATEWAY, None)
        assert g.handle("POST", f"/fcm/{TOKEN}", *push_request())[0] == 503
        assert g.handle("GET", "/health", {}, b"") == (
            200,
            {"status": "ok", "fcm": False, "apns": False},
        )

    def test_wsgi(self, vapid, gateway, google):
        headers, body = push_request()
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": f"/fcm/{TOKEN}",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            **{"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()},
        }
        started = []
        out = gateway(environ, lambda status, hdrs: started.append(status))
        assert started == ["201 Created"] and json.loads(b"".join(out)) == {}

    def test_start_braucht_https(self, monkeypatch):
        monkeypatch.setenv("PUSH_GATEWAY_PUBLIC_URL", "http://push.example")
        with pytest.raises(RuntimeError):
            gw.create()


@pytest.mark.django_db
class TestGooglePushInHubiplan:
    def register(self, token, endpoint=ENDPOINT):
        r = Receiver()
        return app(token).put(
            f"{APP}devices/current/push/",
            {"kind": "fcm", "endpoint": endpoint, "p256dh": r.p256dh, "auth": b64(r.auth)},
            content_type=JSON,
        )

    def test_nur_ueber_eingestelltes_gateway(self, anna, settings, allow_endpoint):
        settings.PUSH_GATEWAY_URL = ""
        assert self.register(anna["token"]).status_code == 400
        settings.PUSH_GATEWAY_URL = GATEWAY + "/"
        assert self.register(anna["token"], "https://fremd.example/fcm/" + TOKEN).status_code == 400
        resp = self.register(anna["token"])
        assert resp.status_code == 200, resp.json()
        assert Device.objects.get().push_kind == "fcm"

    def test_instanz_nennt_gateway(self, settings):
        from django.test import Client

        settings.PUSH_GATEWAY_URL = GATEWAY
        ways = Client().get(f"{APP}instance/").json()["push"]
        assert {
            "kind": "fcm",
            "gateway": GATEWAY,
            "vapid_public_key": webpush.vapid_public_key(),
        } in ways

    def test_grosse_nachricht_passt_zu_fcm(self, anna, settings, allow_endpoint, push_outbox):
        from devices.push import send_to_user

        settings.PUSH_GATEWAY_URL = GATEWAY
        assert self.register(anna["token"]).status_code == 200
        text = "ä" * 1400  # gut 2800 Bytes: für FCM zu groß, für UnifiedPush nicht
        assert send_to_user(anna["user"].pk, {"t": "info", "text": text}) == 1
        body = push_outbox[0]["body"]
        assert len(body) <= gw.MAX_BODY
        assert push_outbox[0]["url"] == ENDPOINT


class TestBindung:
    """Härtung H5: Endpunkt an den VAPID-Schlüssel der Instanz gebunden, Grenzen, Auffüllen."""

    def test_nur_mit_dem_schluessel_der_instanz(self, vapid, gateway, google):
        kid = gw.key_id(vapid.vapid_public_key())
        path = f"/fcm/{TOKEN}/{kid}"
        endpoint = f"{GATEWAY}{path}"
        assert gateway.handle("POST", path, *push_request(endpoint=endpoint))[0] == 201
        # Fremde Instanz mit eigenem Schlüssel, die den Endpunkt kennt
        other = gw.Gateway(GATEWAY, gateway.fcm, rate=3)
        vapid.reset_cache()
        vapid.key_path().unlink()
        status, data = other.handle("POST", path, *push_request(endpoint=endpoint))
        assert status == 403 and data["reason"] == "anderer Absender"
        assert len(google.messages) == 1

    def test_selbst_gewaehlte_kennung_mit_freigabeliste(self, vapid, google, creds):
        """Audit 02.11., PG-S01: fremder Schlüssel mit neu berechneter Kennung."""
        data = {k: v for k, v in creds.items() if not k.startswith("_")}
        own = gw.key_id(vapid.vapid_public_key())
        g = gw.Gateway(GATEWAY, gw.Fcm(data), allowed_keys=frozenset({own}))
        path = f"/fcm/{TOKEN}/{own}"
        assert g.handle("POST", path, *push_request(endpoint=f"{GATEWAY}{path}"))[0] == 201
        # Angreifer: eigener Schlüssel, Kennung passend dazu
        vapid.reset_cache()
        vapid.key_path().unlink()
        forged = f"/fcm/{TOKEN}/{gw.key_id(vapid.vapid_public_key())}"
        status, body = g.handle("POST", forged, *push_request(endpoint=f"{GATEWAY}{forged}"))
        assert status == 403 and body["reason"] == "Absender nicht freigegeben"
        # auch ohne Kennung im Pfad
        assert g.handle("POST", f"/fcm/{TOKEN}", *push_request())[0] == 403
        assert len(google.messages) == 1

    def test_freigabeliste_aus_umgebung(self):
        assert gw.allowed_keys(" 0123456789ABCDEF, ,fedcba9876543210") == {
            "0123456789abcdef",
            "fedcba9876543210",
        }
        assert gw.allowed_keys("") == frozenset()
        with pytest.raises(RuntimeError):
            gw.allowed_keys("kein-schluessel")

    def test_ohne_kennung_abschaltbar(self, vapid, google, creds):
        data = {k: v for k, v in creds.items() if not k.startswith("_")}
        strict = gw.Gateway(GATEWAY, gw.Fcm(data), allow_unbound=False)
        assert strict.handle("POST", f"/fcm/{TOKEN}", *push_request())[0] == 404
        assert strict.handle("POST", f"/fcm/{TOKEN}/zzzz", *push_request())[0] == 404

    def test_grenze_je_geraet_und_ip(self, vapid, google, creds):
        data = {k: v for k, v in creds.items() if not k.startswith("_")}
        g = gw.Gateway(GATEWAY, gw.Fcm(data), rate=100, rate_token=2, rate_ip=3)
        path = f"/fcm/{TOKEN}"
        statuses = [g.handle("POST", path, *push_request(), "1.2.3.4")[0] for _ in range(3)]
        assert statuses == [201, 201, 429]
        other = "fcm-token_" + "y" * 40
        assert g.handle("POST", f"/fcm/{other}", *push_request(), "1.2.3.4")[0] == 429
        assert g.handle("POST", f"/fcm/{other}", *push_request(), "5.6.7.8")[0] == 201

    def test_gleiche_groesse_fuer_kurze_nachrichten(self):
        keys = _receiver_keys()
        short = webpush.encrypt(b'{"t":"sync"}', *keys, pad_to=webpush.padded_size(12, 2600))
        longer = b'{"t":"info","text":"' + b"x" * 500 + b'"}'
        medium = webpush.encrypt(longer, *keys, pad_to=webpush.padded_size(len(longer), 2600))
        assert len(short) == len(medium)
        big = b"x" * 2000
        full = webpush.encrypt(big, *keys, pad_to=webpush.padded_size(len(big), 2600))
        assert len(full) <= gw.MAX_BODY


# --- Apple-Push (iOS-App, Stufe I3) ---

APNS_TOKEN = "ab12" * 16


def apns_key():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return key, pem


class AppleFake:
    """Ersetzt http2_post: Apples Push-Dienst."""

    def __init__(self):
        self.calls = []
        self.answer = (200, {})

    def __call__(self, url, headers, body):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        return self.answer


@pytest.fixture
def apple(monkeypatch):
    fake = AppleFake()
    monkeypatch.setattr(gw, "http2_post", fake)
    return fake


@pytest.fixture
def apns_gateway(apple):
    key, pem = apns_key()
    service = gw.Apns(pem, "ABCDE12345", "TEAM123456", "de.hubiplan.app")
    gateway = gw.Gateway(GATEWAY, None, rate=5, apns=service)
    gateway.test_key = key
    return gateway


def apns_path(kid=None):
    return f"/apns/{APNS_TOKEN}/{kid or gw.key_id(webpush.vapid_public_key())}"


def apns_request(**kwargs):
    return push_request(endpoint=GATEWAY + apns_path(), **kwargs)


class TestApple:
    def test_reicht_an_apple_weiter(self, vapid, apns_gateway, apple):
        headers, body = apns_request()
        before = int(time.time())
        assert apns_gateway.handle("POST", apns_path(), headers, body)[0] == 201
        call = apple.calls[0]
        assert call["url"] == f"https://api.push.apple.com/3/device/{APNS_TOKEN}"
        sent = call["headers"]
        assert sent["apns-topic"] == "de.hubiplan.app"
        assert sent["apns-push-type"] == "alert"
        assert sent["apns-priority"] == "10"
        assert before + 86400 <= int(sent["apns-expiration"]) <= before + 86400 + 5
        # Anmeldung: ES256-JWT mit Schlüssel-ID und Team, vom .p8-Schlüssel signiert
        kind, _, token = sent["authorization"].partition(" ")
        head, claims, sig = token.split(".")
        assert kind == "bearer"
        assert json.loads(gw._unb64(head)) == {"alg": "ES256", "kid": "ABCDE12345"}
        assert json.loads(gw._unb64(claims))["iss"] == "TEAM123456"
        raw = gw._unb64(sig)
        apns_gateway.test_key.public_key().verify(
            encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
            f"{head}.{claims}".encode(),
            ec.ECDSA(hashes.SHA256()),
        )
        # Inhalt bleibt verschlüsselt; sichtbar ist nur ein Platzhalter, den die App ersetzt
        payload = call["body"]
        assert base64.b64decode(payload["b"]) == body
        assert payload["aps"]["mutable-content"] == 1
        assert payload["aps"]["alert"] == {"title": "HUBIplan", "loc-key": "PUSH_PLATZHALTER"}
        # Anmelde-Token wird wiederverwendet; normale Dringlichkeit
        apns_gateway.handle("POST", apns_path(), *apns_request(urgency="normal"))
        assert apple.calls[1]["headers"]["authorization"] == sent["authorization"]
        assert apple.calls[1]["headers"]["apns-priority"] == "5"

    def test_groesste_nachricht_passt_in_4_kb(self, vapid, apns_gateway, apple):
        headers, _ = apns_request()
        body = b"x" * gw.MAX_BODY
        assert apns_gateway.handle("POST", apns_path(), headers, body)[0] == 201
        assert len(json.dumps(apple.calls[0]["body"], separators=(",", ":"))) <= 4096

    def test_testumgebung(self, vapid, apple):
        _, pem = apns_key()
        service = gw.Apns(pem, "ABCDE12345", "TEAM123456", "de.hubiplan.app", sandbox=True)
        g = gw.Gateway(GATEWAY, None, apns=service)
        assert g.handle("POST", apns_path(), *apns_request())[0] == 201
        assert apple.calls[0]["url"].startswith("https://api.sandbox.push.apple.com/3/device/")

    @pytest.mark.parametrize(
        ("answer", "status"),
        [
            ((410, {"reason": "Unregistered"}), 410),
            ((400, {"reason": "DeviceTokenNotForTopic"}), 410),
            ((400, {"reason": "BadDeviceToken"}), 404),
            ((429, {"reason": "TooManyRequests"}), 429),
            ((503, {}), 429),
            ((400, {"reason": "PayloadTooLarge"}), 502),
            ((500, {}), 502),
        ],
    )
    def test_antworten_von_apple(self, vapid, apns_gateway, apple, answer, status):
        apple.answer = answer
        assert apns_gateway.handle("POST", apns_path(), *apns_request())[0] == status

    def test_abgelehnte_anmeldung_stellt_neues_token_aus(self, vapid, apns_gateway, apple):
        apple.answer = (403, {"reason": "ExpiredProviderToken"})
        assert apns_gateway.handle("POST", apns_path(), *apns_request())[0] == 502
        assert apns_gateway.apns._token == ""
        apple.answer = (200, {})
        assert apns_gateway.handle("POST", apns_path(), *apns_request())[0] == 201

    def test_anmelde_token_wird_nach_45_minuten_erneuert(self):
        _, pem = apns_key()
        service = gw.Apns(pem, "ABCDE12345", "TEAM123456", "de.hubiplan.app")
        first = service.provider_token(now=1_000_000)
        assert service.provider_token(now=1_000_000 + 44 * 60) == first
        later = service.provider_token(now=1_000_000 + 46 * 60)
        assert later != first
        assert json.loads(gw._unb64(later.split(".")[1]))["iat"] == 1_000_000 + 46 * 60

    def test_ablehnungen(self, vapid, apns_gateway, apple):
        headers, body = apns_request()
        # Ohne Kennung, mit fremder Kennung, mit falschem Token
        assert apns_gateway.handle("POST", f"/apns/{APNS_TOKEN}", headers, body)[0] == 404
        assert apns_gateway.handle("POST", apns_path("0" * 16), headers, body)[0] == 403
        assert apns_gateway.handle("POST", "/apns/KEINHEX" + "0" * 60, headers, body)[0] == 404
        assert apns_gateway.handle("POST", f"/apns/{'ab' * 20}/{'0' * 16}", headers, body)[0] == 404
        assert apns_gateway.handle("GET", apns_path(), headers, body)[0] == 405
        big = b"x" * (gw.MAX_BODY + 1)
        assert apns_gateway.handle("POST", apns_path(), headers, big)[0] == 413
        assert (
            apns_gateway.handle("POST", apns_path(), {**headers, "authorization": ""}, body)[0]
            == 401
        )
        assert apple.calls == []

    def test_ohne_apple_schluessel(self, vapid, gateway, google):
        assert gateway.handle("POST", apns_path(), *apns_request())[0] == 503
        assert gateway.handle("GET", "/health", {}, b"")[1] == {
            "status": "ok",
            "fcm": True,
            "apns": False,
        }
        assert google.calls == []

    def test_falsche_einstellungen_brechen_den_start_ab(self):
        _, pem = apns_key()
        rsa_pem = rsa_credentials()["private_key"]
        for args in [
            (rsa_pem, "ABCDE12345", "TEAM123456", "de.hubiplan.app"),
            (pem, "kurz", "TEAM123456", "de.hubiplan.app"),
            (pem, "ABCDE12345", "", "de.hubiplan.app"),
            (pem, "ABCDE12345", "TEAM123456", "de hubiplan/app"),
        ]:
            with pytest.raises(RuntimeError):
                gw.Apns(*args)

    def test_start_aus_umgebung(self, monkeypatch, tmp_path):
        _, pem = apns_key()
        path = tmp_path / "apns.p8"
        path.write_text(pem)
        monkeypatch.setenv("PUSH_GATEWAY_PUBLIC_URL", GATEWAY)
        monkeypatch.delenv("PUSH_GATEWAY_FCM_CREDENTIALS", raising=False)
        monkeypatch.setenv("PUSH_GATEWAY_APNS_KEY", str(path))
        monkeypatch.setenv("PUSH_GATEWAY_APNS_KEY_ID", "ABCDE12345")
        monkeypatch.setenv("PUSH_GATEWAY_APNS_TEAM", "TEAM123456")
        monkeypatch.setenv("PUSH_GATEWAY_APNS_SANDBOX", "1")
        g = gw.create()
        assert g.apns.topic == "de.hubiplan.app"
        assert g.apns.host == gw.APNS_HOST_SANDBOX
        assert g.handle("GET", "/health", {}, b"")[1]["apns"] is True


@pytest.mark.django_db
class TestApplePushInHubiplan:
    def endpoint(self, kid=None):
        return GATEWAY + apns_path(kid)

    def register(self, token, endpoint):
        r = Receiver()
        return app(token).put(
            f"{APP}devices/current/push/",
            {"kind": "apns", "endpoint": endpoint, "p256dh": r.p256dh, "auth": b64(r.auth)},
            content_type=JSON,
        )

    def test_nur_eingeschaltet_gebunden_und_ueber_das_gateway(
        self, anna, settings, allow_endpoint, vapid
    ):
        settings.PUSH_GATEWAY_URL = GATEWAY
        settings.PUSH_GATEWAY_APNS = False
        assert self.register(anna["token"], self.endpoint()).status_code == 400
        settings.PUSH_GATEWAY_APNS = True
        fremd = "https://fremd.example" + apns_path()
        assert self.register(anna["token"], fremd).status_code == 400
        # Ohne Kennung oder mit der Kennung einer anderen Instanz
        assert self.register(anna["token"], f"{GATEWAY}/apns/{APNS_TOKEN}").status_code == 400
        assert self.register(anna["token"], self.endpoint("0" * 16)).status_code == 400
        # Der Google-Weg nimmt keinen Apple-Endpunkt und umgekehrt
        assert self.register(anna["token"], f"{GATEWAY}/fcm/{TOKEN}").status_code == 400
        resp = self.register(anna["token"], self.endpoint())
        assert resp.status_code == 200, resp.json()
        assert Device.objects.get().push_kind == "apns"

    def test_instanz_nennt_den_weg_nur_wenn_eingeschaltet(self, settings, vapid):
        from django.test import Client

        settings.PUSH_GATEWAY_URL = GATEWAY
        settings.PUSH_GATEWAY_APNS = False
        kinds = [w["kind"] for w in Client().get(f"{APP}instance/").json()["push"]]
        assert kinds == ["unifiedpush", "fcm"]
        settings.PUSH_GATEWAY_APNS = True
        ways = Client().get(f"{APP}instance/").json()["push"]
        assert {
            "kind": "apns",
            "gateway": GATEWAY,
            "vapid_public_key": webpush.vapid_public_key(),
        } in ways
        settings.PUSH_GATEWAY_URL = ""
        kinds = [w["kind"] for w in Client().get(f"{APP}instance/").json()["push"]]
        assert kinds == ["unifiedpush"]

    def test_grosse_nachricht_passt_zu_apple(
        self, anna, settings, allow_endpoint, push_outbox, vapid
    ):
        from devices.push import send_to_user

        settings.PUSH_GATEWAY_URL = GATEWAY
        settings.PUSH_GATEWAY_APNS = True
        assert self.register(anna["token"], self.endpoint()).status_code == 200
        assert send_to_user(anna["user"].pk, {"t": "info", "text": "ä" * 1400}) == 1
        assert len(push_outbox[0]["body"]) <= gw.MAX_BODY
        assert push_outbox[0]["url"] == self.endpoint()
