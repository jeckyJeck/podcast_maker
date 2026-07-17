import type { RunDetails, RunListItem } from "../types";

const API_BASE = import.meta.env.VITE_PROMPTS_TEST_API_BASE ?? "";

function summarizeApiError(responseText: string): string {
  const MAX_LEN = 800;
  try {
    const parsed = JSON.parse(responseText) as { detail?: unknown; message?: unknown };
    const detail = parsed.detail ?? parsed.message;
    if (typeof detail === "string") {
      return detail.length > MAX_LEN ? `${detail.slice(0, MAX_LEN)}...` : detail;
    }
    if (Array.isArray(detail)) {
      return detail.map(item => typeof item === "string" ? item : JSON.stringify(item)).join(" | ");
    }
  } catch {
    // ignore JSON parse errors
  }
  return responseText.length > MAX_LEN ? `${responseText.slice(0, MAX_LEN)}...` : responseText || "Unknown server error";
}

async function apiFetch<T>(path: string, init?: RequestInit, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined)
  };

  if (!(init?.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${summarizeApiError(text)}`);
  }

  // Handle plain text response (e.g. raw YAML)
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("yaml") || contentType.includes("text/plain")) {
    return (await response.text()) as unknown as T;
  }

  return (await response.json()) as T;
}

export function getMeta(token?: string) {
  return apiFetch<any>("/prompts-test-api/meta", undefined, token);
}

// Pipelines CRUD
export function getPipelines(token?: string) {
  return apiFetch<{ pipelines: Array<{ id: string; name: string; description: string; version: number }> }>(
    "/prompts-test-api/pipelines",
    undefined,
    token
  );
}

export function getPipeline(pipelineId: string, token?: string) {
  return apiFetch<string>(
    `/prompts-test-api/pipelines/${encodeURIComponent(pipelineId)}`,
    undefined,
    token
  );
}

export function savePipeline(pipelineId: string, yamlContent: string, token?: string) {
  return apiFetch<{ status: string; id: string }>(
    `/prompts-test-api/pipelines/${encodeURIComponent(pipelineId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: yamlContent
    },
    token
  );
}

export function deletePipeline(pipelineId: string, token?: string) {
  return apiFetch<{ status: string; id: string }>(
    `/prompts-test-api/pipelines/${encodeURIComponent(pipelineId)}`,
    { method: "DELETE" },
    token
  );
}

export function getPipelineTemplates(token?: string) {
  return apiFetch<{ templates: Array<{ id: string; name: string; description: string; yaml: string }> }>(
    "/prompts-test-api/pipeline-templates",
    undefined,
    token
  );
}

export function runPipeline(
  payload: {
    pipeline_yaml: string;
    inputs: Record<string, any>;
    run_stages?: string[];
    mock_outputs?: Record<string, any>;
  },
  token?: string
) {
  return apiFetch<{ status: string; run_id: string; outputs: Record<string, any>; manifest: any }>(
    "/prompts-test-api/pipelines/run",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    token
  );
}

// Runs history
export function getRuns(token?: string): Promise<RunListItem[]> {
  return apiFetch<{ runs: RunListItem[] }>("/prompts-test-api/runs", undefined, token).then(res => res.runs);
}

export function getRun(runId: string, token?: string) {
  return apiFetch<RunDetails>(`/prompts-test-api/runs/${encodeURIComponent(runId)}`, undefined, token);
}

export function getRunFile(runId: string, fileName: string, token?: string): Promise<string> {
  return apiFetch<{ content: string }>(
    `/prompts-test-api/runs/${encodeURIComponent(runId)}/files/${encodeURIComponent(fileName)}`,
    undefined,
    token
  ).then(res => res.content);
}

// Prompt templates API (for stage prompts)
export function listPromptTemplates(stage: string, token?: string) {
  const params = new URLSearchParams({ stage });
  return apiFetch<{ templates: any[] }>(
    `/prompts-test-api/prompt-templates?${params.toString()}`,
    undefined,
    token
  ).then(res => res.templates);
}
