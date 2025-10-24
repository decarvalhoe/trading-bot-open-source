import React from "react";
import PropTypes from "prop-types";
import { useTranslation } from "react-i18next";
import AccountApp from "../../account/AccountApp.jsx";
import { bootstrap } from "../../bootstrap";

export default function AccountPage({ onSessionChange }) {
  const { t } = useTranslation();
  const config = bootstrap?.config?.account || {};
  const data = bootstrap?.data?.account || {};
  const endpoints = {
    session: data.sessionEndpoint || config.sessionEndpoint || "/account/session",
    login: data.loginEndpoint || config.loginEndpoint || "/account/login",
    logout: data.logoutEndpoint || config.logoutEndpoint || "/account/logout",
    brokerCredentials:
      data.brokerCredentialsEndpoint || config.brokerCredentialsEndpoint || "/account/broker/credentials",
  };

  return (
    <div className="account-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Compte & API")}</h1>
        <p className="text text--muted">
          {t("Gérez votre session, configurez les brokers et consultez vos identifiants API.")}
        </p>
      </header>
      <AccountApp endpoints={endpoints} onSessionChange={onSessionChange} />
    </div>
  );
}

AccountPage.propTypes = {
  onSessionChange: PropTypes.func,
};

AccountPage.defaultProps = {
  onSessionChange: undefined,
};
