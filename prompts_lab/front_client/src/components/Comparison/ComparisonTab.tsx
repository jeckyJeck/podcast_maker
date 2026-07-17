import { useState, useEffect } from "react";
import { getRuns, getRun, getRunFile } from "../../services/api";
import { RunListItem } from "../../types";
import { GitCompare, Copy, Check } from "lucide-react";

export default function ComparisonTab() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runA, setRunA] = useState("");
  const [runB, setRunB] = useState("");
  
  const [detailsA, setDetailsA] = useState<any | null>(null);
  const [detailsB, setDetailsB] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const token = localStorage.getItem("prompts_lab_token") || "";

  useEffect(() => {
    getRuns(token)
      .then(res => setRuns(res || []))
      .catch(err => console.error("Failed to load runs:", err));
  }, [token]);

  const handleCompare = async () => {
    if (!runA || !runB) return;
    setLoading(true);
    try {
      const [detA, detB] = await Promise.all([
        getRun(runA, token),
        getRun(runB, token)
      ]);

      // Load specific files content (e.g. prompt_architect, blueprint.json, research.md, outline.json, script.txt)
      const loadContents = async (details: any, runId: string) => {
        const fileContents: Record<string, string> = {};
        const targets = [
          "blueprint.json", "blueprint.snapshot.json",
          "research.md", "research.snapshot.md",
          "outline.json", "outline.snapshot.json",
          "script.txt", "script.snapshot.txt"
        ];
        
        for (const file of details.files) {
          if (targets.includes(file) || file.startsWith("prompt_")) {
            try {
              fileContents[file] = await getRunFile(runId, file, token);
            } catch {
              fileContents[file] = "";
            }
          }
        }
        return fileContents;
      };

      const [contentsA, contentsB] = await Promise.all([
        loadContents(detA, runA),
        loadContents(detB, runB)
      ]);

      setDetailsA({ details: detA, contents: contentsA });
      setDetailsB({ details: detB, contents: contentsB });
    } catch (err) {
      alert(`Comparison Failed: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text: string, id: string) => {
    void navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const formatStageLabel = (file: string) => {
    return file.replace(".json", "").replace(".md", "").replace(".txt", "").replace("prompt_", "Prompt: ").toUpperCase();
  };

  return (
    <div className="comparison-container">
      <div className="comparison-hero">
        <div>
          <h2>Runs Comparison</h2>
          <p>Analyze differences in stage configurations, source prompts, and output files side-by-side.</p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            className="btn btn-primary"
            onClick={handleCompare}
            disabled={loading || !runA || !runB}
          >
            <GitCompare size={16} /> Compare Runs
          </button>
        </div>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "1.5rem",
        background: "var(--bg-panel)",
        border: "1px solid var(--border-color)",
        padding: "1rem",
        borderRadius: 8,
        marginBottom: "1.5rem"
      }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Compare Run A</label>
          <select className="form-select" value={runA} onChange={e => setRunA(e.target.value)}>
            <option value="">Select first run...</option>
            {runs.map(r => (
              <option key={r.run_id} value={r.run_id}>{r.run_id} ({r.topic || "no topic"})</option>
            ))}
          </select>
        </div>
        
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label>Compare Run B</label>
          <select className="form-select" value={runB} onChange={e => setRunB(e.target.value)}>
            <option value="">Select second run...</option>
            {runs.map(r => (
              <option key={r.run_id} value={r.run_id}>{r.run_id} ({r.topic || "no topic"})</option>
            ))}
          </select>
        </div>
      </div>

      {loading && (
        <div style={{ display: "flex", justifyContent: "center", padding: "4rem", color: "#64748b" }}>
          Fetching execution records and source diffs...
        </div>
      )}

      {!loading && detailsA && detailsB && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          
          {/* Metadata Comparison */}
          <div className="compare-row">
            <div className="compare-box">
              <div className="compare-box-header">
                <span>Run A Metadata</span>
              </div>
              <div style={{ fontSize: "0.85rem", color: "#94a3b8", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                <div>ID: <strong style={{ color: "#f8fafc" }}>{detailsA.details.run_id}</strong></div>
                <div>Topic: <strong>{detailsA.details.manifest?.topic || "N/A"}</strong></div>
                <div>Created: <strong>{detailsA.details.manifest?.created_at_utc || "N/A"}</strong></div>
              </div>
            </div>
            <div className="compare-box">
              <div className="compare-box-header">
                <span>Run B Metadata</span>
              </div>
              <div style={{ fontSize: "0.85rem", color: "#94a3b8", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                <div>ID: <strong style={{ color: "#f8fafc" }}>{detailsB.details.run_id}</strong></div>
                <div>Topic: <strong>{detailsB.details.manifest?.topic || "N/A"}</strong></div>
                <div>Created: <strong>{detailsB.details.manifest?.created_at_utc || "N/A"}</strong></div>
              </div>
            </div>
          </div>

          {/* Files List Comparison */}
          {Array.from(new Set([
            ...Object.keys(detailsA.contents),
            ...Object.keys(detailsB.contents)
          ])).sort().map(file => {
            const contentA = detailsA.contents[file] || "";
            const contentB = detailsB.contents[file] || "";

            if (!contentA && !contentB) return null;

            return (
              <div key={file} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{
                  fontWeight: 600,
                  fontSize: "0.9rem",
                  color: "#f8fafc",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  marginTop: "0.5rem"
                }}>
                  <div style={{ width: 6, height: 6, background: "var(--accent-color)", borderRadius: "50%" }} />
                  {formatStageLabel(file)}
                  <span style={{ fontSize: "0.7rem", color: "#64748b", fontWeight: 400 }}>({file})</span>
                </div>

                <div className="compare-row">
                  <div className="compare-box" style={{ position: "relative" }}>
                    <div style={{ position: "absolute", top: "0.5rem", right: "0.5rem" }}>
                      <button
                        className="toolbar-btn"
                        onClick={() => handleCopy(contentA, `a-${file}`)}
                        title="Copy content"
                      >
                        {copiedId === `a-${file}` ? <Check size={14} className="edge-badge map" /> : <Copy size={14} />}
                      </button>
                    </div>
                    <textarea
                      className="form-textarea"
                      style={{ height: "180px", fontFamily: "JetBrains Mono", fontSize: "0.75rem", background: "#030712" }}
                      value={contentA}
                      readOnly
                      placeholder="File not generated in this run."
                    />
                  </div>

                  <div className="compare-box" style={{ position: "relative" }}>
                    <div style={{ position: "absolute", top: "0.5rem", right: "0.5rem" }}>
                      <button
                        className="toolbar-btn"
                        onClick={() => handleCopy(contentB, `b-${file}`)}
                        title="Copy content"
                      >
                        {copiedId === `b-${file}` ? <Check size={14} className="edge-badge map" /> : <Copy size={14} />}
                      </button>
                    </div>
                    <textarea
                      className="form-textarea"
                      style={{ height: "180px", fontFamily: "JetBrains Mono", fontSize: "0.75rem", background: "#030712" }}
                      value={contentB}
                      readOnly
                      placeholder="File not generated in this run."
                    />
                  </div>
                </div>
              </div>
            );
          })}

        </div>
      )}

      {!detailsA && !detailsB && !loading && (
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "5rem",
          color: "#64748b",
          border: "1px dashed var(--border-color)",
          borderRadius: 8,
          gap: "0.5rem"
        }}>
          <GitCompare size={32} />
          <p>Please select two runs above and click "Compare Runs" to analyze.</p>
        </div>
      )}
    </div>
  );
}
