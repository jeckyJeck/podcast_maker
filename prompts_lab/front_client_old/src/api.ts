import type {
  DefaultsResponse,
  MetaResponse,
  PromptTemplate,
  PromptTemplateCreateRequest,
  PromptTemplateUpdateRequest,
  RunDetails,
  RunListItem,
  StageName
} from "./types";

const API_BASE = import.meta.env.VITE_PROMPTS_TEST_API_BASE ?? "";

function summarizeApiError(responseText: string): string {
  const MAX_LEN = 800;

  try {
    const parsed = JSON.parse(responseText) as { detail?: unknown; message?: unknown };
    const detail = parsed.detail ?? parsed.message;
    if (typeof detail === "string") {
      return detail.length > MAX_LEN ? `${detail.slice(0, MAX_LEN)}... [truncated]` : detail;
    }
    if (Array.isArray(detail)) {
      const joined = detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object") {
            const entry = item as { msg?: unknown; loc?: unknown[] };
            const msg = typeof entry.msg === "string" ? entry.msg : JSON.stringify(item);
            const loc = Array.isArray(entry.loc) ? entry.loc.join(".") : "";
            return loc ? `${loc}: ${msg}` : msg;
          }
          return String(item);
        })
        .join(" | ");
      return joined.length > MAX_LEN ? `${joined.slice(0, MAX_LEN)}... [truncated]` : joined;
    }
  } catch {
    // Fall back to raw text handling.
  }

  if (!responseText.trim()) return "Unknown server error";
  return responseText.length > MAX_LEN ? `${responseText.slice(0, MAX_LEN)}... [truncated]` : responseText;
}

async function apiFetch<T>(path: string, init?: RequestInit, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined)
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${summarizeApiError(text)}`);
  }

  return (await response.json()) as T;
}

export function getMeta(token?: string) {
  return apiFetch<MetaResponse>("/prompts-test-api/meta", undefined, token);
}

export function getDefaults(
  payload: {
    topic: string;
    format: "dialogue" | "solo";
    host_ids: string[];
    injected: {
      blueprint_json?: unknown;
      research_text?: string;
      outline_json?: unknown;
    };
  },
  token?: string
) {
  return apiFetch<DefaultsResponse>(
    "/prompts-test-api/defaults",
    { method: "POST", body: JSON.stringify(payload) },
    token
  );
}

export async function runStages(
  payload: {
    topic: string;
    format: "dialogue" | "solo";
    host_ids: string[];
    stages: StageName[];
    async_mode: false;
    injected: {
      blueprint_json?: unknown;
      research_text?: string;
      outline_json?: unknown;
    };
    prompt_overrides: {
      architect?: { text: string };
      researcher?: { text: string };
      outliner?: { text: string };
      scriptwriter?: { text: string };
    };
  },
  token?: string
) {
  return apiFetch<{ status: string; result?: { run_id: string } }>(
    "/prompts-test-api/runs",
    { method: "POST", body: JSON.stringify(payload) },
    token
  );
}

export async function getRuns(token?: string): Promise<RunListItem[]> {
  const res = await apiFetch<{ runs: RunListItem[] }>("/prompts-test-api/runs", undefined, token);
  return res.runs;
}

export function getRun(runId: string, token?: string) {
  return apiFetch<RunDetails>(`/prompts-test-api/runs/${encodeURIComponent(runId)}`, undefined, token);
}

export async function getRunFile(runId: string, fileName: string, token?: string): Promise<string> {
  const res = await apiFetch<{ content: string }>(
    `/prompts-test-api/runs/${encodeURIComponent(runId)}/files/${encodeURIComponent(fileName)}`,
    undefined,
    token
  );
  return res.content;
}

export function compareRuns(
  payload: { run_a: string; run_b: string; file_name: string; max_lines: number },
  token?: string
) {
  return apiFetch<{ diff: string }>(
    "/prompts-test-api/compare",
    { method: "POST", body: JSON.stringify(payload) },
    token
  );
}

export async function listPromptTemplates(stage: StageName, token?: string): Promise<PromptTemplate[]> {
  const params = new URLSearchParams({ stage });
  const res = await apiFetch<{ templates: PromptTemplate[] }>(
    `/prompts-test-api/prompt-templates?${params.toString()}`,
    undefined,
    token
  );
  return res.templates;
}

export function createPromptTemplate(payload: PromptTemplateCreateRequest, token?: string) {
  return apiFetch<PromptTemplate>(
    "/prompts-test-api/prompt-templates",
    { method: "POST", body: JSON.stringify(payload) },
    token
  );
}

export function updatePromptTemplate(
  templateId: string,
  payload: PromptTemplateUpdateRequest,
  token?: string
) {
  return apiFetch<PromptTemplate>(
    `/prompts-test-api/prompt-templates/${encodeURIComponent(templateId)}`,
    { method: "PUT", body: JSON.stringify(payload) },
    token
  );
}

export function deletePromptTemplate(templateId: string, token?: string) {
  return apiFetch<{ status: string; id: string }>(
    `/prompts-test-api/prompt-templates/${encodeURIComponent(templateId)}`,
    { method: "DELETE" },
    token
  );
}
