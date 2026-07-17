# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

`prompts_lab` is a sandbox for iterating on the prompts used by the podcastMaker pipeline (architect → researcher → outliner → scriptwriter). It lets a human (via `front_client`) or an autonomous agent (`optimization_agent`, not yet wired to a UI) define a pipeline as YAML, run it against real LLMs, inspect per-stage prompts/outputs, and diff results across runs. Audio/TTS generation is intentionally out of scope here — that lives in the main podcastMaker app, not this lab.

## Folder map

- `lab_backend/` — the only backend that matters. FastAPI app exposing `/prompts-test-api/*`.
- `common_resources/` — shared contract, YAML pipeline templates, and historical run artifacts (gitignored).
- `front_client/` — the active React/Vite UI (visual pipeline builder + run/compare tooling).
- `optimization_agent/` — in-progress autonomous agent that reads past runs and writes new pipeline YAML for the backend to execute. No UI control surface yet.
- `front_client_old/`, `backend/` — superseded/stale copies (the top-level `backend/` folder is untracked in git; `lab_backend` replaced it — see commit "separate lab from backend"). Don't build new features here.
- `lab_env/` — local Python venv (gitignored).

## Commands

Backend (from `lab_backend/`, using `lab_env`):
```
..\lab_env\Scripts\activate
python run_server.py          # or: uvicorn app.main:app --reload --port 8000
```
CORS only allows the frontend's dev origin `http://localhost:5180`.

CLI for running/comparing stages directly (from `lab_backend/`):
```
python -m prompts_test.cli run --topic "..." --stages architect,researcher,outliner,scriptwriter
python -m prompts_test.cli compare --run-a <name> --run-b <name> --file research.md
python -m prompts_test.cli list-runs
```

Frontend (from `front_client/`):
```
npm run dev        # vite dev server, expects backend on 5180 CORS allowlist
npm run build       # tsc && vite build
npm run lint
```

No test suite currently exists in this subtree.

## Architecture

### The pipeline contract

Everything flows through the YAML format defined in `common_resources/PIPELINE_CONTRACT.md` — read it before writing or editing a pipeline YAML or touching the engine. Key shape:

- `inputs`: typed external values (`text`/`json`/`number`/`boolean`).
- `stages`: ordered list, each with `execution` (`single` / `map` / `map_with_context`), a `prompt` source (`inline` / `file` / `template`), `bindings` (placeholder → source substitutions), a `response` spec (raw model output persistence), and `outputs` (named values later stages/UI can reference via `<stage_id>.<output_name>`).
- Source references follow `inputs.<name>`, `<stage>.<output>`, `item[.field]`, `context.<name>`.

`common_resources/templates/{duo_long,solo_short}/pipeline.yaml` are the canonical starting templates; `lab_backend/engine/validate_pipeline.py` validates a pipeline dict against the contract before it's run.

### lab_backend layers

- `app/main.py` — FastAPI entrypoint, mounts `app/routers/prompts_test_api.py` at `/prompts-test-api`.
- `app/routers/prompts_test_api.py` — all HTTP routes: meta/hosts, default-prompt preview (`/defaults`), run creation (async via `BackgroundTasks` + in-memory `TASKS` dict), run listing/inspection/compare, CRUD for saved prompt templates, and full pipeline builder endpoints (list/get/save/delete pipeline YAML under `common_resources/templates/`, plus `/pipelines/run` which validates and executes an arbitrary YAML pipeline with optional per-stage prompt/output mocking).
- `prompts_test/` — the stage-runner layer used by both the API and the CLI:
  - `stage_runner.py` (`RunnerInputs`, `PromptTestRunner`) drives execution of one or more stages, writing outputs + a `run_manifest.json` per run.
  - `prompt_resolver.py` (`InstrumentedOverridePromptManager`) lets prompts be overridden by file/text/template instead of using the built-in defaults, and captures the actually-rendered prompt text for preview/inspection.
  - `io_contracts.py` — defines `STAGE_ORDER` and injected-artifact contracts (blueprint/research/outline) so stages can be run standalone with mocked upstream outputs.
  - `compare.py` — diffs an output file between two run directories.
- `podcast_maker/` — vendored copy of the core pipeline logic shared conceptually with the main app: `core/{architect,researcher,outliner,scriptwriter}.py` (per-stage logic), `core/prompt_manager.py` (`PodcastConfig`, default prompt construction), `core/hosts_config.py` (`AVAILABLE_HOSTS`), `services/{llm_provider,llm_provider_factory,gemini_adapter}.py` (LLM abstraction, Gemini-backed), `services/prompt_template_store.py` (persistence for user-saved prompt templates, keyed by a fixed local user id since auth is disabled in this lab).
- `engine/validate_pipeline.py` + `engine/schemas/*.schema.json` — contract validation and JSON schemas for architect/outliner outputs.

Auth is stubbed out everywhere in this lab (`AuthContext(user_id="lab-local-user")`, `method="disabled"`) — there is no real login here, unlike the main app's `AuthProvider` abstraction.

### Run artifacts

Every run writes to a directory under `common_resources/experiments_runs/` (gitignored) containing per-stage prompt text (`prompt_<stage>.txt`), raw outputs (`blueprint.json`, `research.md`, `outline.json`, `script.txt`), and `run_manifest.json`. The API only ever serves files from an explicit allowlist (`ALLOWED_FILES` in `prompts_test_api.py`) plus anything prefixed `prompt_`.

### front_client

Vite/React app (`front_client_new` package). `src/components/PipelineEditor/` is an `@xyflow/react`-based visual DAG editor for building/editing pipeline YAML (`PipelineBuilderTab.tsx`, `PipelineCanvas.tsx`, node/edge types). `src/components/Comparison/ComparisonTab.tsx` drives the run-diff view. `src/services/api.ts` is a thin fetch wrapper reading `VITE_PROMPTS_TEST_API_BASE` (empty by default, i.e. same-origin/proxied) for all `/prompts-test-api/*` calls.
