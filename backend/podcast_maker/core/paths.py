from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Versioned, shipped with the Docker image.
RESOURCES_DIR = BACKEND_ROOT / "resources"
PROMPTS_DIR = RESOURCES_DIR / "prompts"
PIPELINES_DIR = RESOURCES_DIR / "pipelines"
SCHEMAS_DIR = RESOURCES_DIR / "schemas"
EVAL_RUBRICS_DIR = RESOURCES_DIR / "eval_rubrics"
HOSTS_FILE = RESOURCES_DIR / "hosts.json"

# Runtime data, gitignored.
DATA_DIR = BACKEND_ROOT / "data"
TEMPLATES_DIR = DATA_DIR / "prompt_templates"
RUNS_DIR = DATA_DIR / "experiment_runs"

OUTPUT_DIR = BACKEND_ROOT / "output"
