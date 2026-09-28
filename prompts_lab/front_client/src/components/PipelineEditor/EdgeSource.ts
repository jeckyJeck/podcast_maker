import { Edge, Node } from "@xyflow/react";

// Resolves an edge's binding source live from the current graph, instead of
// trusting a string baked in when the edge was drawn - the same node/field
// lookup used for normal bindings, the map "over" array reference, and the
// sidebar's read-only status display.
export function resolveEdgeSource(edge: Edge, nodes: Node[]): string {
  const sourceNode = nodes.find(n => n.id === edge.source);
  const edgeData: any = edge.data || {};
  if (sourceNode?.type === "inputNode") {
    return `inputs.${(sourceNode.data as any)?.id ?? edge.source}`;
  }
  if (sourceNode) {
    const outputField =
      edgeData.outputField ||
      Object.keys((sourceNode.data as any)?.outputs || {})[0] ||
      "response";
    return `${sourceNode.id}.${outputField}`;
  }
  return (edgeData.source as string) || "";
}

// Coerces an Input node's raw (always string, from the sidebar textbox)
// value/default into the shape its declared type implies for the run payload.
export function parseInputValue(raw: any, inputType?: string): any {
  if (typeof raw !== "string") return raw;
  switch (inputType) {
    case "number": {
      const n = Number(raw);
      return Number.isNaN(n) ? raw : n;
    }
    case "boolean":
      return raw === "true";
    case "json":
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    default:
      return raw;
  }
}
