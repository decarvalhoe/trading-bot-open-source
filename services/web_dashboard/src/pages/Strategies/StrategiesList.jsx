import React, { useCallback, useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import useApi from "../../hooks/useApi.js";

function normaliseListItem(entry, index = 0) {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const identifier =
    entry.id ??
    entry.strategy_id ??
    entry.identifier ??
    entry.slug ??
    `strategy-${index + 1}`;

  const name =
    entry.name ??
    entry.title ??
    entry.strategy_name ??
    entry.label ??
    `Stratégie ${index + 1}`;

  const strategyType = entry.strategy_type ?? entry.type ?? entry.format ?? "";

  const updatedAt =
    entry.updated_at ??
    entry.updatedAt ??
    entry.modified_at ??
    entry.modifiedAt ??
    entry.created_at ??
    entry.createdAt ??
    null;

  const description = entry.description ?? entry.summary ?? "";

  return {
    id: String(identifier),
    name,
    strategy_type: strategyType ? String(strategyType) : "",
    updated_at: updatedAt,
    description,
    raw: entry,
  };
}

function normaliseListPayload(payload, fallbackPage, fallbackSize) {
  if (!payload) {
    return { items: [], total: 0, page: fallbackPage, page_size: fallbackSize };
  }

  if (Array.isArray(payload)) {
    const items = payload
      .map((item, index) => normaliseListItem(item, index))
      .filter(Boolean);
    return { items, total: items.length, page: fallbackPage, page_size: fallbackSize };
  }

  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  const items = rawItems.map((item, index) => normaliseListItem(item, index)).filter(Boolean);

  const total = Number.isFinite(payload.total) ? Number(payload.total) : items.length;
  const resolvedPage = Number.isFinite(payload.page) ? Number(payload.page) : fallbackPage;
  const resolvedSize = Number.isFinite(payload.page_size)
    ? Number(payload.page_size)
    : fallbackSize;

  return {
    items,
    total,
    page: resolvedPage,
    page_size: resolvedSize,
  };
}

function formatDate(value) {
  if (!value) {
    return "-";
  }

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return typeof value === "string" ? value : String(value);
  }

  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ensurePageSize(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return 10;
  }
  return Math.max(1, Math.floor(numeric));
}

export function StrategiesListView({ pageSize = 10, api }) {
  const size = ensurePageSize(pageSize);
  const { strategies: strategiesApi, useQuery, useMutation, queryClient } = api;

  const [page, setPage] = useState(1);
  const [feedback, setFeedback] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorStatus, setEditorStatus] = useState("idle");
  const [editorError, setEditorError] = useState(null);
  const [editorData, setEditorData] = useState(null);
  const [formState, setFormState] = useState({ name: "", description: "" });

  const listQueryKey = useMemo(() => ["strategies", "list", { page, pageSize: size }], [page, size]);

  const {
    data: listPayload = { items: [], total: 0, page, page_size: size },
    isLoading,
    isFetching,
    error,
  } = useQuery({
    queryKey: listQueryKey,
    keepPreviousData: true,
    queryFn: async () => {
      const response = await strategiesApi.list({ query: { page, page_size: size } });
      return normaliseListPayload(response, page, size);
    },
  });

  const strategies = listPayload.items || [];
  const total = Number.isFinite(listPayload.total) ? Number(listPayload.total) : strategies.length;
  const totalPages = Math.max(1, Math.ceil(Math.max(total, 1) / size));
  const currentPage = Number.isFinite(listPayload.page) ? Number(listPayload.page) : page;

  useEffect(() => {
    if (currentPage !== page) {
      setPage(Math.max(1, currentPage));
    }
  }, [currentPage, page]);

  const handlePreviousPage = useCallback(() => {
    setPage((current) => Math.max(1, current - 1));
  }, []);

  const handleNextPage = useCallback(() => {
    setPage((current) => Math.min(totalPages, current + 1));
  }, [totalPages]);

  const updateMutation = useMutation({
    mutationFn: async ({ id, payload }) => strategiesApi.update(id, payload),
    onSuccess: (data, variables) => {
      setFeedback({ type: "success", message: "Stratégie mise à jour." });
      queryClient.setQueryData(listQueryKey, (previous) => {
        if (!previous) {
          return previous;
        }
        const updatedItem = normaliseListItem(data || variables.payload, 0) || variables.payload;
        return {
          ...previous,
          items: previous.items.map((item) => {
            if (String(item.id) !== String(variables.id)) {
              return item;
            }
            if (!updatedItem || typeof updatedItem !== "object") {
              return item;
            }
            return {
              ...item,
              ...normaliseListItem({ ...item.raw, ...updatedItem }, 0),
              raw: { ...item.raw, ...updatedItem },
            };
          }),
        };
      });
      queryClient.invalidateQueries({ queryKey: ["strategies", "list"] });
    },
    onError: (mutationError) => {
      setFeedback({
        type: "error",
        message: mutationError?.message || "Impossible de mettre à jour la stratégie.",
      });
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (id) => strategiesApi.remove(id),
    onMutate: async (id) => {
      setFeedback(null);
      await queryClient.cancelQueries({ queryKey: listQueryKey });
      const previous = queryClient.getQueryData(listQueryKey);
      if (previous) {
        const nextItems = previous.items.filter((item) => String(item.id) !== String(id));
        const removed = nextItems.length !== previous.items.length;
        const nextTotal = removed
          ? Math.max(0, (Number.isFinite(previous.total) ? Number(previous.total) - 1 : nextItems.length))
          : Number.isFinite(previous.total)
          ? Number(previous.total)
          : nextItems.length;

        queryClient.setQueryData(listQueryKey, {
          ...previous,
          items: nextItems,
          total: nextTotal,
        });

        if (removed && nextItems.length === 0 && page > 1) {
          setPage((current) => Math.max(1, current - 1));
        }
      }
      return { previous };
    },
    onError: (mutationError, _id, context) => {
      if (context?.previous) {
        queryClient.setQueryData(listQueryKey, context.previous);
      }
      setFeedback({
        type: "error",
        message: mutationError?.message || "Impossible de supprimer la stratégie.",
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies", "list"] });
    },
    onSuccess: () => {
      setFeedback({ type: "success", message: "Stratégie supprimée." });
    },
  });

  const cloneMutation = useMutation({
    mutationFn: async (id) => {
      const endpoint = `/strategies/${encodeURIComponent(id)}/clone`;
      return strategiesApi.create({}, { endpoint });
    },
    onSuccess: () => {
      setFeedback({ type: "success", message: "Stratégie clonée avec succès." });
    },
    onError: (mutationError) => {
      setFeedback({
        type: "error",
        message: mutationError?.message || "Impossible de cloner la stratégie.",
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies", "list"] });
    },
  });

  const closeEditor = useCallback(() => {
    setEditorOpen(false);
    setEditorStatus("idle");
    setEditorError(null);
    setEditorData(null);
    setFormState({ name: "", description: "" });
  }, []);

  const openEditor = useCallback(
    async (strategy) => {
      if (!strategy || !strategy.id) {
        return;
      }
      setFeedback(null);
      setEditorError(null);
      setEditorStatus("loading");
      setEditorOpen(true);
      try {
        const detail = await strategiesApi.detail(strategy.id);
        const resolved = detail && typeof detail === "object" ? detail : strategy.raw || {};
        const name =
          resolved.name ??
          resolved.title ??
          resolved.strategy_name ??
          strategy.name ??
          "";
        const description = resolved.description ?? resolved.summary ?? strategy.description ?? "";
        setEditorData({ ...resolved, id: strategy.id });
        setFormState({ name: String(name), description: description ? String(description) : "" });
        setEditorStatus("idle");
      } catch (detailError) {
        setEditorError(detailError);
        setEditorStatus("idle");
      }
    },
    [strategiesApi]
  );

  const handleDelete = useCallback(
    async (strategy) => {
      if (!strategy?.id) {
        return;
      }
      setPendingAction({ id: strategy.id, type: "delete" });
      try {
        await removeMutation.mutateAsync(strategy.id);
      } finally {
        setPendingAction(null);
      }
    },
    [removeMutation]
  );

  const handleClone = useCallback(
    async (strategy) => {
      if (!strategy?.id) {
        return;
      }
      setPendingAction({ id: strategy.id, type: "clone" });
      try {
        await cloneMutation.mutateAsync(strategy.id);
      } finally {
        setPendingAction(null);
      }
    },
    [cloneMutation]
  );

  const handleFormSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      if (!editorData?.id) {
        return;
      }
      setEditorStatus("saving");
      setEditorError(null);
      try {
        const payload = {
          ...editorData,
          name: formState.name.trim(),
          description: formState.description.trim(),
        };
        await updateMutation.mutateAsync({ id: editorData.id, payload });
        closeEditor();
      } catch (mutationError) {
        setEditorError(mutationError);
      } finally {
        setEditorStatus("idle");
      }
    },
    [editorData, formState, updateMutation, closeEditor]
  );

  const isLoadingList = isLoading || isFetching;
  const isEditorLoading = editorStatus === "loading";
  const isEditorSaving = editorStatus === "saving";

  return (
    <section className="card card--strategies-list" aria-labelledby="strategies-list-title">
      <div className="card__header">
        <h2 id="strategies-list-title" className="heading heading--lg">
          Stratégies enregistrées
        </h2>
        <p className="text text--muted">
          Gérez vos stratégies existantes, modifiez-les ou créez des copies en un clic.
        </p>
      </div>
      <div className="card__body">
        {feedback ? (
          <div
            className={`strategies-list__banner strategies-list__banner--${feedback.type}`}
            role={feedback.type === "error" ? "alert" : "status"}
          >
            {feedback.message}
          </div>
        ) : null}
        {error ? (
          <div className="strategies-list__banner strategies-list__banner--error" role="alert">
            {error.message || "Impossible de charger les stratégies pour le moment."}
          </div>
        ) : null}
        <div className="strategies-list__table-wrapper" role="region" aria-live="polite">
          <table className="table strategies-list__table">
            <thead>
              <tr>
                <th scope="col">Nom</th>
                <th scope="col">Type</th>
                <th scope="col">Dernière mise à jour</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {strategies.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <p className="text text--muted">
                      {isLoadingList ? "Chargement des stratégies…" : "Aucune stratégie disponible pour le moment."}
                    </p>
                  </td>
                </tr>
              ) : (
                strategies.map((strategy) => {
                  const disabled = pendingAction?.id && String(pendingAction.id) === String(strategy.id);
                  return (
                    <tr key={strategy.id}>
                      <td data-label="Nom">
                        <div className="strategies-list__name">{strategy.name}</div>
                        {strategy.description ? (
                          <p className="text text--muted strategies-list__description">{strategy.description}</p>
                        ) : null}
                      </td>
                      <td data-label="Type">{strategy.strategy_type || "-"}</td>
                      <td data-label="Dernière mise à jour">{formatDate(strategy.updated_at)}</td>
                      <td data-label="Actions" className="strategies-list__actions">
                        <button
                          type="button"
                          className="button button--ghost"
                          onClick={() => openEditor(strategy)}
                          disabled={disabled}
                        >
                          Voir / éditer
                        </button>
                        <button
                          type="button"
                          className="button button--secondary"
                          onClick={() => handleClone(strategy)}
                          disabled={disabled}
                        >
                          Cloner
                        </button>
                        <button
                          type="button"
                          className="button button--danger"
                          onClick={() => handleDelete(strategy)}
                          disabled={disabled}
                        >
                          Supprimer
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="strategies-list__pagination">
          <button
            type="button"
            className="button button--ghost"
            onClick={handlePreviousPage}
            disabled={page <= 1}
          >
            Précédent
          </button>
          <span className="text text--muted">
            Page {Math.min(page, totalPages)} / {totalPages}
          </span>
          <button
            type="button"
            className="button button--ghost"
            onClick={handleNextPage}
            disabled={page >= totalPages}
          >
            Suivant
          </button>
        </div>
      </div>

      {editorOpen ? (
        <div className="strategies-editor" role="dialog" aria-modal="true" aria-labelledby="strategy-editor-title">
          <div className="strategies-editor__content">
            <h3 id="strategy-editor-title" className="heading heading--md">
              Modifier la stratégie
            </h3>
            {editorError ? (
              <p className="strategies-list__banner strategies-list__banner--error" role="alert">
                {editorError.message || "Impossible de charger la stratégie sélectionnée."}
              </p>
            ) : null}
            <form onSubmit={handleFormSubmit} className="strategies-editor__form">
              <label className="form-field">
                <span className="form-field__label">Nom</span>
                <input
                  type="text"
                  value={formState.name}
                  onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
                  disabled={isEditorLoading || isEditorSaving}
                  required
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">Description</span>
                <textarea
                  value={formState.description}
                  onChange={(event) =>
                    setFormState((current) => ({ ...current, description: event.target.value }))
                  }
                  disabled={isEditorLoading || isEditorSaving}
                  rows={4}
                />
              </label>
              <div className="strategies-editor__actions">
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={closeEditor}
                  disabled={isEditorSaving}
                >
                  Fermer
                </button>
                <button
                  type="submit"
                  className="button button--primary"
                  disabled={isEditorLoading || isEditorSaving}
                >
                  {isEditorSaving ? "Enregistrement…" : "Enregistrer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}

StrategiesListView.propTypes = {
  pageSize: PropTypes.number,
  api: PropTypes.shape({
    strategies: PropTypes.shape({
      list: PropTypes.func.isRequired,
      detail: PropTypes.func.isRequired,
      update: PropTypes.func.isRequired,
      remove: PropTypes.func.isRequired,
      create: PropTypes.func.isRequired,
    }).isRequired,
    useQuery: PropTypes.func.isRequired,
    useMutation: PropTypes.func.isRequired,
    queryClient: PropTypes.shape({
      cancelQueries: PropTypes.func.isRequired,
      getQueryData: PropTypes.func.isRequired,
      setQueryData: PropTypes.func.isRequired,
      invalidateQueries: PropTypes.func.isRequired,
    }).isRequired,
  }).isRequired,
};

export default function StrategiesList(props) {
  const api = useApi();
  return <StrategiesListView {...props} api={api} />;
}

StrategiesList.propTypes = {
  pageSize: PropTypes.number,
};
