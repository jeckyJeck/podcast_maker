export type ExecutionMode = "single" | "map" | "map_with_context";
export type PromptSourceType = "inline" | "file" | "template";
export type ResponseKind = "text" | "json";

export interface PipelinePrompt {
  source: PromptSourceType;
  text?: string;
  path?: string;
  template_id?: string;
  revision?: string;
}

export interface PipelineBinding {
  placeholder: string;
  source: string;
  format?: "text" | "json";
}

export interface PipelineMapConfig {
  over: string;
  item_name: string;
  context_name?: string;
  context_strategy?: string;
}

export interface PipelineResponseConfig {
  kind: ResponseKind;
  file?: string;
  per_item_file?: string;
  aggregate_file?: string;
  aggregate_strategy?: string;
  schema?: string;
}

export interface PipelineOutputSpec {
  source: string;
}

export interface PipelineStage {
  id: string;
  type: "llm";
  execution: ExecutionMode;
  map?: PipelineMapConfig;
  prompt: PipelinePrompt;
  bindings?: PipelineBinding[];
  response: PipelineResponseConfig;
  outputs: Record<string, PipelineOutputSpec>;
  model?: {
    provider?: string;
    name?: string;
  };
  failure?: {
    strategy?: "abort" | "retry" | "skip";
    max_attempts?: number;
  };
}

export interface PipelineInputSpec {
  type: "text" | "json" | "number" | "boolean";
  required?: boolean;
  default?: any;
}

export interface PipelineConfig {
  version: number;
  id: string;
  name?: string;
  description?: string;
  defaults?: {
    model?: {
      provider?: string;
      name?: string;
    };
    failure?: {
      strategy?: string;
      max_attempts?: number;
    };
  };
  inputs: Record<string, PipelineInputSpec>;
  stages: PipelineStage[];
}

export interface RunListItem {
  run_id: string;
  run_directory: string;
  has_manifest: boolean;
  topic: string | null;
  stages: string[];
  created_at_utc: string | null;
}

export interface RunDetails {
  run_id: string;
  run_directory: string;
  files: string[];
  manifest: any | null;
}
