import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, FormControl, FormField, FormLabel, FormMessage, Select, Textarea } from "../components/ui/index.js";

function ReviewForm({ onSubmit, status, errorMessage }) {
  const { t } = useTranslation();
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
      <h3 className="heading heading--sm">{t("Partager un avis")}</h3>
      <div className="review-form__fields">
        <FormField className="review-form__field">
          <FormLabel htmlFor="review-rating" className="review-form__label">
            {t("Note")}
          </FormLabel>
          <FormControl>
            <Select id="review-rating" value={rating} onChange={(event) => setRating(event.target.value)}>
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={value}>
                  {t("{value} / 5", { value })}
                </option>
              ))}
            </Select>
          </FormControl>
        </FormField>
        <FormField className="review-form__field review-form__field--grow">
          <FormLabel htmlFor="review-comment" className="review-form__label">
            {t("Commentaire")}
          </FormLabel>
          <FormControl>
            <Textarea
              id="review-comment"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              rows={3}
              placeholder={t("Décrivez votre expérience")}
            />
          </FormControl>
        </FormField>
      </div>
      <div className="review-form__actions">
        <Button type="submit" variant="secondary" disabled={status === "submitting"}>
          {status === "submitting" ? t("Envoi…") : t("Envoyer")}
        </Button>
        {status === "success" && <FormMessage variant="success">{t("Avis enregistré")}</FormMessage>}
        {status === "error" && (
          <FormMessage variant="error">{errorMessage || t("Erreur lors de l'envoi")}</FormMessage>
        )}
      </div>
    </form>
  );
}

export default ReviewForm;
