"""Auth routes — token endpoint for issuing JWTs."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.security import create_jwt_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Simple dev users; replace later with DB
DEV_USERS = {
    "demo": "demo123",
    "admin": "admin123",
}


@router.post("/token", response_model=TokenResponse)
def issue_token(body: TokenRequest) -> TokenResponse:
    """Issue a JWT bearer token for the given dev credentials."""
    expected = DEV_USERS.get(body.username)
    if not expected or expected != body.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_jwt_token(subject=body.username)
    return TokenResponse(access_token=token)