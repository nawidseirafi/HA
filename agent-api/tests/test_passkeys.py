"""Exercise real WebAuthn signature verification with a software authenticator."""
import hashlib
import json
import secrets
import time

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from webauthn.helpers import bytes_to_base64url as encode

from backend.api.auth_routes import router
from backend.services import auth_service as auth, passkey_service as keys

ORIGIN = "https://steve.example"
RP_ID = "steve.example"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(keys, "DB_PATH", tmp_path / "passkeys.sqlite3")
    monkeypatch.setattr(auth, "_auth_config", lambda: {})
    monkeypatch.setattr(auth, "_load_env_files", lambda: {})
    monkeypatch.setenv("AGENT_API_USERNAME", "test-user")
    monkeypatch.setenv("AGENT_API_PASSWORD", "test-password")
    monkeypatch.setenv("AGENT_API_JWT_SECRET", "test-secret-only")
    monkeypatch.setenv("ROBOTERSTEVE_PASSKEY_ORIGIN", ORIGIN)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, base_url=ORIGIN, headers={"origin": ORIGIN}) as result:
        session = result.post("/api/auth/login", json={"username": "test-user", "password": "test-password"}).json()
        result.headers["authorization"] = "Bearer " + session["access_token"]
        yield result


class Authenticator:
    def __init__(self):
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.id = secrets.token_bytes(32)
        self.handle = None

    def registration(self, options, *, origin=ORIGIN, rp_id=RP_ID, flags=0x45, challenge=None, cross_origin=False):
        self.handle = options["user"]["id"]
        public = self.private.public_key().public_numbers()
        cose_key = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: public.x.to_bytes(32, "big"), -3: public.y.to_bytes(32, "big")})
        auth_data = (hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + (0).to_bytes(4, "big")
                     + bytes(16) + len(self.id).to_bytes(2, "big") + self.id + cose_key)
        client_data = json.dumps({"type": "webauthn.create", "challenge": challenge or options["challenge"], "origin": origin, "crossOrigin": cross_origin}).encode()
        return {"id": encode(self.id), "rawId": encode(self.id), "type": "public-key", "response": {
            "clientDataJSON": encode(client_data),
            "attestationObject": encode(cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})),
            "transports": ["internal"],
        }}

    def assertion(self, options, *, origin=ORIGIN, rp_id=RP_ID, flags=5, count=0, challenge=None, bad_signature=False, cross_origin=False):
        auth_data = hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + count.to_bytes(4, "big")
        client_data = json.dumps({"type": "webauthn.get", "challenge": challenge or options["challenge"], "origin": origin, "crossOrigin": cross_origin}).encode()
        signature = self.private.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": encode(self.id), "rawId": encode(self.id), "type": "public-key", "response": {
            "clientDataJSON": encode(client_data), "authenticatorData": encode(auth_data),
            "signature": encode(b"invalid" if bad_signature else signature), "userHandle": self.handle,
        }}


def begin_register(client):
    response = client.post("/api/auth/passkeys/register/options", json={"password": "test-password"})
    assert response.status_code == 200, response.text
    return response.json()


def enroll(client):
    device = Authenticator()
    ceremony = begin_register(client)
    response = client.post("/api/auth/passkeys/register/verify", json={
        "challenge_id": ceremony["challenge_id"], "credential": device.registration(ceremony["options"]), "name": "Mein iPad",
    })
    assert response.status_code == 200, response.text
    return device


def begin_login(client):
    response = client.post("/api/auth/passkeys/login/options")
    assert response.status_code == 200, response.text
    return response.json()


def finish_login(client, device, **kwargs):
    ceremony = begin_login(client)
    payload = {"challenge_id": ceremony["challenge_id"], "credential": device.assertion(ceremony["options"], **kwargs)}
    return client.post("/api/auth/passkeys/login/verify", json=payload), payload


def test_password_fallback_and_passkey_login_persistence_replay_and_revocation(client):
    device = enroll(client)
    listed = client.get("/api/auth/passkeys").json()["passkeys"]
    assert listed[0]["name"] == "Mein iPad"
    assert "public_key" not in listed[0]
    del client.headers["authorization"]
    response, payload = finish_login(client, device)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert auth.verify_token(token)["sub"] == "test-user"
    assert client.post("/api/auth/passkeys/login/verify", json=payload).status_code == 400
    # Synced passkeys may legitimately always report a zero counter.
    assert finish_login(client, device)[0].status_code == 200
    client.headers["authorization"] = "Bearer " + token
    assert client.get("/api/auth/passkeys").json()["passkeys"][0]["last_used_at"]
    assert client.delete("/api/auth/passkeys/" + encode(device.id)).status_code == 200
    assert finish_login(client, device)[0].status_code == 400
    assert client.post("/api/auth/login", json={"username": "test-user", "password": "test-password"}).status_code == 200


@pytest.mark.parametrize("override", [
    {"origin": "https://evil.example"}, {"rp_id": "evil.example"}, {"flags": 1},
    {"challenge": encode(b"wrong-challenge")}, {"bad_signature": True}, {"cross_origin": True},
])
def test_rejects_invalid_assertions(client, override):
    device = enroll(client)
    response, payload = finish_login(client, device, **override)
    assert response.status_code == 400, response.text
    assert client.post("/api/auth/passkeys/login/verify", json=payload).status_code == 400


@pytest.mark.parametrize("override", [
    {"origin": "https://evil.example"}, {"rp_id": "evil.example"}, {"flags": 0x41},
    {"challenge": encode(b"wrong-challenge")}, {"cross_origin": True},
])
def test_rejects_invalid_registrations(client, override):
    ceremony = begin_register(client)
    credential = Authenticator().registration(ceremony["options"], **override)
    response = client.post("/api/auth/passkeys/register/verify", json={"challenge_id": ceremony["challenge_id"], "credential": credential})
    assert response.status_code == 400, response.text
    assert client.get("/api/auth/passkeys").json() == {"passkeys": []}


def test_requires_session_password_and_matching_registration_session(client):
    assert client.post("/api/auth/passkeys/register/options", json={"password": "wrong"}).status_code == 400
    ceremony = begin_register(client)
    credential = Authenticator().registration(ceremony["options"])
    client.headers["authorization"] = "Bearer " + auth.create_token({"sub": "test-user", "exp": int(time.time()) + 200, "nonce": "another-session"})
    assert client.post("/api/auth/passkeys/register/verify", json={"challenge_id": ceremony["challenge_id"], "credential": credential}).status_code == 400
    del client.headers["authorization"]
    assert client.post("/api/auth/passkeys/register/options", json={"password": "test-password"}).status_code == 401
    assert client.get("/api/auth/passkeys").status_code == 401
    assert client.delete("/api/auth/passkeys/something").status_code == 401


def test_challenge_expiry_and_ceremony_type(client):
    device = enroll(client)
    ceremony = begin_login(client)
    with keys.connect() as con:
        con.execute("UPDATE passkey_challenges SET expires_at = 0")
    assert client.post("/api/auth/passkeys/login/verify", json={"challenge_id": ceremony["challenge_id"], "credential": device.assertion(ceremony["options"])}).status_code == 400
    ceremony = begin_register(client)
    assert client.post("/api/auth/passkeys/login/verify", json={"challenge_id": ceremony["challenge_id"], "credential": device.assertion(ceremony["options"])}).status_code == 400


def test_account_handle_counter_and_changed_username(client, monkeypatch):
    device = enroll(client)
    device.handle = encode(b"another-account")
    assert finish_login(client, device)[0].status_code == 400
    with keys.connect() as con:
        device.handle = encode(con.execute("SELECT handle FROM passkey_users").fetchone()[0])
    assert finish_login(client, device, count=1)[0].status_code == 200
    assert finish_login(client, device, count=1)[0].status_code == 400
    assert finish_login(client, device, count=2)[0].status_code == 200
    monkeypatch.setenv("AGENT_API_USERNAME", "different-account")
    assert finish_login(client, device, count=3)[0].status_code == 400


def test_away_login_preserves_session_only_policy(client, monkeypatch):
    device = enroll(client)
    monkeypatch.setattr(auth, "auth_presence_state", lambda: {"enabled": True, "available": True, "state": "away"})
    response, _ = finish_login(client, device)
    assert response.status_code == 200
    assert response.json()["force_session"] is True
    assert auth.verify_token(response.json()["access_token"])["auth_scope"] == "away"


def test_origin_validation_rate_limit_and_local_development(client, monkeypatch):
    assert client.post("/api/auth/passkeys/login/options", headers={"origin": "https://evil.example"}).status_code == 400
    monkeypatch.setenv("ROBOTERSTEVE_PASSKEY_ORIGIN", "http://192.168.1.2:8080")
    assert client.post("/api/auth/passkeys/login/options").status_code == 400
    monkeypatch.setenv("ROBOTERSTEVE_PASSKEY_ORIGIN", "http://localhost:5173")
    assert client.post("/api/auth/passkeys/login/options", headers={"origin": "http://localhost:5173"}).status_code == 200
    monkeypatch.delenv("ROBOTERSTEVE_PASSKEY_ORIGIN")
    assert client.post("/api/auth/passkeys/login/options").status_code == 200
    for _ in range(26):
        assert client.post("/api/auth/passkeys/login/options").status_code == 200
    assert client.post("/api/auth/passkeys/login/options").status_code == 429

@pytest.mark.parametrize('response', [None, [], {}, {'clientDataJSON': 123}, {'clientDataJSON': 'not-base64-json'}])
def test_malformed_registration_is_rejected_without_server_error(client, response):
    ceremony = begin_register(client)
    result = client.post('/api/auth/passkeys/register/verify', json={
        'challenge_id': ceremony['challenge_id'], 'credential': {'response': response},
    })
    assert result.status_code == 400
