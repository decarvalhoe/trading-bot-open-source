# Dashboard Modernization Specification (Rev. 2026-01)

## Purpose
Align modernization efforts for the trading dashboard SPA with the foundation already implemented in `services/web_dashboard/src`. This revision supersedes earlier assumptions that a fresh router or layout were required.

## Current Foundation
- **SPA bootstrap** — `src/main.jsx` already mounts the application with i18n, TanStack Query, routing, and authentication context providers, ensuring a consistent shell and data layer.
- **Route map** — `src/App.jsx` defines authenticated areas for dashboards, trading, marketplace, strategies, help, and status, plus public auth pages, using `ProtectedRoute` for access control.
- **Layout shell** — `layouts/DashboardLayout.jsx` delivers the sidebar navigation, language switcher, auth-aware header, outlet, and footer across all pages.

The modernization scope must build on these assets instead of re-implementing navigation, routing, or context plumbing.

## Authentication & Session Round-trip

The existing React shell already performs a complete cookie-backed authentication loop that the modernization effort must preserve.

- `AuthProvider` reads the dashboard bootstrap config to resolve the `/account/login`, `/account/logout`, and `/account/session` endpoints exposed by the FastAPI service and stores them in context for consumers. When the provider mounts, it calls `fetchSession` with `credentials: "include"`, normalises the payload, and transitions the app into `authenticated`, `anonymous`, or `error` states while synchronising the bearer token stored by `ApiClient` for follow-up API calls.
- `login` delegates to the dashboard service, then immediately refreshes the session so the SPA state is driven by the canonical `/account/session` response. `logout` always clears the stored token and re-fetches the session, even if the server-side logout fails, so the client mirrors server cookies.
- `normalizeSession` tolerates payloads that provide `token` or `access_token`, ensuring the SPA keeps working as long as the dashboard service continues to return the canonical session shape.

### Backend `/account/*` contract

- `POST /account/login` calls the upstream auth service, sets secure `access_token` and `refresh_token` cookies, and then resolves the authenticated user profile through `_auth_me` so the SPA receives the same `AccountSession` structure as `/account/session`.
- `GET /account/session` inspects the incoming cookies, attempts to refresh expired access tokens server-side, and returns `authenticated: true` only when a user profile is confirmed. Failed lookups clear cookies and emit `authenticated: false`.
- `POST /account/logout` notifies the upstream auth service (best effort), clears both cookies, and responds with `authenticated: false`. Registration flows reuse the SPA shell but do not alter the session until the user explicitly logs in.

Modernisation work must treat this loop as source of truth: client state changes only after `/account/session` resolves, and cookies remain the primary long-lived credential store.

## API Integration Baseline

The SPA already centralises HTTP calls through `src/lib/api.js`.

- `ApiClient` encapsulates base URL resolution, bearer token persistence, query-string construction, and automatic `credentials: "include"` handling for the `/account/*` endpoints.
- Feature-specific helpers (`alerts`, `strategies`, `orders`, `marketplace`, `dashboard`, `onboarding`, etc.) all call the dashboard service endpoints emitted by `_build_global_config` instead of targeting downstream microservices directly. They inherit consistent headers, error parsing, and token injection, and can be re-pointed via configuration when the backend proxy changes.
- The same client instance is imported throughout the SPA, so once `AuthProvider` updates the stored bearer token the entire application benefits without per-module changes.

### Modernization guardrails for auth & integrations

- **Preserve the cookie/session contract.** Do not bypass `/account/login`, `/account/logout`, or `/account/session`; any UX improvements (e.g., session expiry banners, proactive refresh triggers) must continue to rely on those endpoints so that cookies remain authoritative.
- **Reuse the central `ApiClient`.** New features must plug into the existing client namespaces or extend it with additional helper groups so that retries, headers, and credential handling stay consistent. Calling microservices directly from the SPA is out of scope unless the backend service is refactored in tandem.
- **Target genuine enhancements.** Focus on surfacing clearer error states, optionally instrumenting session refresh telemetry, or collaborating with the backend if additional token metadata is required. Avoid inventing alternate auth flows or duplicating HTTP wrappers that the current client already covers.

## Active Navigation Inventory

The current router and sidebar expose the following destinations. Each item is tagged to clarify whether the modernization effort must deliver a redesigned experience (`Redesign`) or preserve the existing UX with only integration polish (`Preserve`).

| Path | Purpose | Source | Modernization status |
| --- | --- | --- | --- |
| `/dashboard` | Authenticated dashboard landing | `App.jsx` route, sidebar link | Redesign |
| `/dashboard/followers` | Copy-trading follower metrics | `App.jsx` route, sidebar link | Redesign |
| `/marketplace` | Strategy marketplace browser | `App.jsx` route, sidebar link | Redesign |
| `/market` | Real-time market view | `App.jsx` route, sidebar link | Redesign |
| `/trading/orders` | Orders management | `App.jsx` route, sidebar link | Redesign |
| `/trading/positions` | Open positions monitoring | `App.jsx` route, sidebar link | Redesign |
| `/trading/execute` | Order ticket execution | `App.jsx` route, sidebar link | Redesign |
| `/alerts` | Alert configuration & feed | `App.jsx` route, sidebar link | Redesign |
| `/reports` | Performance reports | `App.jsx` route, sidebar link | Redesign |
| `/strategies` | Strategy portfolio overview | `App.jsx` route, sidebar link | Redesign |
| `/strategies/new` | Strategy Express builder | `App.jsx` route, sidebar link | Redesign |
| `/strategies/documentation` | Strategy documentation library | `App.jsx` route, sidebar link | Preserve |
| `/help` | Help center & training hub | `App.jsx` route, sidebar link | Preserve |
| `/status` | Service status dashboard | `App.jsx` route, sidebar link | Preserve |
| `/account/settings` | Account & API management | `App.jsx` route, sidebar link | Redesign |
| `/account` → `/account/settings` | Redirect to account settings | `App.jsx` redirect | Preserve |
| `/account/login` | Public login | `App.jsx` route | Preserve |
| `/account/register` | Public registration | `App.jsx` route | Preserve |
| `*` | Not-found boundary | `App.jsx` catch-all | Preserve |

### Navigation tree for modernization

- **Dashboard**
  - `/dashboard` (Redesign)
  - `/dashboard/followers` (Redesign)
- **Trading**
  - `/trading/orders` (Redesign)
  - `/trading/positions` (Redesign)
  - `/trading/execute` (Redesign)
- **Market Intelligence**
  - `/market` (Redesign)
  - `/alerts` (Redesign)
  - `/reports` (Redesign)
- **Strategies**
  - `/strategies` (Redesign)
  - `/strategies/new` (Redesign)
  - `/strategies/documentation` (Preserve)
- **Marketplace**
  - `/marketplace` (Redesign)
- **Support**
  - `/help` (Preserve)
  - `/status` (Preserve)
- **Account**
  - `/account/settings` (Redesign)
  - `/account` redirect (Preserve)
  - `/account/login` (Preserve)
  - `/account/register` (Preserve)
- **System**
  - `*` not-found (Preserve)

Retain all sidebar entries defined in `layouts/DashboardLayout.jsx` while applying the redesign treatments noted above to sections flagged for modernization.

## Gaps to Address
1. **Visual refinements**
   - Harmonize spacing/typography with the design tokens in `docs/ui/README.md` and add missing dark-mode states for secondary panels.
   - Refresh the sidebar and header to match current branding (iconography, responsive collapse behaviour).
2. **Performance & responsiveness**
   - Audit bundle size, enable code-splitting on infrequently used routes (e.g., strategy documentation) and lazy-load heavy charting modules.
   - Define loading skeletons for slow queries surfaced through TanStack Query to avoid layout shift.
3. **Observability & error handling**
   - Standardize toast/alert surfaces for mutation errors; log critical client errors to the observability pipeline via existing APIs.
   - Instrument route transitions and data fetch timings to feed UX performance dashboards.
4. **Internationalisation polish**
   - Treat the backend bootstrap as the source of truth for languages and translations. `LocalizationMiddleware` resolves the active language (query string → persisted cookie → `Accept-Language`) and injects an `<script id="i18n-bootstrap">` payload exposing the selected language, the full language list, and each catalog via `template_base_context`. `src/i18n/config.js` consumes this payload at startup to initialise i18next and derive `availableLanguages`, so new strings must be added to the backend JSON catalogs before front-end usage.
   - The `DashboardLayout` switcher should keep relying on the i18next `languages` array so it always reflects the backend bundle. When a user picks a language, update the current URL's `lang` query parameter (use `window.location.replace` to avoid stacking history entries) and allow the subsequent navigation to reload with the correct bootstrap payload. The middleware will refresh the `dashboard_lang` cookie at the same time, ensuring the choice survives future visits without an explicit query parameter. Consider adding a brief pressed/loading state on the selected option while the page reloads to communicate that the locale is changing.
   - When no `lang` parameter is present, the client should continue to honour the bootstrap-provided default so the initial render matches the server-rendered `<html lang>` attribute.
   - Optional client-side persistence: if we want to remember the selection beyond the server cookie (e.g., multi-profile browsers or pre-auth flows), store the chosen language in `localStorage`. On boot, read the stored value before rendering the switcher; if it differs from the bootstrap language, call `i18next.changeLanguage` using the already embedded catalogs and `history.replaceState` the `lang` parameter so the backend can catch up on the next navigation. Backend changes required: expose a lightweight endpoint (e.g., `POST /api/preferences/language`) that writes the preference to the user profile and teaches `template_base_context` to prioritise this persisted value when assembling the bootstrap payload.

## Out of Scope
- Replacing React Router, rebuilding the layout container, or re-writing auth guards. These components are already production-ready.
- Backend API contract changes beyond what is already captured in `docs/ui/dashboard-data-contracts.md`.

## Deliverables
1. Updated UI components meeting the visual, performance, and observability requirements above.
2. Documentation updates (component inventory, i18n checklist, performance instrumentation notes).
3. QA checklist covering protected-route access, responsive layouts, and language persistence.
4. Navigation audit sign-off from product and engineering confirming that all routes listed in the Active Navigation Inventory remain functional post-modernization.

## Stakeholders & Approval
- **Product**: Emma Laurent
- **Engineering**: Julien Martin (frontend), Sofia Benali (platform observability)
- **Design**: Alice Moreau

The revised specification must be reviewed and approved by the stakeholders above before work is scheduled. As part of this review, product and engineering leads must explicitly revalidate the navigation scope outlined above to prevent accidental feature loss. Record approvals in the communications log referenced below.
