# Podcast Maker Backend

The backend of Podcast Maker is a FastAPI-based service responsible for orchestrating AI-driven podcast generation, managing cloud storage, and exposing the API used by the frontend.

## Features

- **FastAPI Core**: High-performance asynchronous API.
- **AI Agent Orchestration**: Managed through the dedicated `podcast_maker` core library.
- **Google Cloud Integration**:
  - **Cloud Storage**: Stores generated assets such as audio, transcripts, and research.
  - **Vertex AI / Gemini**: Handles content generation.
  - **Text-to-Speech**: Generates natural host voices.
- **Supabase Integration**: Handles user management, authentication, and metadata storage.
- **Background Processing**: Handles long-running generation tasks from research through audio.
- **Rate Limiting**: Integrated using `slowapi`.

## Pipelines and the Prompt Lab

Podcast text generation (architect -> researcher -> outliner -> scriptwriter) runs through the YAML pipeline engine in `podcast_maker/engine`. The `dialogue` format uses `resources/pipelines/duo_long`, `solo` uses `resources/pipelines/solo_short`; `podcast_maker/core/podcast_job.py` runs the pipeline, uploads each artifact, then does TTS and transcripts. The YAML contract is in `resources/PIPELINE_CONTRACT.md`.

### Recovery

When a podcast is created, its exact pipeline YAML is saved in the episode's bucket folder (`urls.pipeline`, the first checkpoint) and the resolved inputs and stage ids go in the record's `config`. A run - first or retry (`POST /podcasts/{id}/retry`) - uses only that frozen copy, never the file on disk. After each stage its output is uploaded (`urls.<stage_id>`) and `checkpoint` becomes that stage id; then `audio` and `transcript`. A retry skips every stage that already has an artifact and seeds the later stages from the saved output; recovery is per stage (a failure inside a stage redoes that stage).

### API

- `GET /formats` lists the formats: one per pipeline YAML (`id` is the pipeline id; `host_count` from its YAML). Each format also lists its `inputs`: the declared inputs a request may set in `inputs` (all but `topic`, `host_profiles`, `host_name`), each as `{name, type, required, default}`.
- `POST /create-podcast/` takes `topic`, `host_ids`, optional `format` (a pipeline id; default: the format written for that many hosts) and optional `inputs` for any other input the pipeline declares. `topic`, `host_profiles` and `host_name` are supplied by the platform.
- `GET /status/{task_id}` returns `status`, `checkpoint`, `stages` (the pipeline's stage ids), `url` (the file URLs above) and `error`.

The same backend serves the prompt lab (`prompts_lab/`) under `/prompts-test-api`. Set `LAB_AUTH_BYPASS=true` in `backend/.env` for local lab use (unauthenticated requests run as `lab-local-user`); the app refuses to start with it if `APP_ENV=production`. Without the flag the lab routes use normal Supabase auth. Never set it in deploy config.

## Project Structure

```text
backend/
|-- app/
|   |-- main.py             # Application entry point and middleware
|   |-- dependencies.py     # FastAPI dependencies (auth, lab auth)
|   `-- routers/            # API endpoints: podcasts, hosts, users, prompts-test-api
|-- podcast_maker/          # Core generation engine
|   |-- core/               # Podcast job runner, hosts, paths
|   |-- engine/             # YAML pipeline engine
|   |-- evaluation/         # LLM-judge evaluation
|   `-- services/           # External service adapters
|-- resources/              # Versioned: pipelines, schemas, hosts.json, eval rubrics
|-- data/                   # Runtime, gitignored: prompt templates, experiment runs
|-- Dockerfile              # Container configuration
`-- requirements.txt        # Python dependencies
```

## Configuration

### Prerequisites

- Python 3.10+
- Google Cloud service account with access to AI Platform, Cloud Storage, and Text-to-Speech.
- Supabase project URL and service key.

### Environment Variables

Create a `backend/.env` file with the following variables:

```env
BUCKET_NAME=your-gcs-bucket
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/gcp-service-account.json
GEMINI_API_KEY=your-gemini-key
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key
PORT=your-service-port
```

## Deployment

The backend includes a `Dockerfile` for production container builds.

## API Documentation

FastAPI exposes interactive Swagger documentation from the deployed API service.
