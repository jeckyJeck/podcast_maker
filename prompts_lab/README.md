# prompts_lab

Developer-only UI for prompt testing and partial stage execution.

## Why this app exists

This app is intentionally separated from the end-user product UI.
It talks only to the isolated backend namespace `/prompts-test-api/*`.

## Features

- Choose format (`dialogue` / `solo`), hosts, and topic.
- Load default prompts and default injected outputs.
- Edit prompt + output per stage in large editors.
- Copy/Clear floating controls per editor.
- Choose which stages to run with per-stage toggles.
- Load previous runs and restore prompt/output windows.
- Compare `research.md` between two runs.

## Run

```powershell
cd prompts_lab/lab_backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8081
```

```powershell
cd prompts_lab
npm install
npm run dev
```

Vite runs on `http://localhost:5180` and proxies `/prompts-test-api` to `http://localhost:8081` by default.

Optional: override backend origin

```powershell
$env:PROMPTS_LAB_BACKEND_ORIGIN="http://localhost:8081"
npm run dev
```

## Auth

`prompts_lab/lab_backend` is dev-only and does not enforce user auth.

## Notes

- This is a developer tool and is not part of the end-user frontend app.
- Stage output editors are used as injected inputs when stages are skipped.
