"""Authentication endpoints for the password-protected local app."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.auth import auth_status, login_user, register_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    display_name: str
    password: str


class LoginRequest(BaseModel):
    password: str


@router.get("/status")
async def get_auth_status(request: Request) -> dict:
    return auth_status(request)


@router.post("/register")
async def register(body: RegisterRequest) -> dict:
    result = register_user(body.display_name, body.password)
    return {
        "status": "ok",
        "token": result["token"],
        "display_name": result["display_name"],
    }


@router.post("/login")
async def login(body: LoginRequest) -> dict:
    result = login_user(body.password)
    return {
        "status": "ok",
        "token": result["token"],
        "display_name": result["display_name"],
    }
