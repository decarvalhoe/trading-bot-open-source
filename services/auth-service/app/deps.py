from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .security import verify_token
from libs.db.db import get_db

bearer = HTTPBearer(auto_error=False)

def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = verify_token(creds.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload

def require_roles(*required):
    def checker(payload=Depends(get_current_user)):
        roles = set(payload.get("roles", []))
        if not roles.intersection(required):
            raise HTTPException(status_code=403, detail="Forbidden")
        return payload
    return checker

def db(dep=Depends(get_db)) -> Session:
    return dep
