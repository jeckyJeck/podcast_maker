import { useEffect, useMemo, useState } from "react";
import {
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

const TABS = ["workspace", "comparison"] as const;

type AppTab = (typeof TABS)[number];

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

interface StageComparisonSnapshot {
  prompt: string;
  output: string;
  promptFile: string | null;
  outputFile: string | null;
}

interface RunComparisonSnapshot {
  runId: string;
  stages: Record<StageName, StageComparisonSnapshot>;
}

interface ComparisonViewData {
  runA: RunComparisonSnapshot;
  runB: RunComparisonSnapshot;
  copyTextA: string;
  copyTextB: string;
  combinedText: string;
}

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

function formatStageTitle(stage: StageName) {
  return stage.charAt(0).toUpperCase() + stage.slice(1);
}

function copyToClipboard(text: string) {
  if (!text.trim()) return;
  void navigator.clipboard.writeText(text);
}

function buildRunCopyText(snapshot: RunComparisonSnapshot) {
  return STAGES.map((stage) => {
    const stageData = snapshot.stages[stage];
    const promptLabel = stageData.promptFile ? `${stageData.promptFile}` : "missing prompt file";
    const outputLabel = stageData.outputFile ? `${stageData.outputFile}` : "missing output file";
    return [
      `## ${formatStageTitle(stage)} (${snapshot.runId})`,
      `Prompt source: ${promptLabel}`,
      stageData.prompt.trim() || "[No prompt]",
      "",
      `Output source: ${outputLabel}`,
      stageData.output.trim() || "[No output]"
    ].join("\n");
  }).join("\n\n");
}

function buildCombinedComparisonText(runA: RunComparisonSnapshot, runB: RunComparisonSnapshot) {
  return [
    `Compare run A (${runA.runId}) with run B (${runB.runId}).`,
    "",
    ...STAGES.flatMap((stage) => {
      const left = runA.stages[stage];
      const right = runB.stages[stage];
      return [
        `## ${formatStageTitle(stage)}`,
        `Prompt A`,
        left.prompt.trim() || "[No prompt]",
        "",
        `Prompt B`,
        right.prompt.trim() || "[No prompt]",
        "",
        `Output A`,
        left.output.trim() || "[No output]",
        "",
        `Output B`,
        right.output.trim() || "[No output]"
      ];
    })
  ].join("\n");
}

async function loadRunComparisonSnapshot(runId: string, token: string): Promise<RunComparisonSnapshot> {
  const details = await getRun(runId, token);
  const stagePairs = await Promise.all(
    STAGES.map(async (stage) => {
      const promptFile = STAGE_PROMPT_FILES[stage];
      const outputFile = STAGE_OUTPUT_FILES[stage].find((file) => details.files.includes(file)) ?? null;

      const [prompt, output] = await Promise.all([
        details.files.includes(promptFile) ? getRunFile(runId, promptFile, token) : Promise.resolve(""),
        outputFile ? getRunFile(runId, outputFile, token) : Promise.resolve("")
      ]);

      return [
        stage,
        {
          prompt,
          output,
          promptFile: details.files.includes(promptFile) ? promptFile : null,
          outputFile
        }
      ] as const;
    })
  );

  return {
    runId,
    stages: Object.fromEntries(stagePairs) as Record<StageName, StageComparisonSnapshot>
  };
}

// ============================================================================
// CUSTOM HOOKS
// ============================================================================

interface AppState {
  token: string;
  meta: MetaResponse | null;
  runs: RunListItem[];
  activeTab: AppTab;
  selectedRun: string;
  compareRunA: string;
  compareRunB: string;
  compareResult: string;
  comparisonData: ComparisonViewData | null;
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
    activeTab: "workspace",
    selectedRun: "",
    compareRunA: "",
    compareRunB: "",
    compareResult: "",
    comparisonData: null,
    topic: "",
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
      const nextTopic = state.topic.trim() || metaRes.default_topic?.trim() || "";
      updateState({
        meta: metaRes,
        runs: runsRes,
        topic: nextTopic,
        format: "dialogue",
        hostIds: metaRes.default_host_ids,
        status: nextTopic ? "Loaded defaults" : "Loaded meta (topic required)"
      });
      if (nextTopic) {
        await loadDefaults(nextTopic, "dialogue", metaRes.default_host_ids);
      }
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
    const sanitizedTopic = newTopic.trim();
    if (!sanitizedTopic) {
      updateState({
        error: "Topic is required before loading defaults.",
        status: "Defaults blocked"
      });
      return;
    }

    updateState({ busy: true, error: "" });
    try {
      const defaults = await getDefaults(
        {
          topic: sanitizedTopic,
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
    const sanitizedTopic = state.topic.trim();
    if (!sanitizedTopic) {
      updateState({
        error: "Topic is required before running stages.",
        status: "Run blocked"
      });
      return;
    }

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
        topic: sanitizedTopic,
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
      const [runA, runB] = await Promise.all([
        loadRunComparisonSnapshot(state.compareRunA, state.token),
        loadRunComparisonSnapshot(state.compareRunB, state.token)
      ]);
      const copyTextA = buildRunCopyText(runA);
      const copyTextB = buildRunCopyText(runB);
      const combinedText = buildCombinedComparisonText(runA, runB);
      updateState({
        comparisonData: { runA, runB, copyTextA, copyTextB, combinedText },
        compareResult: combinedText,
        activeTab: "comparison",
        status: "Comparison ready"
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
  runOptions: string[];
  comparisonData: ComparisonViewData | null;
  compareResult: string;
  onRunAChange: (runId: string) => void;
  onRunBChange: (runId: string) => void;
  onCompare: () => void;
  busy: boolean;
}

function ComparePanel({
  compareRunA,
  compareRunB,
  comparisonData,
  compareResult,
  runOptions,
  onRunAChange,
  onRunBChange,
  onCompare,
  busy
}: ComparePanelProps) {
  return (
    <section className="panel comparison-panel">
      <header className="comparison-hero">
        <div>
          <h2>Comparison tab</h2>
          <p>Compare two runs stage by stage, copy each side separately, or grab one combined block for judgment.</p>
        </div>
        <div className="actions left">
          <button onClick={onCompare} disabled={busy || !compareRunA || !compareRunB}>Load comparison</button>
          <button
            onClick={() => copyToClipboard(compareResult)}
            disabled={!compareResult.trim()}
          >
            Copy judge pack
          </button>
        </div>
      </header>

      <div className="grid-3 comparison-selectors">
        <label className="field">
          <span>Run A</span>
          <select value={compareRunA} onChange={(event) => onRunAChange(event.target.value)} disabled={busy}>
            <option value="">Select run...</option>
            {runOptions.map((runId) => (
              <option key={`a-${runId}`} value={runId}>{runId}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Run B</span>
          <select value={compareRunB} onChange={(event) => onRunBChange(event.target.value)} disabled={busy}>
            <option value="">Select run...</option>
            {runOptions.map((runId) => (
              <option key={`b-${runId}`} value={runId}>{runId}</option>
            ))}
          </select>
        </label>
        <div className="actions left comparison-summary-actions">
          <button onClick={() => copyToClipboard(comparisonData?.copyTextA ?? "")} disabled={!comparisonData}>
            Copy run A
          </button>
          <button onClick={() => copyToClipboard(comparisonData?.copyTextB ?? "")} disabled={!comparisonData}>
            Copy run B
          </button>
        </div>
      </div>

      {comparisonData ? (
        <div className="comparison-stack">
          <section className="comparison-pack panel-inner">
            <div className="comparison-pack-header">
              <h3>Judge pack</h3>
              <button onClick={() => copyToClipboard(comparisonData.combinedText)}>
                Copy full pack
              </button>
            </div>
            <textarea className="editor compare" value={comparisonData.combinedText} readOnly />
          </section>

          {STAGES.map((stage) => {
            const left = comparisonData.runA.stages[stage];
            const right = comparisonData.runB.stages[stage];
            return (
              <section className="comparison-stage panel-inner" key={stage}>
                <div className="comparison-stage-header">
                  <div>
                    <h3>{formatStageTitle(stage)}</h3>
                    <p>Prompts and outputs are shown separately for each run.</p>
                  </div>
                  <div className="actions left">
                    <button onClick={() => copyToClipboard(left.prompt)}>Copy prompt A</button>
                    <button onClick={() => copyToClipboard(right.prompt)}>Copy prompt B</button>
                    <button onClick={() => copyToClipboard(left.output)}>Copy A</button>
                    <button onClick={() => copyToClipboard(right.output)}>Copy B</button>
                  </div>
                </div>
                <div className="comparison-subsection">
                  <div className="comparison-subsection-header">
                    <h4>Prompt</h4>
                    <span>Editable source prompt for each run.</span>
                  </div>
                  <div className="comparison-columns">
                    <article className="comparison-column">
                      <div className="comparison-column-header">
                        <span>Run A</span>
                        <small>{left.promptFile ?? "Missing prompt file"}</small>
                      </div>
                      <textarea className="editor compare comparison-text" value={left.prompt} readOnly />
                    </article>
                    <article className="comparison-column">
                      <div className="comparison-column-header">
                        <span>Run B</span>
                        <small>{right.promptFile ?? "Missing prompt file"}</small>
                      </div>
                      <textarea className="editor compare comparison-text" value={right.prompt} readOnly />
                    </article>
                  </div>
                </div>

                <div className="comparison-subsection">
                  <div className="comparison-subsection-header">
                    <h4>Output</h4>
                    <span>Generated result for the same stage.</span>
                  </div>
                  <div className="comparison-columns">
                    <article className="comparison-column">
                      <div className="comparison-column-header">
                        <span>Run A</span>
                        <small>{left.outputFile ?? "Missing output file"}</small>
                      </div>
                      <textarea className="editor compare comparison-text" value={left.output} readOnly />
                    </article>
                    <article className="comparison-column">
                      <div className="comparison-column-header">
                        <span>Run B</span>
                        <small>{right.outputFile ?? "Missing output file"}</small>
                      </div>
                      <textarea className="editor compare comparison-text" value={right.output} readOnly />
                    </article>
                  </div>
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <p className="comparison-empty">Load two runs to see the stage-by-stage comparison.</p>
      )}
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
        <div>
          <h1>Prompts Lab</h1>
          <p>Developer-only playground for podcast stages, prompts, outputs, and comparisons.</p>
        </div>
        <div className="hero-tabs" role="tablist" aria-label="Workspace tabs">
          {TABS.map((tab) => (
            <button
              key={tab}
              className={state.activeTab === tab ? "tab active" : "tab"}
              onClick={() => updateState({ activeTab: tab })}
              role="tab"
              aria-selected={state.activeTab === tab}
            >
              {tab === "workspace" ? "Workspace" : "Comparison"}
            </button>
          ))}
        </div>
      </header>

      {state.activeTab === "workspace" ? (
        <>
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
        </>
      ) : (
        <ComparePanel
          compareRunA={state.compareRunA}
          compareRunB={state.compareRunB}
          comparisonData={state.comparisonData}
          compareResult={state.compareResult}
          runOptions={runOptions}
          onRunAChange={(runId) => updateState({ compareRunA: runId })}
          onRunBChange={(runId) => updateState({ compareRunB: runId })}
          onCompare={() => void runCompare()}
          busy={state.busy}
        />
      )}

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
