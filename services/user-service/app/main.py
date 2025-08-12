from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, JSON, ForeignKey, text, select
from libs.db.db import get_db
from jose import jwt
import os

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

class UserPreferences(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    preferences: Mapped[dict] = mapped_column(JSON, server_default=text("'{}'::json"))

app = FastAPI(title="User Service", version="0.1.0")

def require_auth(authorization: str = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split()[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/users/me")
def get_me(payload=Depends(require_auth), db: Session = Depends(get_db)):
    uid = int(payload["sub"])
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    prefs = db.execute(select(UserPreferences).where(UserPreferences.user_id==uid)).scalar_one_or_none()
    return {"id": u.id, "email": u.email, "preferences": (prefs.preferences if prefs else {})}

@app.put("/users/me/preferences")
def update_prefs(body: dict, payload=Depends(require_auth), db: Session = Depends(get_db)):
    uid = int(payload["sub"])
    existing = db.execute(select(UserPreferences).where(UserPreferences.user_id==uid)).scalar_one_or_none()
    if existing:
        existing.preferences = body
    else:
        db.execute(UserPreferences.__table__.insert().values(user_id=uid, preferences=body))
    db.commit()
    return {"ok": True}



