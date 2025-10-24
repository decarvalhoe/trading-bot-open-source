import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bootstrap } from "../../bootstrap";

function TutorialCard({ tutorial }) {
  const { t } = useTranslation();
  return (
    <article className="tutorial-card" id={`tutorial-${tutorial.slug}`}>
      <h3 className="heading heading--md">{tutorial.title}</h3>
      {tutorial.embed_kind === "iframe" && tutorial.embed_url && (
        <iframe title={tutorial.embed_title || tutorial.title} src={tutorial.embed_url} className="tutorial-card__iframe" />
      )}
      {tutorial.embed_kind === "video" && tutorial.embed_url && (
        <video controls className="tutorial-card__video">
          <source src={tutorial.embed_url} />
        </video>
      )}
      {tutorial.embed_kind === "html" && tutorial.embed_html && (
        <div className="tutorial-card__html" dangerouslySetInnerHTML={{ __html: tutorial.embed_html }} />
      )}
      {tutorial.notes_html && (
        <div className="tutorial-card__notes" dangerouslySetInnerHTML={{ __html: tutorial.notes_html }} />
      )}
      {tutorial.source_url && (
        <a className="button button--ghost" href={tutorial.source_url} target="_blank" rel="noreferrer">
          {t("Consulter la source")}
        </a>
      )}
    </article>
  );
}

export default function StrategyDocumentationPage() {
  const { t } = useTranslation();
  const [documentation, setDocumentation] = useState(bootstrap?.data?.strategyDocumentation || {});
  const endpoint = bootstrap?.config?.strategyDocumentation?.endpoint || "/strategies/documentation/bundle";

  useEffect(() => {
    if (documentation.body_html) {
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (!cancelled) {
          setDocumentation(payload || {});
        }
      } catch (error) {
        if (!cancelled) {
          console.error("Impossible de charger la documentation des stratégies", error);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [documentation.body_html, endpoint]);

  return (
    <div className="strategy-documentation-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Documentation stratégies")}</h1>
        <p className="text text--muted">
          {t("Référentiel des champs YAML/Python et tutoriels pour l'algo-engine.")}
        </p>
        {documentation.schema_version && (
          <p className="text text--muted">
            {t("Version du schéma : {{version}}", { version: documentation.schema_version })}
          </p>
        )}
      </header>

      {documentation.body_html && (
        <section className="card" aria-labelledby="strategy-doc-body">
          <div className="card__body">
            <div id="strategy-doc-body" className="strategy-doc" dangerouslySetInnerHTML={{ __html: documentation.body_html }} />
          </div>
        </section>
      )}

      {Array.isArray(documentation.tutorials) && documentation.tutorials.length > 0 && (
        <section className="card" aria-labelledby="tutorials-title">
          <div className="card__header">
            <h2 id="tutorials-title" className="heading heading--lg">
              {t("Tutoriels")}
            </h2>
          </div>
          <div className="card__body tutorials-grid">
            {documentation.tutorials.map((tutorial) => (
              <TutorialCard key={tutorial.slug} tutorial={tutorial} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
