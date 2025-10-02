import React from "react";
import { BLOCK_DEFINITIONS, DATA_TRANSFER_FORMAT } from "./designerConstants.js";

function PaletteItem({ type, definition, onAdd }) {
  const handleDragStart = (event) => {
    event.dataTransfer.setData(DATA_TRANSFER_FORMAT, type);
    event.dataTransfer.effectAllowed = "copyMove";
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onAdd({ type, section: definition.category });
    }
  };

  return (
    <article className="palette-item" role="listitem">
      <header className="palette-item__header">
        <div>
          <span className="palette-item__title heading heading--sm">{definition.label}</span>
          <p className="palette-item__category text text--muted">{definition.category === "actions" ? "Action" : "Condition"}</p>
        </div>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => onAdd({ type, section: definition.category })}
          aria-label={`Ajouter ${definition.label}`}
        >
          Ajouter
        </button>
      </header>
      <p className="palette-item__description text">{definition.description}</p>
      <div
        className="palette-item__draggable"
        role="button"
        tabIndex={0}
        draggable
        data-testid={`palette-item-${type}`}
        onDragStart={handleDragStart}
        onKeyDown={handleKeyDown}
        aria-label={`Glisser ${definition.label} vers la zone de composition`}
      >
        Glisser-déposer
      </div>
    </article>
  );
}

export default function BlockPalette({ onAdd }) {
  return (
    <section className="designer-panel designer-panel--palette" aria-labelledby="palette-title">
      <div className="designer-panel__header">
        <h2 id="palette-title" className="heading heading--md">
          Bibliothèque de blocs
        </h2>
        <p className="text text--muted">
          Faites glisser un bloc dans la colonne « Composition » ou cliquez sur « Ajouter » pour l'insérer.
        </p>
      </div>
      <div className="designer-panel__body" role="list" aria-label="Types de blocs disponibles">
        {Object.entries(BLOCK_DEFINITIONS).map(([type, definition]) => (
          <PaletteItem key={type} type={type} definition={definition} onAdd={onAdd} />
        ))}
      </div>
    </section>
  );
}
