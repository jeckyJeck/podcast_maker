import { Node, Edge } from "@xyflow/react";

const WORKSPACE_KEY = "prompts_lab_pipeline_workspace";

export interface SavedWorkspace {
  nodes: Node[];
  edges: Edge[];
  inputs: Record<string, { type: "text" | "json" | "number" | "boolean"; required?: boolean; default?: any }>;
  metadata: {
    id: string;
    name: string;
    description: string;
  };
}

export function saveWorkspace(data: SavedWorkspace) {
  try {
    localStorage.setItem(WORKSPACE_KEY, JSON.stringify(data));
  } catch (err) {
    console.error("Failed to save pipeline workspace:", err);
  }
}

export function loadWorkspace(): SavedWorkspace | null {
  try {
    const raw = localStorage.getItem(WORKSPACE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SavedWorkspace;
  } catch (err) {
    console.error("Failed to load pipeline workspace:", err);
    return null;
  }
}

export function clearWorkspace() {
  localStorage.removeItem(WORKSPACE_KEY);
}
