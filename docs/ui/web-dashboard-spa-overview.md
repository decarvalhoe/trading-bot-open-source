# Web Dashboard SPA Shell — Capabilities Overview

## Entry Point and Providers
- `src/main.jsx` bootstraps the React application with `StrictMode`, i18n via `I18nextProvider`, TanStack Query (`QueryClientProvider` with retries disabled on mutations and window focus refetch turned off), React Router's `BrowserRouter`, and an `AuthProvider`. It also forces the `<html>` element into dark mode and renders the app into `#root`.
- The shared providers guarantee authenticated routes can access context and data fetching features consistently.

## Routing Structure
- `src/App.jsx` defines all routes under a single `<Routes>` tree rooted by `DashboardLayout`.
  - The index route redirects to `/dashboard` and authenticated sections are wrapped in `<ProtectedRoute>` components to enforce session checks.
  - Authenticated namespaces include dashboards, trading (orders, positions, execution), market data, alerts, reports, marketplace, follower management, strategies (list, express wizard, documentation), help, status, and account settings.
  - Public routes are limited to login, registration, and a not-found fallback.

## Layout Composition
- `src/layouts/DashboardLayout.jsx` supplies the structural shell: sidebar navigation, header, main content, and footer.
  - Sidebar lists all primary navigation links, highlights the active route, and includes a language switcher using Headless UI's `Listbox` with i18next locales. Language changes are applied immediately via `i18n.changeLanguage` and persisted to `localStorage`, and the same selector also appears on the settings page for easier discovery.
  - Header displays the authenticated user identity and exposes a logout button tied to the auth context.
  - `<Outlet />` renders nested page content and is keyed by pathname for transitions, while the footer displays demo context messaging.

## Access Control
- `components/ProtectedRoute.jsx` reads from `AuthContext`, shows a loading placeholder until auth status resolves, redirects unauthenticated users to `/account/login`, and otherwise renders the requested child component.

These primitives provide a fully functional SPA shell with routing, layout, and auth-aware guards suitable for incremental feature work.
