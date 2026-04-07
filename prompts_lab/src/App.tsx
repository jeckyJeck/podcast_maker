import { useEffect, useMemo, useState } from "react";
import {
  compareRuns,
  createPromptTemplate,
  deletePromptTemplate,
  getDefaults,
  getMeta,
  getRun,
  getRunFile,
  getRuns,
  listPromptTemplates,
  runStages,
  updatePromptTemplate
} from "./api";
import type { MetaResponse, PromptTemplate, RunListItem, StageName } from "./types";

// ============================================================================
// CONSTANTS
// ============================================================================

const STAGES: StageName[] = ["architect", "researcher", "outliner", "scriptwriter"];

const STAGE_OUTPUT_FILES: Record<StageName, string[]> = {
  architect: ["blueprint.json", "blueprint.snapshot.json"],
  researcher: ["research.md", "research.snapshot.md"],
  outliner: ["outline.json", "outline.snapshot.json"],
  scriptwriter: ["script.txt", "script.snapshot.txt"]
};

const STAGE_PROMPT_FILES: Record<StageName, string> = {
  architect: "prompt_architect.txt",
  researcher: "prompt_researcher.txt",
  outliner: "prompt_outliner.txt",
  scriptwriter: "prompt_scriptwriter.txt"
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function parseJsonCandidate(text: string): unknown | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;

  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const candidate = fenced ? fenced[1].trim() : trimmed;

  try {
    return JSON.parse(candidate);
  } catch {
    return undefined;
  }
}

function parseJsonForSubmission(stage: string, text: string): { value: unknown | undefined; error: string | null } {
  const trimmed = text.trim();
  if (!trimmed) {
    return { value: undefined, error: `${stage} output is empty. Paste valid JSON before running later stages.` };
  }

  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const candidate = fenced ? fenced[1].trim() : trimmed;

  try {
    return { value: JSON.parse(candidate), error: null };
  } catch {
    return {
      value: undefined,
      error: `${stage} output must be valid JSON before running later stages. Remove markdown fences or fix the JSON syntax, then try again.`
    };
  }
}

// ============================================================================
// CUSTOM HOOKS
// ============================================================================

interface AppState {
  token: string;
  meta: MetaResponse | null;
  runs: RunListItem[];
  selectedRun: string;
  compareRunA: string;
  compareRunB: string;
  compareResult: string;
  topic: string;
  format: "dialogue" | "solo";
  hostIds: string[];
  runFlags: Record<StageName, boolean>;
  prompts: Record<StageName, string>;
  outputs: Record<StageName, string>;
  busy: boolean;
  error: string;
  status: string;
  promptTemplates: Record<StageName, PromptTemplate[]>;
  templatePicker: {
    isOpen: boolean;
    stage: StageName | null;
    selectedTemplateId: string;
    draftName: string;
    draftPromptText: string;
    error: string;
    busy: boolean;
  };
}

function useAppState() {
  const [state, setState] = useState<AppState>({
    token: localStorage.getItem("prompts_lab_token") ?? "",
    meta: null,
    runs: [],
    selectedRun: "",
    compareRunA: "",
    compareRunB: "",
    compareResult: "",
    topic: "SQL",
    format: "dialogue",
    hostIds: ["sarah_curious", "mike_expert"],
    runFlags: {
      architect: true,
      researcher: true,
      outliner: true,
      scriptwriter: true
    },
    prompts: {
      architect: "",
      researcher: "",
      outliner: "",
      scriptwriter: ""
    },
    outputs: {
      architect: "",
      researcher: "",
      outliner: "",
      scriptwriter: ""
    },
    busy: false,
    error: "",
    status: "Ready",
    promptTemplates: {
      architect: [],
      researcher: [],
      outliner: [],
      scriptwriter: []
    },
    templatePicker: {
      isOpen: false,
      stage: null,
      selectedTemplateId: "",
      draftName: "",
      draftPromptText: "",
      error: "",
      busy: false
    }
  });

  const updateState = (updates: Partial<AppState>) => {
    setState(prev => ({ ...prev, ...updates }));
  };

  const setTokenAndPersist = (token: string) => {
    localStorage.setItem("prompts_lab_token", token);
    setState(prev => ({ ...prev, token }));
  };

  return { state, updateState, setTokenAndPersist };
}

// ============================================================================
// API OPERATIONS HOOK
// ============================================================================

function useApiOperations(state: AppState, updateState: (updates: Partial<AppState>) => void) {
  const bootstrap = async () => {
    updateState({ busy: true, error: "" });
    try {
      const [metaRes, runsRes] = await Promise.all([getMeta(state.token), getRuns(state.token)]);
      updateState({
        meta: metaRes,
        runs: runsRes,
        topic: metaRes.default_topic,
        format: "dialogue",
        hostIds: metaRes.default_host_ids,
        status: "Loaded defaults"
      });
      await loadDefaults(metaRes.default_topic, "dialogue", metaRes.default_host_ids);
    } catch (e) {
      updateState({
        error: (e as Error).message,
        status: "Failed to initialize"
      });
    } finally {
      updateState({ busy: false });
    }
  };

  const refreshRuns = async () => {
    try {
      const list = await getRuns(state.token);
      updateState({ runs: list });
    } catch (e) {
      updateState({ error: (e as Error).message });
    }
  };

  const loadDefaults = async (
    newTopic = state.topic,
    newFormat = state.format,
    newHostIds = state.hostIds
  ) => {
    updateState({ busy: true, error: "" });
    try {
      const defaults = await getDefaults(
        {
          topic: newTopic,
          format: newFormat,
          host_ids: newHostIds,
          injected: {
            blueprint_json: parseJsonCandidate(state.outputs.architect),
            research_text: state.outputs.researcher || undefined,
            outline_json: parseJsonCandidate(state.outputs.outliner)
          }
        },
        state.token
      );
      updateState({
        prompts: defaults.prompts,
        outputs: defaults.outputs,
        status: "Defaults loaded"
      });
    } catch (e) {
      updateState({
        error: (e as Error).message,
        status: "Defaults failed"
      });
    } finally {
      updateState({ busy: false });
    }
  };

  const loadRun = async (runId: string) => {
    if (!runId) return;
    updateState({ busy: true, error: "" });
    try {
      const details = await getRun(runId, state.token);
      const nextPrompts = { ...state.prompts };
      const nextOutputs = { ...state.outputs };

      for (const stage of STAGES) {
        const promptFile = STAGE_PROMPT_FILES[stage];
        if (details.files.includes(promptFile)) {
          nextPrompts[stage] = await getRunFile(runId, promptFile, state.token);
        }

        const outputCandidate = STAGE_OUTPUT_FILES[stage].find((file) => details.files.includes(file));
        if (outputCandidate) {
          nextOutputs[stage] = await getRunFile(runId, outputCandidate, state.token);
        }
      }

      const manifest = details.manifest as { topic?: string; format?: "dialogue" | "solo"; host_ids?: string[] } | null;
      const updates: Partial<AppState> = {
        prompts: nextPrompts,
        outputs: nextOutputs,
        status: `Loaded run ${runId}`
      };

      if (manifest?.topic) updates.topic = manifest.topic;
      if (manifest?.format === "dialogue" || manifest?.format === "solo") updates.format = manifest.format;
      if (manifest?.host_ids && manifest.host_ids.length > 0) updates.hostIds = manifest.host_ids;

      updateState(updates);
    } catch (e) {
      updateState({
        error: (e as Error).message,
        status: "Run load failed"
      });
    } finally {
      updateState({ busy: false });
    }
  };

  const runSelectedStages = async () => {
    const selectedStages = STAGES.filter((stage) => state.runFlags[stage]);
    if (selectedStages.length === 0) {
      updateState({ error: "Select at least one stage to run." });
      return;
    }

    // Validation checks
    const needsBlueprintFromEditor = !state.runFlags.architect && selectedStages.some((stage) => stage === "researcher" || stage === "outliner");
    if (needsBlueprintFromEditor) {
      const parsedBlueprint = parseJsonForSubmission("Architect", state.outputs.architect);
      if (parsedBlueprint.error) {
        updateState({ error: parsedBlueprint.error, status: "Run blocked" });
        return;
      }
    }

    const needsResearchFromEditor = !state.runFlags.researcher && selectedStages.some((stage) => stage === "outliner" || stage === "scriptwriter");
    if (needsResearchFromEditor && !state.outputs.researcher.trim()) {
      updateState({
        error: "Researcher output is empty. Run researcher first or paste valid research text before running later stages.",
        status: "Run blocked"
      });
      return;
    }

    const needsOutlineFromEditor = !state.runFlags.outliner && selectedStages.includes("scriptwriter");
    if (needsOutlineFromEditor) {
      const parsedOutline = parseJsonForSubmission("Outliner", state.outputs.outliner);
      if (parsedOutline.error) {
        updateState({ error: parsedOutline.error, status: "Run blocked" });
        return;
      }
    }

    updateState({ busy: true, error: "", status: "Running selected stages..." });

    try {
      const injected: { blueprint_json?: unknown; research_text?: string; outline_json?: unknown } = {};
      const bp = parseJsonCandidate(state.outputs.architect);
      const ol = parseJsonCandidate(state.outputs.outliner);
      if (bp) injected.blueprint_json = bp;
      if (state.outputs.researcher.trim()) injected.research_text = state.outputs.researcher;
      if (ol) injected.outline_json = ol;

      const payload = {
        topic: state.topic,
        format: state.format,
        host_ids: state.hostIds,
        stages: selectedStages,
        async_mode: false as const,
        injected,
        prompt_overrides: {
          architect: { text: state.prompts.architect },
          researcher: { text: state.prompts.researcher },
          outliner: { text: state.prompts.outliner },
          scriptwriter: { text: state.prompts.scriptwriter }
        }
      };

      const res = await runStages(payload, state.token);
      const runId = res.result?.run_id;
      if (!runId) {
        throw new Error("Run finished without run_id.");
      }

      await refreshRuns();
      await loadRun(runId);
      updateState({ status: `Completed run ${runId}` });
    } catch (e) {
      updateState({
        error: (e as Error).message,
        status: "Run failed"
      });
    } finally {
      updateState({ busy: false });
    }
  };

  const runCompare = async () => {
    if (!state.compareRunA || !state.compareRunB) {
      updateState({ error: "Select both runs for compare." });
      return;
    }

    updateState({ busy: true, error: "" });
    try {
      const result = await compareRuns(
        { run_a: state.compareRunA, run_b: state.compareRunB, file_name: "research.md", max_lines: 400 },
        state.token
      );
      updateState({
        compareResult: result.diff || "No diff output",
        status: "Compare done"
      });
    } catch (e) {
      updateState({
        error: (e as Error).message,
        status: "Compare failed"
      });
    } finally {
      updateState({ busy: false });
    }
  };

  const openTemplatePicker = async (stage: StageName) => {
    updateState({
      templatePicker: {
        isOpen: true,
        stage,
        selectedTemplateId: "",
        draftName: "",
        draftPromptText: state.prompts[stage],
        error: "",
        busy: true
      }
    });

    try {
      const templates = await listPromptTemplates(stage, state.token);
      updateState({
        promptTemplates: { ...state.promptTemplates, [stage]: templates },
        templatePicker: {
          isOpen: true,
          stage,
          selectedTemplateId: "",
          draftName: "",
          draftPromptText: state.prompts[stage],
          error: "",
          busy: false
        }
      });
    } catch (e) {
      updateState({
        templatePicker: {
          isOpen: true,
          stage,
          selectedTemplateId: "",
          draftName: "",
          draftPromptText: state.prompts[stage],
          error: (e as Error).message,
          busy: false
        }
      });
    }
  };

  const closeTemplatePicker = () => {
    updateState({
      templatePicker: {
        isOpen: false,
        stage: null,
        selectedTemplateId: "",
        draftName: "",
        draftPromptText: "",
        error: "",
        busy: false
      }
    });
  };

  const selectTemplateForPreview = (templateId: string) => {
    const picker = state.templatePicker;
    if (!picker.stage) return;
    const selected = state.promptTemplates[picker.stage].find((template) => template.id === templateId);
    updateState({
      templatePicker: {
        ...picker,
        selectedTemplateId: templateId,
        draftName: selected?.name ?? picker.draftName,
        draftPromptText: selected?.prompt_text ?? picker.draftPromptText,
        error: ""
      }
    });
  };

  const applySelectedTemplate = () => {
    const picker = state.templatePicker;
    if (!picker.stage) return;
    updateState({
      prompts: {
        ...state.prompts,
        [picker.stage]: picker.draftPromptText
      },
      templatePicker: {
        ...picker,
        error: ""
      },
      status: `Applied ${picker.stage} template`
    });
  };

  const createTemplateFromPicker = async () => {
    const picker = state.templatePicker;
    if (!picker.stage) return;
    if (!picker.draftName.trim() || !picker.draftPromptText.trim()) {
      updateState({
        templatePicker: {
          ...picker,
          error: "Template name and prompt text are required."
        }
      });
      return;
    }

    updateState({ templatePicker: { ...picker, busy: true, error: "" } });
    try {
      await createPromptTemplate(
        {
          stage: picker.stage,
          name: picker.draftName,
          prompt_text: picker.draftPromptText
        },
        state.token
      );
      const templates = await listPromptTemplates(picker.stage, state.token);
      updateState({
        promptTemplates: { ...state.promptTemplates, [picker.stage]: templates },
        templatePicker: { ...picker, busy: false, error: "" },
        status: `Saved new ${picker.stage} template`
      });
    } catch (e) {
      updateState({
        templatePicker: {
          ...picker,
          busy: false,
          error: (e as Error).message
        }
      });
    }
  };

  const updateSelectedTemplate = async () => {
    const picker = state.templatePicker;
    if (!picker.stage || !picker.selectedTemplateId) {
      updateState({
        templatePicker: {
          ...picker,
          error: "Select a template to update."
        }
      });
      return;
    }

    updateState({ templatePicker: { ...picker, busy: true, error: "" } });
    try {
      await updatePromptTemplate(
        picker.selectedTemplateId,
        {
          name: picker.draftName,
          prompt_text: picker.draftPromptText
        },
        state.token
      );
      const templates = await listPromptTemplates(picker.stage, state.token);
      updateState({
        promptTemplates: { ...state.promptTemplates, [picker.stage]: templates },
        templatePicker: { ...picker, busy: false, error: "" },
        status: `Updated ${picker.stage} template`
      });
    } catch (e) {
      updateState({
        templatePicker: {
          ...picker,
          busy: false,
          error: (e as Error).message
        }
      });
    }
  };

  const deleteSelectedTemplate = async () => {
    const picker = state.templatePicker;
    if (!picker.stage || !picker.selectedTemplateId) {
      updateState({
        templatePicker: {
          ...picker,
          error: "Select a template to delete."
        }
      });
      return;
    }
    if (!window.confirm("Delete selected template?")) return;

    updateState({ templatePicker: { ...picker, busy: true, error: "" } });
    try {
      await deletePromptTemplate(picker.selectedTemplateId, state.token);
      const templates = await listPromptTemplates(picker.stage, state.token);
      updateState({
        promptTemplates: { ...state.promptTemplates, [picker.stage]: templates },
        templatePicker: {
          ...picker,
          selectedTemplateId: "",
          draftName: "",
          draftPromptText: state.prompts[picker.stage],
          busy: false,
          error: ""
        },
        status: `Deleted ${picker.stage} template`
      });
    } catch (e) {
      updateState({
        templatePicker: {
          ...picker,
          busy: false,
          error: (e as Error).message
        }
      });
    }
  };

  return {
    bootstrap,
    refreshRuns,
    loadDefaults,
    loadRun,
    runSelectedStages,
    runCompare,
    openTemplatePicker,
    closeTemplatePicker,
    selectTemplateForPreview,
    applySelectedTemplate,
    createTemplateFromPicker,
    updateSelectedTemplate,
    deleteSelectedTemplate
  };
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

interface TokenPanelProps {
  token: string;
  onTokenChange: (token: string) => void;
  onReloadMeta: () => void;
  onLoadDefaults: () => void;
  onRunSelected: () => void;
  busy: boolean;
}

function TokenPanel({
  token,
  onTokenChange,
  onReloadMeta,
  onLoadDefaults,
  onRunSelected,
  busy
}: TokenPanelProps) {
  return (
    <section className="panel grid-2">
      <label className="field token-field">
        <span>Supabase Bearer Token (dev)</span>
        <input
          type="password"
          value={token}
          onChange={(event) => onTokenChange(event.target.value)}
          placeholder="Paste JWT token"
        />
      </label>
      <div className="actions">
        <button onClick={onReloadMeta} disabled={busy}>Reload Meta</button>
        <button onClick={onLoadDefaults} disabled={busy}>Load Defaults</button>
        <button className="primary" onClick={onRunSelected} disabled={busy}>Run Selected</button>
      </div>
    </section>
  );
}

interface ConfigPanelProps {
  format: "dialogue" | "solo";
  topic: string;
  hostIds: string[];
  meta: MetaResponse | null;
  onFormatChange: (format: "dialogue" | "solo") => void;
  onTopicChange: (topic: string) => void;
  onHostsChange: (hostIds: string[]) => void;
  busy: boolean;
}

function ConfigPanel({
  format,
  topic,
  hostIds,
  meta,
  onFormatChange,
  onTopicChange,
  onHostsChange,
  busy
}: ConfigPanelProps) {
  return (
    <section className="panel grid-3">
      <label className="field">
        <span>Format</span>
        <select
          value={format}
          onChange={(event) => onFormatChange(event.target.value as "dialogue" | "solo")}
          disabled={busy}
        >
          <option value="dialogue">dialogue</option>
          <option value="solo">solo</option>
        </select>
      </label>

      <label className="field">
        <span>Topic</span>
        <input
          value={topic}
          onChange={(event) => onTopicChange(event.target.value)}
          disabled={busy}
        />
      </label>

      <label className="field">
        <span>Hosts</span>
        <select
          multiple
          value={hostIds}
          onChange={(event) => {
            const values = Array.from(event.target.selectedOptions).map((option) => option.value);
            onHostsChange(values);
          }}
          disabled={busy}
        >
          {meta?.hosts.map((host) => (
            <option key={host.id} value={host.id}>
              {host.name} ({host.role})
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

interface RunLoaderPanelProps {
  selectedRun: string;
  runOptions: string[];
  onRunSelect: (runId: string) => void;
  onRefresh: () => void;
  onLoad: () => void;
  busy: boolean;
}

function RunLoaderPanel({
  selectedRun,
  runOptions,
  onRunSelect,
  onRefresh,
  onLoad,
  busy
}: RunLoaderPanelProps) {
  return (
    <section className="panel grid-3">
      <label className="field">
        <span>Load Previous Run</span>
        <select value={selectedRun} onChange={(event) => onRunSelect(event.target.value)} disabled={busy}>
          <option value="">Select run...</option>
          {runOptions.map((runId) => (
            <option key={runId} value={runId}>{runId}</option>
          ))}
        </select>
      </label>
      <div className="actions left">
        <button onClick={onRefresh} disabled={busy}>Refresh Runs</button>
        <button onClick={onLoad} disabled={busy || !selectedRun}>Load Run</button>
      </div>
    </section>
  );
}

interface ComparePanelProps {
  compareRunA: string;
  compareRunB: string;
  compareResult: string;
  runOptions: string[];
  onRunAChange: (runId: string) => void;
  onRunBChange: (runId: string) => void;
  onCompare: () => void;
  busy: boolean;
}

function ComparePanel({
  compareRunA,
  compareRunB,
  compareResult,
  runOptions,
  onRunAChange,
  onRunBChange,
  onCompare,
  busy
}: ComparePanelProps) {
  return (
    <section className="panel compare-panel">
      <h2>Quick Compare</h2>
      <div className="grid-3">
        <label className="field">
          <span>Run A</span>
          <select
            value={compareRunA}
            onChange={(event) => onRunAChange(event.target.value)}
            disabled={busy}
          >
            <option value="">Select run...</option>
            {runOptions.map((runId) => (
              <option key={`a-${runId}`} value={runId}>{runId}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Run B</span>
          <select
            value={compareRunB}
            onChange={(event) => onRunBChange(event.target.value)}
            disabled={busy}
          >
            <option value="">Select run...</option>
            {runOptions.map((runId) => (
              <option key={`b-${runId}`} value={runId}>{runId}</option>
            ))}
          </select>
        </label>
        <div className="actions left">
          <button onClick={onCompare} disabled={busy}>Compare research.md</button>
        </div>
      </div>
      <textarea className="editor compare" value={compareResult} readOnly />
    </section>
  );
}

interface EditorCardProps {
  title: string;
  value: string;
  onChange: (value: string) => void;
  onOpenTemplates?: () => void;
}

function EditorCard({ title, value, onChange, onOpenTemplates: onOpenTemplates }: EditorCardProps) {
  return (
    <div className="editor-card">
      <h3>{title}</h3>
      <div className="editor-wrap">
        <div className="editor-toolbar">
          {onOpenTemplates && (
            <button className="icon-btn" onClick={onOpenTemplates} title="Templates">
              Templates
            </button>
          )}
          <button className="icon-btn" onClick={() => void navigator.clipboard.writeText(value)} title="Copy">
            Copy
          </button>
          <button className="icon-btn" onClick={() => onChange("")} title="Clear">
            Clear
          </button>
        </div>
        <textarea className="editor" value={value} onChange={(event) => onChange(event.target.value)} />
      </div>
    </div>
  );
}

interface StagePanelProps {
  stage: StageName;
  prompt: string;
  output: string;
  runFlag: boolean;
  onPromptChange: (value: string) => void;
  onOutputChange: (value: string) => void;
  onRunFlagChange: (checked: boolean) => void;
  onOpenTemplatePicker: () => void;
}

function StagePanel({
  stage,
  prompt,
  output,
  runFlag,
  onPromptChange,
  onOutputChange,
  onRunFlagChange,
  onOpenTemplatePicker
}: StagePanelProps) {
  return (
    <section className="panel stage">
      <div className="stage-header">
        <label className="stage-toggle">
          <input
            type="checkbox"
            checked={runFlag}
            onChange={(event) => onRunFlagChange(event.target.checked)}
          />
          <span>Run {stage}</span>
        </label>
      </div>

      <div className="editors">
        <EditorCard
          title={`${stage} prompt`}
          value={prompt}
          onChange={onPromptChange}
          onOpenTemplates={onOpenTemplatePicker}
        />
        <EditorCard title={`${stage} output`} value={output} onChange={onOutputChange} />
      </div>
    </section>
  );
}

interface TemplatePickerProps {
  isOpen: boolean;
  stage: StageName | null;
  templates: PromptTemplate[];
  selectedTemplateId: string;
  draftName: string;
  draftPromptText: string;
  busy: boolean;
  error: string;
  onSelectTemplate: (templateId: string) => void;
  onDraftNameChange: (value: string) => void;
  onDraftPromptTextChange: (value: string) => void;
  onApply: () => void;
  onCreate: () => void;
  onUpdate: () => void;
  onDelete: () => void;
  onClose: () => void;
}

function TemplatePickerModal({
  isOpen,
  stage,
  templates,
  selectedTemplateId,
  draftName,
  draftPromptText,
  busy,
  error,
  onSelectTemplate,
  onDraftNameChange,
  onDraftPromptTextChange,
  onApply,
  onCreate,
  onUpdate,
  onDelete,
  onClose
}: TemplatePickerProps) {
  if (!isOpen || !stage) return null;

  return (
    <div className="template-modal-backdrop" role="dialog" aria-modal="true">
      <section className="template-modal">
        <header>
          <h2>{stage} templates</h2>
        </header>

        <label className="field">
          <span>Choose existing template</span>
          <select value={selectedTemplateId} onChange={(event) => onSelectTemplate(event.target.value)} disabled={busy}>
            <option value="">New template...</option>
            {templates.map((template) => (
              <option key={template.id} value={template.id}>{template.name}</option>
            ))}
          </select>
        </label>

        {templates.length === 0 && <p className="template-empty">No templates yet for this stage.</p>}

        <label className="field">
          <span>Template name</span>
          <input
            value={draftName}
            onChange={(event) => onDraftNameChange(event.target.value)}
            placeholder="My HTTPS researcher variant"
            disabled={busy}
          />
        </label>

        <label className="field">
          <span>Preview (applies only after confirm)</span>
          <textarea
            className="editor template-preview"
            value={draftPromptText}
            onChange={(event) => onDraftPromptTextChange(event.target.value)}
            disabled={busy}
          />
        </label>

        <div className="actions left template-actions">
          <button onClick={onApply} disabled={busy || !draftPromptText.trim()}>Apply To Editor</button>
          <button onClick={onCreate} disabled={busy || !draftName.trim() || !draftPromptText.trim()}>Save New</button>
          <button onClick={onUpdate} disabled={busy || !selectedTemplateId}>Update Selected</button>
          <button onClick={onDelete} disabled={busy || !selectedTemplateId}>Delete Selected</button>
          <button onClick={onClose} disabled={busy}>Close</button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}

// ============================================================================
// MAIN APP COMPONENT
// ============================================================================

export default function App() {
  const { state, updateState, setTokenAndPersist } = useAppState();
  const {
    bootstrap,
    refreshRuns,
    loadDefaults,
    loadRun,
    runSelectedStages,
    runCompare,
    openTemplatePicker,
    closeTemplatePicker,
    selectTemplateForPreview,
    applySelectedTemplate,
    createTemplateFromPicker,
    updateSelectedTemplate,
    deleteSelectedTemplate
  } = useApiOperations(state, updateState);

  useEffect(() => {
    void bootstrap();
  }, []);

  const runOptions = useMemo(() => state.runs.map((run) => run.run_id), [state.runs]);

  return (
    <div className="page">
      <header className="hero">
        <h1>Prompts Lab</h1>
        <p>Developer-only playground for podcast stages, prompts, and outputs.</p>
      </header>

      <TokenPanel
        token={state.token}
        onTokenChange={setTokenAndPersist}
        onReloadMeta={() => void bootstrap()}
        onLoadDefaults={() => void loadDefaults()}
        onRunSelected={() => void runSelectedStages()}
        busy={state.busy}
      />

      <ConfigPanel
        format={state.format}
        topic={state.topic}
        hostIds={state.hostIds}
        meta={state.meta}
        onFormatChange={(format) => {
          updateState({ format });
          void loadDefaults(state.topic, format, state.hostIds);
        }}
        onTopicChange={(topic) => updateState({ topic })}
        onHostsChange={(hostIds) => {
          updateState({ hostIds });
          void loadDefaults(state.topic, state.format, hostIds);
        }}
        busy={state.busy}
      />

      <RunLoaderPanel
        selectedRun={state.selectedRun}
        runOptions={runOptions}
        onRunSelect={(runId) => updateState({ selectedRun: runId })}
        onRefresh={() => void refreshRuns()}
        onLoad={() => void loadRun(state.selectedRun)}
        busy={state.busy}
      />

      <ComparePanel
        compareRunA={state.compareRunA}
        compareRunB={state.compareRunB}
        compareResult={state.compareResult}
        runOptions={runOptions}
        onRunAChange={(runId) => updateState({ compareRunA: runId })}
        onRunBChange={(runId) => updateState({ compareRunB: runId })}
        onCompare={() => void runCompare()}
        busy={state.busy}
      />

      {STAGES.map((stage) => (
        <StagePanel
          key={stage}
          stage={stage}
          prompt={state.prompts[stage]}
          output={state.outputs[stage]}
          runFlag={state.runFlags[stage]}
          onPromptChange={(value) =>
            updateState({
              prompts: { ...state.prompts, [stage]: value }
            })
          }
          onOutputChange={(value) =>
            updateState({
              outputs: { ...state.outputs, [stage]: value }
            })
          }
          onRunFlagChange={(checked) =>
            updateState({
              runFlags: { ...state.runFlags, [stage]: checked }
            })
          }
          onOpenTemplatePicker={() => void openTemplatePicker(stage)}
        />
      ))}

      <TemplatePickerModal
        isOpen={state.templatePicker.isOpen}
        stage={state.templatePicker.stage}
        templates={state.templatePicker.stage ? state.promptTemplates[state.templatePicker.stage] : []}
        selectedTemplateId={state.templatePicker.selectedTemplateId}
        draftName={state.templatePicker.draftName}
        draftPromptText={state.templatePicker.draftPromptText}
        busy={state.templatePicker.busy}
        error={state.templatePicker.error}
        onSelectTemplate={(templateId) => selectTemplateForPreview(templateId)}
        onDraftNameChange={(value) =>
          updateState({
            templatePicker: {
              ...state.templatePicker,
              draftName: value,
              error: ""
            }
          })
        }
        onDraftPromptTextChange={(value) =>
          updateState({
            templatePicker: {
              ...state.templatePicker,
              draftPromptText: value,
              error: ""
            }
          })
        }
        onApply={() => applySelectedTemplate()}
        onCreate={() => void createTemplateFromPicker()}
        onUpdate={() => void updateSelectedTemplate()}
        onDelete={() => void deleteSelectedTemplate()}
        onClose={() => closeTemplatePicker()}
      />

      <footer className="status-bar">
        <span>{state.busy ? "Busy..." : state.status}</span>
        {state.error && <span className="error">{state.error}</span>}
      </footer>
    </div>
  );
}
