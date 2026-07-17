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
      let defaultLabel = `{{${params.source}}}`;
      let defaultSource = `${params.source}`;

      if (sourceNode) {
        if (sourceNode.type === "inputNode") {
          // If source is a pipeline input
          const inputName = sourceNode.data.id as string;
          defaultLabel = `{{${inputName}}}`;
          defaultSource = `inputs.${inputName}`;
        } else {
          // If source is another prompt stage, bind to first output
          const outputs = Object.keys(sourceNode.data.outputs || {});
          const firstOutput = outputs[0] || "response";
          defaultLabel = `{{${firstOutput}}}`;
          defaultSource = `${params.source}.${firstOutput}`;
        }
      }

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
          type: "normal",
          label: defaultLabel,
          source: defaultSource,
          format: "text"
        }
      };
      setEdges(eds => addEdge(newEdge, eds));
    },
    [nodes, setEdges]
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
