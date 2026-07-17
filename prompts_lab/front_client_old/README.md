# prompts_lab

Developer-only UI for prompt testing and partial stage execution.

## Why This App Exists

This app is intentionally separated from the end-user product UI. It talks only to the isolated backend namespace `/prompts-test-api/*`.

## Features

- Choose format (`dialogue` / `solo`), hosts, and topic.
- Load default prompts and default injected outputs.
- Edit prompt and output per stage in large editors.
- Copy and clear content with floating controls per editor.
- Choose which stages to run with per-stage toggles.
- Load previous runs and restore prompt/output windows.
- Compare `research.md` between two runs.

## Notes

- This is a developer tool and is not part of the end-user frontend app.
- Stage output editors are used as injected inputs when stages are skipped.
