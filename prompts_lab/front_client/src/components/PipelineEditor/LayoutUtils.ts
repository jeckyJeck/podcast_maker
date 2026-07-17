import { Node, Edge } from "@xyflow/react";

/**
 * Computes topological layout positioning for nodes in a DAG dependency structure.
 * Places nodes in columns based on their maximum dependency depth.
 */
export function layoutPipelineNodes(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return [];

  // Build adjacency list for incoming edges
  const parentMap = new Map<string, string[]>();
  nodes.forEach(node => parentMap.set(node.id, []));
  
  edges.forEach(edge => {
    const targets = parentMap.get(edge.target);
    if (targets) {
      targets.push(edge.source);
    }
  });

  // Memoization map for computed depths
  const depthCache = new Map<string, number>();
  
  // Track visiting to detect circular loops
  const visiting = new Set<string>();

  function getDepth(nodeId: string): number {
    if (depthCache.has(nodeId)) {
      return depthCache.get(nodeId)!;
    }
    
    if (visiting.has(nodeId)) {
      // Circular dependency detected, return 0 to break loop
      return 0;
    }

    visiting.add(nodeId);
    const parents = parentMap.get(nodeId) || [];
    
    let maxParentDepth = -1;
    parents.forEach(parent => {
      maxParentDepth = Math.max(maxParentDepth, getDepth(parent));
    });
    
    visiting.delete(nodeId);
    const depth = maxParentDepth + 1;
    depthCache.set(nodeId, depth);
    return depth;
  }

  // Calculate depths for all nodes
  const nodeDepths = nodes.map(node => ({
    node,
    depth: getDepth(node.id)
  }));

  // Group nodes by depth
  const depthGroups = new Map<number, Node[]>();
  nodeDepths.forEach(({ node, depth }) => {
    if (!depthGroups.has(depth)) {
      depthGroups.set(depth, []);
    }
    depthGroups.get(depth)!.push(node);
  });

  // Layout parameters
  const columnWidth = 320;
  const rowHeight = 160;
  const startX = 60;
  const startY = 100;

  // Assign coordinates based on groups
  const layedOutNodes: Node[] = [];
  depthGroups.forEach((groupNodes, depth) => {
    groupNodes.forEach((node, index) => {
      layedOutNodes.push({
        ...node,
        position: {
          x: startX + depth * columnWidth,
          y: startY + index * rowHeight
        }
      });
    });
  });

  return layedOutNodes;
}
