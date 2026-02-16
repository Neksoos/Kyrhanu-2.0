from pydantic import BaseModel, EmailStr

class AuthRegisterIn(BaseModel):
    email: EmailStr
    password: str

class AuthLoginIn(BaseModel):
    email: EmailStr
    password: str

class AuthTelegramInitDataIn(BaseModel):
    initData: str

class AuthTelegramWidgetIn(BaseModel):
    payload: dict

class UserOut(BaseModel):
    id: str
    email: str | None = None
    telegram_id: int | None = None
    telegram_username: str | None = None

class AuthOut(BaseModel):
    ok: bool = True
    user: UserOut
    accessToken: str