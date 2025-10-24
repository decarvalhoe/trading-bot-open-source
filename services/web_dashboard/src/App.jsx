import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import DashboardLayout from "./layouts/DashboardLayout.jsx";
import DashboardPage from "./pages/Dashboard/DashboardPage.jsx";
import FollowerDashboardPage from "./pages/Follower/FollowerDashboardPage.jsx";
import MarketplacePage from "./pages/Marketplace/MarketplacePage.jsx";
import StrategiesPage from "./pages/Strategies/StrategiesPage.jsx";
import StrategyExpressPage from "./pages/Strategies/StrategyExpressPage.jsx";
import StrategyDocumentationPage from "./pages/Strategies/StrategyDocumentationPage.jsx";
import StrategyDesignerPage from "./pages/Strategies/StrategyDesignerPage.jsx";
import StrategyBacktestPage from "./pages/Strategies/StrategyBacktestPage.jsx";
import AIStrategyAssistantPage from "./pages/Strategies/AIStrategyAssistantPage.jsx";
import HelpCenterPage from "./pages/Help/HelpCenterPage.jsx";
import StatusPage from "./pages/Status/StatusPage.jsx";
import OrdersPage from "./pages/trading/OrdersPage.jsx";
import PositionsPage from "./pages/trading/PositionsPage.jsx";
import ExecutePage from "./pages/trading/ExecutePage.jsx";
import MarketPage from "./pages/MarketPage.jsx";
import AlertsPage from "./pages/AlertsPage.jsx";
import ReportsPage from "./pages/ReportsPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import AccountLoginPage from "./pages/Account/AccountLoginPage.jsx";
import AccountRegisterPage from "./pages/Account/AccountRegisterPage.jsx";
import NotFoundPage from "./pages/NotFound/NotFoundPage.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import OnboardingPage from "./pages/Onboarding/OnboardingPage.jsx";

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
          path="/market"
          element={(
            <ProtectedRoute>
              <MarketPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/trading/orders"
          element={(
            <ProtectedRoute>
              <OrdersPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/trading/positions"
          element={(
            <ProtectedRoute>
              <PositionsPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/trading/execute"
          element={(
            <ProtectedRoute>
              <ExecutePage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/alerts"
          element={(
            <ProtectedRoute>
              <AlertsPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/reports"
          element={(
            <ProtectedRoute>
              <ReportsPage />
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
          path="/strategies/designer"
          element={(
            <ProtectedRoute>
              <StrategyDesignerPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/strategies/backtest"
          element={(
            <ProtectedRoute>
              <StrategyBacktestPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="/strategies/ai-assistant"
          element={(
            <ProtectedRoute>
              <AIStrategyAssistantPage />
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
          path="/onboarding"
          element={(
            <ProtectedRoute>
              <OnboardingPage />
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
          path="/account/settings"
          element={(
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          )}
        />
        <Route path="/account" element={<Navigate to="/account/settings" replace />} />
        <Route path="/account/login" element={<AccountLoginPage />} />
        <Route path="/account/register" element={<AccountRegisterPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
