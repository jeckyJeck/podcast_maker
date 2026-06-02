# Optimization Agent

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

To add another provider, subclass `AgentLLM`, implement `complete()`, then register it in `build_agent_llm()`.
