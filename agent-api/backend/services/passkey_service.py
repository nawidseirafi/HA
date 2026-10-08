"""Persistent WebAuthn credentials and single-use, session-bound ceremonies."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options, generate_registration_options,
    options_to_json, verify_authentication_response, verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, parse_client_data_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorAttachment, AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor, ResidentKeyRequirement, UserVerificationRequirement,
)

from backend.paths import API_DIR
from backend.services import auth_service as auth

DB_PATH = API_DIR / "data" / "auth" / "passkeys.sqlite3"
CEREMONY_SECONDS = 300


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS passkey_users (
                username TEXT PRIMARY KEY, handle BLOB NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS passkeys (
                id TEXT PRIMARY KEY, username TEXT NOT NULL, rp_id TEXT NOT NULL,
                public_key BLOB NOT NULL, sign_count INTEGER NOT NULL,
                name TEXT NOT NULL, created_at INTEGER NOT NULL, last_used_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS passkey_challenges (
                id TEXT PRIMARY KEY, challenge BLOB NOT NULL, kind TEXT NOT NULL,
                username TEXT NOT NULL, session_hash TEXT NOT NULL,
                origin TEXT NOT NULL, rp_id TEXT NOT NULL, expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS passkey_attempts (
                client TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS passkey_attempts_client ON passkey_attempts(client, created_at);
        """)
        with con:
            yield con
    finally:
        con.close()


def relying_party(request: Request) -> tuple[str, str]:
    # Never trust the Origin header to choose the relying party. An explicit
    # external URL supports reverse proxies and a separate development frontend.
    configured = auth._secret_value("ROBOTERSTEVE_PASSKEY_ORIGIN")
    origin = (configured or str(request.base_url)).rstrip("/")
    parsed = urlsplit(origin)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path
            or parsed.query or parsed.fragment
            or (parsed.scheme != "https" and not (
                parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}))):
        raise HTTPException(400, "Passkeys benötigen eine feste HTTPS-Adresse. Bitte ROBOTERSTEVE_PASSKEY_ORIGIN konfigurieren.")
    if request.headers.get("origin") != origin:
        raise HTTPException(400, "Die Website-Adresse stimmt nicht mit der Passkey-Adresse überein. Bitte ROBOTERSTEVE_PASSKEY_ORIGIN prüfen.")
    return origin, parsed.hostname


def account(request: Request) -> str:
    username = auth.user_from_request(request)["username"]
    if username != auth.configured_username():
        raise HTTPException(401, "Bitte erneut anmelden.")
    return username


def rate_limit(request: Request):
    # Trust only the ASGI client's address (proxy trust is configured in uvicorn).
    client = hashlib.sha256((request.client.host if request.client else "local").encode()).hexdigest()
    now = int(time.time())
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM passkey_attempts WHERE created_at <= ?", (now - 300,))
        count = con.execute("SELECT count(*) FROM passkey_attempts WHERE client = ?", (client,)).fetchone()[0]
        if count >= 30:
            raise HTTPException(429, "Zu viele Versuche. Bitte in fünf Minuten erneut versuchen.")
        con.execute("INSERT INTO passkey_attempts VALUES (?, ?)", (client, now))


def session_hash(request: Request) -> str:
    return hashlib.sha256(request.headers.get("authorization", "").encode()).hexdigest()


def save_challenge(request, options, kind, username, origin, rp_id):
    challenge_id = secrets.token_urlsafe(32)
    with connect() as con:
        con.execute("DELETE FROM passkey_challenges WHERE expires_at <= ?", (int(time.time()),))
        con.execute("INSERT INTO passkey_challenges VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            challenge_id, options.challenge, kind, username,
            session_hash(request) if kind == "register" else "", origin, rp_id,
            int(time.time()) + CEREMONY_SECONDS,
        ))
    return {"challenge_id": challenge_id, "options": json.loads(options_to_json(options))}


def consume_challenge(request, challenge_id, kind, username):
    origin, rp_id = relying_party(request)
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM passkey_challenges WHERE id = ?", (challenge_id,)).fetchone()
        con.execute("DELETE FROM passkey_challenges WHERE id = ?", (challenge_id,))
    if (not row or row["expires_at"] <= time.time() or row["kind"] != kind
            or row["username"] != username or row["origin"] != origin or row["rp_id"] != rp_id
            or (kind == "register" and row["session_hash"] != session_hash(request))):
        raise HTTPException(400, "Die Passkey-Anfrage ist abgelaufen oder ungültig. Bitte erneut starten.")
    return row


def registration_options(request, password):
    rate_limit(request)
    username = account(request)
    try:
        auth.verify_password(username, password)
    except HTTPException as exc:
        raise HTTPException(400, "Das aktuelle Passwort ist falsch.") from exc
    origin, rp_id = relying_party(request)
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO passkey_users VALUES (?, ?)", (username, secrets.token_bytes(32)))
        handle = con.execute("SELECT handle FROM passkey_users WHERE username = ?", (username,)).fetchone()[0]
        existing = con.execute("SELECT id FROM passkeys WHERE username = ? AND rp_id = ?", (username, rp_id)).fetchall()
    if len(existing) >= 20:
        raise HTTPException(400, "Bitte zuerst einen nicht mehr benötigten Passkey entfernen.")
    options = generate_registration_options(
        rp_id=rp_id, rp_name="RoboterSteve", user_name=username, user_id=handle,
        timeout=120000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(row["id"])) for row in existing],
    )
    return save_challenge(request, options, "register", username, origin, rp_id)


def register(request, challenge_id, credential, name):
    username = account(request)
    challenge = consume_challenge(request, challenge_id, "register", username)
    try:
        require_same_origin_context(credential)
        result = verify_registration_response(
            credential=credential, expected_challenge=challenge["challenge"],
            expected_rp_id=challenge["rp_id"], expected_origin=challenge["origin"],
            require_user_verification=True,
        )
    except (WebAuthnException, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(400, "Der Passkey konnte nicht bestätigt werden. Bitte erneut versuchen.") from exc
    try:
        with connect() as con:
            con.execute("INSERT INTO passkeys VALUES (?, ?, ?, ?, ?, ?, ?, NULL)", (
                bytes_to_base64url(result.credential_id), username, challenge["rp_id"],
                result.credential_public_key, result.sign_count,
                name.strip() or "Mein Passkey", int(time.time()),
            ))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Dieser Passkey ist bereits eingerichtet.") from exc
    return {"ok": True}


def authentication_options(request):
    rate_limit(request)
    origin, rp_id = relying_party(request)
    options = generate_authentication_options(
        rp_id=rp_id, timeout=120000, user_verification=UserVerificationRequirement.REQUIRED,
    )
    return save_challenge(request, options, "login", auth.configured_username(), origin, rp_id)


def login(request, challenge_id, credential):
    username = auth.configured_username()
    challenge = consume_challenge(request, challenge_id, "login", username)
    # Serialize verification/counter updates so concurrent assertions cannot
    # overwrite a newer counter or authenticate a concurrently revoked credential.
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM passkeys WHERE id = ? AND username = ? AND rp_id = ?", (
            str(credential.get("id", "")), username, challenge["rp_id"],
        )).fetchone()
        if not row:
            raise HTTPException(400, "Dieser Passkey ist nicht registriert. Bitte mit Passwort anmelden und einen Passkey einrichten.")
        handle = con.execute("SELECT handle FROM passkey_users WHERE username = ?", (username,)).fetchone()[0]
        response = credential.get("response")
        if not isinstance(response, dict) or response.get("userHandle") != bytes_to_base64url(handle):
            raise HTTPException(400, "Der Passkey gehört nicht zu diesem Benutzerkonto.")
        try:
            require_same_origin_context(credential)
            result = verify_authentication_response(
                credential=credential, expected_challenge=challenge["challenge"],
                expected_rp_id=challenge["rp_id"], expected_origin=challenge["origin"],
                credential_public_key=row["public_key"], credential_current_sign_count=row["sign_count"],
                require_user_verification=True,
            )
        except (WebAuthnException, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise HTTPException(400, "Die Passkey-Anmeldung konnte nicht bestätigt werden. Bitte erneut versuchen.") from exc
        con.execute("UPDATE passkeys SET sign_count = ?, last_used_at = ? WHERE id = ?", (
            result.new_sign_count, int(time.time()), row["id"],
        ))
    return auth.issue_session(username)


def require_same_origin_context(credential):
    """This app does not authorize WebAuthn ceremonies in cross-origin frames."""
    client_data = parse_client_data_json(base64url_to_bytes(credential["response"]["clientDataJSON"]))
    if client_data.cross_origin:
        raise ValueError("Cross-origin WebAuthn is not supported")


def list_passkeys(request):
    username = account(request)
    with connect() as con:
        rows = con.execute("SELECT id, name, rp_id, created_at, last_used_at FROM passkeys WHERE username = ? ORDER BY created_at DESC", (username,)).fetchall()
    return {"passkeys": [dict(row) for row in rows]}


def delete_passkey(request, credential_id):
    username = account(request)
    with connect() as con:
        con.execute("DELETE FROM passkeys WHERE id = ? AND username = ?", (credential_id, username))
    return {"ok": True}
