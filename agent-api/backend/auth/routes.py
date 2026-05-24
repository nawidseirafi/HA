from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.auth.service import authenticate, user_from_request


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
