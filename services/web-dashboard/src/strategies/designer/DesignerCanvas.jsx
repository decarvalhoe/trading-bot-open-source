import React from "react";
import StrategyBlock from "./StrategyBlock.jsx";
import { DATA_TRANSFER_FORMAT } from "./designerConstants.js";

function Section({
  title,
  description,
  emptyMessage,
  nodes,
  section,
  onDrop,
  onConfigChange,
  onRemove,
  dropTestId,
}) {
  const handleDrop = (event) => {
    event.preventDefault();
    const type = event.dataTransfer.getData(DATA_TRANSFER_FORMAT);
    if (!type) {
      return;
    }
    onDrop({ section, targetId: null, type });
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };

  return (
    <section className="designer-panel designer-panel--canvas" aria-labelledby={`${dropTestId}-title`}>
      <div className="designer-panel__header">
        <h2 id={`${dropTestId}-title`} className="heading heading--md">
          {title}
        </h2>
        <p className="text text--muted">{description}</p>
      </div>
      <div
        className="designer-canvas"
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        data-testid={dropTestId}
      >
        {nodes.length ? (
          nodes.map((node) => (
            <StrategyBlock
              key={node.id}
              node={node}
              section={section}
              onDrop={onDrop}
              onConfigChange={onConfigChange}
              onRemove={onRemove}
            />
          ))
        ) : (
          <p className="designer-canvas__empty text text--muted">{emptyMessage}</p>
        )}
      </div>
    </section>
  );
}

export default function DesignerCanvas({
  conditions,
  actions,
  onDrop,
  onConfigChange,
  onRemove,
}) {
  return (
    <div className="designer-canvas-grid">
      <Section
        title="Conditions"
        description="Construisez l'arbre logique déclenchant la stratégie."
        emptyMessage="Glissez une condition, un opérateur logique ou un indicateur pour démarrer."
        nodes={conditions}
        section="conditions"
        onDrop={onDrop}
        onConfigChange={onConfigChange}
        onRemove={onRemove}
        dropTestId="designer-conditions-dropzone"
      />
      <Section
        title="Actions"
        description="Définissez la liste des actions à exécuter lorsque les conditions sont satisfaites."
        emptyMessage="Ajoutez une action d'exécution ou une temporisation."
        nodes={actions}
        section="actions"
        onDrop={onDrop}
        onConfigChange={onConfigChange}
        onRemove={onRemove}
        dropTestId="designer-actions-dropzone"
      />
    </div>
  );
}
