# CLAUDE.md

Guidance for Claude Code when working in `prompts_lab/`.

## Purpose

`prompts_lab` is a sandbox for iterating on podcast-generation prompts via YAML-defined pipelines. A human (via `front_client`) or an autonomous agent (`optimization_agent`) defines/edits a pipeline, runs it against real LLMs, inspects per-stage prompts/outputs, and compares runs. Audio/TTS is out of scope here.

## There is no lab backend

The lab uses the main backend (`../backend`) over HTTP, under `/prompts-test-api`. All the engine, evaluation, resources and data live there:

- Engine: `backend/podcast_maker/engine/` (`executor`, `validate_pipeline`, `sources`, `inputs`, `tools`). Contract: `backend/resources/PIPELINE_CONTRACT.md` (read it before editing a pipeline YAML or the engine).
- Pipelines: `backend/resources/pipelines/<id>/pipeline.yaml` (`duo_long`, `solo_short` are also what production runs). Schemas: `backend/resources/schemas/`. Rubrics: `backend/resources/eval_rubrics/`.
- Runtime data (gitignored): `backend/data/prompt_templates/`, `backend/data/experiment_runs/`.
- Routes: `backend/app/routers/prompts_test_api.py` (`/meta`, `/runs*`, `/compare`, `/prompt-templates`, `/pipelines*`, `/pipeline-templates`, evaluation). `POST /pipelines/run` is registered before `/pipelines/{pipeline_id}` on purpose (route order).
- Auth: routes use `get_lab_user`. With `LAB_AUTH_BYPASS=true` (local `backend/.env`) requests run as `lab-local-user`; otherwise real auth applies. The app refuses to start with the flag if `APP_ENV=production`.

## Folder map

- `front_client/` - React/Vite UI (visual pipeline builder, run/compare, evaluation). Dev server on :5180, proxies `/prompts-test-api` to the backend on :8000.
- `optimization_agent/` - autonomous agent. Talks to the backend over HTTP (`backend_client.py`); keeps only local scratch (`workspace/`, `experiments/`) and its own `test_topics.yaml`.

## Commands

Backend + UI: run `run_prompts_lab.ps1` from the repo root (local, gitignored), or manually:
```
cd backend && LAB_AUTH_BYPASS=true uvicorn app.main:app --reload --port 8000   # backend venv: backend/myEnv
cd prompts_lab/front_client && npm run dev
```
Agent (backend must be running; `BACKEND_URL` defaults to http://127.0.0.1:8000):
```
python optimization_agent/agent.py --format duo_long --task "..."
```
Frontend scripts: `npm run build` (tsc && vite build), `npm run lint`. No test suite exists in this subtree.

## front_client

`src/components/PipelineEditor/` is an `@xyflow/react` DAG editor for pipeline YAML. `src/components/Comparison/ComparisonTab.tsx` drives run diffs, `src/components/Evaluation/EvaluationTab.tsx` the rubric evaluation. `src/services/api.ts` wraps fetch and reads `VITE_PROMPTS_TEST_API_BASE` (empty = same-origin/proxied).
