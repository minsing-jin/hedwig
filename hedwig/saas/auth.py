"""
Supabase Auth integration for Hedwig SaaS.

Provides signup, signin, session management, and JWT verification.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from fastapi import HTTPException, Request

from hedwig.config import SUPABASE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


class AuthError(Exception):
    pass


async def sign_up(email: str, password: str) -> dict:
    """Create a new user account via Supabase Auth."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise AuthError("Supabase not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
        )
        if resp.status_code not in (200, 201):
            raise AuthError(f"Signup failed: {resp.text}")
        return resp.json()


async def sign_in(email: str, password: str) -> dict:
    """Sign in an existing user."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise AuthError("Supabase not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
        )
        if resp.status_code != 200:
            raise AuthError(f"Signin failed: {resp.text}")
        return resp.json()


async def sign_out(access_token: str) -> bool:
    """Invalidate a user session."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/logout",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {access_token}",
            },
        )
        return resp.status_code in (200, 204)


async def get_user(access_token: str) -> Optional[dict]:
    """Get current user from access token."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {access_token}",
            },
        )
        if resp.status_code != 200:
            return None
        return resp.json()


async def refresh_token(refresh_token: str) -> Optional[dict]:
    """Refresh an expired access token."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json",
            },
            json={"refresh_token": refresh_token},
        )
        if resp.status_code != 200:
            return None
        return resp.json()


# ---------------------------------------------------------------------------
# FastAPI dependency for protected routes
# ---------------------------------------------------------------------------

async def get_current_user(request: Request) -> Optional[dict]:
    """FastAPI dependency: extract user from session cookie or Authorization header."""
    token = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("hedwig_access_token")

    if not token:
        return None

    user = await get_user(token)
    return user


async def require_auth(request: Request) -> dict:
    """FastAPI dependency: require authenticated user or raise 401."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
