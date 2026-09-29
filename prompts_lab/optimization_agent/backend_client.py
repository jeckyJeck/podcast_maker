"""Thin HTTP client for the merged backend's /prompts-test-api.

The agent owns no copy of the engine or the data: pipelines, runs and evaluations
all live behind the backend. Configure with BACKEND_URL (default http://127.0.0.1:8000)
and, only if the backend has real auth on, BACKEND_TOKEN (sent as a Bearer token).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API_PREFIX = "/prompts-test-api"
# Pipeline runs and LLM judging are synchronous on the backend and can take minutes.
REQUEST_TIMEOUT_SECONDS = float(os.getenv("BACKEND_TIMEOUT_SECONDS", "1800"))


class BackendError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    token = os.getenv("BACKEND_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    url = f"{BACKEND_URL}{API_PREFIX}{path}"
    try:
        response = httpx.request(
            method, url, headers=_headers(), timeout=REQUEST_TIMEOUT_SECONDS, **kwargs
        )
    except httpx.HTTPError as exc:
        raise BackendError(f"Backend unreachable at {BACKEND_URL} ({exc}). Is it running?") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise BackendError(f"{method} {path} -> {response.status_code}: {detail}")
    return response


def get_pipeline_yaml(pipeline_id: str) -> str:
    return request("GET", f"/pipelines/{pipeline_id}").text


def save_pipeline_yaml(pipeline_id: str, yaml_text: str) -> None:
    # The route takes the raw YAML as the request body.
    request(
        "POST",
        f"/pipelines/{pipeline_id}",
        content=yaml_text.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8", **_headers()},
    )


def run_pipeline(pipeline_yaml: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return request("POST", "/pipelines/run", json={"pipeline_yaml": pipeline_yaml, "inputs": inputs}).json()


def list_runs() -> list[dict[str, Any]]:
    return request("GET", "/runs").json()["runs"]


def get_run(run_id: str) -> dict[str, Any]:
    return request("GET", f"/runs/{run_id}").json()


def read_run_file(run_id: str, file_name: str) -> str | None:
    """Return a run file's text, or None if it does not exist."""
    try:
        return request("GET", f"/runs/{run_id}/files/{file_name}").json()["content"]
    except BackendError as exc:
        if "404" in str(exc):
            return None
        raise


def get_evaluation(run_id: str) -> dict[str, Any] | None:
    try:
        return request("GET", f"/runs/{run_id}/evaluation").json()["evaluation"]
    except BackendError as exc:
        if "404" in str(exc):
            return None
        raise


def evaluate_run(
    run_id: str,
    content_files: dict[str, str],
    context_files: dict[str, str] | None = None,
    rubric_id: str = "podcast_quality",
) -> dict[str, Any]:
    body: dict[str, Any] = {"content_files": content_files, "rubric_id": rubric_id}
    if context_files:
        body["context_files"] = context_files
    return request("POST", f"/runs/{run_id}/evaluate", json=body).json()["evaluation"]


def compare_runs(run_a: str, run_b: str, file_name: str, max_lines: int = 200) -> str:
    body = {"run_a": run_a, "run_b": run_b, "file_name": file_name, "max_lines": max_lines}
    return request("POST", "/compare", json=body).json()["diff"]
