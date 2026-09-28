import React, { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  Node,
  Edge,
  Connection,
  addEdge,
  MarkerType,
  OnNodesChange,
  OnEdgesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import PromptNode from "./NodeTypes/PromptNode";
import PipelineEdge from "./EdgeTypes/PipelineEdge";

interface PipelineCanvasProps {
  nodes: Node[];
  edges: Edge[];
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>;
  setEdges: React.Dispatch<React.SetStateAction<Edge[]>>;
  onSelectNode: (node: Node | null) => void;
  onSelectEdge: (edge: Edge | null) => void;
}

export default function PipelineCanvas({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  setNodes,
  setEdges,
  onSelectNode,
  onSelectEdge
}: PipelineCanvasProps) {
  
  // Custom Node registration
  const nodeTypes = useMemo(() => ({
    promptNode: PromptNode,
    // input nodes use the standard promptNode wrapper but styled slightly differently in PromptNode
    inputNode: PromptNode 
  }), []);

  // Custom Edge registration
  const edgeTypes = useMemo(() => ({
    pipelineEdge: PipelineEdge
  }), []);

  // Handle link creation via Shift + Drag
  const onConnect = useCallback(
    (params: Connection) => {
      const sourceNode = nodes.find(n => n.id === params.source);
      const targetNode = nodes.find(n => n.id === params.target);
      let defaultLabel = `{{${params.source}}}`;
      // Only the *chosen output field* is recorded here for stage sources.
      // The node/stage identity itself is resolved live at compile time
      // (see compileGraphToYaml) so renames can never leave this stale.
      let outputField: string | undefined;

      if (sourceNode) {
        if (sourceNode.type === "inputNode") {
          const inputName = sourceNode.data.id as string;
          defaultLabel = `{{${inputName}}}`;
        } else {
          // If source is another prompt stage, bind to first output
          const outputs = Object.keys(sourceNode.data.outputs || {});
          outputField = outputs[0] || "response";
          defaultLabel = `{{${outputField}}}`;
        }
      }

      // Default to the array-source connection type when the target stage
      // is a map/map_with_context execution and doesn't have one yet, so
      // drawing the "loop over this" edge doesn't silently fall back to a
      // plain Link that the user has to remember to reclassify by hand.
      // isOverSource is the explicit, single source of truth for which edge
      // defines map.over - never inferred later from "first match in array",
      // since that breaks once a second map-typed edge (an item field tap)
      // exists between the same pair.
      const targetExecution = (targetNode?.data as any)?.execution;
      const existingOverEdge = edges.find(
        e => e.target === params.target && (e.data as any)?.isOverSource === true
      );
      let defaultType: "normal" | "map" | "accum" = "normal";
      let isOverSource = false;
      if (!existingOverEdge && targetExecution === "map") {
        defaultType = "map";
        isOverSource = true;
      } else if (!existingOverEdge && targetExecution === "map_with_context") {
        defaultType = "accum";
        isOverSource = true;
      } else if (
        existingOverEdge &&
        existingOverEdge.source === params.source &&
        (targetExecution === "map" || targetExecution === "map_with_context")
      ) {
        // Same node that already feeds the loop - this new edge is almost
        // certainly meant to pull a field out of the current item, not to
        // bind the whole array again.
        defaultType = "map";
      }

      // Multiple edges between the same two nodes render as an identical,
      // fully-overlapping bezier curve by default - fan them out so an
      // existing binding edge can never visually bury this one (or vice versa).
      const laneIndex = edges.filter(e => e.source === params.source && e.target === params.target).length;

      const newEdge: Edge = {
        ...params,
        id: `e-${params.source}-${params.target}-${Date.now()}`,
        type: "pipelineEdge",
        animated: false,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "var(--normal-edge)",
        },
        data: {
          type: defaultType,
          label: defaultLabel,
          outputField,
          isOverSource,
          format: "text",
          laneIndex
        }
      };
      setEdges(eds => addEdge(newEdge, eds));
    },
    [nodes, edges, setEdges]
  );

  // Canvas selection listeners
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onSelectNode(node);
      onSelectEdge(null);
    },
    [onSelectNode, onSelectEdge]
  );

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      onSelectEdge(edge);
      onSelectNode(null);
    },
    [onSelectEdge, onSelectNode]
  );

  const onPaneClick = useCallback(() => {
    onSelectNode(null);
    onSelectEdge(null);
  }, [onSelectNode, onSelectEdge]);

  // Double click canvas to spawn a new node
  const onDoubleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const reactFlowBounds = event.currentTarget.getBoundingClientRect();
      const position = {
        x: event.clientX - reactFlowBounds.left - 100,
        y: event.clientY - reactFlowBounds.top - 40,
      };

      const nodeId = `stage_${nodes.length + 1}`;
      const newNode: Node = {
        id: nodeId,
        type: "promptNode",
        position,
        data: {
          id: nodeId,
          execution: "single",
          prompt: {
            source: "inline",
            text: "Write your prompt here..."
          },
          response: {
            kind: "text",
            file: `outputs/${nodeId}.txt`
          },
          outputs: {
            result: { source: "response" }
          },
          runMode: "run",
          mockOutput: "",
          onDelete: (idToDelete: string) => {
            setNodes(nds => nds.filter(n => n.id !== idToDelete));
            setEdges(eds => eds.filter(e => e.source !== idToDelete && e.target !== idToDelete));
          }
        }
      };

      setNodes(nds => [...nds, newNode]);
    },
    [nodes, setNodes, setEdges]
  );

  return (
    <div className="canvas-pane" onDoubleClick={onDoubleClick}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        zoomOnDoubleClick={false}
        fitView
      >
        <Controls />
        <Background color="#334155" gap={16} />
      </ReactFlow>
    </div>
  );
}
