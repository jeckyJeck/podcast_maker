import { useState, useEffect } from "react";
import { Node, Edge } from "@xyflow/react";
import { ExecutionMode, PromptSourceType, ResponseKind } from "../../types";
import { Trash2, Plus, X, Play, FileCode } from "lucide-react";
import { resolveEdgeSource } from "./EdgeSource";

interface SidebarNodePropsProps {
  selectedNode: Node | null;
  selectedEdge: Edge | null;
  nodes?: Node[];
  edges?: Edge[];
  promptTemplates: Record<string, any[]>;
  onUpdateNode: (nodeId: string, updates: any) => void;
  onUpdateEdge: (edgeId: string, updates: any) => void;
  onDeleteEdge?: (edgeId: string) => void;
  onChangeNodeType?: (nodeId: string, newType: "promptNode" | "inputNode") => void;
  onClose: () => void;

  onDeleteNode?: (id: string) => void;
  onRunPipeline?: () => void;
  pipelineId?: string;
  setPipelineId?: (id: string) => void;
  pipelineName?: string;
  setPipelineName?: (name: string) => void;
  pipelineDesc?: string;
  setPipelineDesc?: (desc: string) => void;
  compileGraphToYaml?: () => string;
  importYamlToGraph?: (yaml: string) => void;
}

export default function SidebarNodeProps({
  selectedNode,
  selectedEdge,
  promptTemplates,
  onUpdateNode,
  onUpdateEdge,
  onDeleteEdge,
  onChangeNodeType,
  onClose,

  onDeleteNode,
  onRunPipeline,
  pipelineId,
  setPipelineId,
  pipelineName,
  setPipelineName,
  pipelineDesc,
  setPipelineDesc,
  compileGraphToYaml,
  importYamlToGraph,
  nodes = [],
  edges = []
}: SidebarNodePropsProps) {
  // --- Local states for Node editing ---
  const [nodeId, setNodeId] = useState("");
  const [execution, setExecution] = useState<ExecutionMode>("single");
  const [mapItem, setMapItem] = useState("");
  const [promptSource, setPromptSource] = useState<PromptSourceType>("inline");
  const [promptText, setPromptText] = useState("");
  const [promptPath, setPromptPath] = useState("");
  const [promptTemplateId, setPromptTemplateId] = useState("");
  const [responseKind, setResponseKind] = useState<ResponseKind>("text");
  const [responseFile, setResponseFile] = useState("");
  const [runMode, setRunMode] = useState<"run" | "mock" | "skip">("run");
  const [mockOutput, setMockOutput] = useState("");
  const [outputsList, setOutputsList] = useState<Array<{ name: string; source: string }>>([]);
  
  // Model & Failure policies
  const [modelProvider, setModelProvider] = useState("");
  const [modelName, setModelName] = useState("");
  const [failStrategy, setFailStrategy] = useState<"abort" | "retry" | "skip">("abort");
  const [failMaxAttempts, setFailMaxAttempts] = useState(2);

  // --- Local states for Input node editing ---
  const [inputType, setInputType] = useState<"text" | "json" | "number" | "boolean">("text");
  const [inputRequired, setInputRequired] = useState(true);
  const [inputDefault, setInputDefault] = useState("");
  const [inputValue, setInputValue] = useState("");

  // --- Local states for Edge editing ---
  const [placeholder, setPlaceholder] = useState("");
  const [edgeFormat, setEdgeFormat] = useState<"text" | "json">("text");
  const [edgeType, setEdgeType] = useState<"normal" | "map" | "accum">("normal");
  const [edgeContextName, setEdgeContextName] = useState("");
  const [edgeItemField, setEdgeItemField] = useState("");
  const [edgeIsOverSource, setEdgeIsOverSource] = useState(false);

  // Sync state with selected node
  useEffect(() => {
    if (selectedNode) {
      const data = selectedNode.data as any;
      setNodeId(selectedNode.id);
      setExecution(data.execution || "single");
      setMapItem(data.map?.item_name || "");
      setPromptSource(data.prompt?.source || "inline");
      setPromptText(data.prompt?.text || "");
      setPromptPath(data.prompt?.path || "");
      setPromptTemplateId(data.prompt?.template_id || "");
      setResponseKind(data.response?.kind || "text");
      setResponseFile(data.response?.file || "");
      setRunMode(data.runMode || "run");
      setMockOutput(data.mockOutput || "");
      
      const outputs = data.outputs || {};
      setOutputsList(
        Object.entries(outputs).map(([name, spec]: [string, any]) => ({
          name,
          source: spec.source || "response"
        }))
      );

      setModelProvider(data.model?.provider || "");
      setModelName(data.model?.name || "");
      setFailStrategy(data.failure?.strategy || "abort");
      setFailMaxAttempts(data.failure?.max_attempts || 2);

      setInputType(data.inputType || "text");
      setInputRequired(data.required !== false);
      setInputDefault(data.default !== undefined ? String(data.default) : "");
      setInputValue(data.value !== undefined ? String(data.value) : "");
    }
  }, [selectedNode]);

  // Sync state with selected edge
  useEffect(() => {
    if (selectedEdge) {
      setPlaceholder((selectedEdge.data?.label as string) || "");
      setEdgeFormat((selectedEdge.data?.format as "text" | "json") || "text");
      setEdgeType((selectedEdge.data?.type as "normal" | "map" | "accum") || "normal");
      setEdgeContextName((selectedEdge.data?.contextName as string) || "");
      setEdgeItemField((selectedEdge.data?.itemField as string) || "");
      setEdgeIsOverSource((selectedEdge.data?.isOverSource as boolean) || false);
    }
  }, [selectedEdge]);

  // Live status for the selected stage's map config - derived from the real
  // "array to loop over" edge, never from a free-text field the user could
  // leave stale. isOverSource is the explicit marker for that edge (set
  // when it's created, or promoted from the Edge panel); older edges saved
  // before isOverSource existed fall back to "first map/accum edge found".
  // It's typed "accum" instead of "map" precisely when the stage accumulates
  // its own output across iterations, so this same edge is also where
  // contextName lives (edited from the Edge panel below). Any other
  // map/accum-typed edge on this stage is a field "tap" on that same
  // connection, not a second loop source.
  const stageIncomingEdges = selectedNode ? edges.filter(e => e.target === selectedNode.id) : [];
  const overEdge =
    stageIncomingEdges.find(e => (e.data as any)?.isOverSource === true && nodes.some(n => n.id === e.source)) ||
    stageIncomingEdges.find(
      e => ((e.data as any)?.type === "map" || (e.data as any)?.type === "accum") && nodes.some(n => n.id === e.source)
    );
  const overSource = overEdge ? resolveEdgeSource(overEdge, nodes) : undefined;
  const overIsAccum = (overEdge?.data as any)?.type === "accum";
  const overContextName = (overEdge?.data as any)?.contextName as string | undefined;

  const [yamlText, setYamlText] = useState("");

  useEffect(() => {
    if (!selectedNode && !selectedEdge && compileGraphToYaml) {
      try {
        setYamlText(compileGraphToYaml());
      } catch (err) {
        console.error("YAML Compilation failed in sidebar:", err);
      }
    }
  }, [selectedNode, selectedEdge, compileGraphToYaml, nodes, edges, pipelineId, pipelineName, pipelineDesc]);

  const handleImport = () => {
    if (importYamlToGraph && yamlText) {
      importYamlToGraph(yamlText);
      alert("YAML configuration successfully loaded into workspace!");
    }
  };

  const handleCopyYaml = () => {
    void navigator.clipboard.writeText(yamlText);
    alert("YAML copied to clipboard!");
  };

  if (!selectedNode && !selectedEdge) {
    // Everything that actually runs comes from the graph/compiled YAML now -
    // no more separate Topic/Format/Hosts fields duplicating what the Input
    // nodes already declare. This is just a live readout + the run button.
    const inputNodes = nodes.filter(n => n.type === "inputNode");
    const missingRequired = inputNodes.filter(n => {
      const d = n.data as any;
      const hasValue = d?.value !== undefined && d?.value !== "";
      const hasDefault = d?.default !== undefined && d?.default !== "";
      return d?.required !== false && !hasValue && !hasDefault;
    });

    return (
      <aside className="sidebar-pane">
        <div className="sidebar-header">
          <h2>Workspace Control</h2>
        </div>

        <div className="sidebar-scrollable">

          {/* Execute Workspace (Run Config) */}
          <div style={{ background: "rgba(59, 130, 246, 0.05)", border: "1px solid var(--border-color)", padding: "1rem", borderRadius: 8, marginBottom: "1.5rem" }}>
            <h3 style={{ margin: "0 0 0.75rem 0", fontSize: "0.9rem", color: "#f8fafc", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Play size={14} className="edge-badge map" /> Execute Pipeline
            </h3>

            {inputNodes.length === 0 ? (
              <p style={{ color: "#94a3b8", fontSize: "0.8rem" }}>No Input nodes on canvas yet.</p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: "0 0 0.75rem 0", fontSize: "0.8rem" }}>
                {inputNodes.map(n => {
                  const d = n.data as any;
                  const name = d?.id || n.id;
                  const hasValue = d?.value !== undefined && d?.value !== "";
                  const shown = hasValue ? d.value : d?.default !== undefined && d?.default !== "" ? d.default : null;
                  return (
                    <li key={n.id} style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", padding: "0.2rem 0", color: shown === null ? "#f59e0b" : "#e2e8f0" }}>
                      <span>{name}</span>
                      <span style={{ maxWidth: "60%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={String(shown ?? "")}>
                        {shown === null ? "⚠ no value set" : String(shown)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}

            {missingRequired.length > 0 && (
              <p style={{ color: "#f59e0b", fontSize: "0.75rem" }}>
                ⚠ Missing required value: {missingRequired.map(n => (n.data as any)?.id || n.id).join(", ")}
              </p>
            )}

            <button
              className="btn btn-primary"
              style={{ width: "100%" }}
              onClick={onRunPipeline}
            >
              <Play size={14} /> Run Pipeline
            </button>
          </div>

          {/* Pipeline Configuration Details */}
          <h3 style={{ margin: "1rem 0 0.75rem 0", fontSize: "0.9rem", color: "#f8fafc" }}>YAML Specifications</h3>
          
          <div className="form-group">
            <label>Pipeline ID</label>
            <input
              type="text"
              className="form-input"
              value={pipelineId || ""}
              onChange={e => setPipelineId && setPipelineId(e.target.value.trim().replace(/[^A-Za-z0-9_-]/g, ""))}
            />
          </div>

          <div className="form-group">
            <label>Pipeline Name</label>
            <input
              type="text"
              className="form-input"
              value={pipelineName || ""}
              onChange={e => setPipelineName && setPipelineName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea
              className="form-textarea"
              style={{ minHeight: "60px" }}
              value={pipelineDesc || ""}
              onChange={e => setPipelineDesc && setPipelineDesc(e.target.value)}
            />
          </div>

          {/* Compiled YAML Preview & Editor */}
          <div className="form-group" style={{ marginTop: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
              <label style={{ margin: 0 }}>YAML Code Definition</label>
              <div style={{ display: "flex", gap: "0.4rem" }}>
                <button
                  onClick={handleCopyYaml}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--accent-color)",
                    fontSize: "0.7rem",
                    cursor: "pointer",
                    padding: 0
                  }}
                >
                  Copy
                </button>
              </div>
            </div>
            
            <textarea
              className="form-textarea"
              style={{ minHeight: "220px", fontSize: "0.75rem", background: "#05070f" }}
              value={yamlText}
              onChange={e => setYamlText(e.target.value)}
            />

            <button
              className="btn btn-secondary"
              style={{ width: "100%", marginTop: "0.5rem" }}
              onClick={handleImport}
            >
              <FileCode size={14} /> Import & Apply YAML
            </button>
          </div>

        </div>
      </aside>
    );
  }

  // --- Node saving updates ---
  const handleSaveNode = () => {
    if (!selectedNode) return;

    // Validate ID
    const cleanId = nodeId.trim().replace(/[^A-Za-z0-9_-]/g, "");
    if (!cleanId) return;

    const outputs: Record<string, { source: string }> = {};
    outputsList.forEach(item => {
      if (item.name.trim()) {
        outputs[item.name.trim()] = { source: item.source.trim() };
      }
    });

    const updates: any = {
      id: cleanId,
      execution,
      prompt: {
        source: promptSource,
        text: promptSource === "inline" ? promptText : undefined,
        path: promptSource === "file" ? promptPath : undefined,
        template_id: promptSource === "template" ? promptTemplateId : undefined
      },
      response: {
        kind: responseKind,
        file: responseFile || undefined
      },
      runMode,
      mockOutput,
      outputs,
      model: modelProvider || modelName ? { provider: modelProvider || undefined, name: modelName || undefined } : undefined,
      failure: {
        strategy: failStrategy,
        max_attempts: failMaxAttempts
      }
    };

    if (execution !== "single") {
      // over / context_name are derived live from graph edges at compile
      // time (see compileGraphToYaml) - only item_name is edited here.
      updates.map = {
        ...(selectedNode.data as any)?.map,
        item_name: mapItem
      };
    }

    onUpdateNode(selectedNode.id, updates);
  };

  // --- Input node saving updates ---
  const handleSaveInputNode = () => {
    if (!selectedNode) return;

    const cleanId = nodeId.trim().replace(/[^A-Za-z0-9_-]/g, "");
    if (!cleanId) return;

    let parsedDefault: any = undefined;
    if (inputDefault.trim() !== "") {
      if (inputType === "number") {
        const n = Number(inputDefault);
        parsedDefault = Number.isNaN(n) ? undefined : n;
      } else if (inputType === "boolean") {
        parsedDefault = inputDefault === "true";
      } else if (inputType === "json") {
        try {
          parsedDefault = JSON.parse(inputDefault);
        } catch {
          parsedDefault = inputDefault;
        }
      } else {
        parsedDefault = inputDefault;
      }
    }

    onUpdateNode(selectedNode.id, {
      id: cleanId,
      inputType,
      required: inputRequired,
      default: parsedDefault,
      value: inputValue.trim() !== "" ? inputValue : undefined
    });
  };

  const handleNodeKindChange = (newType: "promptNode" | "inputNode") => {
    if (!selectedNode || !onChangeNodeType) return;
    onChangeNodeType(selectedNode.id, newType);
  };

  // --- Edge saving updates ---
  const handleSaveEdge = () => {
    if (!selectedEdge) return;
    onUpdateEdge(selectedEdge.id, {
      label: placeholder.trim(),
      format: edgeFormat,
      type: edgeType,
      itemField: edgeItemField.trim()
    });
  };

  const addOutputField = () => {
    setOutputsList([...outputsList, { name: "new_output", source: "response" }]);
  };

  const removeOutputField = (index: number) => {
    const next = [...outputsList];
    next.splice(index, 1);
    setOutputsList(next);
  };

  const updateOutputField = (index: number, key: "name" | "source", value: string) => {
    const next = [...outputsList];
    next[index][key] = value;
    setOutputsList(next);
  };

  return (
    <aside className="sidebar-pane">
      <div className="sidebar-header">
        <h2>{selectedNode ? `${selectedNode.type === "inputNode" ? "Input" : "Stage"}: ${nodeId}` : "Connection"}</h2>
        <button onClick={onClose} className="toolbar-btn" style={{ padding: "0.2rem" }} title="Close">
          <X size={18} />
        </button>
      </div>

      <div className="sidebar-scrollable">
        {selectedNode ? (
          <div>
            {/* Node Kind toggle - convert between execution stage and static input */}
            <div className="form-group">
              <label>Node Kind</label>
              <select
                className="form-select"
                value={selectedNode.type === "inputNode" ? "inputNode" : "promptNode"}
                onChange={e => handleNodeKindChange(e.target.value as "promptNode" | "inputNode")}
              >
                <option value="promptNode">Execution Stage (runs an LLM call)</option>
                <option value="inputNode">Pipeline Input (static data, not executed)</option>
              </select>
            </div>

            {/* Node Identification */}
            <div className="form-group">
              <label>{selectedNode.type === "inputNode" ? "Input Name" : "Stage ID"}</label>
              <input
                type="text"
                className="form-input"
                value={nodeId}
                onChange={e => setNodeId(e.target.value)}
                onBlur={selectedNode.type === "inputNode" ? handleSaveInputNode : handleSaveNode}
              />
            </div>

            {selectedNode.type === "inputNode" ? (
              <div>
                <div className="form-group">
                  <label>Value Type</label>
                  <select
                    className="form-select"
                    value={inputType}
                    onChange={e => setInputType(e.target.value as any)}
                    onBlur={handleSaveInputNode}
                  >
                    <option value="text">Text</option>
                    <option value="json">JSON</option>
                    <option value="number">Number</option>
                    <option value="boolean">Boolean</option>
                  </select>
                </div>

                <div className="form-group checkbox-label" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <input
                    type="checkbox"
                    checked={inputRequired}
                    onChange={e => {
                      setInputRequired(e.target.checked);
                      onUpdateNode(selectedNode.id, { required: e.target.checked });
                    }}
                  />
                  <label style={{ margin: 0 }}>Required</label>
                </div>

                <div className="form-group">
                  <label>Value {inputType === "json" && "(JSON)"} — used when you click Run Pipeline</label>
                  {inputType === "json" ? (
                    <textarea
                      className="form-textarea"
                      value={inputValue}
                      onChange={e => setInputValue(e.target.value)}
                      onBlur={handleSaveInputNode}
                      placeholder='e.g. {"key": "value"}'
                    />
                  ) : inputType === "boolean" ? (
                    <select
                      className="form-select"
                      value={inputValue || ""}
                      onChange={e => {
                        setInputValue(e.target.value);
                        onUpdateNode(selectedNode.id, { value: e.target.value || undefined });
                      }}
                    >
                      <option value="">(use default)</option>
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : (
                    <input
                      type={inputType === "number" ? "number" : "text"}
                      className="form-input"
                      value={inputValue}
                      onChange={e => setInputValue(e.target.value)}
                      onBlur={handleSaveInputNode}
                      placeholder="This is the actual content sent to the pipeline"
                    />
                  )}
                  <small style={{ color: "#94a3b8" }}>
                    This is the real content for this run - not just a schema default.
                  </small>
                </div>

                <div className="form-group">
                  <label>Default Value {inputType === "json" && "(JSON)"} (schema fallback if no value is given)</label>
                  {inputType === "json" ? (
                    <textarea
                      className="form-textarea"
                      value={inputDefault}
                      onChange={e => setInputDefault(e.target.value)}
                      onBlur={handleSaveInputNode}
                      placeholder='e.g. {"key": "value"}'
                    />
                  ) : inputType === "boolean" ? (
                    <select
                      className="form-select"
                      value={inputDefault || ""}
                      onChange={e => setInputDefault(e.target.value)}
                      onBlur={handleSaveInputNode}
                    >
                      <option value="">No default</option>
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : (
                    <input
                      type={inputType === "number" ? "number" : "text"}
                      className="form-input"
                      value={inputDefault}
                      onChange={e => setInputDefault(e.target.value)}
                      onBlur={handleSaveInputNode}
                      placeholder="Optional default value"
                    />
                  )}
                </div>

                {onDeleteNode && (
                  <div style={{ marginTop: "1.5rem", borderTop: "1px solid var(--border-color)", paddingTop: "1rem" }}>
                    <button
                      className="btn btn-danger"
                      style={{ width: "100%" }}
                      onClick={() => onDeleteNode(selectedNode.id)}
                    >
                      <Trash2 size={14} /> Delete Input Node
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <>
            {/* Run mode (Partial execution) */}
            <div className="form-group">
              <label>Run Mode (Partial Execution)</label>
              <select
                className="form-select"
                value={runMode}
                onChange={e => {
                  setRunMode(e.target.value as any);
                  // Auto save on selection
                  onUpdateNode(selectedNode.id, { runMode: e.target.value });
                }}
              >
                <option value="run">Execute Stage (LLM)</option>
                <option value="mock">Stub Output (Pre-filled/Mock)</option>
                <option value="skip">Skip / Exclude Stage</option>
              </select>
            </div>

            {/* Mock Output editor (if stubbed) */}
            {runMode === "mock" && (
              <div className="form-group">
                <label>Mock Output (Raw or JSON)</label>
                <textarea
                  className="form-textarea"
                  value={mockOutput}
                  onChange={e => setMockOutput(e.target.value)}
                  onBlur={handleSaveNode}
                  placeholder='Enter plain text or JSON (e.g. {"key": "val"})'
                />
              </div>
            )}

            {/* Execution settings */}
            <div className="form-group">
              <label>Execution Mode</label>
              <select
                className="form-select"
                value={execution}
                onChange={e => setExecution(e.target.value as ExecutionMode)}
                onBlur={handleSaveNode}
              >
                <option value="single">Single Run (Once)</option>
                <option value="map">Map (Loop over a list)</option>
                <option value="map_with_context">Map with Context (Reduce/Loop)</option>
              </select>
            </div>

            {execution !== "single" && (
              <div style={{ padding: "0.5rem", background: "rgba(0,0,0,0.15)", borderRadius: 6, marginBottom: "1rem" }}>
                <div className="form-group">
                  <label>Array to Loop Over</label>
                  {overSource ? (
                    <div className="form-input" style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: "#e2e8f0" }}>
                      <span className={`edge-badge ${overIsAccum ? "accum" : "map"}`} title={overIsAccum ? "Map with Accumulation connection" : "Map connection"}>
                        {overIsAccum ? "+ ↺" : "↺"}
                      </span>
                      <code>{overSource}</code>
                      {execution === "map_with_context" && !overIsAccum && (
                        <span style={{ color: "#f59e0b" }} title="This stage needs a Map with Accumulation edge, not a plain Map edge">⚠ wrong type</span>
                      )}
                    </div>
                  ) : (
                    <div className="form-input" style={{ color: "#f59e0b" }}>
                      ⚠ No array connected. Drag an edge here from the stage/input
                      producing the list; it'll default to the right connection type automatically.
                    </div>
                  )}
                </div>
                <div className="form-group">
                  <label>Item Variable Name</label>
                  <input
                    type="text"
                    className="form-input"
                    value={mapItem}
                    onChange={e => setMapItem(e.target.value)}
                    onBlur={handleSaveNode}
                    placeholder="e.g. segment"
                  />
                </div>
                {execution === "map_with_context" && (
                  <div className="form-group">
                    <label>Accumulated Context Variable</label>
                    <div className="form-input" style={{ color: overContextName ? "#e2e8f0" : "#f59e0b" }}>
                      {overContextName ? <code>{overContextName}</code> : "⚠ Not set - select the accumulation edge to name it"}
                    </div>
                    <small style={{ color: "#94a3b8" }}>
                      Select the incoming edge on canvas to rename it (Edge panel → Context Variable Name).
                    </small>
                  </div>
                )}
              </div>
            )}

            {/* Prompt Source Selection */}
            <div className="form-group">
              <label>Prompt Source</label>
              <select
                className="form-select"
                value={promptSource}
                onChange={e => setPromptSource(e.target.value as PromptSourceType)}
                onBlur={handleSaveNode}
              >
                <option value="inline">Inline Text</option>
                <option value="file">Local File Path</option>
                <option value="template">Stored Prompt Template</option>
              </select>
            </div>

            {promptSource === "inline" && (
              <div className="form-group">
                <label>Prompt Text</label>
                <textarea
                  className="form-textarea"
                  style={{ minHeight: "150px" }}
                  value={promptText}
                  onChange={e => setPromptText(e.target.value)}
                  onBlur={handleSaveNode}
                />
              </div>
            )}

            {promptSource === "file" && (
              <div className="form-group">
                <label>File Path</label>
                <input
                  type="text"
                  className="form-input"
                  value={promptPath}
                  onChange={e => setPromptPath(e.target.value)}
                  onBlur={handleSaveNode}
                  placeholder="prompts/my_stage.md"
                />
              </div>
            )}

            {promptSource === "template" && (
              <div className="form-group">
                <label>Select Template</label>
                <select
                  className="form-select"
                  value={promptTemplateId}
                  onChange={e => setPromptTemplateId(e.target.value)}
                  onBlur={handleSaveNode}
                >
                  <option value="">Choose prompt template...</option>
                  {(promptTemplates[nodeId] || []).map(t => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Outputs Contract */}
            <div className="form-group">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <label style={{ margin: 0 }}>Exposed Outputs</label>
                <button className="toolbar-btn" onClick={addOutputField} title="Add Output">
                  <Plus size={16} />
                </button>
              </div>

              {outputsList.map((item, idx) => (
                <div key={idx} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.4rem" }}>
                  <input
                    type="text"
                    className="form-input"
                    style={{ flex: 1, padding: "0.4rem" }}
                    value={item.name}
                    onChange={e => updateOutputField(idx, "name", e.target.value)}
                    onBlur={handleSaveNode}
                    placeholder="name"
                  />
                  <input
                    type="text"
                    className="form-input"
                    style={{ flex: 1, padding: "0.4rem" }}
                    value={item.source}
                    onChange={e => updateOutputField(idx, "source", e.target.value)}
                    onBlur={handleSaveNode}
                    placeholder="response.field"
                  />
                  <button className="toolbar-btn" style={{ color: "#f87171" }} onClick={() => removeOutputField(idx)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>

            {/* Response Config */}
            <div className="form-group">
              <label>Response Content Kind</label>
              <select
                className="form-select"
                value={responseKind}
                onChange={e => setResponseKind(e.target.value as ResponseKind)}
                onBlur={handleSaveNode}
              >
                <option value="text">Plain Text</option>
                <option value="json">Structured JSON</option>
              </select>
            </div>

            <div className="form-group">
              <label>Output Filename</label>
              <input
                type="text"
                className="form-input"
                value={responseFile}
                onChange={e => setResponseFile(e.target.value)}
                onBlur={handleSaveNode}
                placeholder="outputs/result.json"
              />
            </div>

            {/* Advanced configurations */}
            <div style={{ borderTop: "1px solid var(--border-color)", marginTop: "1.5rem", paddingTop: "1rem" }}>
              <h4 style={{ margin: "0 0 0.75rem 0", color: "#94a3b8", fontSize: "0.8rem", textTransform: "uppercase" }}>Advanced (Model & Failures)</h4>
              
              <div className="form-group">
                <label>Model Provider</label>
                <input
                  type="text"
                  className="form-input"
                  value={modelProvider}
                  onChange={e => setModelProvider(e.target.value)}
                  onBlur={handleSaveNode}
                  placeholder="e.g. gemini"
                />
              </div>

              <div className="form-group">
                <label>Model Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={modelName}
                  onChange={e => setModelName(e.target.value)}
                  onBlur={handleSaveNode}
                  placeholder="e.g. gemini-2.5-flash"
                />
              </div>

              <div className="form-group">
                <label>Failure Strategy</label>
                <select
                  className="form-select"
                  value={failStrategy}
                  onChange={e => setFailStrategy(e.target.value as any)}
                  onBlur={handleSaveNode}
                >
                  <option value="abort">Abort Pipeline</option>
                  <option value="retry">Retry Stage</option>
                  <option value="skip">Skip / Continue</option>
                </select>
              </div>

              {failStrategy === "retry" && (
                <div className="form-group">
                  <label>Max Attempts</label>
                  <input
                    type="number"
                    className="form-input"
                    value={failMaxAttempts}
                    onChange={e => setFailMaxAttempts(parseInt(e.target.value) || 1)}
                    onBlur={handleSaveNode}
                  />
                </div>
              )}
            </div>

            {onDeleteNode && (
              <div style={{ marginTop: "1.5rem", borderTop: "1px solid var(--border-color)", paddingTop: "1rem" }}>
                <button
                  className="btn btn-danger"
                  style={{ width: "100%" }}
                  onClick={() => onDeleteNode(selectedNode.id)}
                >
                  <Trash2 size={14} /> Delete Stage Node
                </button>
              </div>
            )}
              </>
            )}

          </div>
        ) : (
          <div>
            {/* Edge properties editing */}
            <div className="form-group">
              <label>Placeholder in Target Prompt</label>
              <input
                type="text"
                className="form-input"
                value={placeholder}
                onChange={e => setPlaceholder(e.target.value)}
                onBlur={handleSaveEdge}
                placeholder="e.g. {{TOPIC}}"
              />
            </div>

            <div className="form-group">
              <label>Connection Line Type</label>
              <select
                className="form-select"
                value={edgeType}
                onChange={e => {
                  setEdgeType(e.target.value as any);
                  // Auto save edge updates
                  onUpdateEdge(selectedEdge!.id, { type: e.target.value });
                }}
              >
                <option value="normal">Normal Link (Pass Output)</option>
                <option value="map">MAP Link (Pass List Item)</option>
                <option value="accum">MAP with Accumulation (Pass Accumulator)</option>
              </select>
            </div>

            {(edgeType === "map" || edgeType === "accum") && (
              <div className="form-group checkbox-label" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  type="checkbox"
                  checked={edgeIsOverSource}
                  onChange={e => {
                    setEdgeIsOverSource(e.target.checked);
                    onUpdateEdge(selectedEdge!.id, { isOverSource: e.target.checked });
                  }}
                />
                <label style={{ margin: 0 }}>Defines the array to loop over (map.over)</label>
              </div>
            )}

            {edgeType === "accum" && edgeIsOverSource && (
              <div className="form-group">
                <label>Context Variable Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={edgeContextName}
                  onChange={e => setEdgeContextName(e.target.value)}
                  onBlur={() => onUpdateEdge(selectedEdge!.id, { contextName: edgeContextName.trim() })}
                  placeholder="e.g. previous_scenes"
                />
                <small style={{ color: "#94a3b8" }}>
                  Referenced in the prompt as source: context.{edgeContextName || "<name>"}
                </small>
              </div>
            )}

            {edgeType === "map" && !edgeIsOverSource && (
              <div className="form-group">
                <label>Field Within Item (optional)</label>
                <input
                  type="text"
                  className="form-input"
                  value={edgeItemField}
                  onChange={e => setEdgeItemField(e.target.value)}
                  onBlur={handleSaveEdge}
                  placeholder="e.g. target_word_count (blank = whole item)"
                />
                <small style={{ color: "#94a3b8" }}>
                  Same connection as the loop's array source - just pulls the current
                  item ({edgeItemField ? `item.${edgeItemField}` : "item"}), not the array itself.
                </small>
              </div>
            )}

            <div className="form-group">
              <label>Value Format</label>
              <select
                className="form-select"
                value={edgeFormat}
                onChange={e => {
                  setEdgeFormat(e.target.value as any);
                  onUpdateEdge(selectedEdge!.id, { format: e.target.value });
                }}
              >
                <option value="text">Text (String)</option>
                <option value="json">JSON Object/Array</option>
              </select>
            </div>

            {onDeleteEdge && (
              <div style={{ marginTop: "1.5rem", borderTop: "1px solid var(--border-color)", paddingTop: "1rem" }}>
                <button
                  className="btn btn-danger"
                  style={{ width: "100%" }}
                  onClick={() => onDeleteEdge(selectedEdge!.id)}
                >
                  <Trash2 size={14} /> Delete Connection
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
