import React from "react";
import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  Button,
  Input,
  Modal,
  ModalHeader,
  ModalTitle,
  Select,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  TabTrigger,
  ToastProvider,
  useToast,
} from "../index.js";

function ToastTester() {
  const { show, toasts } = useToast();
  return (
    <>
      <Button onClick={() => show({ title: "Bonjour", description: "Toast de test", duration: 100 })}>
        Afficher un toast
      </Button>
      <span data-testid="toast-count">{toasts.length}</span>
    </>
  );
}

describe("UI primitives", () => {
  it("renders input and propagates change", () => {
    const handleChange = vi.fn();
    render(<Input aria-label="Email" onChange={handleChange} />);
    const input = screen.getByLabelText("Email");
    fireEvent.change(input, { target: { value: "test@example.com" } });
    expect(handleChange).toHaveBeenCalled();
  });

  it("renders select options", () => {
    const handleChange = vi.fn();
    render(
      <Select aria-label="Tri" defaultValue="recent" onChange={handleChange}>
        <option value="recent">Récent</option>
        <option value="ancien">Ancien</option>
      </Select>,
    );
    const select = screen.getByLabelText("Tri");
    fireEvent.change(select, { target: { value: "ancien" } });
    expect(handleChange).toHaveBeenCalled();
    expect(select.value).toBe("ancien");
  });

  it("closes modal when clicking outside", () => {
    const handleClose = vi.fn();
    render(
      <Modal open onClose={handleClose} labelledBy="modal-title">
        <ModalHeader>
          <ModalTitle id="modal-title">Modale</ModalTitle>
        </ModalHeader>
      </Modal>,
    );

    const overlay = screen.getByTestId("modal-overlay");
    fireEvent.click(overlay);
    expect(handleClose).toHaveBeenCalled();
  });

  it("changes active tab when trigger is pressed", () => {
    render(
      <Tabs defaultValue="overview">
        <TabList>
          <TabTrigger value="overview">Vue</TabTrigger>
          <TabTrigger value="details">Détails</TabTrigger>
        </TabList>
        <TabPanels>
          <TabPanel value="overview">
            <p>Données de synthèse</p>
          </TabPanel>
          <TabPanel value="details">
            <p>Données détaillées</p>
          </TabPanel>
        </TabPanels>
      </Tabs>,
    );

    expect(screen.getByText("Données de synthèse")).toBeVisible();
    const detailsTrigger = screen.getByRole("tab", { name: "Détails" });
    fireEvent.click(detailsTrigger);
    expect(screen.getByText("Données détaillées")).toBeVisible();
  });

  it("displays and dismisses toast notifications", async () => {
    render(
      <ToastProvider duration={50}>
        <ToastTester />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Afficher un toast" }));
    await waitFor(() => {
      expect(screen.getByTestId("toast-count").textContent).toBe("1");
    });

    await waitFor(() => {
      expect(screen.getByTestId("toast-count").textContent).toBe("0");
    });
  });
});
