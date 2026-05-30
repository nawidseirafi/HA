import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import yaml
from fastapi import HTTPException, Request
from backend.paths import BACKEND_DIR, API_DIR, PROJECT_DIR, API_CONFIG_PATH, FRONTEND_DIST, LOG_DIR, ENV_PATH

def _load_config() -> dict[str, Any]:
    if not API_CONFIG_PATH.exists():
        return {}
    with API_CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def _auth_config() -> dict[str, Any]:
    return _load_config().get("auth", {})


def _secret_value(value: str, default: str = "") -> str:
    env_values = _load_env_files()
    return (
        os.getenv(value)
        or os.getenv(value.upper())
        or env_values.get(value)
        or env_values.get(value.upper())
        or default
    )


def _load_env_files() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip().strip("\"'")
    return values


def configured_username() -> str:
    config = _auth_config()
    return _secret_value(config.get("username_env", "AGENT_API_USERNAME"), config.get("username", "admin"))


def configured_password() -> str:
    config = _auth_config()
    return _secret_value(config.get("password_env", "AGENT_API_PASSWORD"), config.get("password", "admin"))


def jwt_secret() -> str:
    config = _auth_config()
    secret = _secret_value(config.get("jwt_secret_env", "AGENT_API_JWT_SECRET"), config.get("jwt_secret", ""))
    if secret:
        return secret
    return hashlib.sha256(str(API_CONFIG_PATH.resolve()).encode("utf-8")).hexdigest()


def token_ttl_seconds() -> int:
    return int(_auth_config().get("token_ttl_seconds", 60 * 60 * 24 * 7))


def authenticate(username: str, password: str) -> dict[str, Any]:
    if not hmac.compare_digest(username, configured_username()):
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort ist falsch.")
    if not hmac.compare_digest(password, configured_password()):
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort ist falsch.")
    expires_at = int(time.time()) + token_ttl_seconds()
    token = create_token({"sub": username, "exp": expires_at})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": {"username": username},
    }


def create_token(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_part = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(f"{header_part}.{payload_part}")
    return f"{header_part}.{payload_part}.{signature}"


def verify_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Token ist ungueltig.")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = _sign(signing_input)
    if not hmac.compare_digest(parts[2], expected):
        raise HTTPException(status_code=401, detail="Token ist ungueltig.")
    try:
        payload = json.loads(_b64decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Token ist ungueltig.") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token ist abgelaufen.")
    return payload


def user_from_request(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    payload = verify_token(token)
    return {"username": payload.get("sub", "")}


def _sign(value: str) -> str:
    digest = hmac.new(jwt_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")
