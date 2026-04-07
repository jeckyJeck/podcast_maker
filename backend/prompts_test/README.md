# prompts_test

Additive-only prompt testing harness for partial podcast-agent runs.

## What it gives you

- Run one stage or a chain of stages.
- Inject intermediate artifacts (`blueprint.json`, `research.md`, `outline.json`).
- Override prompt file per stage without touching existing prompt files.
- Save outputs, resolved prompts, and run metadata under `prompts_test/runs/`.
- Compare outputs between two runs.
- Uses the shared `LLMProvider` abstraction (Gemini via adapter) and does not call Gemini API directly from stage code.

## Run from backend

```powershell
cd backend
python -m prompts_test.cli list-runs
```

## Isolated API for UI

Prompt testing API is intentionally separated from the existing podcast API.

- Existing production flow remains under routes like `/create-podcast/` and `/status/{task_id}`.
- New prompt-lab flow is namespaced under `/prompts-test-api/*`.

Main endpoints:

- `GET /prompts-test-api/meta`
- `GET /prompts-test-api/runs`
- `GET /prompts-test-api/runs/{run_id}`
- `GET /prompts-test-api/runs/{run_id}/files/{file_name}`
- `POST /prompts-test-api/runs`
- `GET /prompts-test-api/tasks/{task_id}`
- `POST /prompts-test-api/compare`

Local-dev auth bypass (prompts-test API only):

```powershell
cd backend
$env:PROMPTS_TEST_API_BYPASS_AUTH="true"
uvicorn app.main:app --reload --port 8080
```

With this flag enabled, only `/prompts-test-api/*` skips JWT auth for local testing.
Existing routes keep their normal auth behavior.

Request model highlights for `POST /prompts-test-api/runs`:

- `topic`, `stages`, `format`, `host_ids`
- `injected` supports either file paths or inline content (`*_path` or `*_json` / `*_text`)
- `prompt_overrides` supports either file path or inline text per stage
- `async_mode` to choose background run or synchronous response

## Examples

Run only researcher with injected blueprint:

```powershell
cd backend
python -m prompts_test.cli run ^
  --topic "ford fulkerson" ^
  --stages researcher ^
  --blueprint-file "prompts_test/fixtures/blueprint.sample.json"
```

Run outliner and scriptwriter from injected inputs:

```powershell
cd backend
python -m prompts_test.cli run ^
  --topic "SQL joins" ^
  --stages outliner,scriptwriter ^
  --blueprint-file "prompts_test/fixtures/blueprint.sample.json" ^
  --research-file "prompts_test/fixtures/research.sample.md"
```

Override only researcher prompt:

```powershell
cd backend
python -m prompts_test.cli run ^
  --topic "react hooks" ^
  --stages researcher ^
  --blueprint-file "prompts_test/fixtures/blueprint.sample.json" ^
  --override-researcher "prompts/researcher.md"
```

Diff two run outputs:

```powershell
cd backend
python -m prompts_test.cli compare ^
  --run-a 20260324_120000_react_hooks ^
  --run-b 20260324_121500_react_hooks ^
  --file research.md
```

## Output layout

Each run creates one folder in `prompts_test/runs/` with:

- `run_manifest.json`
- Stage outputs (`blueprint.json`, `research.md`, `outline.json`, `script.txt`) when generated
- Resolved prompt snapshots (`prompt_<stage>.txt`) for stages that executed
- Snapshot files for injected artifacts that were not regenerated in the run
