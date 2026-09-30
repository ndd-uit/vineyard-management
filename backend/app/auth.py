"""Clerk session authentication for all business API routes."""

import os
from dataclasses import dataclass

from clerk_backend_api.security import verify_token
from clerk_backend_api.security.types import VerifyTokenOptions
from fastapi import HTTPException, Request


@dataclass(frozen=True)
class AuthenticatedUser:
    sub: str


def verify_clerk_session(token: str) -> dict:
    """Verify a Clerk session JWT; this boundary can be replaced in tests."""
    secret = os.getenv("CLERK_SECRET_KEY")
    jwt_key = os.getenv("CLERK_JWT_KEY")
    issuer = os.getenv("CLERK_ISSUER")
    parties = [item.strip() for item in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if item.strip()]
    if not (secret or jwt_key) or not issuer or not parties:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    try:
        claims = verify_token(token, VerifyTokenOptions(secret_key=None if jwt_key else secret, jwt_key=jwt_key, authorized_parties=parties))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session.") from None
    if claims.get("iss") != issuer or not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return claims


def get_current_user(request: Request) -> AuthenticatedUser:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token or " " in token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    claims = verify_clerk_session(token)
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    allowed = {item.strip() for item in os.getenv("CLERK_ALLOWED_USER_IDS", "").split(",") if item.strip()}
    if allowed and sub not in allowed:
        raise HTTPException(status_code=403, detail="Access denied.")
    return AuthenticatedUser(sub=sub)
