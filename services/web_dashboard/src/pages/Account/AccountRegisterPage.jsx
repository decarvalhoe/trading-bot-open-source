import React from "react";
import { useTranslation } from "react-i18next";
import { bootstrap } from "../../bootstrap";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Form,
  FormControl,
  FormField,
  FormLabel,
  FormMessage,
  Input,
} from "../../components/ui/index.js";

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
      <Card aria-labelledby="register-title">
        <CardHeader>
          <CardTitle id="register-title">{t("Inscription")}</CardTitle>
          <CardDescription>
            {t("Renseignez une adresse e-mail valide et un mot de passe respectant nos exigences de sécurité.")}
          </CardDescription>
        </CardHeader>
        <CardContent className="gap-6">
          <Form className="form-grid" action="/account/register" method="post">
            <FormField>
              <FormLabel htmlFor="register-email">{t("Adresse e-mail")}</FormLabel>
              <FormControl>
                <Input
                  id="register-email"
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  defaultValue={data.formEmail || ""}
                />
              </FormControl>
            </FormField>
            <FormField>
              <FormLabel htmlFor="register-password">{t("Mot de passe")}</FormLabel>
              <FormControl>
                <Input id="register-password" type="password" name="password" autoComplete="new-password" required />
              </FormControl>
            </FormField>
            {data.errorMessage && (
              <FormMessage variant="error" role="alert">
                {data.errorMessage}
              </FormMessage>
            )}
            <div>
              <Button type="submit" variant="primary">
                {t("Créer mon compte")}
              </Button>
            </div>
          </Form>
          <p className="text text--muted">
            {t("Déjà inscrit ?")}
            <a href="/account/login" className="ml-1">
              {t("Se connecter")}
            </a>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
