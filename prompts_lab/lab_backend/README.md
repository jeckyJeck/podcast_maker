# lab_backend

Standalone backend for prompts_lab experiments.

This module is isolated from production backend routes and runs the pipeline through:

- architect
- researcher
- outliner
- scriptwriter

TTS/audio generation is intentionally excluded.

## Run

```powershell
cd prompts_lab/lab_backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8081
```

## API

The API namespace is unchanged for UI compatibility:

- /prompts-test-api/*

Useful checks:

```powershell
curl http://127.0.0.1:8081/health
curl http://127.0.0.1:8081/prompts-test-api/meta
```

## Auth

This module is dev-only and does not enforce user auth.
Prompt template data is stored locally under:

- prompts_test/prompt_templates/lab-local-user/
