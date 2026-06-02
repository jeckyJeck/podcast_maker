# lab_backend

Standalone backend for prompts_lab experiments.

This module is isolated from production backend routes and runs the pipeline through:

- architect
- researcher
- outliner
- scriptwriter

TTS/audio generation is intentionally excluded.

## API

The API namespace is unchanged for UI compatibility:

- `/prompts-test-api/*`
