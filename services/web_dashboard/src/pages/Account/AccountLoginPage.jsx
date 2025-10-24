import React, { useCallback, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import AccountPage from "./AccountPage.jsx";

export default function AccountLoginPage() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const redirectTarget = location.state?.from?.pathname || "/dashboard";

  useEffect(() => {
    if (auth.status === "authenticated") {
      navigate(redirectTarget, { replace: true });
    }
  }, [auth.status, navigate, redirectTarget]);

  const handleSessionChange = useCallback(
    (sessionState) => {
      if (sessionState.status === "ready" || sessionState.status === "anonymous") {
        auth.refresh();
      }
    },
    [auth]
  );

  return <AccountPage onSessionChange={handleSessionChange} />;
}
