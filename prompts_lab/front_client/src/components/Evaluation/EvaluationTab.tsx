import { useEffect, useState } from "react";
import {
  getRuns,
  getRun,
  listEvalRubrics,
  evaluateRun,
  getRunEvaluation,
  type EvaluationResult
} from "../../services/api";
import { RunListItem } from "../../types";
import { ClipboardCheck, Loader2 } from "lucide-react";

export default function EvaluationTab() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [runFiles, setRunFiles] = useState<string[]>([]);
  const [contentFiles, setContentFiles] = useState<Set<string>>(new Set());
  const [contextFiles, setContextFiles] = useState<Set<string>>(new Set());
  const [rubrics, setRubrics] = useState<string[]>([]);
  const [rubricId, setRubricId] = useState("podcast_quality");
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = localStorage.getItem("prompts_lab_token") || "";

  useEffect(() => {
    getRuns(token).then(setRuns).catch(err => console.error("Failed to load runs:", err));
    listEvalRubrics(token).then(setRubrics).catch(err => console.error("Failed to load rubrics:", err));
  }, [token]);

  const selectRun = async (runId: string) => {
    setSelectedRunId(runId);
    setEvaluation(null);
    setError(null);
    setContentFiles(new Set());
    setContextFiles(new Set());
    setRunFiles([]);
    if (!runId) return;

    setLoadingRun(true);
    try {
      const details = await getRun(runId, token);
      setRunFiles(details.files);
      // Preselect what the run's pipeline YAML says should be judged (editable below).
      if (details.evaluation_defaults) {
        setContentFiles(new Set(Object.values(details.evaluation_defaults.content_files)));
        setContextFiles(new Set(Object.values(details.evaluation_defaults.context_files)));
      }
      try {
        const existing = await getRunEvaluation(runId, token);
        setEvaluation(existing);
      } catch {
        // no cached evaluation yet - fine
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingRun(false);
    }
  };

  const toggleFile = (set: Set<string>, setter: (s: Set<string>) => void, file: string) => {
    const next = new Set(set);
    if (next.has(file)) next.delete(file);
    else next.add(file);
    setter(next);
  };

  const handleEvaluate = async () => {
    if (!selectedRunId || contentFiles.size === 0) return;
    setRunning(true);
    setError(null);
    try {
      const content_files: Record<string, string> = {};
      contentFiles.forEach(f => (content_files[f] = f));
      const context_files: Record<string, string> = {};
      contextFiles.forEach(f => (context_files[f] = f));

      const result = await evaluateRun(
        selectedRunId,
        {
          content_files,
          rubric_id: rubricId,
          context_files: Object.keys(context_files).length ? context_files : undefined
        },
        token
      );
      setEvaluation(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="comparison-container">
      <div className="comparison-hero">
        <div>
          <h2>Evaluation</h2>
          <p>Judge a run's output with an LLM-as-a-judge rubric and inspect the scored breakdown.</p>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1.5rem",
          background: "var(--bg-panel)",
          border: "1px solid var(--border-color)",
          padding: "1rem",
          borderRadius: 8,
          marginBottom: "1.5rem"
        }}
      >
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Run</label>
          <select className="form-select" value={selectedRunId} onChange={e => selectRun(e.target.value)}>
            <option value="">Select a run...</option>
            {runs.map(r => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id} ({r.label || r.pipeline_id || "no label"})
              </option>
            ))}
          </select>
        </div>

        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Rubric</label>
          <select className="form-select" value={rubricId} onChange={e => setRubricId(e.target.value)}>
            {rubrics.length === 0 && <option value="podcast_quality">podcast_quality</option>}
            {rubrics.map(r => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loadingRun && (
        <div style={{ display: "flex", justifyContent: "center", padding: "2rem", color: "#64748b" }}>
          Loading run files...
        </div>
      )}

      {!loadingRun && selectedRunId && runFiles.length > 0 && (
        <div
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-color)",
            borderRadius: 8,
            padding: "1rem",
            marginBottom: "1.5rem"
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: "0.75rem" }}>Pick files</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {runFiles.map(file => (
              <div key={file} style={{ display: "flex", alignItems: "center", gap: "1rem", fontSize: "0.85rem" }}>
                <span style={{ flex: 1, color: "#e2e8f0" }}>{file}</span>
                <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", color: "#94a3b8" }}>
                  <input
                    type="checkbox"
                    checked={contentFiles.has(file)}
                    onChange={() => toggleFile(contentFiles, setContentFiles, file)}
                  />
                  score this
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", color: "#94a3b8" }}>
                  <input
                    type="checkbox"
                    checked={contextFiles.has(file)}
                    onChange={() => toggleFile(contextFiles, setContextFiles, file)}
                  />
                  context only
                </label>
              </div>
            ))}
          </div>

          <button
            className="btn btn-primary"
            style={{ marginTop: "1rem" }}
            onClick={handleEvaluate}
            disabled={running || contentFiles.size === 0}
          >
            {running ? <Loader2 size={16} className="spin" /> : <ClipboardCheck size={16} />}
            {running ? "Evaluating..." : "Evaluate"}
          </button>
        </div>
      )}

      {error && (
        <div style={{ color: "#f87171", padding: "0.75rem", marginBottom: "1rem" }}>{error}</div>
      )}

      {evaluation && (
        <div
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--border-color)",
            borderRadius: 8,
            padding: "1.25rem"
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", marginBottom: "1rem" }}>
            <span style={{ fontSize: "2rem", fontWeight: 700, color: "#f8fafc" }}>
              {evaluation.overall_score.toFixed(1)}
            </span>
            <span style={{ color: "#64748b" }}>/ 10 overall &middot; rubric: {evaluation.rubric_id}</span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginBottom: "1rem" }}>
            {evaluation.dimensions.map(d => (
              <div key={d.name}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: "0.2rem" }}>
                  <span style={{ color: "#e2e8f0" }}>{d.name}</span>
                  <span style={{ color: "#94a3b8" }}>{d.score.toFixed(1)}</span>
                </div>
                <div style={{ background: "#0f172a", borderRadius: 4, height: 6, overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${Math.max(0, Math.min(100, (d.score / 10) * 100))}%`,
                      background: "var(--accent-color)",
                      height: "100%"
                    }}
                  />
                </div>
                {d.rationale && (
                  <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.2rem" }}>{d.rationale}</div>
                )}
              </div>
            ))}
          </div>

          {evaluation.reasoning && (
            <div style={{ fontSize: "0.85rem", color: "#94a3b8", marginBottom: "1rem" }}>
              <strong style={{ color: "#e2e8f0" }}>Reasoning: </strong>
              {evaluation.reasoning}
            </div>
          )}

          {evaluation.suggestions.length > 0 && (
            <div>
              <strong style={{ color: "#e2e8f0", fontSize: "0.85rem" }}>Suggestions</strong>
              <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.2rem", fontSize: "0.85rem", color: "#94a3b8" }}>
                {evaluation.suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ fontSize: "0.7rem", color: "#475569", marginTop: "1rem" }}>
            {evaluation.evaluator_model} &middot; {evaluation.evaluated_at_utc} &middot; {evaluation.duration_ms}ms
          </div>
        </div>
      )}

      {!selectedRunId && !loadingRun && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            padding: "5rem",
            color: "#64748b",
            border: "1px dashed var(--border-color)",
            borderRadius: 8,
            gap: "0.5rem"
          }}
        >
          <ClipboardCheck size={32} />
          <p>Select a run above to evaluate its output.</p>
        </div>
      )}
    </div>
  );
}
