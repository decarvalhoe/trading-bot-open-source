(function () {
  const container = document.querySelector("[data-help-center]");
  if (!container) {
    return;
  }

  const endpoint = container.getAttribute("data-articles-endpoint");
  if (!endpoint) {
    return;
  }

  const progressValue = container.querySelector("[data-progress-value]");
  const progressFill = container.querySelector("[data-progress-fill]");
  const progressBar = container.querySelector("[data-progressbar]");
  const recentList = container.querySelector("[data-recent-resources]");

  async function refreshProgress(slug) {
    try {
      const url = new URL(endpoint, window.location.origin);
      if (slug) {
        url.searchParams.set("viewed", slug);
      }
      const response = await fetch(url.toString(), {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      if (!payload || typeof payload !== "object" || !payload.progress) {
        return;
      }

      const progress = payload.progress;
      const completion = Number(progress.completion_rate ?? progress.completionRate ?? 0);
      if (progressValue) {
        progressValue.textContent = `${completion}%`;
      }
      if (progressFill) {
        progressFill.style.width = `${Math.min(Math.max(completion, 0), 100)}%`;
      }
      if (progressBar) {
        progressBar.setAttribute("aria-valuenow", `${Math.min(Math.max(completion, 0), 100)}`);
      }

      if (!recentList) {
        return;
      }

      const visits = Array.isArray(progress.recent_resources)
        ? progress.recent_resources
        : Array.isArray(progress.recentResources)
        ? progress.recentResources
        : [];

      recentList.innerHTML = "";
      if (!visits.length) {
        const empty = document.createElement("li");
        empty.className = "help-recent__item help-recent__item--empty";
        empty.textContent = "Aucune ressource consultée pour le moment.";
        recentList.appendChild(empty);
        return;
      }

      visits.forEach((visit) => {
        const item = document.createElement("li");
        item.className = "help-recent__item";

        const title = document.createElement("p");
        title.className = "help-recent__title";
        title.textContent = visit.title || "Ressource";

        const meta = document.createElement("p");
        meta.className = "help-recent__meta";
        const viewedAt = visit.viewed_at || visit.viewedAt;
        let formattedDate = "Consulté récemment";
        if (viewedAt) {
          const parsed = new Date(viewedAt);
          if (!Number.isNaN(parsed.getTime())) {
            formattedDate = parsed.toLocaleString("fr-FR", {
              day: "2-digit",
              month: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
            });
          }
        }
        const resourceType = visit.resource_type || visit.resourceType || "ressource";
        meta.textContent = `${resourceType} · ${formattedDate}`;

        item.appendChild(title);
        item.appendChild(meta);
        recentList.appendChild(item);
      });
    } catch (error) {
      console.warn("Impossible de mettre à jour la progression de formation", error);
    }
  }

  container.addEventListener("toggle", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLDetailsElement)) {
      return;
    }
    if (!target.open) {
      return;
    }
    const slug = target.getAttribute("data-article-slug");
    if (!slug) {
      return;
    }
    void refreshProgress(slug);
  });

  container.querySelectorAll("[data-article-link]").forEach((element) => {
    element.addEventListener("click", () => {
      const slug = element.getAttribute("data-article-link");
      if (!slug) {
        return;
      }
      void refreshProgress(slug);
    });
  });
})();
