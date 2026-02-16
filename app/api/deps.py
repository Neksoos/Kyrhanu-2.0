from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import SessionLocal
from app.core.config import settings

bearer = HTTPBearer(auto_error=False)

async def get_db():
    async with SessionLocal() as session:
        yield session

def get_ip(request: Request) -> str | None:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else None)

async def get_current_user_id(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
):
    if not creds:
        raise HTTPException(status_code=401, detail="Missing token")
    token = creds.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")