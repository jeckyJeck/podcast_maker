# 🎙️ Podcast Maker

An automated end-to-end system for creating high-quality podcasts from any topic using Generative AI. 

Podcast Maker transforms a simple topic into a fully produced podcast episode, complete with deep research, a structured outline, a professional script, and high-quality audio with multiple AI hosts.

---

## 🚀 Overview

Podcast Maker leverages the power of Large Language Models (LLMs) and Text-to-Speech (TTS) technologies to automate the entire podcast production pipeline:

1.  **Researcher**: Performs deep research on the chosen topic.
2.  **Architect**: Defines the episode's "blueprint" and style.
3.  **Outliner**: Structures the content into a coherent flow.
4.  **Scriptwriter**: Crafts a natural-sounding dialogue between two hosts.
5.  **Audio Producer**: Generates high-quality audio and synchronized transcripts.

## 🛠️ Tech Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12+)
- **AI/LLM**: [Google Gemini (Generative AI)](https://ai.google.dev/)
- **TTS**: [Google Cloud Text-to-Speech](https://cloud.google.com/text-to-speech) & [ElevenLabs](https://elevenlabs.io/)
- **Storage**: [Google Cloud Storage](https://cloud.google.com/storage)
- **Database/Auth**: [Supabase](https://supabase.com/)
- **DevOps**: Docker, Google Cloud Run

### Frontend
- **Framework**: [React](https://reactjs.org/) + [TypeScript](https://www.typescriptlang.org/)
- **Build Tool**: [Vite](https://vitejs.dev/)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/)
- **Icons**: [React Icons](https://react-icons.github.io/react-icons/)

---

## 📂 Project Structure

```
podcastMaker/
├── backend/                     # FastAPI Server logic
│   ├── app/                     # API routes and dependencies
│   ├── podcast_maker/           # Core generation engine
│   │   ├── core/                # Agent logic (Architect, Researcher, etc.)
│   │   └── services/            # Cloud & AI providers
│   ├── prompts/                 # System prompts for AI agents
│   └── requirements.txt         # Backend dependencies
├── frontend/                    # React + Vite Application
│   ├── src/                     # React source code
│   │   ├── components/          # UI elements (Player, Transcript, etc.)
│   │   ├── context/             # Global state
│   │   ├── hooks/               # Custom logic hooks
│   │   └── services/            # API client
│   └── package.json             # Frontend dependencies
├── prompts/                     # Global prompt templates
└── README.md                    # Main documentation
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Google Cloud Project with enabled APIs (Generative AI, TTS, Storage).
- Supabase account.

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-repo/podcastMaker.git
    cd podcastMaker
    ```

2.  **Setup Backend**:
    Follow the instructions in [backend/README.md](backend/README.md).

3.  **Setup Frontend**:
    Follow the instructions in [frontend/README.md](frontend/README.md).

---

## 🔄 The Generation Process

When you create a podcast, the system follows this workflow:

1.  **Architecture** 🏗️: Creates a structured "Blueprint" planning the content flow.
2.  **Research** 🔍: Generative AI researches the topic and collects context.
3.  **Outline** 📋: Generates a detailed episode outline with segments.
4.  **Script Writing** ✍️: Crafts a natural dialogue between hosts.
5.  **Audio Generation** 🎤: Converts script to speech via Google TTS or ElevenLabs.
6.  **Transcript Generation** 📝: Generates a VTT transcript synchronized with audio.
7.  **Storage & Delivery** ☁️: Uploads assets to Google Cloud Storage with Secure Signed URLs.

---

## 📸 Screenshots
*(Placeholders for future images)*
> **Note to user**: You can provide screenshots of the Create Screen, Podcast Library, and Audio Player to be included here.

---

## 📄 License
This project is licensed under the MIT License.
