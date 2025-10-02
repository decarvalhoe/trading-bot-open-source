import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrategyDesigner } from "../src/strategies/designer/index.js";

function createDataTransfer() {
  const data = {};
  return {
    data,
    setData(type, value) {
      data[type] = value;
      this.types = Object.keys(data);
    },
    getData(type) {
      return data[type] ?? "";
    },
    clearData() {
      for (const key of Object.keys(data)) {
        delete data[key];
      }
      this.types = [];
    },
    dropEffect: "move",
    effectAllowed: "all",
    files: [],
    items: [],
    types: [],
  };
}

function dragAndDrop(source, target) {
  const dataTransfer = createDataTransfer();
  fireEvent.dragStart(source, { dataTransfer });
  fireEvent.dragOver(target, { dataTransfer });
  fireEvent.drop(target, { dataTransfer });
}

test("permet de composer une condition avec indicateur imbriqué", () => {
  render(<StrategyDesigner defaultName="Test" saveEndpoint="/noop" />);

  const conditionsZone = screen.getByTestId("designer-conditions-dropzone");
  const conditionItem = screen.getByTestId("palette-item-condition");
  dragAndDrop(conditionItem, conditionsZone);

  expect(document.querySelectorAll(".designer-block[data-node-type='condition']")).toHaveLength(1);

  const indicatorItem = screen.getByTestId("palette-item-indicator");
  const conditionDropzones = screen.getAllByTestId("designer-dropzone-condition");
  dragAndDrop(indicatorItem, conditionDropzones[0]);

  expect(document.querySelectorAll(".designer-block[data-node-type='indicator']")).toHaveLength(1);

  const preview = screen.getByTestId("strategy-preview");
  expect(preview.value).toContain("rules:");
  expect(preview.value).toMatch(/field:/);
});

test("génère un export Python après ajout d'une action", async () => {
  const user = userEvent.setup();
  render(<StrategyDesigner defaultName="Breakout" saveEndpoint="/noop" />);

  const actionButton = screen.getByRole("button", { name: "Ajouter Action d'exécution" });
  await user.click(actionButton);

  const formatSelect = screen.getByLabelText("Format d'export");
  await user.selectOptions(formatSelect, "python");

  const preview = screen.getByTestId("strategy-preview");
  expect(preview.value).toContain("STRATEGY = ");
  expect(preview.value).toContain("\"name\": \"Breakout\"");
  expect(preview.value).toContain("\"steps\"");
});
