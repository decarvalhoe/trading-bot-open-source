import React from "react";
import StrategyBlock from "./StrategyBlock.jsx";
import { DATA_TRANSFER_FORMAT } from "./designerConstants.js";

function Section({
  title,
  description,
  emptyMessage,
  nodes,
  section,
  layout,
  selection,
  clipboardAvailable,
  onDrop,
  onConfigChange,
  onRemove,
  onSelect,
  onSectionFocus,
  onCopy,
  onPaste,
  onDuplicate,
  onClearSelection,
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

  const isSectionSelected = selection?.section === section && !selection?.nodeId;
  const maxColumn = Math.max(
    0,
    ...Object.values(layout || {}).map((entry) =>
      typeof entry.column === "number" ? entry.column : 0
    )
  );

  const handleCanvasClick = (event) => {
    if (event.target === event.currentTarget) {
      onSectionFocus?.(section);
    }
  };

  const handleCanvasFocus = () => {
    onSectionFocus?.(section);
  };

  const handleCanvasBlur = (event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      onClearSelection?.();
    }
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
        className={`designer-canvas${isSectionSelected ? " designer-canvas--active" : ""}`}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={handleCanvasClick}
        onFocus={handleCanvasFocus}
        onBlur={handleCanvasBlur}
        data-testid={dropTestId}
        tabIndex={0}
        aria-selected={isSectionSelected}
        style={{ "--layout-columns": maxColumn + 1 }}
      >
        {nodes.length ? (
          nodes.map((node) => (
            <StrategyBlock
              key={node.id}
              node={node}
              section={section}
              layout={layout}
              selection={selection}
              clipboardAvailable={clipboardAvailable}
              onDrop={onDrop}
              onConfigChange={onConfigChange}
              onRemove={onRemove}
              onSelect={onSelect}
              onCopy={onCopy}
              onPaste={onPaste}
              onDuplicate={onDuplicate}
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
  layout,
  selection,
  clipboardAvailable,
  onDrop,
  onConfigChange,
  onRemove,
  onSelect,
  onSectionFocus,
  onCopy,
  onPaste,
  onDuplicate,
  onClearSelection,
}) {
  return (
    <div className="designer-canvas-grid" onClick={(event) => {
      if (event.target === event.currentTarget) {
        onClearSelection?.();
      }
    }}>
      <Section
        title="Conditions"
        description="Construisez l'arbre logique déclenchant la stratégie."
        emptyMessage="Glissez une condition, un opérateur logique ou un indicateur pour démarrer."
        nodes={conditions}
        section="conditions"
        layout={layout}
        selection={selection}
        clipboardAvailable={clipboardAvailable}
        onDrop={onDrop}
        onConfigChange={onConfigChange}
        onRemove={onRemove}
        onSelect={onSelect}
        onSectionFocus={onSectionFocus}
        onCopy={onCopy}
        onPaste={onPaste}
        onDuplicate={onDuplicate}
        onClearSelection={onClearSelection}
        dropTestId="designer-conditions-dropzone"
      />
      <Section
        title="Actions"
        description="Définissez la liste des actions à exécuter lorsque les conditions sont satisfaites."
        emptyMessage="Ajoutez une action d'exécution ou une temporisation."
        nodes={actions}
        section="actions"
        layout={layout}
        selection={selection}
        clipboardAvailable={clipboardAvailable}
        onDrop={onDrop}
        onConfigChange={onConfigChange}
        onRemove={onRemove}
        onSelect={onSelect}
        onSectionFocus={onSectionFocus}
        onCopy={onCopy}
        onPaste={onPaste}
        onDuplicate={onDuplicate}
        onClearSelection={onClearSelection}
        dropTestId="designer-actions-dropzone"
      />
    </div>
  );
}
