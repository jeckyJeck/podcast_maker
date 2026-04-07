export type StageName = "architect" | "researcher" | "outliner" | "scriptwriter";

export interface HostOption {
  id: string;
  name: string;
  tone: string;
  role: string;
  gender: string;
}

export interface MetaResponse {
  formats: Array<"dialogue" | "solo">;
  stages: StageName[];
  default_host_ids: string[];
  default_topic: string;
  hosts: HostOption[];
  default_runs_root: string;
}

export interface RunListItem {
  run_id: string;
  run_directory: string;
  has_manifest: boolean;
  topic: string | null;
  stages: StageName[];
  created_at_utc: string | null;
}

export interface RunDetails {
  run_id: string;
  run_directory: string;
  files: string[];
  manifest: Record<string, unknown> | null;
}

export interface DefaultsResponse {
  topic: string;
  format: "dialogue" | "solo";
  host_ids: string[];
  prompts: Record<StageName, string>;
  outputs: Record<StageName, string>;
}

export interface PromptTemplate {
  id: string;
  user_id: string;
  stage: StageName;
  name: string;
  prompt_text: string;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface PromptTemplateCreateRequest {
  stage: StageName;
  name: string;
  prompt_text: string;
}

export interface PromptTemplateUpdateRequest {
  name?: string;
  prompt_text?: string;
}
