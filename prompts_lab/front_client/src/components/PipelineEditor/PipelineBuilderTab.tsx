import { useState, useEffect, useCallback } from "react";
import {
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  MarkerType
} from "@xyflow/react";
import { parse as parseYaml, stringify as stringifyYaml } from "yaml";
import {
  Save,
  FolderOpen,
  BookOpen,
  RotateCcw,
  Sparkles,
  ChevronRight,
  X
} from "lucide-react";

import PipelineCanvas from "./PipelineCanvas";
import SidebarNodeProps from "./SidebarNodeProps";
import { layoutPipelineNodes } from "./LayoutUtils";
import { resolveEdgeSource, parseInputValue } from "./EdgeSource";
import {
  saveWorkspace,
  loadWorkspace
} from "../../services/localStorage";
import {
  getPipelines,
  getPipeline,
  savePipeline,
  getPipelineTemplates,
  runPipeline,
  getRuns,
  listPromptTemplates,
  getMeta
} from "../../services/api";

export default function PipelineBuilderTab() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Top level pipeline settings
  const [pipelineId, setPipelineId] = useState("stable_pipeline_id");
  const [pipelineName, setPipelineName] = useState("My Podcast Pipeline");
  const [pipelineDesc, setPipelineDesc] = useState("Custom workflow to generate podcast stages.");
  
  // Selection states
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);

  // Fetch prompts templates (from backend) for stage settings
  const [promptTemplates, setPromptTemplates] = useState<Record<string, any[]>>({});

  // Dialog popups states
  const [showLoadModal, setShowLoadModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [showRunResults, setShowRunResults] = useState(false);
  const [runLogs, setRunLogs] = useState<any | null>(null);

  // Backend fetched items list
  const [pipelinesList, setPipelinesList] = useState<any[]>([]);
  const [templatesList, setTemplatesList] = useState<any[]>([]);
  const [_runsList, setRunsList] = useState<any[]>([]);
  const [_meta, setMeta] = useState<any>(null);
  
  // Token (from localstorage)
  const token = localStorage.getItem("prompts_lab_token") || "";

  // Common delete stage callback
  const deleteStageNode = useCallback((idToDelete: string) => {
    setNodes(nds => nds.filter(n => n.id !== idToDelete));
    setEdges(eds => eds.filter(e => e.source !== idToDelete && e.target !== idToDelete));
    setSelectedNode(null);
  }, [setNodes, setEdges]);

  // Convert a node between an execution stage and a static pipeline input
  const handleChangeNodeType = useCallback((nodeId: string, newType: "promptNode" | "inputNode") => {
    setNodes(nds => nds.map((node: Node) => {
      if (node.id !== nodeId || node.type === newType) return node;

      const currentId = ((node.data as any)?.id as string) || node.id;

      if (newType === "inputNode") {
        // Dropping stage-only wiring (execution/prompt/response/outputs) since it's not a step anymore
        return {
          ...node,
          type: "inputNode",
          data: {
            id: currentId,
            inputType: "text",
            required: true,
            default: undefined,
            onDelete: deleteStageNode
          }
        };
      }

      return {
        ...node,
        type: "promptNode",
        data: {
          id: currentId,
          execution: "single",
          prompt: { source: "inline", text: "Write your prompt here..." },
          response: { kind: "text", file: `outputs/${currentId}.txt` },
          outputs: { result: { source: "response" } },
          runMode: "run",
          mockOutput: "",
          onDelete: deleteStageNode
        }
      };
    }));
    // Edges touching this node no longer make sense once its role changes
    setEdges(eds => eds.filter(e => e.source !== nodeId && e.target !== nodeId));
    setSelectedNode(null);
  }, [setNodes, setEdges, deleteStageNode]);

  // Load from local storage workspace on component mount
  useEffect(() => {
    const saved = loadWorkspace();
    if (saved) {
      setPipelineId(saved.metadata.id || "stable_pipeline_id");
      setPipelineName(saved.metadata.name || "My Podcast Pipeline");
      setPipelineDesc(saved.metadata.description || "");
      
      // Re-attach delete callbacks to parsed nodes
      const nodesWithCallbacks = saved.nodes.map(n => ({
        ...n,
        data: {
          ...n.data,
          onDelete: deleteStageNode
        }
      }));
      setNodes(nodesWithCallbacks);
      setEdges(saved.edges);
    } else {
      // Default initial layout (Architect, Researcher, Outliner, Scriptwriter flow)
      loadDefaultStandardFlow();
    }
  }, [deleteStageNode, setNodes, setEdges]);

  // Auto-save nodes & edges configuration to localStorage on change
  useEffect(() => {
    if (nodes.length > 0) {
      const inputs: Record<string, any> = {};
      nodes.filter(n => n.type === "inputNode").forEach(n => {
        const data = n.data as any;
        const inputName = (data?.id as string) || n.id;
        const spec: any = { type: data?.inputType || "text", required: data?.required !== false };
        if (data?.default !== undefined && data?.default !== "") spec.default = data.default;
        inputs[inputName] = spec;
      });

      saveWorkspace({
        nodes,
        edges,
        inputs,
        metadata: {
          id: pipelineId,
          name: pipelineName,
          description: pipelineDesc
        }
      });
    }
  }, [nodes, edges, pipelineId, pipelineName, pipelineDesc]);

  // Load templates list and list runs from api
  const fetchBackendLists = async () => {
    try {
      const pipes = await getPipelines(token);
      setPipelinesList(pipes.pipelines || []);
      
      const temps = await getPipelineTemplates(token);
      setTemplatesList(temps.templates || []);

      const runs = await getRuns(token);
      setRunsList(runs || []);

      const metadata = await getMeta(token);
      setMeta(metadata);
    } catch (err) {
      console.error("Failed to load list data:", err);
    }
  };

  useEffect(() => {
    void fetchBackendLists();
  }, []);

  // Fetch prompt templates of a node when selected
  useEffect(() => {
    if (selectedNode && selectedNode.type === "promptNode") {
      const nodeId = selectedNode.id;
      listPromptTemplates(nodeId, token)
        .then(templates => {
          setPromptTemplates(prev => ({ ...prev, [nodeId]: templates }));
        })
        .catch(err => console.error("Failed to fetch stage templates:", err));
    }
  }, [selectedNode, token]);

  // Node updates from properties panel
  const handleUpdateNode = useCallback((nodeId: string, updates: any) => {
    setNodes(nds =>
      nds.map(node => {
        if (node.id === nodeId) {
          // If ID changes, we must align handles and edges
          const nextId = updates.id || node.id;
          return {
            ...node,
            id: nextId,
            data: {
              ...node.data,
              ...updates,
              id: nextId
            }
          };
        }
        return node;
      })
    );

    // If ID changed, update all edges referencing it
    if (updates.id && updates.id !== nodeId) {
      setEdges(eds =>
        eds.map(edge => {
          const nextEdge = { ...edge };
          if (edge.source === nodeId) nextEdge.source = updates.id;
          if (edge.target === nodeId) nextEdge.target = updates.id;
          return nextEdge;
        })
      );
    }
  }, [setNodes, setEdges]);

  // Edge updates from properties panel
  const handleUpdateEdge = useCallback((edgeId: string, updates: any) => {
    setEdges(eds => {
      const target = eds.find(e => e.id === edgeId)?.target;
      return eds.map(edge => {
        if (edge.id === edgeId) {
          return {
            ...edge,
            data: {
              ...edge.data,
              ...updates
            }
          };
        }
        // Only one edge per stage can define map.over - promoting this one
        // demotes any other edge already marked as the array-source for the
        // same target.
        if (updates.isOverSource === true && target && edge.target === target) {
          return { ...edge, data: { ...edge.data, isOverSource: false } };
        }
        return edge;
      });
    });
  }, [setEdges]);

  // Remove a single edge (used by the Edge properties panel's Delete button)
  const handleDeleteEdge = useCallback((edgeId: string) => {
    setEdges(eds => eds.filter(e => e.id !== edgeId));
    setSelectedEdge(null);
  }, [setEdges]);

  // Load a default standard 4-stage pipeline layout
  const loadDefaultStandardFlow = () => {
    const defaultYaml = `version: 1
id: standard_podcast
name: Standard Podcast Builder
description: Standard workflow incorporating architect, researcher, outliner, and scriptwriter.
inputs:
  topic:
    type: text
    required: true
  hosts:
    type: text
    required: true
stages:
  - id: architect
    type: llm
    execution: single
    prompt:
      source: inline
      text: "You are a podcast blueprint architect. Generate segments for the topic: {{topic}} and hosts: {{hosts}}."
    bindings:
      - placeholder: "{{topic}}"
        source: inputs.topic
      - placeholder: "{{hosts}}"
        source: inputs.hosts
    response:
      kind: json
      file: outputs/blueprint.json
    outputs:
      blueprint:
        source: response
      segments:
        source: response.segments

  - id: researcher
    type: llm
    execution: map
    map:
      over: architect.segments
      item_name: segment
    prompt:
      source: inline
      text: "Research the segment: {{segment}}."
    bindings:
      - placeholder: "{{segment}}"
        source: item
    response:
      kind: text
      aggregate_file: outputs/research.md
      aggregate_strategy: concat_with_headers
    outputs:
      research:
        source: response.aggregate

  - id: outliner
    type: llm
    execution: single
    prompt:
      source: inline
      text: "Create a detailed script outline using the blueprint: {{blueprint}} and research material: {{research}}."
    bindings:
      - placeholder: "{{blueprint}}"
        source: architect.blueprint
      - placeholder: "{{research}}"
        source: researcher.research
    response:
      kind: json
      file: outputs/outline.json
    outputs:
      outline:
        source: response

  - id: scriptwriter
    type: llm
    execution: single
    prompt:
      source: inline
      text: "Write the full audio script for outline: {{outline}} and research: {{research}}."
    bindings:
      - placeholder: "{{outline}}"
        source: outliner.outline
      - placeholder: "{{research}}"
        source: researcher.research
    response:
      kind: text
      file: outputs/script.txt
    outputs:
      script:
        source: response
`;
    importYamlToGraph(defaultYaml);
  };

  // Convert current Flow Graph structure to strict Pipeline YAML v1
  const compileGraphToYaml = (): string => {
    // 1. Compile Inputs
    const inputs: Record<string, any> = {};
    nodes
      .filter(n => n.type === "inputNode")
      .forEach(n => {
        const data = n.data as any;
        const inputName = (data?.id as string) || n.id;
        const spec: any = { type: data?.inputType || "text" };
        if (data?.required !== undefined) spec.required = data.required;
        if (data?.default !== undefined && data?.default !== "") spec.default = data.default;
        inputs[inputName] = spec;
      });

    // 2. Compile Stages and Sort topologically
    const stageNodes = nodes.filter(n => n.type === "promptNode");
    
    // Sort stages topologically to meet contract ordering constraints
    const sortedNodes = layoutPipelineNodes(stageNodes, edges);
    
    const stages = sortedNodes.map(node => {
      const data = node.data as any;
      const incomingEdges = edges.filter(e => e.target === node.id);

      // The "array to loop over" must be a real edge from the node that
      // produces it - never free text. isOverSource is the explicit,
      // single source of truth for which incoming edge defines map.over;
      // it's set when the edge is created/promoted (see PipelineCanvas
      // onConnect and the sidebar's edge panel) and never inferred from
      // "first map/accum-typed edge found", since that breaks once a
      // second map/accum-typed edge (an item/context field tap) exists
      // between the same pair. Older edges saved before isOverSource
      // existed fall back to that legacy first-match behavior. When the
      // over edge is "accum", its contextName is the single source of
      // truth for every context.<name> tap below.
      const explicitOverEdge = incomingEdges.find(
        e => (e.data as any)?.isOverSource === true && nodes.some(n => n.id === e.source)
      );
      const legacyOverEdge = incomingEdges.find(
        e => ((e.data as any)?.type === "map" || (e.data as any)?.type === "accum") && nodes.some(n => n.id === e.source)
      );
      const overEdge = explicitOverEdge || legacyOverEdge;
      const overSource = overEdge ? resolveEdgeSource(overEdge, nodes) : undefined;
      const contextName =
        (overEdge?.data as any)?.type === "accum" ? ((overEdge?.data as any)?.contextName as string | undefined) : undefined;

      const bindings = incomingEdges
        .filter(e => e !== overEdge || (e.data as any)?.label) // pure array-source edge with no placeholder isn't a prompt binding
        .map(edge => {
          const edgeData: any = edge.data || {};
          const sourceNode = nodes.find(n => n.id === edge.source);
          const isTap = edge !== overEdge && (edgeData.type === "map" || edgeData.type === "accum");

          let source: string;
          if (edgeData.type === "accum" && !sourceNode) {
            // Legacy phantom "context" pseudo-edge from an older import -
            // always rewrite to the live contextName from the array-source
            // edge above, instead of trusting whatever name was baked in
            // when it was created.
            const legacyField = ((edgeData.source as string) || "").startsWith("context.")
              ? (edgeData.source as string).slice("context.".length)
              : undefined;
            source = `context.${contextName || legacyField || ""}`;
          } else if (edgeData.type === "map" && !sourceNode) {
            // Legacy phantom "item" pseudo-edge from an older import.
            const legacyField = ((edgeData.source as string) || "").startsWith("item.")
              ? (edgeData.source as string).slice("item.".length)
              : undefined;
            source = legacyField ? `item.${legacyField}` : "item";
          } else if (isTap && edgeData.type === "accum") {
            // Secondary accum-typed edge attached to the real producing
            // node - still just re-exposes the same accumulated context.
            source = `context.${contextName || ""}`;
          } else if (isTap && edgeData.type === "map") {
            // Secondary map-typed edge attached to the real producing
            // node (the one this stage loops over) - pulls the current
            // loop item, or one field of it, not the whole array.
            source = edgeData.itemField ? `item.${edgeData.itemField}` : "item";
          } else {
            source = resolveEdgeSource(edge, nodes);
          }

          return {
            placeholder: (edgeData.label as string) || "",
            source,
            format: (edgeData.format as string) !== "text" ? (edgeData.format as "text" | "json") : undefined
          };
        });

      const stageObj: any = {
        id: node.id,
        type: "llm",
        execution: data.execution || "single",
        prompt: data.prompt,
        bindings: bindings.length > 0 ? bindings : undefined,
        response: data.response,
        outputs: data.outputs,
        model: data.model,
        failure: data.failure
      };

      if (data.execution !== "single") {
        stageObj.map = {
          ...data.map,
          over: overSource || data.map?.over
        };
        if (data.execution === "map_with_context") {
          stageObj.map.context_name = contextName || data.map?.context_name;
        }
      }

      return stageObj;
    });

    const pipelineObj = {
      version: 1,
      id: pipelineId.trim(),
      name: pipelineName.trim(),
      description: pipelineDesc.trim() || undefined,
      inputs,
      stages
    };

    return stringifyYaml(pipelineObj);
  };

  // Parse YAML string and construct the Flow Nodes & Edges layout
  const importYamlToGraph = (yamlString: string) => {
    try {
      const doc = parseYaml(yamlString);
      if (!doc || doc.version !== 1) {
        throw new Error("Only version: 1 prompt pipelines are supported.");
      }

      setPipelineId(doc.id || "pipeline_id");
      setPipelineName(doc.name || "Imported Pipeline");
      setPipelineDesc(doc.description || "");

      const newNodes: Node[] = [];
      const newEdges: Edge[] = [];

      // 1. Create Input Nodes
      const inputs = doc.inputs || {};
      Object.entries(inputs).forEach(([name, spec]: [string, any], index) => {
        newNodes.push({
          id: `inputs.${name}`,
          type: "inputNode",
          position: { x: 50, y: 100 + index * 140 },
          data: {
            id: name,
            inputType: spec?.type || "text",
            required: spec?.required !== false,
            default: spec?.default,
            onDelete: deleteStageNode
          }
        });
      });

      // 2. Create Stage Nodes
      const stages = doc.stages || [];
      stages.forEach((stage: any, index: number) => {
        newNodes.push({
          id: stage.id,
          type: "promptNode",
          position: { x: 300 + index * 260, y: 150 },
          data: {
            id: stage.id,
            execution: stage.execution || "single",
            map: stage.map,
            prompt: stage.prompt || { source: "inline", text: "" },
            response: stage.response || { kind: "text" },
            outputs: stage.outputs || {},
            runMode: "run",
            mockOutput: "",
            model: stage.model,
            failure: stage.failure,
            onDelete: deleteStageNode
          }
        });

        // Counts existing edges between a given (source, target) pair among
        // the edges built so far in this import, so duplicates fan out
        // visually instead of drawing as one fully-overlapping curve.
        const laneIndexFor = (sourceId: string, targetId: string) =>
          newEdges.filter(e => e.source === sourceId && e.target === targetId).length;

        // Create the real "array to loop over" edge from map.over - this
        // used to be a free-text field on the stage with no graph
        // representation at all. It's typed "accum" (not "map") whenever the
        // stage accumulates its own output across iterations, so the
        // dedicated "map with accumulation" styling actually shows up on it,
        // and it carries context_name directly (no separate self-loop needed).
        if (stage.execution !== "single" && stage.map) {
          const overSource: string = stage.map.over || "";
          if (overSource && !(overSource === "item" || overSource.startsWith("item.") || overSource.startsWith("context."))) {
            const parts = overSource.split(".");
            const overSourceNodeId = overSource.startsWith("inputs.") ? `inputs.${parts[1]}` : parts[0];
            const overOutputField = overSource.startsWith("inputs.") ? undefined : parts.slice(1).join(".") || undefined;
            const isAccum = stage.execution === "map_with_context";
            newEdges.push({
              id: `e-map-over-${overSourceNodeId}-${stage.id}-${Date.now()}`,
              source: overSourceNodeId,
              target: stage.id,
              type: "pipelineEdge",
              markerEnd: { type: MarkerType.ArrowClosed, color: isAccum ? "var(--accum-edge)" : "var(--map-edge)" },
              data: {
                type: isAccum ? "accum" : "map",
                label: "",
                outputField: overOutputField,
                contextName: isAccum ? stage.map.context_name : undefined,
                isOverSource: true,
                laneIndex: laneIndexFor(overSourceNodeId, stage.id)
              }
            });
          }
        }

        // The current map item (and, for map_with_context, the accumulated
        // context) always comes from the same node this stage loops over
        // (stage.map.over) - never a standalone source. Resolve that real
        // node id once so item/context bindings below attach to it instead
        // of a phantom "item"/"context" node with no place on the canvas.
        const overSource: string = stage.map?.over || "";
        const overSourceNodeId =
          overSource && !(overSource === "item" || overSource.startsWith("item.") || overSource.startsWith("context."))
            ? (overSource.startsWith("inputs.") ? `inputs.${overSource.split(".")[1]}` : overSource.split(".")[0])
            : undefined;

        // Create Edges from bindings
        const bindings = stage.bindings || [];
        bindings.forEach((binding: any, bIdx: number) => {
          const source = binding.source || "";
          let sourceNodeId = "";
          let outputField: string | undefined;
          let itemField: string | undefined;

          if (source.startsWith("inputs.")) {
            // e.g. inputs.topic -> source is node inputs.topic
            const inputKey = source.split(".")[1];
            sourceNodeId = `inputs.${inputKey}`;
          } else if (source === "item" || source.startsWith("item.")) {
            // Attach to the real node producing the loop's array so this
            // shows up as a normal, editable edge instead of a dangling
            // reference to a node that doesn't exist on the canvas.
            sourceNodeId = overSourceNodeId || "item";
            itemField = source.startsWith("item.") ? source.slice("item.".length) : undefined;
          } else if (source.startsWith("context.")) {
            sourceNodeId = overSourceNodeId || "context";
          } else {
            // e.g. architect.blueprint -> source node is architect, field is blueprint
            const parts = source.split(".");
            sourceNodeId = parts[0];
            outputField = parts.slice(1).join(".") || undefined;
          }

          // Verify source node exists
          if (sourceNodeId) {
            let edgeType: "normal" | "map" | "accum" = "normal";
            if (stage.execution !== "single" && (source === "item" || source.startsWith("item."))) {
              edgeType = "map";
            } else if (stage.execution === "map_with_context" && source.startsWith("context.")) {
              edgeType = "accum";
            }

            newEdges.push({
              id: `e-${sourceNodeId}-${stage.id}-${bIdx}-${Date.now()}`,
              source: sourceNodeId,
              target: stage.id,
              type: "pipelineEdge",
              markerEnd: {
                type: MarkerType.ArrowClosed,
                color: "var(--normal-edge)",
              },
              data: {
                type: edgeType,
                label: binding.placeholder,
                source: binding.source,
                outputField,
                itemField,
                // The binding-derived edges are always taps on the loop's
                // array-source node - the primary "Array to Loop Over" edge
                // is created separately above (from stage.map.over) and is
                // the only one ever marked isOverSource: true.
                isOverSource: false,
                format: binding.format || "text",
                laneIndex: laneIndexFor(sourceNodeId, stage.id)
              }
            });
          }
        });
      });

      // Apply DAG auto positioning layout
      const layedOut = layoutPipelineNodes(newNodes, newEdges);
      setNodes(layedOut);
      setEdges(newEdges);
      setSelectedNode(null);
      setSelectedEdge(null);
    } catch (err) {
      alert(`YAML Import Error: ${(err as Error).message}`);
    }
  };

  // --- Backend operations ---
  const handleSaveToBackend = async () => {
    try {
      const yamlContent = compileGraphToYaml();
      await savePipeline(pipelineId, yamlContent, token);
      alert(`Pipeline ${pipelineId} saved to server successfully!`);
      void fetchBackendLists();
    } catch (err) {
      alert(`Save Failed: ${(err as Error).message}`);
    }
  };

  const handleLoadPipeline = async (pipeId: string) => {
    try {
      const yamlContent = await getPipeline(pipeId, token);
      importYamlToGraph(yamlContent);
      setShowLoadModal(false);
    } catch (err) {
      alert(`Load Failed: ${(err as Error).message}`);
    }
  };

  const handleApplyTemplate = (yamlContent: string) => {
    importYamlToGraph(yamlContent);
    setShowTemplateModal(false);
  };

  const handleRunPipeline = async () => {
    try {
      const yamlContent = compileGraphToYaml();
      
      // Determine subset of nodes to run
      const runStages = nodes
        .filter(n => n.type === "promptNode" && (n.data as any).runMode === "run")
        .map(n => n.id);

      if (runStages.length === 0) {
        alert("Please toggle at least one prompt stage to 'Execute Stage' to run.");
        return;
      }

      // Compile mock outputs for stubbed nodes
      const mockOutputs: Record<string, any> = {};
      nodes
        .filter(n => n.type === "promptNode" && (n.data as any).runMode === "mock")
        .forEach(n => {
          const nodeData = n.data as any;
          const rawMock = (nodeData.mockOutput as string) || "";
          try {
            // Attempt to parse JSON if possible, otherwise treat as plain text
            mockOutputs[n.id] = JSON.parse(rawMock);
          } catch {
            mockOutputs[n.id] = rawMock;
          }
        });

      // Runtime input values come from each Input node's own "Value" field -
      // this is the graph's single source of truth; nothing here is
      // hardcoded to specific input names anymore.
      const inputs: Record<string, any> = {};
      nodes
        .filter(n => n.type === "inputNode")
        .forEach(n => {
          const nodeData = n.data as any;
          const name = (nodeData?.id as string) || n.id;
          const raw = nodeData?.value !== undefined && nodeData?.value !== "" ? nodeData.value : nodeData?.default;
          if (raw === undefined) return;
          inputs[name] = parseInputValue(raw, nodeData?.inputType);
        });

      setRunLogs({ status: "running", message: "Executing pipeline stages on server..." });
      setShowRunResults(true);

      const res = await runPipeline({
        pipeline_yaml: yamlContent,
        inputs,
        run_stages: runStages,
        mock_outputs: mockOutputs
      }, token);

      setRunLogs(res);
      void fetchBackendLists();
    } catch (err) {
      setRunLogs({ status: "failed", error: (err as Error).message });
    }
  };

  return (
    <div className="workspace-root">
      
      {/* Canvas Toolbars */}
      <div className="canvas-toolbar">
        <button className="toolbar-btn" onClick={() => void fetchBackendLists().then(() => setShowLoadModal(true))} title="Load Saved Pipelines">
          <FolderOpen size={16} />
        </button>
        <button className="toolbar-btn" onClick={handleSaveToBackend} title="Save to Backend">
          <Save size={16} />
        </button>
        <button className="toolbar-btn" onClick={() => void fetchBackendLists().then(() => setShowTemplateModal(true))} title="Templates">
          <BookOpen size={16} />
        </button>
        <div className="toolbar-divider" />
        <button className="toolbar-btn" onClick={() => {
          if (confirm("Reset current workspace?")) {
            loadDefaultStandardFlow();
          }
        }} title="Reset standard pipeline">
          <RotateCcw size={16} />
        </button>
        <button className="toolbar-btn" onClick={() => {
          const sorted = layoutPipelineNodes(nodes, edges);
          setNodes(sorted);
        }} title="Auto layout stages">
          <Sparkles size={16} />
        </button>
      </div>

      {/* Main Drag and Drop Canvas */}
      <PipelineCanvas
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        setNodes={setNodes}
        setEdges={setEdges}
        onSelectNode={setSelectedNode}
        onSelectEdge={setSelectedEdge}
      />

      {/* Pipeline configuration pane (Input forms & executing panel) */}
      <SidebarNodeProps
        selectedNode={selectedNode}
        selectedEdge={selectedEdge}
        nodes={nodes}
        edges={edges}
        promptTemplates={promptTemplates}
        onUpdateNode={handleUpdateNode}
        onUpdateEdge={handleUpdateEdge}
        onDeleteEdge={handleDeleteEdge}
        onChangeNodeType={handleChangeNodeType}
        onClose={() => {
          setSelectedNode(null);
          setSelectedEdge(null);
        }}
        onDeleteNode={deleteStageNode}
        onRunPipeline={handleRunPipeline}
        pipelineId={pipelineId}
        setPipelineId={setPipelineId}
        pipelineName={pipelineName}
        setPipelineName={setPipelineName}
        pipelineDesc={pipelineDesc}
        setPipelineDesc={setPipelineDesc}
        compileGraphToYaml={compileGraphToYaml}
        importYamlToGraph={importYamlToGraph}
      />

      {/* Load Pipeline Modal */}
      {showLoadModal && (
        <div className="modal-backdrop" onClick={() => setShowLoadModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Load Pipeline</h3>
              <button className="toolbar-btn" onClick={() => setShowLoadModal(false)}><X size={16} /></button>
            </div>
            <div className="modal-body">
              {pipelinesList.length === 0 ? (
                <p style={{ color: "#64748b", textAlign: "center" }}>No custom pipelines saved on backend.</p>
              ) : (
                pipelinesList.map(p => (
                  <div key={p.id} className="list-item" onClick={() => handleLoadPipeline(p.id)}>
                    <div>
                      <span className="list-item-title">{p.name || p.id}</span>
                      <div className="list-item-subtitle">{p.description || "No description"}</div>
                    </div>
                    <ChevronRight size={16} />
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Templates Modal */}
      {showTemplateModal && (
        <div className="modal-backdrop" onClick={() => setShowTemplateModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Select Pipeline Template</h3>
              <button className="toolbar-btn" onClick={() => setShowTemplateModal(false)}><X size={16} /></button>
            </div>
            <div className="modal-body">
              {templatesList.length === 0 ? (
                <p style={{ color: "#64748b", textAlign: "center" }}>No default templates found on backend.</p>
              ) : (
                templatesList.map(t => (
                  <div key={t.id} className="list-item" onClick={() => handleApplyTemplate(t.yaml)}>
                    <div>
                      <span className="list-item-title">{t.name}</span>
                      <div className="list-item-subtitle">{t.description || "Flow diagram template"}</div>
                    </div>
                    <ChevronRight size={16} />
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Run Results Console overlay */}
      {showRunResults && (
        <div className="modal-backdrop" onClick={() => setShowRunResults(false)}>
          <div className="modal-content" style={{ width: "640px" }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Execution Results</h3>
              <button className="toolbar-btn" onClick={() => setShowRunResults(false)}><X size={16} /></button>
            </div>
            <div className="modal-body" style={{ background: "#090d16" }}>
              {!runLogs ? (
                <p style={{ color: "#64748b" }}>Preparing stage variables...</p>
              ) : runLogs.status === "running" ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "2rem", gap: "1rem" }}>
                  <RotateCcw className="edge-badge map" style={{ animation: "spin 1.5s linear infinite" }} />
                  <p>{runLogs.message}</p>
                </div>
              ) : runLogs.status === "failed" ? (
                <div style={{ padding: "1rem", color: "#f87171", border: "1px solid rgba(239, 68, 68, 0.3)", background: "rgba(239, 68, 68, 0.05)", borderRadius: 6 }}>
                  <strong>Execution Failed:</strong>
                  <pre style={{ margin: "0.5rem 0 0 0", fontFamily: "JetBrains Mono", fontSize: "0.75rem" }}>{runLogs.error}</pre>
                </div>
              ) : (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
                    <span>Status: <strong style={{ color: "#10b981" }}>Success</strong></span>
                    <span>Run ID: <strong>{runLogs.run_id}</strong></span>
                  </div>
                  
                  <h4 style={{ margin: "0 0 0.5rem 0", fontSize: "0.85rem", color: "#cbd5e1" }}>Outputs generated:</h4>
                  {Object.entries(runLogs.outputs || {}).map(([stage, outputObj]: [string, any]) => {
                    const keys = Object.keys(outputObj);
                    return (
                      <div key={stage} style={{ marginBottom: "0.75rem", border: "1px solid var(--border-color)", borderRadius: 6, padding: "0.5rem", background: "rgba(255,255,255,0.02)" }}>
                        <div style={{ fontWeight: 600, fontSize: "0.8rem", marginBottom: "0.25rem", color: "#f8fafc" }}>
                          Stage: {stage}
                        </div>
                        {keys.map(k => {
                          const val = outputObj[k];
                          const strVal = typeof val === "string" ? val : JSON.stringify(val, null, 2);
                          return (
                            <div key={k} style={{ marginTop: "0.25rem" }}>
                              <div style={{ fontSize: "0.7rem", color: "#94a3b8" }}>Key: {k}</div>
                              <pre style={{
                                margin: "0.25rem 0 0 0",
                                padding: "0.4rem",
                                background: "#030712",
                                border: "1px solid rgba(255,255,255,0.05)",
                                borderRadius: 4,
                                fontSize: "0.7rem",
                                overflowX: "auto",
                                maxHeight: "120px",
                                fontFamily: "JetBrains Mono"
                              }}>{strVal}</pre>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowRunResults(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* CSS Spin Animation rule */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>

    </div>
  );
}
