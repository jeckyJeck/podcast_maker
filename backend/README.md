# ⚙️ Podcast Maker Backend

The backend of Podcast Maker is a FastAPI-based service responsible for orchestrating the AI-driven podcast generation process, managing cloud storage, and exposing an API for the frontend.

## 🚀 Features

- **FastAPI Core**: High-performance asynchronous API.
- **AI Agent Orchestration**: Managed via a dedicated `podcast_maker` core library.
- **Google Cloud Integration**:
    - **Cloud Storage**: For storing generated assets (audio, transcripts, research).
    - **Vertex AI / Gemini**: For content generation.
    - **Text-to-Speech**: For generating natural host voices.
- **Supabase Integration**: For user management, authentication, and metadata storage.
- **Background Processing**: Handles long-running agent tasks (Research -> Script -> Audio).
- **Rate Limiting**: Integrated using `slowapi`.

## 📂 Project Structure

```
backend/
├── app/
│   ├── main.py             # Application entry point & middleware
│   ├── dependencies.py     # FastAPI dependencies (auth, rate limiting)
│   └── routers/            # API endpoints (podcasts, hosts, users)
├── podcast_maker/          # Core logic engine
│   ├── core/               # AI Agent implementations (Architect, Researcher, etc.)
│   └── services/           # External service adapters (GCS, TTS, Gemini)
├── prompts/                # System instructions for AI roles (Markdown files)
├── Dockerfile              # Docker container configuration
└── requirements.txt        # Python dependencies
```

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.10+
- Google Cloud Service Account with:
    - `AI Platform Service Agent`
    - `Storage Object Admin`
    - `Cloud Text-to-Speech API`
- Supabase Project URL and Service Key.

### Environment Variables
Create a `backend/.env` file with the following variables:

```env
# Google Cloud
BUCKET_NAME=your-gcs-bucket
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/gcp-service-account.json

# AI Configuration
GEMINI_API_KEY=your-gemini-key

# Supabase
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key

# App Settings
PORT=8000
```

### Installation

1.  **Navigate to the backend directory**:
    ```bash
    cd backend
    ```

2.  **Create and activate a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the server**:
    ```bash
    uvicorn app.main:app --reload --port 8000
    ```

## 🐳 Docker Deployment

You can containerize the backend using the provided `Dockerfile`.

```bash
docker build -t podcast-maker-backend .
docker run -p 8000:8000 --env-file .env podcast-maker-backend
```

---

## 📸 API Documentation
Once the server is running, you can access the interactive Swagger documentation at:
`http://localhost:8000/docs`
