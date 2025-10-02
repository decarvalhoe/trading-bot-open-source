# Marketplace Service

The marketplace service exposes APIs to publish algorithmic strategies and to
manage copy-trading subscriptions. It relies on the shared entitlements service
for access control and records all actions in the global audit trail.

## Feature status

| Feature | Status | Notes |
| --- | --- | --- |
| Listings publication & versioning | ✅ Beta (private) | Requires `can.publish_strategy` entitlement and Stripe Connect ID |
| Copy-trading subscriptions | ✅ Beta | Requires `can.copy_trade` entitlement; payments optional via `payment_reference` |
| Moderation & analytics | 🔜 Planned | Moderation workflows and creator analytics scheduled for Q1 2026 |

## Database schema

| Table | Description |
| --- | --- |
| `marketplace_listings` | Published strategies (owner, pricing, Stripe Connect account). |
| `marketplace_versions` | Immutable payloads for each listing version. |
| `marketplace_subscriptions` | Copy-trading subscriptions referencing listings and versions. |
| `audit_logs` | Shared audit trail recording marketplace events. |

## Stripe Connect integration

Publishing a listing requires the creator to provide their Stripe Connect
account identifier (`connect_account_id`). This enables automated revenue
sharing when investors subscribe to the listing.

## Entitlements

Capabilities are resolved through the entitlements middleware:

- `can.publish_strategy` – required to publish or update listings.
- `can.copy_trade` – required to subscribe to a listing or view copies.

Requests must include an `X-User-Id` header (or `X-Customer-Id`) so the
middleware can resolve entitlements.

## REST API

All endpoints are served from the `/marketplace` prefix.

### `POST /marketplace/listings`
Publish a new listing.

```json
{
  "strategy_name": "Momentum Edge",
  "description": "Breakout strategy",
  "price_cents": 19900,
  "currency": "USD",
  "connect_account_id": "acct_123",
  "initial_version": {
    "version": "1.0.0",
    "configuration": {"risk": 2}
  }
}
```

Returns the created listing with the current versions.

### `GET /marketplace/listings`
Browse published listings. Returns the latest version metadata for each entry.

### `POST /marketplace/listings/{listing_id}/versions`
Publish a new version for an existing listing. Only the owner can perform this
operation.

### `POST /marketplace/copies`
Create a copy-trading subscription. Optional `payment_reference` allows linking
to Stripe payment intents.

### `GET /marketplace/copies`
Return the subscriptions owned by the authenticated investor. Each read
operation is recorded to the audit trail.

## Audit trail

All state changes (listing publication, version releases, copy subscriptions and
copy views) are inserted into `audit_logs`. This provides a central trace of
monetisation events for compliance and revenue reconciliation.

## Activation checklist

1. Configure Stripe Connect account IDs and share them securely with operators.
2. Ensure entitlements `can.publish_strategy` and `can.copy_trade` are provisioned via the billing service.
3. Review audit entries in `audit_logs` after each publication to validate compliance.
4. Track follow-up work (moderation tooling, analytics dashboards) under the roadmap in `docs/release-highlights/2025-12.md`.
