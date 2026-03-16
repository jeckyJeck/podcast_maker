# 🌐 Podcast Maker Frontend

The frontend of Podcast Maker is a React-based web application that allows users to create podcasts by simply typing a topic. It provides a real-time status tracker, an interactive audio player, and an integrated transcript viewer.

## ✨ Features

- **Topic Input & Host Selection**: Easily specify the topic and choose between different AI host personalities (male/female, varied accents).
- **Real-Time Status Tracking**: Follow the AI's progress through Research, Outlining, Scriptwriting, and Audio Synthesis with detailed live status messages.
- **Advanced Audio Player**: 
    - Smooth Seekbar with time markers.
    - Play/Pause, Rewind/Fast-Forward (15s).
    - Playback Speed control (0.5x, 1x, 1.5x, 2x).
    - Volume control.
- **Synchronous Transcript Viewer**: Displays the text of the podcast, highlighting the current word as it is spoken. Supports .VTT format.
- **Asset Download Manager**: One-click download for all generated assets including Audio, Script, Research paper, and Blueprint JSON.
- **Responsive UI**: Optimized for mobile and desktop using **Tailwind CSS**.
- **Dark Mode**: Integrated with modern design aesthetics.

## 🛠️ Tech Stack

- **React & TypeScript**: Strong typing and component-based architecture.
- **Vite**: Modern, ultra-fast build tool.
- **Tailwind CSS**: Utility-first styling.
- **Axios**: HTTP client for API requests.
- **Supabase**: Integrated for authentication and database management.
- **JSZip**: Bundling multiple generated assets into a single ZIP for the user.

## 📂 Project Structure

```
frontend/
├── src/
│   ├── components/         # UI Components (AudioPlayer, StatusDisplay, etc.)
│   ├── context/            # Authentication & Podcast Global State
│   ├── hooks/              # Custom logic for status polling & audio control
│   ├── services/           # Backend API integration (Axios client)
│   ├── types/              # TypeScript definitions & interfaces
│   ├── App.tsx             # Main application layout
│   └── main.tsx            # React bootstrap file
├── index.html              # Entry HTML file
├── package.json            # Frontend dependencies & scripts
├── tailwind.config.js      # Styling configuration
└── vite.config.ts          # Vite build configuration
```

## ⚡ Setup & Development

### Prerequisites
- Node.js 18+
- Active backend service running.

### Installation

1.  **Navigate to the frontend directory**:
    ```bash
    cd frontend
    ```

2.  **Install dependencies**:
    ```bash
    npm install
    ```

3.  **Setup Environment Variables**:
    Create a `frontend/.env` file:
    ```env
    VITE_API_BASE_URL=http://localhost:8000
    VITE_SUPABASE_URL=your-supabase-url
    VITE_SUPABASE_ANON_KEY=your-supabase-key
    ```

4.  **Start the development server**:
    ```bash
    npm run dev
    ```

---

## 📸 Component Highlights
- **`CreateScreen.tsx`**: Entry point for initiating podcast generation.
- **`StatusDisplay.tsx`**: Live feedback for the multi-step AI orchestration.
- **`PlayerScreen.tsx`**: Dedicated player and asset management dashboard.
- **`TranscriptViewer.tsx`**: High-performance text-syncing component.

> **Note to user**: You can provide screenshots of the dynamic status tracker and the transcript viewer to be added here.
