import React from "react";
import { useTranslation } from "react-i18next";
import { bootstrap } from "../../bootstrap";

export default function AccountRegisterPage() {
  const { t } = useTranslation();
  const data = bootstrap?.data?.accountRegister || {};

  return (
    <div className="account-register-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Créer un compte utilisateur")}</h1>
        <p className="text text--muted">
          {t("Inscrivez-vous pour accéder au tableau de bord, gérer vos stratégies et configurer vos clés API.")}
        </p>
      </header>
      <section className="card" aria-labelledby="register-title">
        <div className="card__header">
          <h2 id="register-title" className="heading heading--lg">
            {t("Inscription")}
          </h2>
          <p className="text text--muted">
            {t("Renseignez une adresse e-mail valide et un mot de passe respectant nos exigences de sécurité.")}
          </p>
        </div>
        <div className="card__body">
          <form className="form-grid" action="/account/register" method="post">
            <label className="designer-field">
              <span className="designer-field__label text text--muted">{t("Adresse e-mail")}</span>
              <input type="email" name="email" autoComplete="email" required defaultValue={data.formEmail || ""} />
            </label>
            <label className="designer-field">
              <span className="designer-field__label text text--muted">{t("Mot de passe")}</span>
              <input type="password" name="password" autoComplete="new-password" required />
            </label>
            {data.errorMessage && (
              <p className="text text--critical" role="alert">
                {data.errorMessage}
              </p>
            )}
            <button type="submit" className="button button--primary">
              {t("Créer mon compte")}
            </button>
          </form>
          <p className="text text--muted">
            {t("Déjà inscrit ?")}
            <a href="/account/login">{t("Se connecter")}</a>
          </p>
        </div>
      </section>
    </div>
  );
}
