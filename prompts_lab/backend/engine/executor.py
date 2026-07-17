"""
Pipeline Execution Engine.
Runs generic prompt pipelines defined in YAML.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from services.gemini import GeminiAdapter
from services.llm import LLMProvider, LLMResponse, TokenUsage
import services.templates as templates

# Root of the backend
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineExecutor:
    """
    Executor for version 1 Prompt Pipelines.
    Runs stages in sequence, resolving inputs, bindings, loops, and outputs.
    """

    def __init__(
        self,
        pipeline_data: Dict[str, Any],
        inputs: Dict[str, Any],
        run_stages: Optional[List[str]] = None,
        mock_outputs: Optional[Dict[str, Any]] = None,
        runs_root: Optional[Path] = None,
        user_id: str = "lab-local-user"
    ):
        self.pipeline_data = pipeline_data
        self.raw_inputs = inputs
        self.user_id = user_id
        
        self.stages_to_run = run_stages
        self.mock_outputs = mock_outputs or {}
        
        # Directories
        self.runs_root = runs_root or (BACKEND_ROOT.parent / "common_resources" / "experiments_runs")
        self.runs_root.mkdir(parents=True, exist_ok=True)
        
        # State
        self.inputs: Dict[str, Any] = {}
        self.stage_outputs: Dict[str, Dict[str, Any]] = {}
        self.stage_records: List[Dict[str, Any]] = []
        
        # Global token tracker (accumulates across all models/adapters)
        self.total_prompt_tokens = 0
        self.total_response_tokens = 0
        self.total_tokens_used = 0
        
        self._initialize_inputs()
        self._initialize_mock_outputs()

    def _initialize_inputs(self) -> None:
        """Parse external inputs applying defaults from spec."""
        spec_inputs = self.pipeline_data.get("inputs", {})
        for key, spec in spec_inputs.items():
            val = self.raw_inputs.get(key)
            if val is None:
                val = spec.get("default")
            
            if val is None and spec.get("required", False):
                raise ValueError(f"Required input '{key}' is missing")
            
            self.inputs[key] = val

    def _initialize_mock_outputs(self) -> None:
        """Initialize stage outputs with mocks for stages not run."""
        for stage_id, mock in self.mock_outputs.items():
            self.stage_outputs[stage_id] = mock

    def _resolve_source(
        self,
        source: str,
        item: Any = None,
        context_val: Any = None,
        context_name: Optional[str] = None
    ) -> Any:
        if source.startswith("inputs."):
            input_name = source.split(".", 1)[1]
            return self.inputs.get(input_name)

        if source == "item":
            return item

        if source.startswith("item."):
            field = source.split(".", 1)[1]
            if isinstance(item, dict):
                return item.get(field)
            return getattr(item, field, None)

        if source.startswith("context."):
            ctx_name = source.split(".", 1)[1]
            if ctx_name == context_name:
                return context_val
            return None

        parts = source.split(".")
        if len(parts) == 2:
            stage_id, output_name = parts
            return self.stage_outputs.get(stage_id, {}).get(output_name)

        return None

    def _render_prompt(
        self,
        prompt_template: str,
        bindings: List[Dict[str, Any]],
        item: Any = None,
        context_val: Any = None,
        context_name: Optional[str] = None
    ) -> str:
        prompt_text = prompt_template
        for binding in bindings:
            placeholder = binding.get("placeholder")
            if not placeholder:
                continue
            source = binding.get("source")
            if not source:
                continue
            fmt = binding.get("format", "text")

            val = self._resolve_source(source, item, context_val, context_name)

            if val is None:
                formatted_val = ""
            elif fmt == "json":
                formatted_val = json.dumps(val, indent=2, ensure_ascii=False)
            else:
                if isinstance(val, (dict, list)):
                    formatted_val = json.dumps(val, indent=2, ensure_ascii=False)
                else:
                    formatted_val = str(val)

            prompt_text = prompt_text.replace(placeholder, formatted_val)
        return prompt_text

    def _load_prompt_template(self, prompt_spec: Dict[str, Any]) -> str:
        source = prompt_spec.get("source")
        if source == "inline":
            return prompt_spec.get("text", "")
        
        if source == "file":
            path_str = prompt_spec.get("path")
            if not path_str:
                raise ValueError("Path is required for file prompt source")
            # Try resolving relative to backend or backend parent
            resolved = BACKEND_ROOT / path_str
            if not resolved.is_file():
                resolved = BACKEND_ROOT.parent / path_str
            if not resolved.is_file():
                raise FileNotFoundError(f"Prompt file not found: {path_str}")
            return resolved.read_text(encoding="utf-8")

        if source == "template":
            tid = prompt_spec.get("template_id")
            if not tid:
                raise ValueError("template_id is required for template prompt source")
            record = templates.get_template(self.user_id, tid)
            return record.get("prompt_text", "")

        raise ValueError(f"Unknown prompt source: {source}")

    def _get_expected_fields(self, stage: Dict[str, Any]) -> List[str]:
        expected = []
        outputs = stage.get("outputs", {})
        for _, spec in outputs.items():
            src = spec.get("source", "")
            if src.startswith("response."):
                field = src.split(".", 1)[1]
                expected.append(field)

        # From schema
        response_spec = stage.get("response", {})
        schema_path_str = response_spec.get("schema")
        if schema_path_str:
            try:
                resolved = BACKEND_ROOT / schema_path_str
                if not resolved.is_file():
                    resolved = BACKEND_ROOT.parent / schema_path_str
                if resolved.is_file():
                    schema_data = json.loads(resolved.read_text(encoding="utf-8"))
                    req = schema_data.get("required", [])
                    if isinstance(req, list):
                        expected.extend(req)
            except Exception:
                pass

        return list(set(expected))

    def _format_path_pattern(self, pattern: str, item: Any) -> str:
        out = pattern
        if "{{ item }}" in out:
            out = out.replace("{{ item }}", str(item))
        matches = re.findall(r"\{\{\s*item\.([A-Za-z0-9_-]+)\s*\}\}", out)
        for m in matches:
            val = ""
            if isinstance(item, dict):
                val = str(item.get(m, ""))
            else:
                val = str(getattr(item, m, ""))
            out = re.sub(r"\{\{\s*item\." + m + r"\s*\}\}", val, out)
        return out

    def _execute_llm_call_with_retry(
        self,
        llm: LLMProvider,
        prompt: str,
        kind: str,
        expected_fields: List[str],
        temperature: float,
        stage_id: str,
        max_attempts: int = 2
    ) -> LLMResponse:
        """
        Execute call with automatic JSON structural verification and multi-turn correction retry loop.
        """
        if kind != "json":
            # Direct text generation
            return llm.generate_text(prompt, temperature=temperature)

        # JSON generation
        response = llm.generate_json(prompt, temperature=temperature)
        
        # Verify JSON properties
        json_data = response.json_data
        missing_fields = []
        is_invalid = False

        if not json_data or "error" in json_data:
            is_invalid = True
        else:
            missing_fields = [f for f in expected_fields if f not in json_data]

        if not is_invalid and not missing_fields:
            return response

        # Correction Loop
        history = [
            {"role": "user", "text": prompt},
            {"role": "model", "text": response.text}
        ]

        attempt = 1
        current_response = response
        
        while (is_invalid or missing_fields) and attempt < max_attempts:
            attempt += 1
            if is_invalid:
                error_desc = "Your previous output is not valid JSON."
            else:
                error_desc = f"Your previous output is missing the following required JSON fields: {', '.join(missing_fields)}."
            
            follow_up_msg = f"{error_desc} Please output a complete, valid JSON structure containing all required fields."
            
            # Send correction prompt
            current_response = llm.generate_follow_up(
                history=history,
                follow_up_message=follow_up_msg,
                temperature=temperature,
                response_mime_type="application/json"
            )
            
            # Update chat history
            history.append({"role": "user", "text": follow_up_msg})
            history.append({"role": "model", "text": current_response.text})

            json_data = current_response.json_data
            if not json_data or "error" in json_data:
                is_invalid = True
                missing_fields = []
            else:
                is_invalid = False
                missing_fields = [f for f in expected_fields if f not in json_data]

        return current_response

    def run(self) -> Path:
        """Run all designated stages in order and return the run directory."""
        pipeline_id = self.pipeline_data.get("id", "pipeline")
        topic_safe = re.sub(r"[^A-Za-z0-9._-]+", "_", self.inputs.get("topic", "default").strip())
        run_name = f"{time.strftime('%Y%m%d_%H%M%S')}_{topic_safe}"
        
        run_dir = self.runs_root / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Save pipeline.yaml in run directory
        (run_dir / "pipeline.yaml").write_text(
            # Save raw representation
            json.dumps(self.pipeline_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        stages = self.pipeline_data.get("stages", [])
        stage_ids = [s.get("id") for s in stages if s.get("id")]
        
        active_stages = self.stages_to_run if self.stages_to_run is not None else stage_ids

        # Load defaults
        defaults = self.pipeline_data.get("defaults", {})
        default_model = defaults.get("model", {}).get("name", "gemini-2.5-flash")
        default_failure = defaults.get("failure", {})
        default_max_attempts = default_failure.get("max_attempts", 2)

        for stage in stages:
            stage_id = stage.get("id")
            if not stage_id or stage_id not in active_stages:
                # Skipped stage: ensure it either has mock outputs or isn't required
                continue

            started_iso = utc_now_iso()
            start_time = time.perf_counter()

            # Resolve model
            stage_model = stage.get("model", {})
            model_name = stage_model.get("name") or default_model
            llm = GeminiAdapter(model=model_name)

            # Stage settings
            execution = stage.get("execution", "single")
            bindings = stage.get("bindings", [])
            prompt_spec = stage.get("prompt", {})
            response_spec = stage.get("response", {})
            kind = response_spec.get("kind", "text")
            
            prompt_template = self._load_prompt_template(prompt_spec)
            expected_fields = self._get_expected_fields(stage)

            # Failure policy
            stage_failure = stage.get("failure", {})
            max_attempts = stage_failure.get("max_attempts") or default_max_attempts

            outputs_dict = {}
            output_files = []
            token_usage = TokenUsage()

            if execution == "single":
                resolved_prompt = self._render_prompt(prompt_template, bindings)
                
                # Run LLM
                response = self._execute_llm_call_with_retry(
                    llm=llm,
                    prompt=resolved_prompt,
                    kind=kind,
                    expected_fields=expected_fields,
                    temperature=0.7,
                    stage_id=stage_id,
                    max_attempts=max_attempts
                )
                token_usage = response.usage
                
                # Save response to file
                output_file = response_spec.get("file")
                if output_file:
                    file_path = run_dir / output_file
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    content = response.text
                    if kind == "json" and response.json_data:
                        content = json.dumps(response.json_data, indent=2, ensure_ascii=False)
                    
                    file_path.write_text(content, encoding="utf-8")
                    output_files.append(output_file)

                # Extract outputs
                outputs_config = stage.get("outputs", {})
                for out_name, out_spec in outputs_config.items():
                    src = out_spec.get("source", "")
                    if src == "response":
                        outputs_dict[out_name] = response.json_data if kind == "json" else response.text
                    elif src.startswith("response."):
                        field = src.split(".", 1)[1]
                        if response.json_data:
                            outputs_dict[out_name] = response.json_data.get(field)
                        else:
                            outputs_dict[out_name] = None
                
                # Save prompt snapshot
                prompt_snapshot_name = f"prompt_{stage_id}.txt"
                (run_dir / prompt_snapshot_name).write_text(resolved_prompt, encoding="utf-8")
                output_files.append(prompt_snapshot_name)

            elif execution == "map":
                map_over_src = stage.get("map", {}).get("over", "")
                loop_list = self._resolve_source(map_over_src)
                if not isinstance(loop_list, list):
                    raise ValueError(f"Source '{map_over_src}' for map did not resolve to a list (got {type(loop_list)})")

                item_responses = []
                aggregated_tokens = TokenUsage()

                for index, item in enumerate(loop_list):
                    resolved_prompt = self._render_prompt(
                        prompt_template, bindings, item=item
                    )
                    
                    response = self._execute_llm_call_with_retry(
                        llm=llm,
                        prompt=resolved_prompt,
                        kind=kind,
                        expected_fields=expected_fields,
                        temperature=0.7,
                        stage_id=stage_id,
                        max_attempts=max_attempts
                    )
                    
                    # Track usage
                    aggregated_tokens.prompt_tokens += response.usage.prompt_tokens
                    aggregated_tokens.response_tokens += response.usage.response_tokens
                    aggregated_tokens.total_tokens += response.usage.total_tokens

                    item_val = response.json_data if kind == "json" else response.text
                    item_responses.append(item_val)

                    # Save per-item response if path pattern is provided
                    per_item_pattern = response_spec.get("per_item_file")
                    if per_item_pattern:
                        per_item_file = self._format_path_pattern(per_item_pattern, item)
                        file_path = run_dir / per_item_file
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        content = response.text
                        if kind == "json" and response.json_data:
                            content = json.dumps(response.json_data, indent=2, ensure_ascii=False)
                            
                        file_path.write_text(content, encoding="utf-8")
                        output_files.append(per_item_file)

                token_usage = aggregated_tokens

                # Handle aggregation
                aggregate_file = response_spec.get("aggregate_file")
                aggregate_val = ""
                
                if aggregate_file:
                    strategy = response_spec.get("aggregate_strategy", "concat")
                    
                    if strategy == "concat":
                        aggregate_val = "\n\n".join(str(r) for r in item_responses)
                    elif strategy == "concat_with_headers":
                        item_name_key = stage.get("map", {}).get("item_name", "item")
                        chunks = []
                        for item, r in zip(loop_list, item_responses):
                            label = ""
                            if isinstance(item, dict):
                                label = item.get("segment_name") or item.get("id") or str(item)
                            else:
                                label = str(item)
                            chunks.append(f"## {item_name_key.capitalize()}: {label}\n\n{r}")
                        aggregate_val = "\n\n".join(chunks)
                    elif strategy == "structured_json":
                        aggregate_val = json.dumps(item_responses, indent=2, ensure_ascii=False)
                    
                    file_path = run_dir / aggregate_file
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(aggregate_val, encoding="utf-8")
                    output_files.append(aggregate_file)

                # Outputs mapping
                outputs_config = stage.get("outputs", {})
                for out_name, out_spec in outputs_config.items():
                    src = out_spec.get("source", "")
                    if src == "response.items":
                        outputs_dict[out_name] = item_responses
                    elif src == "response.aggregate":
                        outputs_dict[out_name] = aggregate_val

            elif execution == "map_with_context":
                map_over_src = stage.get("map", {}).get("over", "")
                loop_list = self._resolve_source(map_over_src)
                if not isinstance(loop_list, list):
                    raise ValueError(f"Source '{map_over_src}' for map_with_context did not resolve to a list")

                context_name = stage.get("map", {}).get("context_name", "context")
                context_val = "" # default rolling string context in v1
                item_responses = []
                aggregated_tokens = TokenUsage()

                for index, item in enumerate(loop_list):
                    resolved_prompt = self._render_prompt(
                        prompt_template,
                        bindings,
                        item=item,
                        context_val=context_val,
                        context_name=context_name
                    )
                    
                    response = self._execute_llm_call_with_retry(
                        llm=llm,
                        prompt=resolved_prompt,
                        kind=kind,
                        expected_fields=expected_fields,
                        temperature=0.7,
                        stage_id=stage_id,
                        max_attempts=max_attempts
                    )

                    aggregated_tokens.prompt_tokens += response.usage.prompt_tokens
                    aggregated_tokens.response_tokens += response.usage.response_tokens
                    aggregated_tokens.total_tokens += response.usage.total_tokens

                    item_val = response.json_data if kind == "json" else response.text
                    item_responses.append(item_val)

                    # Update context (rolling concat)
                    if context_val:
                        context_val += f"\n\n{response.text}"
                    else:
                        context_val = response.text

                    # Save per item response
                    per_item_pattern = response_spec.get("per_item_file")
                    if per_item_pattern:
                        per_item_file = self._format_path_pattern(per_item_pattern, item)
                        file_path = run_dir / per_item_file
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        content = response.text
                        if kind == "json" and response.json_data:
                            content = json.dumps(response.json_data, indent=2, ensure_ascii=False)
                            
                        file_path.write_text(content, encoding="utf-8")
                        output_files.append(per_item_file)

                token_usage = aggregated_tokens

                # Handle aggregation
                aggregate_file = response_spec.get("aggregate_file")
                if aggregate_file:
                    file_path = run_dir / aggregate_file
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(context_val, encoding="utf-8")
                    output_files.append(aggregate_file)

                # Outputs mapping
                outputs_config = stage.get("outputs", {})
                for out_name, out_spec in outputs_config.items():
                    src = out_spec.get("source", "")
                    if src == "response.items":
                        outputs_dict[out_name] = item_responses
                    elif src == "response.aggregate":
                        outputs_dict[out_name] = context_val

            # Store results
            self.stage_outputs[stage_id] = outputs_dict

            # Save state metrics
            self.total_prompt_tokens += token_usage.prompt_tokens
            self.total_response_tokens += token_usage.response_tokens
            self.total_tokens_used += token_usage.total_tokens

            elapsed = round(time.perf_counter() - start_time, 3)
            self.stage_records.append({
                "stage": stage_id,
                "started_at_utc": started_iso,
                "finished_at_utc": utc_now_iso(),
                "duration_seconds": elapsed,
                "output_files": output_files,
                "tokens": {
                    "prompt_tokens": token_usage.prompt_tokens,
                    "response_tokens": token_usage.response_tokens,
                    "total_tokens": token_usage.total_tokens
                }
            })

        # Save Run Manifest
        manifest = {
            "run_id": run_dir.name,
            "topic": self.inputs.get("topic", "default"),
            "stages": active_stages,
            "model": default_model,
            "created_at_utc": utc_now_iso(),
            "run_directory": str(run_dir),
            "tokens": {
                "prompt_tokens": self.total_prompt_tokens,
                "response_tokens": self.total_response_tokens,
                "total_tokens": self.total_tokens_used
            },
            "stage_records": self.stage_records
        }
        
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        
        return run_dir
