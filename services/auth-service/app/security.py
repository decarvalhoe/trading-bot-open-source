import os, pyotp
from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
ACCESS_MIN = int(os.getenv("ACCESS_MIN", "15"))
REFRESH_DAYS = int(os.getenv("REFRESH_DAYS", "7"))

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return pwd.hash(p)

def verify_password(p: str, hashed: str) -> bool:
    return pwd.verify(p, hashed)

def create_token_pair(sub: str, roles: list[str]):
    now = datetime.now(timezone.utc)
    access = jwt.encode(
        {"sub": sub, "roles": roles, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=ACCESS_MIN)).timestamp())},
        JWT_SECRET,
        algorithm=JWT_ALG,
    )
    refresh = jwt.encode(
        {"sub": sub, "type": "refresh", "iat": int(now.timestamp()), "exp": int((now + timedelta(days=REFRESH_DAYS)).timestamp())},
        JWT_SECRET,
        algorithm=JWT_ALG,
    )
    return access, refresh

def verify_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

def generate_totp_secret() -> str:
    return pyotp.random_base32()

def totp_now(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret)

