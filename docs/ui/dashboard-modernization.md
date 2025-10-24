# Dashboard Modernization Specification (Rev. 2026-01)

## Purpose
Align modernization efforts for the trading dashboard SPA with the foundation already implemented in `services/web_dashboard/src`. This revision supersedes earlier assumptions that a fresh router or layout were required.

## Current Foundation
- **SPA bootstrap** — `src/main.jsx` already mounts the application with i18n, TanStack Query, routing, and authentication context providers, ensuring a consistent shell and data layer.
- **Route map** — `src/App.jsx` defines authenticated areas for dashboards, trading, marketplace, strategies, help, and status, plus public auth pages, using `ProtectedRoute` for access control.
- **Layout shell** — `layouts/DashboardLayout.jsx` delivers the sidebar navigation, language switcher, auth-aware header, outlet, and footer across all pages.

The modernization scope must build on these assets instead of re-implementing navigation, routing, or context plumbing.

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
   - Complete locale coverage for new UI texts introduced during modernization and ensure the language switcher persists selections via query params/local storage.

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
