# Build Prompt: Autonomous Podcast Pipeline Improvement Agent

You are building an autonomous improvement agent for a podcast production pipeline. The agent runs as a standalone Python script, iterates on pipeline configuration and prompts to improve podcast quality.

Read this entire document before writing any code.

---

## System Overview

The system has two layers:

**Layer 1 — The Pipeline** (`engine.py`): Executes podcast production. Reads a YAML config, calls an external LLM API for each stage, writes outputs. You will build this.

**Layer 2 — The Agent** (`agent.py`): Reads pipeline outputs, proposes changes to config/prompts, runs the pipeline again, reads evaluations, decides next step. You will also build this.

### LLM Split

The two layers use **different LLMs**:

- **Pipeline LLM** (engine.py): External API — Google Gemini (`gemini-2.5-flash`). This is where the expensive content generation happens (architect, researcher, outliner, scriptwriter, evaluator).
- **Agent LLM** (agent.py): Local model via Ollama. The agent only reasons about what to change — it never generates podcast content. A small local model is sufficient.

This split means the heavy work is done by the external API, while the decision-making loop runs cheaply on the local machine.

The agent controls the pipeline entirely through files and CLI calls — it never imports or calls `engine.py` directly.

---

## Directory Structure

```
project/
  engine.py              # Pipeline executor — interprets pipeline YAML
  agent.py               # Autonomous improvement agent

  pipeline/
    duo_long.yaml        # Pipeline definition for 30-min two-host format
    solo_short.yaml      # Pipeline definition for 5-min solo format

  prompts/
    architect-duo-long.md
    researcher.md
    outline-duo-long.md
    outline-solo-short.md
    scriptwriter-duo-long.md
    scriptwriter_5min_solo.md

  schemas/
    blueprint.schema.json
    outline.schema.json

  evaluation/
    goals.md             # What a good podcast looks like (written by human, read by evaluator)
    test_topics.yaml     # Fixed topics used for all evaluation runs
    evaluator_prompt.md  # Prompt sent to the LLM judge

  runs/
    run_001/
      manifest.json
      blueprint.json
      research.md
      outline.json
      script.txt
      evaluation.json
      snapshots/         # Copies of all prompt files and pipeline YAML used in this run
        architect-duo-long.md
        researcher.md
        ...
        duo_long.yaml
      pipeline.log
    run_002/
      ...

  experiments/
    exp_001.json         # Agent's log of what it tried and why
    ...
```

---

## Part 1: Pipeline YAML Format

Each format has its own YAML file. Here is the full specification.

### Execution Types

Every stage has an `execution` field with one of four values:

**`single`** — one LLM call, one output.

**`map`** — iterate over a list from a previous stage's output. One LLM call per item. Outputs are saved per-item and optionally aggregated.

**`map_with_context`** — same as `map`, but each iteration receives the accumulated outputs of all previous iterations. Used for the scriptwriter, which needs to see previously written scenes.

**`loop_until`** — call LLM repeatedly until a condition is met or `max_iterations` is reached. Reserved for future use (critic loop). The engine must support parsing this type but does not need to implement it yet — raise `NotImplementedError` with a clear message.

### Input Reference Syntax

Inputs reference previous stage outputs using `{{stage_id.field}}` syntax. Examples:

- `{{user.topic}}` — user input field named `topic`
- `{{architect.blueprint}}` — the `blueprint` output of the `architect` stage
- `{{architect.blueprint.segments}}` — the `segments` field inside `blueprint`
- `{{outliner.outline.scenes}}` — the `scenes` list inside `outline`
- `{{researcher.aggregate}}` — the aggregated output of a `map` stage

The engine resolves these references at runtime by reading the relevant output files from the current run directory.

### Aggregate Strategies

When a `map` or `map_with_context` stage produces multiple outputs, it can aggregate them:

- `concat` — concatenate all outputs as plain text, in order
- `concat_with_headers` — concatenate with a markdown header before each item, using the item's name or index
- `structured_json` — wrap all per-item outputs in a JSON array (used when downstream stages need structured access)

### On-Failure Strategies

Each stage can define `on_failure`:

- `retry` — retry up to `max_attempts` times before failing
- `skip` — log the error, skip this item (only valid for `map` stages), continue
- `abort` — stop the pipeline immediately and write failure info to manifest

### Full YAML Example (duo_long format)

```yaml
format: duo_long
description: "30-minute two-host podcast"

stages:
  - id: architect
    execution: single
    prompt: prompts/architect-duo-long.md
    inputs:
      topic: "{{user.topic}}"
      format: "{{user.format}}"
    outputs:
      blueprint:
        file: blueprint.json
        schema: schemas/blueprint.schema.json
        required_fields: [segments, detected_genre, episode_title]
    on_failure:
      strategy: retry
      max_attempts: 2

  - id: researcher
    execution: map
    over: "{{architect.blueprint.segments}}"
    item_var: segment
    prompt: prompts/researcher.md
    inputs:
      segment: "{{segment}}"
    outputs:
      per_item: "research_{{segment.segment_name}}.md"
      aggregate:
        file: research.md
        strategy: concat_with_headers
    on_failure:
      strategy: retry
      max_attempts: 2

  - id: outliner
    execution: single
    prompt: prompts/outline-duo-long.md
    inputs:
      blueprint: "{{architect.blueprint}}"
      research: "{{researcher.aggregate}}"
    outputs:
      outline:
        file: outline.json
        schema: schemas/outline.schema.json
        required_fields: [scenes, outline_metadata]
    on_failure:
      strategy: retry
      max_attempts: 2

  - id: scriptwriter
    execution: map_with_context
    over: "{{outliner.outline.scenes}}"
    item_var: scene
    accumulate_var: previous_scenes
    prompt: prompts/scriptwriter-duo-long.md
    inputs:
      scene: "{{scene}}"
      outline: "{{outliner.outline}}"
      research: "{{researcher.aggregate}}"
      previous_scenes: "{{previous_scenes}}"
    outputs:
      per_item: "scene_{{scene.scene_number}}.txt"
      aggregate:
        file: script.txt
        strategy: concat
    on_failure:
      strategy: retry
      max_attempts: 2

user_inputs:
  - key: topic
    type: string
    required: true
  - key: format
    type: string
    required: true
```

---

## Part 2: Engine (`engine.py`)

### Responsibilities

1. Parse a pipeline YAML file
2. Accept user inputs (topic, format, any additional fields defined in `user_inputs`)
3. Execute stages in order, resolving input references
4. Write all outputs to a run directory under `runs/run_{N}/`
5. Write a `manifest.json` at the end of every run (success or failure)
6. Save snapshots of all prompt files and the pipeline YAML to `runs/{run_id}/snapshots/`
7. Validate JSON outputs against schemas when a schema is specified
8. Handle failures according to `on_failure` strategy

### LLM Integration

Use the Google Gemini API (`google-genai` library). Use `gemini-2.5-flash` as the default model. The model name should be a constant at the top of the file so it is easy to change.

Prompt construction: load the prompt file, replace `{{PLACEHOLDER}}` tokens with the resolved input values using simple string replacement. When an input value is a dict or list, serialize it to JSON before substituting.

### Run Directory

Every run gets a unique directory: `runs/run_{N}/` where N is zero-padded to 3 digits (run_001, run_002, etc.). Determine N by counting existing run directories.

### Manifest Format

Write `manifest.json` at the end of every run:

```json
{
  "run_id": "run_001",
  "timestamp": "2025-01-15T10:30:00Z",
  "pipeline_file": "pipeline/duo_long.yaml",
  "pipeline_hash": "<sha256 of the YAML file contents>",
  "prompt_hashes": {
    "architect": "<sha256 of prompts/architect-duo-long.md>",
    "researcher": "<sha256 of prompts/researcher.md>",
    "outliner": "<sha256>",
    "scriptwriter": "<sha256>"
  },
  "user_inputs": {
    "topic": "The invention of SQL",
    "format": "duo_long"
  },
  "stage_results": {
    "architect": {
      "status": "ok",
      "attempts": 1,
      "duration_ms": 3400
    },
    "researcher": {
      "status": "ok",
      "attempts": 1,
      "items_total": 4,
      "items_succeeded": 4,
      "items_failed": 0,
      "duration_ms": 18000
    },
    "outliner": {
      "status": "ok",
      "attempts": 1,
      "duration_ms": 4200
    },
    "scriptwriter": {
      "status": "ok",
      "attempts": 1,
      "items_total": 10,
      "items_succeeded": 10,
      "items_failed": 0,
      "duration_ms": 45000
    }
  },
  "overall_status": "ok"
}
```

If a stage fails fatally, set `overall_status` to `"failed"` and add a `"failure_reason"` field.

### CLI Interface

```
python engine.py \
  --pipeline pipeline/duo_long.yaml \
  --topic "The invention of SQL" \
  --format duo_long \
  --run-id run_001        # optional, auto-generated if omitted
```

Additional user input fields defined in `user_inputs` can be passed as `--key value` arguments.

### Schema Validation

For outputs that specify a `schema` file: after writing the output file, validate that all `required_fields` exist at the top level of the JSON. If validation fails, treat it as a stage failure and apply the `on_failure` strategy.

Do not use a full JSON Schema validator library — simple required-field checking is sufficient for now.

---

## Part 3: Evaluation

### test_topics.yaml

```yaml
topics:
  - id: sql_history
    topic: "The invention of SQL"
    format: duo_long
    tags: [historical, technical]

  - id: gps_explainer
    topic: "How GPS works"
    format: solo_short
    tags: [technical, scientific]

  - id: french_revolution
    topic: "The French Revolution"
    format: duo_long
    tags: [historical, narrative]
```

### Evaluator

The evaluator is a separate function (or module) that:

1. Reads a completed run directory
2. Reads `evaluation/goals.md`
3. Reads `evaluation/evaluator_prompt.md`
4. Sends the script + goals + prompt to a smart LLM (use `gemini-2.5-pro` for evaluation)
5. Parses the response and writes `evaluation.json` to the run directory

### Evaluation Output Format

```json
{
  "run_id": "run_001",
  "topic": "The invention of SQL",
  "format": "duo_long",
  "evaluator_model": "gemini-2.5-pro",
  "overall_score": 7.2,
  "dimension_scores": {
    "narrative_quality": 8.0,
    "technical_depth": 6.0,
    "speakability": 7.5,
    "engagement": 7.0,
    "accuracy": 8.0
  },
  "reasoning": "Free text from the LLM judge explaining the scores...",
  "evaluated_at": "2025-01-15T10:35:00Z"
}
```

The dimensions listed above are placeholders — the actual dimensions will be defined later in `goals.md`. The evaluator must parse whatever dimensions the LLM returns as a JSON object and write them as-is. Do not hardcode dimension names in the evaluator code.

The evaluator prompt instructs the LLM to return valid JSON only, with the structure above, where `dimension_scores` is an object with string keys and float values between 0 and 10.

### evaluator_prompt.md (create this file)

Write a prompt that:
- Tells the LLM it is evaluating a podcast script
- Instructs it to read the attached goals document and score the script against those goals
- Specifies the exact JSON output format (overall_score, dimension_scores, reasoning)
- Instructs it to return ONLY valid JSON, no preamble, no markdown fences
- Tells it to base dimension names on the goals document it receives

---

## Part 4: Agent (`agent.py`)

### What the Agent Is

A Python script that runs a self-directed improvement loop. It uses a **local LLM via Ollama** as its reasoning engine. The agent only makes decisions — it never generates podcast content. All content generation happens in `engine.py` via the external Gemini API.

### Agent LLM: Ollama

Use the Ollama Python library (`ollama`) to call the local model. The model name should be a constant at the top of `agent.py`:

```python
AGENT_MODEL = "qwen2.5:7b"  # local model via Ollama
```

The agent does NOT use function calling. Instead, it uses **structured JSON output** — the model always returns a single JSON object describing its next action. The Python code reads this JSON and executes the action.

### Agent Loop

Each iteration follows this pattern:

```
1. Build a context document (current state: runs, scores, prompts, pipeline config)
2. Send context + system prompt to local LLM
3. LLM returns a JSON action object
4. Python executes the action by calling the appropriate tool function
5. Append the tool result to context
6. Repeat steps 2-5 until the LLM returns action "done" or max_steps is reached
7. Log the experiment
8. Start next iteration from step 1
```

The agent runs for a fixed number of iterations specified by `--max-iterations` (default: 5). Each iteration can take multiple steps (multiple LLM calls + tool executions) before concluding.

### Action Format

The local LLM always returns a JSON object with this structure:

```json
{
  "reasoning": "I notice the narrative scores are consistently low across all topics. The researcher prompt does not instruct the researcher to find conflict or tension...",
  "action": "write_file",
  "params": {
    "path": "prompts/researcher.md",
    "content": "... full new content ..."
  },
  "done": false
}
```

- `reasoning`: The model's explanation of why it is taking this action. Always required.
- `action`: One of the tool names listed below.
- `params`: The parameters for that tool, as a JSON object.
- `done`: Set to `true` when the model has finished the current iteration and wants to log the experiment and move on.

If `done` is `true`, the Python code calls `log_experiment` automatically using the reasoning field as the conclusion, then starts the next iteration.

The system prompt must instruct the model to return ONLY valid JSON, no preamble, no markdown fences, no explanation outside the JSON object.

### Tools

Implement each tool as a plain Python function. The agent loop calls them directly — there is no function-calling API involved.

```python
def read_file(path: str) -> str:
    """Read a file and return its contents as a string.
    Returns the file contents, or an error message if the file does not exist."""

def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it if it does not exist.
    Returns 'ok' on success or an error message on failure."""

def list_runs() -> str:
    """Return a JSON list of all run directories with their manifest summaries.
    Each entry includes: run_id, timestamp, topic, format, overall_status,
    overall_score (if evaluated)."""

def read_run(run_id: str) -> str:
    """Return key contents of a run as a JSON object.
    Includes: manifest, evaluation (if exists), and the script content.
    Does NOT include intermediate files (blueprint, research, outline)
    to keep context small."""

def read_run_full(run_id: str) -> str:
    """Return ALL contents of a run directory as a JSON object.
    Use this when diagnosing a specific stage (e.g. why the research is weak).
    Includes: manifest, evaluation, blueprint, research, outline, script."""

def diff_files(path_a: str, path_b: str) -> str:
    """Return a unified diff between two files."""

def diff_runs(run_id_a: str, run_id_b: str, stage: str = "script") -> str:
    """Return a diff of a specific output file between two runs.
    stage can be: 'script', 'outline', 'blueprint', 'research'."""

def run_pipeline(topic: str, format: str, extra_inputs: dict = None) -> str:
    """Execute the pipeline for a given topic and format by calling engine.py as a subprocess.
    Returns the run_id of the new run, or an error message if the pipeline failed."""

def run_evaluation(run_id: str) -> str:
    """Run the LLM evaluator on a completed run and write evaluation.json.
    Returns the evaluation summary (overall_score and dimension_scores) as a JSON string."""

def run_all_test_topics(extra_inputs: dict = None) -> str:
    """Run the pipeline on ALL topics in evaluation/test_topics.yaml,
    then run evaluation on all resulting runs.
    Returns a JSON summary: {topic_id: {run_id, overall_score, dimension_scores}}."""

def log_experiment(name: str, hypothesis: str, changes_made: list,
                   results: dict, conclusion: str) -> str:
    """Write an experiment log entry to experiments/exp_{N}.json.
    changes_made: list of file paths that were modified.
    results: dict mapping topic_id to score delta
             e.g. {"sql_history": +0.5, "gps_explainer": -0.2}
    Returns the experiment file path."""

def revert_file(path: str, run_id: str) -> str:
    """Revert a prompt or pipeline YAML file to the version used in a specific run.
    Restores from the snapshot saved at runs/{run_id}/snapshots/.
    Returns 'ok' or an error message."""
```

### Dispatching Actions

The agent loop maps action names to tool functions:

```python
TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "list_runs": list_runs,
    "read_run": read_run,
    "read_run_full": read_run_full,
    "diff_files": diff_files,
    "diff_runs": diff_runs,
    "run_pipeline": run_pipeline,
    "run_evaluation": run_evaluation,
    "run_all_test_topics": run_all_test_topics,
    "log_experiment": log_experiment,
    "revert_file": revert_file,
}
```

After parsing the JSON response, call `TOOLS[action](**params)` and append the result to the running context before the next LLM call.

### Context Document

Before each LLM call, build a context string that includes:

1. The current pipeline YAML (summarized, not the full file)
2. The last 5 experiment logs (if any)
3. The current evaluation scores for all test topics across all runs (a compact table)
4. The result of the last tool call (if any)

Keep the context under ~3000 tokens. Truncate older history if needed — the local model has a limited context window.

### Agent System Prompt

Write a system prompt for the agent LLM that explains:
- Its role: improve podcast quality by iterating on prompts and pipeline configuration
- The available actions and when to use each
- The improvement loop it should follow
- That it must form an explicit hypothesis before making changes
- That it should revert changes that make scores worse
- That it should make at most 2-3 changes per iteration to isolate causality
- That changes to the pipeline YAML (adding/removing stages, changing execution types) are allowed
- That new `user_input` fields can be proposed by adding them to the YAML and updating relevant prompts
- That it must ALWAYS return valid JSON matching the action format — no prose, no markdown

### Agent CLI

```
python agent.py \
  --max-iterations 5 \
  --format duo_long        # optional, runs all formats if omitted
```

---

## Part 5: Initial Content Files to Create

### `evaluation/goals.md`

Write a placeholder goals document describing what makes a good podcast episode. Include at least 5 dimensions with brief descriptions. These will be refined later — make them reasonable defaults. Example dimensions: narrative quality, technical depth, speakability, engagement, factual accuracy.

### `evaluation/evaluator_prompt.md`

As described in Part 3.

### `evaluation/test_topics.yaml`

As shown in Part 3.

### `schemas/blueprint.schema.json`

Minimal schema with required fields: `segments`, `detected_genre`, `episode_title`, `total_target_words`.

### `schemas/outline.schema.json`

Minimal schema with required fields: `scenes`, `outline_metadata`.

---

## Implementation Notes

- Use `python-dotenv` to load a `.env` file for the Gemini API key (`GEMINI_API_KEY`)
- All file paths in YAML and tool calls are relative to the project root
- Both scripts must be runnable from the project root directory
- Use `rich` for console output if available, otherwise plain print
- Log all LLM calls (prompt length, response length, duration) to `pipeline.log` in each run directory
- The agent imports nothing from the engine — they communicate only through the filesystem and subprocess calls
- Write clean, readable Python. Prefer clarity over cleverness.
- Include a `requirements.txt`

---

## What to Build First

Build in this order:

1. Directory structure and placeholder files
2. `engine.py` — start with `single` and `map` execution types, add `map_with_context` once those work
3. Test the engine manually on the SQL topic
4. Evaluator function (can be in `engine.py` or a separate `evaluator.py`)
5. `agent.py` — implement all tool functions first, then the agent loop

Do not proceed to the next step until the current one runs without errors on the SQL test topic.
