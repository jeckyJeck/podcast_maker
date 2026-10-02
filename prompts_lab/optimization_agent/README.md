# Optimization Agent

The agent holds no copy of the pipeline engine or of the data. Everything (pipelines, runs, evaluations) goes through the merged backend's `/prompts-test-api` over HTTP. Start the backend first (`run_prompts_lab.ps1`, or `uvicorn app.main:app` from `backend/` with `LAB_AUTH_BYPASS=true`), then:

```bash
python agent.py --format duo_long --task "..."
```

Environment: `BACKEND_URL` (default `http://127.0.0.1:8000`); `BACKEND_TOKEN` only if the backend runs with real auth. `agent_config.yaml` holds the agent's own settings: per-pipeline evaluation settings (which stage outputs the judge sees) and the fixed test cases (pipeline id + inputs) for `run_all_test_cases`; `workspace/` and `experiments/` are local scratch.

The optimization agent can run against different reasoning model providers through the `AgentLLM` abstraction in `agent_llm.py`.

## Agent Model Selection

Ollama is the default provider:

```bash
python agent.py --agent-provider ollama --agent-model qwen2.5:7b
```

Gemini is also available when `GEMINI_API_KEY` is configured:

```bash
python agent.py --agent-provider gemini --agent-model gemini-2.5-flash
```

You can also use environment variables:

```powershell
$env:AGENT_PROVIDER = "ollama"
$env:AGENT_MODEL = "qwen2.5:7b"
```

```bash
AGENT_PROVIDER=ollama
AGENT_MODEL=qwen2.5:7b
```

To add another provider, subclass `AgentLLM`, implement `complete()` with `ToolSpec` support, and return an `AgentLLMResponse` with `tool_call` populated when the provider returns a structured function call. Then register it in `build_agent_llm()`.
