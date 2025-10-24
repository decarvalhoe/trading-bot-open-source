import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bootstrap } from "../../bootstrap";

function ProgressSummary({ progress }) {
  const { t } = useTranslation();
  if (!progress) {
    return null;
  }
  return (
    <section className="card help-card" aria-labelledby="help-progress-title">
      <div className="card__header">
        <h2 id="help-progress-title" className="heading heading--lg">
          {t("Suivi de progression")}
        </h2>
        <p className="text text--muted">
          {t("Visualisez vos avancées dans la base de connaissances et reprenez là où vous vous êtes arrêté.")}
        </p>
      </div>
      <div className="card__body help-progress">
        <div
          className="help-progress__bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress.completion_rate}
        >
          <span className="help-progress__bar-fill" style={{ width: `${progress.completion_rate}%` }} />
        </div>
        <p className="text" aria-live="polite">
          {t("Progression globale : {{rate}}% — {{completed}} / {{total}} ressources parcourues.", {
            rate: progress.completion_rate,
            completed: progress.completed_resources,
            total: progress.total_resources,
          })}
        </p>
        {progress.recent_resources && progress.recent_resources.length > 0 && (
          <section className="help-recent" aria-labelledby="help-recent-title">
            <div className="help-recent__header">
              <h3 id="help-recent-title" className="heading heading--md">
                {t("Dernières ressources consultées")}
              </h3>
              <p className="text text--muted">{t("Mises à jour après chaque consultation.")}</p>
            </div>
            <ul className="help-recent__list">
              {progress.recent_resources.map((item) => (
                <li key={item.slug} className="help-recent__item">
                  <p className="help-recent__title">{item.title}</p>
                  <p className="help-recent__meta">
                    {item.resource_type} · {new Date(item.viewed_at).toLocaleString()}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </section>
  );
}

function ArticleAccordion({ articles }) {
  const { t } = useTranslation();
  if (!articles?.length) {
    return <p className="text text--muted">{t("Aucune question enregistrée pour le moment.")}</p>;
  }
  return (
    <div className="help-faq" role="list">
      {articles.map((article) => (
        <details key={article.slug} className="help-faq__item" role="listitem">
          <summary className="help-faq__question">{article.title}</summary>
          <div className="help-article" dangerouslySetInnerHTML={{ __html: article.body_html }} />
          {article.tags && article.tags.length > 0 && (
            <ul className="help-article__tags" aria-label={t("Mots-clés")}>
              {article.tags.map((tag) => (
                <li key={tag} className="help-article__tag">
                  {tag}
                </li>
              ))}
            </ul>
          )}
        </details>
      ))}
    </div>
  );
}

function ResourceList({ title, items, onMarkViewed }) {
  const { t } = useTranslation();
  if (!items?.length) {
    return (
      <section className="card help-card" aria-labelledby={`${title}-title`}>
        <div className="card__header">
          <h2 id={`${title}-title`} className="heading heading--lg">
            {title}
          </h2>
        </div>
        <div className="card__body">
          <p className="text text--muted">{t("Aucun contenu disponible pour le moment.")}</p>
        </div>
      </section>
    );
  }
  return (
    <section className="card help-card" aria-labelledby={`${title}-title`}>
      <div className="card__header">
        <h2 id={`${title}-title`} className="heading heading--lg">
          {title}
        </h2>
      </div>
      <div className="card__body help-guides">
        <ul className="help-guides__list">
          {items.map((article) => (
            <li key={article.slug} className="help-guides__item">
              <div className="help-guides__content">
                <h3 className="heading heading--md">{article.title}</h3>
                <p className="text text--muted">{article.summary}</p>
              </div>
              <div className="help-guides__actions">
                {onMarkViewed && (
                  <button type="button" className="button button--ghost" onClick={() => onMarkViewed(article.slug)}>
                    {t("Marquer comme consulté")}
                  </button>
                )}
                {article.resource_link && (
                  <a href={article.resource_link} className="button" target="_blank" rel="noreferrer">
                    {t("Ouvrir")}
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function HelpCenterPage() {
  const { t } = useTranslation();
  const helpData = bootstrap?.data?.help || {};
  const [progress, setProgress] = useState(helpData.progress || null);
  const [faq, setFaq] = useState(helpData.faq || []);
  const [guides, setGuides] = useState(helpData.guides || []);
  const [resources, setResources] = useState(helpData.resources || []);
  const articlesEndpoint = helpData.articlesEndpoint || bootstrap?.config?.help?.articlesEndpoint || "/help/articles";

  useEffect(() => {
    if (faq.length || guides.length || resources.length) {
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch(articlesEndpoint, { headers: { Accept: "application/json" } });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (!cancelled && payload) {
          if (payload.progress) {
            setProgress(payload.progress);
          }
          if (payload.sections?.faq) {
            setFaq(payload.sections.faq);
          }
          if (payload.sections?.guide) {
            setGuides(payload.sections.guide);
          }
          const webinars = payload.sections?.webinar || [];
          const notebooks = payload.sections?.notebook || [];
          setResources([...webinars, ...notebooks]);
        }
      } catch (error) {
        if (!cancelled) {
          console.error("Impossible de charger le centre d'aide", error);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [articlesEndpoint, faq.length, guides.length, resources.length]);

  const markViewed = useCallback(
    async (slug) => {
      try {
        const response = await fetch(`${articlesEndpoint}?viewed=${encodeURIComponent(slug)}`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (payload?.progress) {
          setProgress(payload.progress);
        }
        if (payload?.sections?.faq) {
          setFaq(payload.sections.faq);
        }
        if (payload?.sections?.guide) {
          setGuides(payload.sections.guide);
        }
        const webinars = payload?.sections?.webinar || [];
        const notebooks = payload?.sections?.notebook || [];
        setResources([...webinars, ...notebooks]);
      } catch (error) {
        console.error("Impossible de mettre à jour la progression", error);
      }
    },
    [articlesEndpoint]
  );

  return (
    <div className="help-center-page">
      <header className="page-header">
        <h1 className="heading heading--xl">{t("Aide & formation")}</h1>
        <p className="text text--muted">
          {t("Explorez la base de connaissances, suivez votre progression et accédez rapidement aux webinars et notebooks.")}
        </p>
      </header>

      <ProgressSummary progress={progress} />

      <section className="card help-card" aria-labelledby="help-faq-title">
        <div className="card__header">
          <h2 id="help-faq-title" className="heading heading--lg">
            {t("FAQ opérationnelle")}
          </h2>
          <p className="text text--muted">
            {t("Questions récurrentes sur la configuration et l'utilisation quotidienne du tableau de bord.")}
          </p>
        </div>
        <div className="card__body">
          <ArticleAccordion articles={faq} />
        </div>
      </section>

      <ResourceList title={t("Guides & ateliers")} items={guides} onMarkViewed={markViewed} />

      <ResourceList title={t("Webinars & notebooks")} items={resources} onMarkViewed={markViewed} />
    </div>
  );
}
