import React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { StrategiesListView } from "./StrategiesList.jsx";

describe("StrategiesListView", () => {
  let listMock;
  let detailMock;
  let updateMock;
  let removeMock;
  let createMock;
  let strategyStore;
  let queryClient;
  let consoleErrorMock;
  const originalConsoleError = console.error;

  async function renderList(props = {}) {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    const api = {
      strategies: { list: listMock, detail: detailMock, update: updateMock, remove: removeMock, create: createMock },
      useQuery,
      useMutation,
      queryClient,
    };

    let renderResult;
    await act(async () => {
      renderResult = render(
        <QueryClientProvider client={queryClient}>
          <StrategiesListView pageSize={2} {...props} api={api} />
        </QueryClientProvider>
      );
    });
    return renderResult;
  }

  beforeEach(() => {
    consoleErrorMock = vi.spyOn(console, "error").mockImplementation((...args) => {
      if (typeof args[0] === "string" && args[0].includes("not wrapped in act")) {
        return;
      }
      originalConsoleError(...args);
    });
    strategyStore = [
      { id: "strat-1", name: "Breakout Alpha", strategy_type: "trend", updated_at: "2024-03-01T09:30:00Z" },
      { id: "strat-2", name: "Momentum Gamma", strategy_type: "momentum", updated_at: "2024-03-03T11:15:00Z" },
      { id: "strat-3", name: "Mean Reversion Beta", strategy_type: "reversion", updated_at: "2024-03-04T16:45:00Z" },
    ];

    listMock = vi.fn(({ query }) => {
      const page = query?.page ?? 1;
      const pageSize = query?.page_size ?? 2;
      const start = (page - 1) * pageSize;
      const items = strategyStore.slice(start, start + pageSize);
      return Promise.resolve({ items, total: strategyStore.length, page, page_size: pageSize });
    });

    detailMock = vi.fn((id) => {
      const strategy = strategyStore.find((item) => item.id === id) || strategyStore[0];
      return Promise.resolve({ ...strategy, description: "Stratégie d'ouverture" });
    });

    updateMock = vi.fn((id, payload) => {
      const index = strategyStore.findIndex((item) => item.id === id);
      if (index !== -1) {
        strategyStore[index] = { ...strategyStore[index], ...payload };
      }
      const updated = strategyStore[index] || { ...payload, id };
      return Promise.resolve({ ...updated });
    });

    removeMock = vi.fn((id) => {
      strategyStore = strategyStore.filter((item) => item.id !== id);
      return Promise.resolve({ success: true });
    });

    createMock = vi.fn((payload, options) => {
      const endpoint = options?.endpoint ?? "";
      const match = endpoint.match(/\/strategies\/(.+)\/clone/);
      const parentId = match ? decodeURIComponent(match[1]) : null;
      const parent = parentId ? strategyStore.find((item) => item.id === parentId) : null;
      const cloneId = parent ? `${parent.id}-clone` : `clone-${Date.now()}`;
      const clone = {
        ...(parent || { name: "Clone", strategy_type: "trend" }),
        ...payload,
        id: cloneId,
        name: parent ? `${parent.name} (Clone)` : "Stratégie clonée",
      };
      strategyStore = [...strategyStore, clone];
      return Promise.resolve(clone);
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    if (queryClient) {
      queryClient.clear();
    }
    if (consoleErrorMock) {
      consoleErrorMock.mockRestore();
    }
  });

  it("renders the strategies list and paginates results", async () => {
    const user = userEvent.setup();

    await renderList();

    expect(await screen.findByText("Breakout Alpha")).toBeInTheDocument();
    expect(screen.getByText("Momentum Gamma")).toBeInTheDocument();
    expect(screen.queryByText("Mean Reversion Beta")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /suivant/i }));

    expect(await screen.findByText("Mean Reversion Beta")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /précédent/i })).not.toBeDisabled();
  });

  it("opens the editor and updates a strategy", async () => {
    const user = userEvent.setup();

    await renderList();

    expect(await screen.findByText("Breakout Alpha")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /voir \/ éditer/i })[0]);

    const nameInput = await screen.findByLabelText("Nom");
    expect(nameInput).toHaveValue("Breakout Alpha");

    await user.clear(nameInput);
    await user.type(nameInput, "Breakout Alpha V2");

    await user.click(screen.getByRole("button", { name: /enregistrer/i }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock).toHaveBeenCalledWith("strat-1", expect.objectContaining({ name: "Breakout Alpha V2" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByText("Stratégie mise à jour.")).toBeInTheDocument();
  });

  it("removes and clones strategies via actions", async () => {
    const user = userEvent.setup();

    await renderList();

    expect(await screen.findByText("Breakout Alpha")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /supprimer/i })[0]);
    await waitFor(() => expect(removeMock).toHaveBeenCalledWith("strat-1"));
    await waitFor(() => expect(screen.queryByText("Breakout Alpha")).not.toBeInTheDocument());
    expect(screen.getByText("Stratégie supprimée.")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /cloner/i })[0]);
    await waitFor(() => expect(createMock).toHaveBeenCalled());
    expect(createMock).toHaveBeenCalledWith({}, { endpoint: "/strategies/strat-2/clone" });
    expect(await screen.findByText("Momentum Gamma (Clone)")).toBeInTheDocument();
    expect(screen.getByText("Stratégie clonée avec succès.")).toBeInTheDocument();
  });
});
