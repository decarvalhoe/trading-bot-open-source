from pydantic import BaseModel, EmailStr

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp: str | None = None

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class Me(BaseModel):
    id: int
    email: EmailStr
    roles: list[str]

class TOTPSetup(BaseModel):
    secret: str
    otpauth_url: str
