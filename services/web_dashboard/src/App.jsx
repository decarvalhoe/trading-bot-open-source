import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import DashboardLayout from "./layouts/DashboardLayout.jsx";
import DashboardPage from "./pages/Dashboard/DashboardPage.jsx";
import FollowerDashboardPage from "./pages/Follower/FollowerDashboardPage.jsx";
import MarketplacePage from "./pages/Marketplace/MarketplacePage.jsx";
import StrategiesPage from "./pages/Strategies/StrategiesPage.jsx";
import StrategyExpressPage from "./pages/Strategies/StrategyExpressPage.jsx";
import StrategyDocumentationPage from "./pages/Strategies/StrategyDocumentationPage.jsx";
import HelpCenterPage from "./pages/Help/HelpCenterPage.jsx";
import StatusPage from "./pages/Status/StatusPage.jsx";
import AccountLoginPage from "./pages/Account/AccountLoginPage.jsx";
import AccountSettingsPage from "./pages/Account/AccountSettingsPage.jsx";
import AccountRegisterPage from "./pages/Account/AccountRegisterPage.jsx";
import NotFoundPage from "./pages/NotFound/NotFoundPage.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/dashboard"
          element={(
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/dashboard/followers"
          element={(
            <ProtectedRoute>
              <FollowerDashboardPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/marketplace"
          element={(
            <ProtectedRoute>
              <MarketplacePage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/strategies"
          element={(
            <ProtectedRoute>
              <StrategiesPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/strategies/new"
          element={(
            <ProtectedRoute>
              <StrategyExpressPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/strategies/documentation"
          element={(
            <ProtectedRoute>
              <StrategyDocumentationPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/help"
          element={(
            <ProtectedRoute>
              <HelpCenterPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/status"
          element={(
            <ProtectedRoute>
              <StatusPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/account"
          element={(
            <ProtectedRoute>
              <AccountSettingsPage />
            </ProtectedRoute>
          )}
        />
        <Route path="/account/login" element={<AccountLoginPage />} />
        <Route path="/account/register" element={<AccountRegisterPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
