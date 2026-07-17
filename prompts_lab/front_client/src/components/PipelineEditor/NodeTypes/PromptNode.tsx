import { Handle, Position } from "@xyflow/react";
import { ExecutionMode, PromptSourceType } from "../../../types";

interface PromptNodeData {
  id: string;
  execution: ExecutionMode;
  prompt: {
    source: PromptSourceType;
    text?: string;
    path?: string;
    template_id?: string;
  };
  response: {
    kind: "text" | "json";
  };
  runMode?: "run" | "mock" | "skip";
  outputs?: Record<string, { source: string }>;
  onDelete?: (id: string) => void;
}

export default function PromptNode({ data, selected }: { data: PromptNodeData; selected: boolean }) {
  const runMode = data.runMode || "run";
  const execution = data.execution || "single";
  const responseKind = data.response?.kind || "text";

  // Prompt snippet preview text
  let promptSnippet = "";
  if (data.prompt) {
    if (data.prompt.source === "inline") {
      promptSnippet = data.prompt.text || "";
    } else if (data.prompt.source === "file") {
      promptSnippet = data.prompt.path || "";
    } else if (data.prompt.source === "template") {
      promptSnippet = data.prompt.template_id || "";
    }
  }
  if (promptSnippet.length > 40) {
    promptSnippet = promptSnippet.slice(0, 38) + "...";
  }

  // Get status dot class and label
  let statusDotClass = "status-run";
  let statusLabel = "Run Node";
  if (runMode === "mock") {
    statusDotClass = "status-mock";
    statusLabel = "Stubbed (Mocked)";
  } else if (runMode === "skip") {
    statusDotClass = "status-skip";
    statusLabel = "Excluded (Skip)";
  }

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.onDelete) {
      data.onDelete(data.id);
    }
  };

  return (
    <div className={`custom-prompt-node ${selected ? "selected" : ""}`}>
      {/* Node input handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{ background: "#475569", width: 8, height: 8 }}
      />

      <div className="node-header">
        <div className="node-title-area">
          <span className="node-id">{data.id}</span>
          <span className="node-type">LLM Stage</span>
        </div>
        
        <div style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
          <span className={`node-badge ${execution === "single" ? "single" : execution === "map" ? "map" : "accum"}`}>
            {execution === "single" ? "Single" : execution === "map" ? "Map" : "Reduce"}
          </span>
          <button 
            onClick={handleDeleteClick}
            style={{
              background: "transparent",
              border: "none",
              color: "#f87171",
              fontSize: "1rem",
              fontWeight: "bold",
              cursor: "pointer",
              padding: "0 0.2rem",
              lineHeight: 1
            }}
            title="Delete stage"
          >
            ×
          </button>
        </div>
      </div>

      <div className="node-body">
        <div style={{ display: "flex", justifyContent: "space-between", color: "#94a3b8", fontSize: "0.7rem", marginBottom: "0.25rem" }}>
          <span>Output: <strong>{responseKind.toUpperCase()}</strong></span>
          <span>Outputs Count: {Object.keys(data.outputs || {}).length}</span>
        </div>
        
        {promptSnippet && (
          <div className="node-prompt-preview" title={promptSnippet}>
            {promptSnippet}
          </div>
        )}

        <div className="node-status-indicator">
          <div className={`node-status-dot ${statusDotClass}`} />
          <span>{statusLabel}</span>
        </div>
      </div>

      {/* Node output handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{ background: "#3b82f6", width: 8, height: 8 }}
      />
    </div>
  );
}
