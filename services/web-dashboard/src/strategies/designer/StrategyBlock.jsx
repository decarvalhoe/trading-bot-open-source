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

function IndicatorMacdFields({ node, onChange }) {
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
        </select>
      </Field>
      <Field label="Période rapide">
        <input
          type="number"
          min="1"
          value={node.config.fastPeriod || ""}
          onChange={(event) => onChange({ ...node.config, fastPeriod: event.target.value })}
        />
      </Field>
      <Field label="Période lente">
        <input
          type="number"
          min="1"
          value={node.config.slowPeriod || ""}
          onChange={(event) => onChange({ ...node.config, slowPeriod: event.target.value })}
        />
      </Field>
      <Field label="Période signal">
        <input
          type="number"
          min="1"
          value={node.config.signalPeriod || ""}
          onChange={(event) => onChange({ ...node.config, signalPeriod: event.target.value })}
        />
      </Field>
    </div>
  );
}

function IndicatorBollingerFields({ node, onChange }) {
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
      <Field label="Déviation">
        <input
          type="number"
          step="0.1"
          min="0"
          value={node.config.deviation || ""}
          onChange={(event) => onChange({ ...node.config, deviation: event.target.value })}
        />
      </Field>
    </div>
  );
}

function IndicatorAtrFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
      <Field label="Source">
        <select
          value={node.config.source || "hlc3"}
          onChange={(event) => onChange({ ...node.config, source: event.target.value })}
        >
          <option value="hlc3">HLC3</option>
          <option value="close">Clôture</option>
          <option value="high">Haut</option>
          <option value="low">Bas</option>
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
      <Field label="Lissage">
        <input
          type="number"
          min="1"
          value={node.config.smoothing || ""}
          onChange={(event) => onChange({ ...node.config, smoothing: event.target.value })}
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

function MarketCrossFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
      <Field label="Direction du croisement">
        <select
          value={node.config.direction || "above"}
          onChange={(event) => onChange({ ...node.config, direction: event.target.value })}
        >
          <option value="above">Croise au-dessus</option>
          <option value="below">Croise sous</option>
        </select>
      </Field>
      <Field label="Fenêtre d'observation">
        <input
          type="number"
          min="1"
          value={node.config.lookback || ""}
          onChange={(event) => onChange({ ...node.config, lookback: event.target.value })}
        />
      </Field>
    </div>
  );
}

function MarketVolumeFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
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
      <Field label="Seuil">
        <input
          type="number"
          min="0"
          value={node.config.value || ""}
          onChange={(event) => onChange({ ...node.config, value: event.target.value })}
        />
      </Field>
      <Field label="Intervalle">
        <input
          type="text"
          value={node.config.timeframe || ""}
          onChange={(event) => onChange({ ...node.config, timeframe: event.target.value })}
        />
      </Field>
    </div>
  );
}

function NegationFields() {
  return (
    <p className="text text--muted">
      Ce bloc inverse le résultat de son enfant direct.
    </p>
  );
}

function GroupFields() {
  return (
    <p className="text text--muted">
      Utilisez ce regroupement pour prioriser l'évaluation des sous-conditions.
    </p>
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

function TakeProfitFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
      <Field label="Type de cible">
        <select
          value={node.config.mode || "percent"}
          onChange={(event) => onChange({ ...node.config, mode: event.target.value })}
        >
          <option value="percent">Pourcentage</option>
          <option value="price">Prix</option>
        </select>
      </Field>
      <Field label="Valeur">
        <input
          type="number"
          step="0.1"
          value={node.config.value || ""}
          onChange={(event) => onChange({ ...node.config, value: event.target.value })}
        />
      </Field>
      <Field label="Part de la position">
        <select
          value={node.config.size || "full"}
          onChange={(event) => onChange({ ...node.config, size: event.target.value })}
        >
          <option value="full">100 %</option>
          <option value="half">50 %</option>
          <option value="custom">Personnalisé</option>
        </select>
      </Field>
      {node.config.size === "custom" ? (
        <Field label="Taille personnalisée">
          <input
            type="number"
            step="0.1"
            value={node.config.customSize || ""}
            onChange={(event) => onChange({ ...node.config, customSize: event.target.value })}
          />
        </Field>
      ) : null}
    </div>
  );
}

function StopLossFields({ node, onChange }) {
  const handleToggle = (event) => {
    onChange({ ...node.config, trailing: event.target.checked });
  };
  return (
    <div className="designer-field-grid">
      <Field label="Type de seuil">
        <select
          value={node.config.mode || "percent"}
          onChange={(event) => onChange({ ...node.config, mode: event.target.value })}
        >
          <option value="percent">Pourcentage</option>
          <option value="price">Prix</option>
        </select>
      </Field>
      <Field label="Valeur">
        <input
          type="number"
          step="0.1"
          value={node.config.value || ""}
          onChange={(event) => onChange({ ...node.config, value: event.target.value })}
        />
      </Field>
      <label className="designer-field designer-field--inline">
        <input type="checkbox" checked={Boolean(node.config.trailing)} onChange={handleToggle} />
        <span className="designer-field__label">Activer le trailing stop</span>
      </label>
    </div>
  );
}

function ClosePositionFields({ node, onChange }) {
  return (
    <Field label="Cible">
      <select
        value={node.config.side || "all"}
        onChange={(event) => onChange({ ...node.config, side: event.target.value })}
      >
        <option value="all">Tout fermer</option>
        <option value="long">Positions longues</option>
        <option value="short">Positions courtes</option>
      </select>
    </Field>
  );
}

function AlertFields({ node, onChange }) {
  return (
    <div className="designer-field-grid">
      <Field label="Canal">
        <select
          value={node.config.channel || "email"}
          onChange={(event) => onChange({ ...node.config, channel: event.target.value })}
        >
          <option value="email">E-mail</option>
          <option value="sms">SMS</option>
          <option value="webhook">Webhook</option>
        </select>
      </Field>
      <Field label="Message">
        <textarea
          value={node.config.message || ""}
          onChange={(event) => onChange({ ...node.config, message: event.target.value })}
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
    case "market_cross":
      return <MarketCrossFields node={node} onChange={onChange} />;
    case "market_volume":
      return <MarketVolumeFields node={node} onChange={onChange} />;
    case "indicator":
      return <IndicatorFields node={node} onChange={onChange} />;
    case "indicator_macd":
      return <IndicatorMacdFields node={node} onChange={onChange} />;
    case "indicator_bollinger":
      return <IndicatorBollingerFields node={node} onChange={onChange} />;
    case "indicator_atr":
      return <IndicatorAtrFields node={node} onChange={onChange} />;
    case "logic":
      return <LogicFields node={node} onChange={onChange} />;
    case "negation":
      return <NegationFields node={node} onChange={onChange} />;
    case "group":
      return <GroupFields node={node} onChange={onChange} />;
    case "action":
      return <ActionFields node={node} onChange={onChange} />;
    case "take_profit":
      return <TakeProfitFields node={node} onChange={onChange} />;
    case "stop_loss":
      return <StopLossFields node={node} onChange={onChange} />;
    case "close_position":
      return <ClosePositionFields node={node} onChange={onChange} />;
    case "alert":
      return <AlertFields node={node} onChange={onChange} />;
    case "delay":
      return <DelayFields node={node} onChange={onChange} />;
    default:
      return null;
  }
}

export default function StrategyBlock({
  node,
  section,
  layout,
  selection,
  clipboardAvailable,
  onDrop,
  onConfigChange,
  onRemove,
  onSelect,
  onCopy,
  onPaste,
  onDuplicate,
  depth = 0,
}) {
  const definition = BLOCK_DEFINITIONS[node.type] || { accepts: [] };
  const acceptsChildren = Array.isArray(definition.accepts) && definition.accepts.length > 0;
  const layoutInfo = layout?.[node.id] || {};
  const isSelected = selection?.section === section && selection?.nodeId === node.id;

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

  const handleSelect = (event) => {
    event.stopPropagation();
    onSelect?.({ section, nodeId: node.id });
  };

  const handleContextMenu = (event) => {
    event.preventDefault();
    event.stopPropagation();
    onCopy?.({ section, nodeId: node.id });
  };

  const handleCopyClick = (event) => {
    event.stopPropagation();
    onCopy?.({ section, nodeId: node.id });
  };

  const handlePasteClick = (event) => {
    event.stopPropagation();
    onPaste?.({ section, nodeId: node.id });
  };

  const handleDuplicateClick = (event) => {
    event.stopPropagation();
    onDuplicate?.({ section, nodeId: node.id });
  };

  return (
    <article
      className={`designer-block${isSelected ? " designer-block--selected" : ""}`}
      data-node-id={node.id}
      data-node-type={node.type}
      data-depth={depth}
      data-layout-column={layoutInfo.column ?? depth}
      data-layout-row={layoutInfo.row ?? 0}
      tabIndex={0}
      onClick={handleSelect}
      onFocus={handleSelect}
      onContextMenu={handleContextMenu}
      style={{ "--layout-column": layoutInfo.column ?? depth, "--layout-row": layoutInfo.row ?? 0 }}
    >
      <header className="designer-block__header">
        <span className="designer-block__title heading heading--sm">{definition.label || node.type}</span>
        <div className="designer-block__actions" aria-label="Actions du bloc">
          <button
            type="button"
            className="button button--ghost"
            onClick={handleCopyClick}
            aria-label="Copier le bloc"
          >
            Copier
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={handleDuplicateClick}
            aria-label="Dupliquer le bloc"
          >
            Dupliquer
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={handlePasteClick}
            aria-label="Coller un bloc enfant"
            disabled={!clipboardAvailable}
          >
            Coller
          </button>
          <button
            type="button"
            className="button button--ghost designer-block__remove"
            onClick={handleRemoveClick}
            aria-label={`Supprimer le bloc ${definition.label || node.type}`}
          >
            Retirer
          </button>
        </div>
      </header>
      <div className="designer-block__body">{renderFields(node, handleConfigUpdate)}</div>
      {acceptsChildren ? (
        <div className="designer-block__children">
          {(node.children || []).map((child) => (
            <StrategyBlock
              key={child.id}
              node={child}
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
