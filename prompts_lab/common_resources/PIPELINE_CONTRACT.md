# Prompt Pipeline YAML Contract v1

This document defines the YAML format accepted by the shared prompt pipeline engine.
It is written for humans and AI agents that need to create or edit pipeline files.

The core idea:

- A pipeline has external `inputs`.
- A pipeline has ordered `stages`.
- Each stage renders a prompt by binding placeholders to sources.
- Each stage receives a model `response`.
- Each stage exposes named `outputs` that later stages can consume.

## Top-Level Shape

```yaml
version: 1
id: stable_pipeline_id
name: Human readable name
description: Optional explanation

defaults:
  model:
    provider: gemini
    name: gemini-2.5-flash
  failure:
    strategy: retry
    max_attempts: 2
  output_contract:
    inject_into_prompt: true

inputs:
  topic:
    type: text
    required: true
  host_name:
    type: text
    default: Alex

stages:
  - id: architect
    type: llm
    execution: single
    prompt: ...
    bindings: ...
    response: ...
    outputs: ...
```

## Top-Level Fields

`version`
: Required. Must be `1`.

`id`
: Required. Stable machine-readable pipeline id. Use lowercase letters, numbers,
  dashes, and underscores.

`name`
: Optional human-readable name.

`description`
: Optional human-readable description.

`defaults`
: Optional defaults inherited by stages. A stage can override them.

`inputs`
: Required mapping of external values supplied by a UI, agent, CLI, or API.

`stages`
: Required non-empty list. Stages run in order in v1. A stage may consume only
  pipeline inputs, its map item/context, or outputs from previous stages.

## Inputs

```yaml
inputs:
  topic:
    type: text
    required: true
  format:
    type: text
    default: solo_short
  extra_settings:
    type: json
    required: false
```

Allowed input types:

- `text`
- `json`
- `number`
- `boolean`

Rules:

- Each input key must be unique.
- `required` is optional and defaults to `false`.
- `default` is optional.
- If an input is required, clients must provide it unless a default exists.

## Stage Shape

```yaml
stages:
  - id: researcher
    type: llm
    execution: map

    map:
      over: architect.segments
      item_name: segment

    prompt:
      source: file
      path: prompts/researcher.md

    bindings:
      - placeholder: "{{SEGMENT_JSON}}"
        source: item
        format: json

    response:
      kind: text
      per_item_file: outputs/research_{{ item.segment_name }}.md
      aggregate_file: outputs/research.md
      aggregate_strategy: concat_with_headers

    outputs:
      research:
        source: response.aggregate
      research_items:
        source: response.items
```

## Stage Fields

`id`
: Required. Unique within the pipeline. Later stages refer to this id.

`type`
: Required. For v1, only `llm` is defined.

`execution`
: Required. One of:

- `single`: render and run the prompt once.
- `map`: run once per item in a list.
- `map_with_context`: run once per item and expose accumulated previous output
  through `context.<name>`.

`map`
: Required for `map` and `map_with_context`; forbidden for `single`.

`prompt`
: Required. Defines where the prompt text comes from.

`bindings`
: Optional list of placeholder replacements.

`response`
: Required. Defines the raw model response format and file persistence.

`outputs`
: Required mapping. Defines named values exposed to later stages.

`model`
: Optional stage-level model override.

`failure`
: Optional stage-level failure policy override.

## Prompt Sources

File prompt:

```yaml
prompt:
  source: file
  path: prompts/outliner/outline-solo-short.md
```

Inline prompt:

```yaml
prompt:
  source: inline
  text: |
    Write an outline for {{TOPIC}}.
```

Stored template prompt:

```yaml
prompt:
  source: template
  template_id: outliner_default
  revision: latest
```

Rules:

- `source: file` requires `path`.
- `source: inline` requires `text`.
- `source: template` requires `template_id`.
- File paths are resolved relative to the lab backend root.

## Bindings

Bindings tell the engine what to replace inside the prompt.

```yaml
bindings:
  - placeholder: "{{TOPIC}}"
    source: inputs.topic
    format: text
  - placeholder: "{{BLUEPRINT}}"
    source: architect.blueprint
    format: json
```

`placeholder`
: Required. Exact text to replace in the prompt.

`source`
: Required. A source reference. See "Source References".

`format`
: Optional. One of `text` or `json`.

Rules:

- A binding source must exist.
- For file and inline prompts, validators should warn/error if the placeholder
  does not appear in the resolved prompt text.
- If `format` is omitted, the engine may format objects/lists as JSON and scalars
  as text.

## Source References

Allowed source references:

```text
inputs.<input_name>
<previous_stage_id>.<output_name>
item
item.<field>
context.<context_name>
```

Examples:

```yaml
source: inputs.topic
source: architect.segments
source: outliner.outline
source: item
source: item.scene_number
source: context.previous_scenes
```

Rules:

- `inputs.<name>` must point to a top-level input.
- `<stage>.<output>` must point to an output exposed by a previous stage.
- `item` and `item.<field>` are valid only in `map` or `map_with_context` stages.
- `context.<name>` is valid only in `map_with_context` stages.

## Map Execution

`map` runs a stage once for each item in a list.

```yaml
execution: map
map:
  over: architect.segments
  item_name: segment
```

`over`
: Required source reference. It must resolve at runtime to a list.

`item_name`
: Required descriptive name for the item. The engine always exposes the current
  item as `item`; `item_name` is metadata for humans/UI and may also be used by
  engines as an alias.

`map_with_context` adds accumulated context:

```yaml
execution: map_with_context
map:
  over: outliner.scenes
  item_name: scene
  context_name: previous_scenes
  context_strategy: concat
```

`context_name`
: Required for `map_with_context`. It is exposed as `context.<context_name>`.

`context_strategy`
: Optional. Defaults to `concat`.

## Response

`response` describes the raw model result for the stage.

Single JSON response:

```yaml
response:
  kind: json
  file: outputs/blueprint.json
  schema: engine/schemas/blueprint.schema.json
  extraction:
    mode: json_object
    allow_markdown_fence: true
```

Single text response:

```yaml
response:
  kind: text
  file: outputs/script.txt
```

Map text response:

```yaml
response:
  kind: text
  per_item_file: outputs/research_{{ item.segment_name }}.md
  aggregate_file: outputs/research.md
  aggregate_strategy: concat_with_headers
```

Fields:

`kind`
: Required. `text` or `json`.

`file`
: Required for `single` stages. Run-relative output path.

`per_item_file`
: Optional for `map` and `map_with_context`. Run-relative path pattern.

`aggregate_file`
: Optional for `map` and `map_with_context`. Run-relative path for aggregate output.

`aggregate_strategy`
: Optional. One of `concat`, `concat_with_headers`, `structured_json`.

`schema`
: Optional for JSON responses. Path to a JSON Schema file, relative to lab backend root.

`extraction`
: Optional JSON extraction policy.

## Outputs

Outputs expose named values from the stage response to later stages.

```yaml
outputs:
  outline:
    source: response
  scenes:
    source: response.scenes
```

For a `single` stage:

```text
response
response.<json_field>
```

For a `map` or `map_with_context` stage:

```text
response.items
response.aggregate
```

Examples:

```yaml
outputs:
  full_blueprint:
    source: response
  segments:
    source: response.segments
  research:
    source: response.aggregate
  research_items:
    source: response.items
```

Rules:

- Each stage must expose at least one output.
- Output names are what later stages use: `architect.segments`, `outliner.outline`.
- Use `source: response` to pass the whole raw parsed response forward.

## Failure Policy

```yaml
failure:
  strategy: retry
  max_attempts: 2
```

Allowed strategies:

- `abort`
- `retry`
- `skip`

`max_attempts` is meaningful for `retry`.

## Validation Checklist

A valid v1 pipeline must satisfy:

- Top-level object has `version: 1`, `id`, `inputs`, and `stages`.
- Stage ids are unique.
- Stage ids and input ids use simple machine-readable identifiers.
- Every binding source points to an existing input, previous stage output, item,
  or context.
- Every map `over` source exists.
- `single` stages do not define `map`.
- `map` and `map_with_context` stages define `map.over` and `map.item_name`.
- `map_with_context` defines `map.context_name`.
- Prompt source has the required fields.
- File prompt paths exist.
- JSON schema paths exist when provided.
- Response shape matches execution mode.
- Output response references are legal for the stage execution.

