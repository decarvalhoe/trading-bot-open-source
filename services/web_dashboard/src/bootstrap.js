const DEFAULT_BOOTSTRAP = {
  initialPath: "/dashboard",
  page: "dashboard",
  data: {},
  config: {
    auth: {
      loginEndpoint: "/account/login",
      logoutEndpoint: "/account/logout",
      sessionEndpoint: "/account/session",
    },
    onboarding: {},
    alerts: {},
    routes: {},
  },
};

export function loadBootstrap() {
  const script = document.getElementById("dashboard-bootstrap");
  if (!script || !script.textContent) {
    return DEFAULT_BOOTSTRAP;
  }
  try {
    const payload = JSON.parse(script.textContent);
    if (!payload || typeof payload !== "object") {
      return DEFAULT_BOOTSTRAP;
    }
    return {
      ...DEFAULT_BOOTSTRAP,
      ...payload,
      config: {
        ...DEFAULT_BOOTSTRAP.config,
        ...(payload.config || {}),
      },
    };
  } catch (error) {
    return DEFAULT_BOOTSTRAP;
  }
}

export const bootstrap = loadBootstrap();
