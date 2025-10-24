import React, { useCallback } from "react";
import { useAuth } from "../../context/AuthContext";
import AccountPage from "./AccountPage.jsx";

export default function AccountSettingsPage() {
  const auth = useAuth();

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
