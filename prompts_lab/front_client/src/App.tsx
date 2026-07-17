import { useState, useEffect } from "react";
import PipelineBuilderTab from "./components/PipelineEditor/PipelineBuilderTab";
import ComparisonTab from "./components/Comparison/ComparisonTab";
import { GitCompare, Workflow, Key } from "lucide-react";

type ActiveTabType = "builder" | "comparison";

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTabType>("builder");
  const [token, setToken] = useState(localStorage.getItem("prompts_lab_token") || "");
  const [statusText, setStatusText] = useState("Ready");

  useEffect(() => {
    localStorage.setItem("prompts_lab_token", token);
  }, [token]);

  return (
    <div className="app-container">
      {/* Visual Navigation Header */}
      <header className="app-header">
        <div className="brand-section">
          <h1>
            <Workflow size={20} className="edge-badge accum" style={{ fill: "currentColor" }} />
            Prompts Lab v2
          </h1>
          <div className="brand-subtitle">Graph Pipeline Tester & Workspace</div>
        </div>

        {/* Tab buttons */}
        <div className="nav-tabs">
          <button
            className={`tab-btn ${activeTab === "builder" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("builder");
              setStatusText("Switched to Pipeline Builder");
            }}
          >
            <Workflow size={14} /> Pipeline Builder
          </button>
          <button
            className={`tab-btn ${activeTab === "comparison" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("comparison");
              setStatusText("Switched to Comparison View");
            }}
          >
            <GitCompare size={14} /> Runs Comparison
          </button>
        </div>

        {/* Supabase Bearer Token Input */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Key size={14} style={{ color: "#94a3b8" }} />
          <input
            type="password"
            style={{
              background: "#0f172a",
              border: "1px solid var(--border-color)",
              borderRadius: "6px",
              padding: "0.4rem 0.6rem",
              fontSize: "0.75rem",
              color: "#e2e8f0",
              width: "180px"
            }}
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="Supabase Auth Token"
          />
        </div>
      </header>

      {/* Main View Port */}
      <main className="view-content">
        {activeTab === "builder" ? (
          <PipelineBuilderTab />
        ) : (
          <ComparisonTab />
        )}
      </main>

      {/* Status Bar */}
      <footer className="status-bar">
        <span>Status: <strong>{statusText}</strong></span>
        <span>Supabase Integration: <strong>{token ? "Active" : "Anonymous"}</strong></span>
      </footer>
    </div>
  );
}
