from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.services.auth_service import authenticate, user_from_request
from backend.services import passkey_service


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginPayload):
    return authenticate(payload.username, payload.password)


@router.get("/me")
def me(request: Request):
    return {"user": user_from_request(request)}


class PasskeyRegistrationPayload(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class PasskeyVerificationPayload(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=128)
    credential: dict
    name: str = Field(default="Mein Passkey", max_length=80)


@router.get("/passkeys")
def list_passkeys(request: Request):
    return passkey_service.list_passkeys(request)


@router.post("/passkeys/register/options")
def passkey_registration_options(payload: PasskeyRegistrationPayload, request: Request):
    return passkey_service.registration_options(request, payload.password)


@router.post("/passkeys/register/verify")
def passkey_register(payload: PasskeyVerificationPayload, request: Request):
    return passkey_service.register(request, payload.challenge_id, payload.credential, payload.name)


@router.post("/passkeys/login/options")
def passkey_login_options(request: Request):
    return passkey_service.authentication_options(request)


@router.post("/passkeys/login/verify")
def passkey_login(payload: PasskeyVerificationPayload, request: Request):
    return passkey_service.login(request, payload.challenge_id, payload.credential)


@router.delete("/passkeys/{credential_id}")
def delete_passkey(credential_id: str, request: Request):
    return passkey_service.delete_passkey(request, credential_id)
