from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.routing import APIRouter
from sqlalchemy.orm import Session

from infra import EntitlementsBase
from libs.db.db import engine, get_db
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

from .config import settings
from .schemas import FeatureIn, PlanFeatureIn, PlanIn
from .service import attach_features, upsert_feature, upsert_plan
from .stripe_utils import handle_stripe_event, parse_stripe_payload, verify_webhook_signature

configure_logging("billing-service")

app = FastAPI(title="Billing Service", version="0.1.0")
app.add_middleware(RequestContextMiddleware, service_name="billing-service")
setup_metrics(app, service_name="billing-service")

EntitlementsBase.metadata.create_all(bind=engine)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/plans", status_code=201)
def create_plan(payload: PlanIn, db: Session = Depends(get_db)):
    plan = upsert_plan(
        db,
        code=payload.code,
        name=payload.name,
        stripe_price_id=payload.stripe_price_id,
        description=payload.description,
        billing_interval=payload.billing_interval,
        trial_period_days=payload.trial_period_days,
    )
    return {"id": plan.id, "code": plan.code, "name": plan.name}


@router.post("/features", status_code=201)
def create_feature(payload: FeatureIn, db: Session = Depends(get_db)):
    feature = upsert_feature(
        db,
        code=payload.code,
        name=payload.name,
        kind=payload.kind,
        description=payload.description,
    )
    return {"id": feature.id, "code": feature.code, "name": feature.name, "kind": feature.kind}


@router.post("/plans/{plan_code}/features", status_code=202)
def map_feature(plan_code: str, payload: PlanFeatureIn, db: Session = Depends(get_db)):
    if payload.plan_code != plan_code:
        raise HTTPException(status_code=400, detail="plan_code mismatch")
    plan = upsert_plan(db, code=plan_code, name=plan_code, stripe_price_id=plan_code)
    feature = upsert_feature(db, code=payload.feature_code, name=payload.feature_code)
    attach_features(db, plan, [(feature, payload.limit)])
    return {"plan_id": plan.id, "feature_id": feature.id, "limit": payload.limit}


app.include_router(router)


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")
    verify_webhook_signature(body, signature, settings.stripe_webhook_secret)
    payload = parse_stripe_payload(body)
    return handle_stripe_event(payload, db=db)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
