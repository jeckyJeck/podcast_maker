# Podcast Maker

An automated end-to-end system for creating high-quality podcasts from any topic using generative AI.

Podcast Maker transforms a topic into a produced podcast episode with research, a structured outline, a professional script, generated audio, and synchronized transcripts.

## Overview

Podcast Maker uses large language models and text-to-speech technologies to automate the podcast production pipeline:

1. **Researcher**: Performs research on the chosen topic.
2. **Architect**: Defines the episode blueprint and style.
3. **Outliner**: Structures the content into a coherent flow.
4. **Scriptwriter**: Crafts a natural-sounding dialogue between hosts.
5. **Audio Producer**: Generates audio and synchronized transcripts.

## Tech Stack

### Backend

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) with Python 3.12+.
- **AI/LLM**: [Google Gemini](https://ai.google.dev/).
- **TTS**: [Google Cloud Text-to-Speech](https://cloud.google.com/text-to-speech) and [ElevenLabs](https://elevenlabs.io/).
- **Storage**: [Supabase](https://supabase.com/).
- **Database/Auth**: [Supabase](https://supabase.com/).
- **DevOps**: Docker and Google Cloud Run.

### Frontend

- **Framework**: [React](https://reactjs.org/) and [TypeScript](https://www.typescriptlang.org/).
- **Build Tool**: [Vite](https://vitejs.dev/).
- **Styling**: [Tailwind CSS](https://tailwindcss.com/).
- **Icons**: [React Icons](https://react-icons.github.io/react-icons/).

## Project Structure

```text
podcastMaker/
|-- backend/                     # FastAPI server logic
|   |-- app/                     # API routes and dependencies
|   |-- podcast_maker/           # Core generation engine
|   |   |-- core/                # Agent logic
|   |   `-- services/            # Cloud and AI providers
|   |-- prompts/                 # System prompts for AI agents
|   `-- requirements.txt         # Backend dependencies
|-- frontend/                    # React + Vite application
|   |-- src/                     # React source code
|   |   |-- components/          # UI elements
|   |   |-- context/             # Global state
|   |   |-- hooks/               # Custom logic hooks
|   |   `-- services/            # API client
|   `-- package.json             # Frontend dependencies
|-- prompts/                     # Global prompt templates
`-- README.md                    # Main documentation
```

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Google Cloud project with enabled APIs for generative AI, TTS, and storage.
- Supabase account.

### Configuration

Use the component-specific documentation for environment variables and deployment notes:

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)

## Generation Process

When a podcast is created, the system follows this workflow:

1. **Architecture**: Creates a structured blueprint for the content flow.
2. **Research**: Collects topic context.
3. **Outline**: Generates a detailed episode outline with segments.
4. **Script Writing**: Crafts a natural dialogue between hosts.
5. **Audio Generation**: Converts script text to speech via Google TTS or ElevenLabs.
6. **Transcript Generation**: Generates a VTT transcript synchronized with audio.
7. **Storage & Delivery**: Uploads assets to Google Cloud Storage with secure signed URLs.

## License

This project is licensed under the MIT License.
