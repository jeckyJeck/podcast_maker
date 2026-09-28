# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

`prompts_lab` is a sandbox for iterating on podcast-generation prompts via arbitrary, YAML-defined pipelines. It lets a human (via `front_client`) or an autonomous agent (`optimization_agent`, not yet wired to a UI) define a pipeline as YAML with arbitrary stage ids, run it against real LLMs, inspect per-stage prompts/outputs, and diff results across runs. Audio/TTS generation is intentionally out of scope here — that lives in the main podcastMaker app, not this lab.

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

CLI for inspecting/comparing run directories (from `lab_backend/`) — pipeline *execution* goes through the API's `POST /pipelines/run`, not the CLI:
```
python -m prompts_test.cli compare --run-a <name> --run-b <name> --file outputs/research.md
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
- `app/routers/prompts_test_api.py` — all HTTP routes: `/meta` (hosts/formats), run listing/inspection/file-serving/compare, CRUD for saved prompt templates, and the pipeline builder endpoints (list/get/save/delete pipeline YAML under `common_resources/templates/`, plus `POST /pipelines/run`, the single execution entry point). `POST /pipelines/run` is registered *before* `GET|POST|DELETE /pipelines/{pipeline_id}` — Starlette matches routes in registration order, so the literal `/pipelines/run` path must come first or it gets shadowed by the `{pipeline_id}` pattern.
- `app/hosts_config.py` — `AVAILABLE_HOSTS`, the host registry backing `/meta`'s `hosts`/`default_host_ids` fields, loaded from `common_resources/hosts.json` (shared reference data, not lab-backend-specific). Lives under `app/` rather than `utils/` because `prompts_test_api.py` is its only consumer — it's app-layer domain data, not cross-cutting infra. Note: the frontend currently fetches `/meta` but never reads the `hosts` field it returns (stored in an underscore-prefixed, unused React state) — the host registry isn't wired into pipeline building today.
- `engine/` — the generic pipeline engine, stage-id-agnostic throughout:
  - `validate_pipeline.py` + `schemas/*.schema.json` — validates a pipeline dict against `PIPELINE_CONTRACT.md` before it's run.
  - `executor.py` — the interpreter: `run_pipeline()` loops over a validated pipeline's `stages` and dispatches by `execution` (`single` / `map` / `map_with_context`), rendering prompts via `bindings`, calling the `LLMProvider`, applying `failure` retry/skip policy, writing `response.file`/`per_item_file`/`aggregate_file`, and populating each stage's `outputs`. Stages can be selectively skipped (`run_stages`) with their context bucket seeded from `mock_outputs[stage_id]` instead — used by `front_client`'s per-node "Execute Stage" / "Mock Output" toggle.
  - `sources.py` — resolves contract source references (`inputs.<name>`, `<stage>.<output>`, `item[.field]`, `context.<name>`) and renders `bindings` into prompt text.
  - `inputs.py` — resolves a pipeline's declared `inputs` block against a request payload (defaults, required checks, type coercion).
  - `tools.py` — maps contract `tools` entries (e.g. `google_search`) to provider-specific tool objects attached to the LLM call.
- `prompts_test/` — supporting utilities, not stage-specific: `compare.py` (diffs a file between two run directories), `cli.py` (`compare`/`list-runs` only — pipeline execution goes through the API, not the CLI).
- `utils/`, `services/` — provider/service plumbing shared conceptually with the main app (previously vendored under a `podcast_maker/` package, flattened to top-level since only these modules were actually reachable): `utils/` holds only dependency-free infra imported by more than one layer — `paths.py` (`BACKEND_ROOT`) and `logging_config.py` (`get_logger`, used by both `app/main.py` and `services/gemini_adapter.py`). `services/{llm_provider,llm_provider_factory,gemini_adapter,rate_limiter}.py` (LLM abstraction, Gemini-backed — `generate_text`/`generate_json` raise rather than silently returning empty/malformed results, so the executor's failure policy sees real errors; `rate_limiter.py` is a generic per-minute/per-day token-bucket used only by `gemini_adapter.py`), `services/prompt_template_store.py` (persistence for user-saved prompt templates, keyed by a fixed local user id since auth is disabled in this lab). The old `podcast_maker/core/{architect,outliner,scriptwriter,prompt_manager}.py` and `services/{storage_provider,local_storage_provider}.py` were leftover/unreferenced from the old hardcoded 4-stage runner and have been deleted — the real prompt text now lives inline in `common_resources/templates/*/pipeline.yaml` (`prompt.source: inline`).

Auth is stubbed out everywhere in this lab (`AuthContext(user_id="lab-local-user")`, `method="disabled"`) — there is no real login here, unlike the main app's `AuthProvider` abstraction.

### Run artifacts

Every run writes to a directory under `common_resources/experiments_runs/` (gitignored) containing a `run_manifest.json` (per-stage status/attempts/duration and overall status) and whatever output files each stage's `response.file`/`per_item_file`/`aggregate_file` declares — paths are pipeline-defined (e.g. `outputs/blueprint.json`), not fixed. `GET /runs/{run_id}/files/{file_name}` serves any file under that run's directory (nested paths allowed; `..`/absolute-path escapes are rejected) — there's no fixed filename allowlist anymore since filenames are pipeline-defined.

### front_client

Vite/React app (`front_client_new` package). `src/components/PipelineEditor/` is an `@xyflow/react`-based visual DAG editor for building/editing pipeline YAML (`PipelineBuilderTab.tsx`, `PipelineCanvas.tsx`, node/edge types). `src/components/Comparison/ComparisonTab.tsx` drives the run-diff view. `src/services/api.ts` is a thin fetch wrapper reading `VITE_PROMPTS_TEST_API_BASE` (empty by default, i.e. same-origin/proxied) for all `/prompts-test-api/*` calls.
