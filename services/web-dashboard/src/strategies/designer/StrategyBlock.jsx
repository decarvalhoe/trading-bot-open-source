import React from "react";
import { BLOCK_DEFINITIONS, DATA_TRANSFER_FORMAT } from "./designerConstants.js";

function Field({ label, children }) {
  return (
    <label className="designer-field">
      <span className="designer-field__label text text--muted">{label}</span>
      {children}
    </label>
  );
}

function ConditionFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
      <Field label="Champ">
        <input
          type="text"
          value={node.config.field || ""}
          onChange={(event) => onChange({ ...node.config, field: event.target.value })}
        />
      </Field>
      <Field label="Opérateur">
        <select
          value={node.config.operator || "gt"}
          onChange={(event) => onChange({ ...node.config, operator: event.target.value })}
        >
          <option value="gt">Supérieur à</option>
          <option value="lt">Inférieur à</option>
          <option value="gte">Supérieur ou égal</option>
          <option value="lte">Inférieur ou égal</option>
          <option value="eq">Égal</option>
          <option value="neq">Différent</option>
        </select>
      </Field>
      <Field label="Valeur">
        <input
          type="text"
          value={node.config.value ?? ""}
          onChange={(event) => onChange({ ...node.config, value: event.target.value })}
        />
      </Field>
    </div>
  );
}

function IndicatorFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
      <Field label="Source">
        <select
          value={node.config.source || "close"}
          onChange={(event) => onChange({ ...node.config, source: event.target.value })}
        >
          <option value="close">Clôture</option>
          <option value="open">Ouverture</option>
          <option value="high">Haut</option>
          <option value="low">Bas</option>
          <option value="volume">Volume</option>
        </select>
      </Field>
      <Field label="Type">
        <select
          value={node.config.kind || "sma"}
          onChange={(event) => onChange({ ...node.config, kind: event.target.value })}
        >
          <option value="sma">Moyenne mobile</option>
          <option value="ema">EMA</option>
          <option value="rsi">RSI</option>
          <option value="vwap">VWAP</option>
        </select>
      </Field>
      <Field label="Période">
        <input
          type="number"
          min="1"
          value={node.config.period || ""}
          onChange={(event) => onChange({ ...node.config, period: event.target.value })}
        />
      </Field>
    </div>
  );
}

function LogicFields({ node, onChange }) {
  return (
    <Field label="Mode">
      <select value={node.config.mode || "all"} onChange={(event) => onChange({ ...node.config, mode: event.target.value })}>
        <option value="all">Toutes les conditions</option>
        <option value="any">Au moins une condition</option>
      </select>
    </Field>
  );
}

function ActionFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
      <Field label="Action">
        <select
          value={node.config.action || "buy"}
          onChange={(event) => onChange({ ...node.config, action: event.target.value })}
        >
          <option value="buy">Achat</option>
          <option value="sell">Vente</option>
          <option value="rebalance">Rééquilibrage</option>
          <option value="alert">Envoyer une alerte</option>
        </select>
      </Field>
      <Field label="Taille">
        <input
          type="number"
          step="0.1"
          value={node.config.size || ""}
          onChange={(event) => onChange({ ...node.config, size: event.target.value })}
        />
      </Field>
    </div>
  );
}

function DelayFields({ node, onChange }) {
  return (
    <Field label="Délai (secondes)">
      <input
        type="number"
        min="0"
        value={node.config.seconds || ""}
        onChange={(event) => onChange({ ...node.config, seconds: event.target.value })}
      />
    </Field>
  );
}

function renderFields(node, onChange) {
  switch (node.type) {
    case "condition":
      return <ConditionFields node={node} onChange={onChange} />;
    case "indicator":
      return <IndicatorFields node={node} onChange={onChange} />;
    case "logic":
      return <LogicFields node={node} onChange={onChange} />;
    case "action":
      return <ActionFields node={node} onChange={onChange} />;
    case "delay":
      return <DelayFields node={node} onChange={onChange} />;
    default:
      return null;
  }
}

export default function StrategyBlock({
  node,
  section,
  onDrop,
  onConfigChange,
  onRemove,
  depth = 0,
}) {
  const definition = BLOCK_DEFINITIONS[node.type] || { accepts: [] };
  const acceptsChildren = Array.isArray(definition.accepts) && definition.accepts.length > 0;

  const handleDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    const type = event.dataTransfer.getData(DATA_TRANSFER_FORMAT);
    if (!type) {
      return;
    }
    onDrop({ section, targetId: node.id, type });
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
  };

  const handleConfigUpdate = (config) => {
    onConfigChange({ section, nodeId: node.id, config });
  };

  const handleRemoveClick = () => {
    onRemove({ section, nodeId: node.id });
  };

  return (
    <article className="designer-block" data-node-id={node.id} data-node-type={node.type} data-depth={depth}>
      <header className="designer-block__header">
        <span className="designer-block__title heading heading--sm">{definition.label || node.type}</span>
        <button
          type="button"
          className="button button--ghost designer-block__remove"
          onClick={handleRemoveClick}
          aria-label={`Supprimer le bloc ${definition.label || node.type}`}
        >
          Retirer
        </button>
      </header>
      <div className="designer-block__body">{renderFields(node, handleConfigUpdate)}</div>
      {acceptsChildren ? (
        <div className="designer-block__children">
          {(node.children || []).map((child) => (
            <StrategyBlock
              key={child.id}
              node={child}
              section={section}
              onDrop={onDrop}
              onConfigChange={onConfigChange}
              onRemove={onRemove}
              depth={depth + 1}
            />
          ))}
          <div
            className="designer-dropzone"
            data-testid={`designer-dropzone-${node.type}`}
            data-node-type={node.type}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            Déposer un bloc compatible ici
          </div>
        </div>
      ) : null}
    </article>
  );
}
