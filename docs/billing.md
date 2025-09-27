# Billing & Entitlements Integration

This repository ships a dedicated `billing-service` (FastAPI) responsible for synchronising Stripe Billing objects with the internal entitlements database as well as an `entitlements-service` exposing a query API.

## Stripe configuration

1. Create a [Stripe API key](https://dashboard.stripe.com/apikeys) with permissions to read subscriptions and products.
2. Create a webhook endpoint targeting `https://<your-host>/webhooks/stripe` and copy the *Signing secret* from the Stripe dashboard.
3. Set the following environment variables for the billing service:

```bash
export STRIPE_API_KEY="sk_live_..."
export STRIPE_WEBHOOK_SECRET="whsec_..."
```

During local development you can forward Stripe events with the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

## Database schema

Both services rely on the shared infrastructure models located in `infra/entitlements_models.py`. They describe plans, features, plan-feature relationships, subscriptions and the entitlement cache.

Apply the metadata to your database when bootstrapping a new environment:

```python
from infra.entitlements_models import Base
from libs.db.db import engine

Base.metadata.create_all(bind=engine)
```

## Enforcing entitlements

The helper `libs.entitlements.install_entitlements_middleware` installs a FastAPI middleware validating capability flags (e.g. `can.use_ibkr`) and quota limits (`quota.active_algos`) on every request. Services receive the resolved entitlements in `request.state.entitlements` when additional per-route checks are required.
