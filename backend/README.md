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

## Prompt Lab Scope

The production backend does not serve prompt lab endpoints. Prompt lab traffic belongs to the isolated backend in `prompts_lab/lab_backend`.

## Project Structure

```text
backend/
|-- app/
|   |-- main.py             # Application entry point and middleware
|   |-- dependencies.py     # FastAPI dependencies
|   `-- routers/            # API endpoints for podcasts, hosts, and users
|-- podcast_maker/          # Core generation engine
|   |-- core/               # AI agent implementations
|   `-- services/           # External service adapters
|-- prompts/                # System instructions for AI roles
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
