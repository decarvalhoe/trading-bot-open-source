import React from "react";
import PropTypes from "prop-types";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }) {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "loading") {
    return <div className="text text--muted">Chargement…</div>;
  }

  if (auth.status !== "authenticated") {
    return <Navigate to="/account/login" replace state={{ from: location }} />;
  }

  return children;
}

ProtectedRoute.propTypes = {
  children: PropTypes.node.isRequired,
};
