from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from infra import EntitlementsBase
from libs.db.db import engine, get_db

from .resolver import resolve_entitlements
from .schemas import ResolveResponse

app = FastAPI(title="Entitlements Service", version="0.1.0")

EntitlementsBase.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/entitlements/resolve", response_model=ResolveResponse)
def resolve(customer_id: str, db: Session = Depends(get_db)):
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    payload = resolve_entitlements(db, customer_id)
    return ResolveResponse(**payload)
