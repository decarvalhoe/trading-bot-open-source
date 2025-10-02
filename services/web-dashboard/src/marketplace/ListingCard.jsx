import React, { useCallback, useEffect, useMemo, useState } from "react";
import ReviewForm from "./ReviewForm.jsx";

function formatPrice(priceCents, currency) {
  const amount = Number(priceCents || 0) / 100;
  try {
    return new Intl.NumberFormat("fr-FR", { style: "currency", currency }).format(amount);
  } catch (error) {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function formatScore(value) {
  if (value === null || value === undefined) {
    return "ND";
  }
  return Number.parseFloat(value).toFixed(1);
}

function ListingCard({ listing, reviewsEndpoint }) {
  const [expanded, setExpanded] = useState(false);
  const [listingSummary, setListingSummary] = useState(listing);
  const [reviews, setReviews] = useState([]);
  const [reviewsStatus, setReviewsStatus] = useState("idle");
  const [formStatus, setFormStatus] = useState("idle");
  const [formError, setFormError] = useState(null);

  useEffect(() => {
    setListingSummary(listing);
  }, [listing]);

  const loadReviews = useCallback(async () => {
    setReviewsStatus("loading");
    try {
      const response = await fetch(reviewsEndpoint, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      const items = Array.isArray(payload) ? payload : [];
      setReviews(items);
      const totalRatings = items.reduce((sum, item) => sum + Number(item.rating || 0), 0);
      setListingSummary((prev) => ({
        ...prev,
        reviews_count: items.length,
        average_rating: items.length ? Number((totalRatings / items.length).toFixed(2)) : null,
      }));
      setReviewsStatus("ready");
    } catch (error) {
      console.error("Impossible de charger les avis", error);
      setReviewsStatus("error");
    }
  }, [reviewsEndpoint]);

  useEffect(() => {
    if (expanded && (reviewsStatus === "idle" || reviewsStatus === "error")) {
      loadReviews();
    }
  }, [expanded, reviewsStatus, loadReviews]);

  useEffect(() => {
    if (formStatus === "success") {
      const timeout = setTimeout(() => setFormStatus("idle"), 2000);
      return () => clearTimeout(timeout);
    }
    return undefined;
  }, [formStatus]);

  const averageLabel = useMemo(() => {
    if (!listingSummary || listingSummary.average_rating === null || listingSummary.average_rating === undefined) {
      return "Non notée";
    }
    return `${Number.parseFloat(listingSummary.average_rating).toFixed(1)} / 5`;
  }, [listingSummary]);

  const handleSubmitReview = useCallback(
    async ({ rating, comment }) => {
      setFormStatus("submitting");
      setFormError(null);
      try {
        const response = await fetch(reviewsEndpoint, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ rating, comment: comment || null }),
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        await loadReviews();
        setFormStatus("success");
        return true;
      } catch (error) {
        console.error("Impossible d'enregistrer l'avis", error);
        setFormStatus("error");
        setFormError("Impossible d'enregistrer l'avis");
        return false;
      }
    },
    [loadReviews, reviewsEndpoint]
  );

  return (
    <article className="marketplace-card" role="listitem">
      <header className="marketplace-card__header">
        <div>
          <h2 className="heading heading--md marketplace-card__title">{listingSummary.strategy_name}</h2>
          <p className="text text--muted marketplace-card__owner">Créateur #{listingSummary.owner_id}</p>
        </div>
        <div className="marketplace-card__price" aria-label="Prix">
          {formatPrice(listingSummary.price_cents, listingSummary.currency)}
        </div>
      </header>

      {listingSummary.description && <p className="text marketplace-card__description">{listingSummary.description}</p>}

      <dl className="marketplace-card__metrics">
        <div className="marketplace-card__metric">
          <dt>Performance</dt>
          <dd>{formatScore(listingSummary.performance_score)}</dd>
        </div>
        <div className="marketplace-card__metric">
          <dt>Risque</dt>
          <dd>{formatScore(listingSummary.risk_score)}</dd>
        </div>
        <div className="marketplace-card__metric">
          <dt>Notes</dt>
          <dd>{averageLabel}</dd>
        </div>
        <div className="marketplace-card__metric">
          <dt>Avis</dt>
          <dd>{listingSummary.reviews_count || 0}</dd>
        </div>
      </dl>

      <div className="marketplace-card__actions">
        <button type="button" className="button button--ghost" onClick={() => setExpanded((prev) => !prev)}>
          {expanded ? "Masquer les détails" : "Voir les détails"}
        </button>
      </div>

      {expanded && (
        <div className="marketplace-card__details">
          <section className="marketplace-card__reviews" aria-label="Avis des utilisateurs">
            {reviewsStatus === "loading" && <p className="text">Chargement des avis…</p>}
            {reviewsStatus === "error" && (
              <p className="text text--critical">Impossible de récupérer les avis pour le moment.</p>
            )}
            {reviewsStatus === "ready" && reviews.length === 0 && (
              <p className="text text--muted">Aucun avis pour le moment.</p>
            )}
            {reviewsStatus === "ready" && reviews.length > 0 && (
              <ul className="reviews" role="list">
                {reviews.map((review) => (
                  <li key={review.id} className="reviews__item" role="listitem">
                    <div className="reviews__header">
                      <span className="reviews__rating">{review.rating} / 5</span>
                      <time dateTime={review.created_at} className="text text--muted">
                        {new Date(review.created_at).toLocaleDateString("fr-FR")}
                      </time>
                    </div>
                    {review.comment && <p className="text reviews__comment">{review.comment}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <ReviewForm onSubmit={handleSubmitReview} status={formStatus} errorMessage={formError} />
        </div>
      )}
    </article>
  );
}

export default ListingCard;
