import React, { useMemo, useRef, useState } from "react";
import BlockPalette from "./BlockPalette.jsx";
import DesignerCanvas from "./DesignerCanvas.jsx";
import { BLOCK_DEFINITIONS, cloneDefaultConfig } from "./designerConstants.js";
import { buildExports } from "./serializer.js";

function createNode(type, idRef) {
  const definition = BLOCK_DEFINITIONS[type];
  return {
    id: `node-${idRef.current++}`,
    type,
    label: definition ? definition.label : type,
    config: cloneDefaultConfig(type),
    children: [],
  };
}

function findNode(nodes, nodeId) {
  for (const node of nodes) {
    if (node.id === nodeId) {
      return node;
    }
    const child = findNode(node.children || [], nodeId);
    if (child) {
      return child;
    }
  }
  return null;
}

function appendNode(nodes, targetId, item) {
  if (!targetId) {
    return [...nodes, item];
  }
  let changed = false;
  const next = nodes.map((node) => {
    if (node.id === targetId) {
      changed = true;
      const children = Array.isArray(node.children) ? [...node.children, item] : [item];
      return { ...node, children };
    }
    if (node.children && node.children.length) {
      const updatedChildren = appendNode(node.children, targetId, item);
      if (updatedChildren !== node.children) {
        changed = true;
        return { ...node, children: updatedChildren };
      }
    }
    return node;
  });
  return changed ? next : nodes;
}

function updateNode(nodes, nodeId, updater) {
  let changed = false;
  const next = nodes.map((node) => {
    if (node.id === nodeId) {
      changed = true;
      return updater(node);
    }
    if (node.children && node.children.length) {
      const updatedChildren = updateNode(node.children, nodeId, updater);
      if (updatedChildren !== node.children) {
        changed = true;
        return { ...node, children: updatedChildren };
      }
    }
    return node;
  });
  return changed ? next : nodes;
}

function removeNode(nodes, nodeId) {
  let changed = false;
  const filtered = [];
  for (const node of nodes) {
    if (node.id === nodeId) {
      changed = true;
      continue;
    }
    let current = node;
    if (node.children && node.children.length) {
      const updatedChildren = removeNode(node.children, nodeId);
      if (updatedChildren !== node.children) {
        current = { ...node, children: updatedChildren };
        changed = true;
      }
    }
    filtered.push(current);
  }
  return changed ? filtered : nodes;
}

export default function StrategyDesigner({
  defaultName = "Nouvelle stratégie",
  defaultFormat = "yaml",
  saveEndpoint = "/strategies/save",
}) {
  const idRef = useRef(1);
  const [name, setName] = useState(defaultName);
  const [format, setFormat] = useState(defaultFormat === "python" ? "python" : "yaml");
  const [conditions, setConditions] = useState([]);
  const [actions, setActions] = useState([]);
  const [status, setStatus] = useState({ type: "idle", message: null });
  const [lastResponse, setLastResponse] = useState(null);

  const exports = useMemo(
    () => buildExports(name, conditions, actions),
    [name, conditions, actions]
  );

  const handleDrop = ({ section, targetId, type }) => {
    const definition = BLOCK_DEFINITIONS[type];
    if (!definition) {
      setStatus({ type: "error", message: "Type de bloc inconnu." });
      return;
    }
    if (section === "conditions" && definition.category !== "conditions") {
      setStatus({ type: "error", message: "Ce bloc ne peut pas être utilisé dans les conditions." });
      return;
    }
    if (section === "actions" && definition.category !== "actions") {
      setStatus({ type: "error", message: "Ce bloc ne peut pas être utilisé dans les actions." });
      return;
    }

    const collection = section === "conditions" ? conditions : actions;
    const parent = targetId ? findNode(collection, targetId) : null;
    if (targetId && (!parent || !BLOCK_DEFINITIONS[parent.type]?.accepts?.includes(type))) {
      setStatus({
        type: "error",
        message: "La cible ne peut pas contenir ce type de bloc.",
      });
      return;
    }

    const node = createNode(type, idRef);
    if (section === "conditions") {
      setConditions((prev) => appendNode(prev, targetId, node));
    } else {
      setActions((prev) => appendNode(prev, targetId, node));
    }
    setStatus({ type: "success", message: `${definition.label} ajouté.` });
  };

  const handleAdd = ({ type, section }) => {
    handleDrop({ section, targetId: null, type });
  };

  const handleConfigChange = ({ section, nodeId, config }) => {
    if (section === "conditions") {
      setConditions((prev) => updateNode(prev, nodeId, (node) => ({ ...node, config })));
    } else {
      setActions((prev) => updateNode(prev, nodeId, (node) => ({ ...node, config })));
    }
  };

  const handleRemove = ({ section, nodeId }) => {
    if (section === "conditions") {
      setConditions((prev) => removeNode(prev, nodeId));
    } else {
      setActions((prev) => removeNode(prev, nodeId));
    }
    setStatus({ type: "info", message: "Bloc supprimé." });
  };

  const handleSave = async (event) => {
    event.preventDefault();
    if (!name.trim()) {
      setStatus({ type: "error", message: "Le nom de la stratégie est obligatoire." });
      return;
    }
    setStatus({ type: "saving", message: "Enregistrement en cours…" });
    setLastResponse(null);

    const payload = {
      name: name.trim(),
      format,
      code: format === "python" ? exports.python : exports.yaml,
    };

    try {
      const response = await fetch(saveEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let detail = `Échec de l'enregistrement (HTTP ${response.status}).`;
        try {
          const body = await response.json();
          if (body && body.detail) {
            detail = Array.isArray(body.detail)
              ? body.detail.map((item) => item.msg || item.detail).join("; ")
              : typeof body.detail === "string"
              ? body.detail
              : JSON.stringify(body.detail);
          }
        } catch (error) {
          // ignore JSON parsing errors
        }
        setStatus({ type: "error", message: detail });
        return;
      }

      let data = null;
      try {
        data = await response.json();
      } catch (error) {
        data = null;
      }
      setLastResponse(data);
      setStatus({ type: "success", message: "Stratégie enregistrée avec succès." });
    } catch (error) {
      setStatus({
        type: "error",
        message: "Impossible de contacter le service de sauvegarde des stratégies.",
      });
    }
  };

  return (
    <form className="strategy-designer" onSubmit={handleSave} aria-labelledby="designer-title">
      <header className="strategy-designer__header">
        <div>
          <h1 id="designer-title" className="heading heading--lg">
            Éditeur de stratégies
          </h1>
          <p className="text text--muted">
            Composez vos règles en glissant-déposant des blocs puis exportez-les vers l'algo-engine.
          </p>
        </div>
        <div className="strategy-designer__actions">
          <label className="designer-field strategy-designer__name-field">
            <span className="designer-field__label text text--muted">Nom de la stratégie</span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </label>
          <label className="designer-field strategy-designer__format-field">
            <span className="designer-field__label text text--muted">Format d'export</span>
            <select value={format} onChange={(event) => setFormat(event.target.value)}>
              <option value="yaml">YAML</option>
              <option value="python">Python</option>
            </select>
          </label>
          <button type="submit" className="button button--primary">
            Enregistrer la stratégie
          </button>
        </div>
      </header>

      {status.message ? (
        <div
          className={`designer-status designer-status--${status.type}`}
          role={status.type === "error" ? "alert" : "status"}
          aria-live="polite"
        >
          {status.message}
        </div>
      ) : null}

      <div className="strategy-designer__layout">
        <BlockPalette onAdd={handleAdd} />
        <DesignerCanvas
          conditions={conditions}
          actions={actions}
          onDrop={handleDrop}
          onConfigChange={handleConfigChange}
          onRemove={handleRemove}
        />
        <section className="designer-panel designer-panel--preview" aria-labelledby="preview-title">
          <div className="designer-panel__header">
            <h2 id="preview-title" className="heading heading--md">
              Aperçu du code
            </h2>
            <p className="text text--muted">
              Utilisez les onglets YAML / Python pour vérifier le rendu avant sauvegarde.
            </p>
          </div>
          <div className="designer-panel__body">
            <textarea
              className="designer-preview"
              readOnly
              value={format === "python" ? exports.python : exports.yaml}
              data-testid="strategy-preview"
              aria-label={`Aperçu ${format}`}
            />
            {lastResponse ? (
              <details className="designer-response">
                <summary>Réponse du moteur</summary>
                <pre>{JSON.stringify(lastResponse, null, 2)}</pre>
              </details>
            ) : null}
          </div>
        </section>
      </div>
    </form>
  );
}
