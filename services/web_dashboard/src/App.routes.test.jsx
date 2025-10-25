import React from "react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter, Outlet } from "react-router-dom";
import { render, screen } from "@testing-library/react";

function createPageStub(testId) {
  const Component = () => <div data-testid={testId}>{testId}</div>;
  Component.displayName = `Mock${testId}`;
  return Component;
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: {
      language: "fr",
      resolvedLanguage: "fr",
      changeLanguage: () => Promise.resolve(),
    },
  }),
}));

vi.mock("./layouts/DashboardLayout.jsx", () => ({
  default: function MockDashboardLayout() {
    return (
      <div data-testid="dashboard-layout">
        <Outlet />
      </div>
    );
  },
}));

vi.mock("./components/ProtectedRoute.jsx", () => ({
  default: function MockProtectedRoute({ children }) {
    return <>{children}</>;
  },
}));

vi.mock("./pages/Dashboard/DashboardPage.jsx", () => ({ default: createPageStub("dashboard-page") }));
vi.mock("./pages/Follower/FollowerDashboardPage.jsx", () => ({ default: createPageStub("follower-page") }));
vi.mock("./pages/Marketplace/MarketplacePage.jsx", () => ({ default: createPageStub("marketplace-page") }));
vi.mock("./pages/Strategies/StrategiesPage.jsx", () => ({ default: createPageStub("strategies-page") }));
vi.mock("./pages/Strategies/StrategyExpressPage.jsx", () => ({ default: createPageStub("strategy-express-page") }));
vi.mock("./pages/Strategies/StrategyDocumentationPage.jsx", () => ({
  default: createPageStub("strategy-documentation-page"),
}));
vi.mock("./pages/Strategies/StrategyDesignerPage.jsx", () => ({
  default: createPageStub("strategy-designer-page"),
}));
vi.mock("./pages/Strategies/StrategyBacktestPage.jsx", () => ({
  default: createPageStub("strategy-backtest-page"),
}));
vi.mock("./pages/Strategies/AIStrategyAssistantPage.jsx", () => ({
  default: createPageStub("strategy-ai-assistant-page"),
}));
vi.mock("./pages/Help/HelpCenterPage.jsx", () => ({ default: createPageStub("help-center-page") }));
vi.mock("./pages/Status/StatusPage.jsx", () => ({ default: createPageStub("status-page") }));
vi.mock("./pages/trading/OrdersPage.jsx", () => ({ default: createPageStub("orders-page") }));
vi.mock("./pages/trading/PositionsPage.jsx", () => ({ default: createPageStub("positions-page") }));
vi.mock("./pages/trading/ExecutePage.jsx", () => ({ default: createPageStub("execute-page") }));
vi.mock("./pages/MarketPage.jsx", () => ({ default: createPageStub("market-page") }));
vi.mock("./pages/AlertsPage.jsx", () => ({ default: createPageStub("alerts-page") }));
vi.mock("./pages/ReportsPage.jsx", () => ({ default: createPageStub("reports-page") }));
vi.mock("./pages/SettingsPage.jsx", () => ({ default: createPageStub("settings-page") }));
vi.mock("./pages/Account/AccountLoginPage.jsx", () => ({ default: createPageStub("account-login-page") }));
vi.mock("./pages/Account/AccountRegisterPage.jsx", () => ({ default: createPageStub("account-register-page") }));
vi.mock("./pages/NotFound/NotFoundPage.jsx", () => ({ default: createPageStub("not-found-page") }));
vi.mock("./pages/Onboarding/OnboardingPage.jsx", () => ({
  default: createPageStub("onboarding-page"),
}));

import App from "./App.jsx";

describe("App routing", () => {
  const renderAppAt = (path) =>
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    );

  const routeCases = [
    { path: "/strategies/designer", testId: "strategy-designer-page" },
    { path: "/strategies/backtest", testId: "strategy-backtest-page" },
    { path: "/strategies/ai-assistant", testId: "strategy-ai-assistant-page" },
    { path: "/onboarding", testId: "onboarding-page" },
  ];

  routeCases.forEach(({ path, testId }) => {
    it(`renders the expected wrapper when navigating to ${path}`, () => {
      renderAppAt(path);

      expect(screen.getByTestId(testId)).toBeInTheDocument();
    });
  });
});
