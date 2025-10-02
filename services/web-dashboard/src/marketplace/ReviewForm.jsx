import React, { useState } from "react";

function ReviewForm({ onSubmit, status, errorMessage }) {
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    const success = await onSubmit({ rating: Number(rating), comment: comment.trim() });
    if (success) {
      setComment("");
    }
  }

  return (
    <form className="review-form" onSubmit={handleSubmit}>
      <h3 className="heading heading--sm">Partager un avis</h3>
      <div className="review-form__fields">
        <label className="review-form__field">
          <span className="review-form__label">Note</span>
          <select value={rating} onChange={(event) => setRating(event.target.value)} className="input">
            {[1, 2, 3, 4, 5].map((value) => (
              <option key={value} value={value}>
                {value} / 5
              </option>
            ))}
          </select>
        </label>
        <label className="review-form__field review-form__field--grow">
          <span className="review-form__label">Commentaire</span>
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className="input"
            rows={3}
            placeholder="Décrivez votre expérience"
          />
        </label>
      </div>
      <div className="review-form__actions">
        <button type="submit" className="button" disabled={status === "submitting"}>
          {status === "submitting" ? "Envoi…" : "Envoyer"}
        </button>
        {status === "success" && <span className="text text--success">Avis enregistré</span>}
        {status === "error" && <span className="text text--critical">{errorMessage || "Erreur lors de l'envoi"}</span>}
      </div>
    </form>
  );
}

export default ReviewForm;
