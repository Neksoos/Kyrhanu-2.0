"""
Authentication router: Telegram + Email/Password.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
import secrets

from database import get_db
from models import User, AuthProvider
from config import settings
from services.telegram_auth import verify_telegram_init_data, extract_user_info, verify_telegram_login_widget
from services.analytics import analytics, TrackedEvent
from schemas import TelegramAuthRequest, TelegramWidgetAuthRequest, RegisterRequest, LoginRequest

router = APIRouter()
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


from typing import Optional


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user."""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Get user from DB
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    if user.banned_at:
        raise HTTPException(status_code=403, detail="Account banned")
    
    # Update last active
    user.last_active_at = datetime.utcnow()
    await db.commit()
    
    return user


@router.post("/telegram")
async def auth_telegram(
    payload: TelegramAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate via Telegram WebApp initData.
    """
    # Verify Telegram data
    try:
        parsed = verify_telegram_init_data(payload.init_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {str(e)}")
    
    if not parsed:
        raise HTTPException(status_code=401, detail="Invalid Telegram data")
    
    user_info = extract_user_info(parsed)
    if not user_info:
        raise HTTPException(status_code=400, detail="User info missing")
    
    # Check existing user
    result = await db.execute(
        select(User).where(
            (User.auth_provider == AuthProvider.TELEGRAM) &
            (User.provider_id == str(user_info['tg_id']))
        )
    )
    user = result.scalar_one_or_none()
    
    is_new = False
    
    if not user:
        # Create new user
        referral_code = secrets.token_urlsafe(8)[:10]

        tg_username = user_info.get('username')
        if tg_username:
            taken = await db.execute(select(User).where(User.username == tg_username))
            if taken.scalar_one_or_none():
                tg_username = None
        
        user = User(
            username=tg_username,
            display_name=user_info.get('first_name'),
            auth_provider=AuthProvider.TELEGRAM,
            provider_id=str(user_info['tg_id']),
            avatar_url=user_info.get('photo_url'),
            referral_code=referral_code,
            accepted_tos=True,  # Telegram implies acceptance
            accepted_privacy=True,
            kleynodu=50  # Welcome bonus
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        is_new = True
        
        # Track registration
        await analytics.track(TrackedEvent(
            name="user_registered",
            user_id=user.id,
            session_id=None,
            properties={"provider": "telegram", "is_premium": user_info.get('is_premium', False)}
        ))
    else:
        # Update info
        if user_info.get('username'):
            new_username = user_info['username']
            taken = await db.execute(
                select(User).where((User.username == new_username) & (User.id != user.id))
            )
            if not taken.scalar_one_or_none():
                user.username = new_username
        if user_info.get('first_name'):
            user.display_name = user_info['first_name']
        if user_info.get('photo_url'):
            user.avatar_url = user_info['photo_url']
        
        await analytics.track(TrackedEvent(
            name="user_login",
            user_id=user.id,
            session_id=None,
            properties={"provider": "telegram"}
        ))
    
    await db.commit()
    
    # Generate tokens
    access_token = create_access_token({"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_new": is_new,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "chervontsi": user.chervontsi,
            "kleynodu": user.kleynodu,
            "level": user.level,
            "experience": user.experience,
            "glory": user.glory,
            "energy": user.energy,
            "max_energy": user.max_energy,
            "referral_code": user.referral_code
        }
    }


@router.post("/telegram-widget")
async def auth_telegram_widget(
    payload: TelegramWidgetAuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate via Telegram Login Widget (browser)."""
    # pydantic v2
    data = payload.model_dump()

    try:
        ok = verify_telegram_login_widget(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {str(e)}")

    if not ok:
        raise HTTPException(status_code=401, detail="Invalid Telegram widget data")

    tg_id = str(payload.id)

    # Check existing TELEGRAM user
    result = await db.execute(
        select(User).where(
            (User.auth_provider == AuthProvider.TELEGRAM) &
            (User.provider_id == tg_id)
        )
    )
    user = result.scalar_one_or_none()

    is_new = False

    if not user:
        referral_code = secrets.token_urlsafe(8)[:10]

        tg_username = payload.username
        if tg_username:
            taken = await db.execute(select(User).where(User.username == tg_username))
            if taken.scalar_one_or_none():
                tg_username = None
        user = User(
            username=tg_username,
            display_name=payload.first_name,
            auth_provider=AuthProvider.TELEGRAM,
            provider_id=tg_id,
            avatar_url=payload.photo_url,
            referral_code=referral_code,
            accepted_tos=True,
            accepted_privacy=True,
            kleynodu=50,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        is_new = True

        await analytics.track(TrackedEvent(
            name="user_registered",
            user_id=user.id,
            session_id=None,
            properties={"provider": "telegram_widget"}
        ))
    else:
        # Update info
        if payload.username:
            new_username = payload.username
            taken = await db.execute(
                select(User).where((User.username == new_username) & (User.id != user.id))
            )
            if not taken.scalar_one_or_none():
                user.username = new_username
        if payload.first_name:
            user.display_name = payload.first_name
        if payload.photo_url:
            user.avatar_url = payload.photo_url

        await analytics.track(TrackedEvent(
            name="user_login",
            user_id=user.id,
            session_id=None,
            properties={"provider": "telegram_widget"}
        ))

        await db.commit()

    access_token = create_access_token({"sub": str(user.id)})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_new": is_new,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "chervontsi": user.chervontsi,
            "kleynodu": user.kleynodu,
            "level": user.level,
            "experience": user.experience,
            "glory": user.glory,
            "energy": user.energy,
            "max_energy": user.max_energy,
            "referral_code": user.referral_code,
        },
    }


@router.post("/register")
async def register_email(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Register with email/password.
    """
    if not payload.age_confirm:
        raise HTTPException(status_code=400, detail="Age confirmation required (13+)")
    
    # Validate
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be 8+ characters")
    
    # Check existing
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username taken")
    
    # Create user
    referral_code = secrets.token_urlsafe(8)[:10]
    
    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=pwd_context.hash(payload.password),
        auth_provider=AuthProvider.EMAIL,
        referral_code=referral_code,
        accepted_tos=True,
        accepted_privacy=True,
        age_verified=payload.age_confirm,
        kleynodu=50
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Track
    await analytics.track(TrackedEvent(
        name="user_registered",
        user_id=user.id,
        session_id=None,
        properties={"provider": "email"}
    ))
    
    # Auto-login
    access_token = create_access_token({"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "chervontsi": user.chervontsi,
            "kleynodu": user.kleynodu,
            "level": user.level,
            "experience": user.experience,
            "glory": user.glory,
            "energy": user.energy,
            "max_energy": user.max_energy,
            "referral_code": user.referral_code
        }
    }


@router.post("/login")
async def login_email(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Login with email or username.
    """
    # Find user
    result = await db.execute(
        select(User).where(
            (User.email == payload.username_or_email) | (User.username == payload.username_or_email)
        )
    )
    user = result.scalar_one_or_none()
    
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not pwd_context.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Update
    user.last_active_at = datetime.utcnow()
    await db.commit()
    
    # Track
    await analytics.track(TrackedEvent(
        name="user_login",
        user_id=user.id,
        session_id=None,
        properties={"provider": "email"}
    ))
    
    access_token = create_access_token({"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "chervontsi": user.chervontsi,
            "kleynodu": user.kleynodu,
            "level": user.level,
            "experience": user.experience,
            "glory": user.glory,
            "energy": user.energy,
            "max_energy": user.max_energy,
            "referral_code": user.referral_code
        }
    }


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "chervontsi": current_user.chervontsi,
        "kleynodu": current_user.kleynodu,
        "level": current_user.level,
        "experience": current_user.experience,
        "glory": current_user.glory,
        "energy": current_user.energy,
        "max_energy": current_user.max_energy,
        "referral_code": current_user.referral_code,
        "anomaly_score": current_user.anomaly_score
    }