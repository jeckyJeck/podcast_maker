# Podcast Maker Frontend

The frontend of Podcast Maker is a React-based web application that lets users create podcasts from a topic. It provides a real-time status tracker, an interactive audio player, and an integrated transcript viewer.

## Features

- **Topic Input & Host Selection**: Specify a topic and choose between different AI host personalities.
- **Real-Time Status Tracking**: Follow progress through research, outlining, scriptwriting, and audio synthesis.
- **Advanced Audio Player**:
  - Seekbar with time markers.
  - Play, pause, rewind, and fast-forward controls.
  - Playback speed control.
  - Volume control.
- **Synchronous Transcript Viewer**: Displays the podcast transcript and highlights the current word during playback.
- **Asset Download Manager**: Downloads generated assets including audio, script, research, and blueprint JSON.
- **Responsive UI**: Supports mobile and desktop layouts using Tailwind CSS.
- **Dark Mode**: Integrated with the application design.

## Tech Stack

- **React & TypeScript**: Strong typing and component-based architecture.
- **Vite**: Modern frontend build tooling.
- **Tailwind CSS**: Utility-first styling.
- **Axios**: HTTP client for API requests.
- **Supabase**: Authentication and database integration.
- **JSZip**: Bundles generated assets into a ZIP for download.

## Project Structure

```text
frontend/
|-- src/
|   |-- components/         # UI components
|   |-- context/            # Authentication and podcast global state
|   |-- hooks/              # Status polling and audio control logic
|   |-- services/           # Backend API integration
|   |-- types/              # TypeScript definitions and interfaces
|   |-- App.tsx             # Main application layout
|   `-- main.tsx            # React bootstrap file
|-- index.html              # Entry HTML file
|-- package.json            # Frontend dependencies and scripts
|-- tailwind.config.js      # Styling configuration
`-- vite.config.ts          # Vite build configuration
```

## Configuration

### Prerequisites

- Node.js 18+
- Active backend API service.

### Environment Variables

Create a `frontend/.env` file:

```env
VITE_API_BASE_URL=your-api-base-url
VITE_SUPABASE_URL=your-supabase-url
VITE_SUPABASE_ANON_KEY=your-supabase-key
```

## PWA / Android TWA

The frontend includes the minimum PWA pieces needed for an Android Trusted Web Activity:

- `public/manifest.webmanifest`
- `public/sw.js`
- `public/icons/`

To wrap the same frontend as an Android app, use the templates in `../android/twa/` and point Bubblewrap to your deployed HTTPS site.

## Component Highlights

- **`CreateScreen.tsx`**: Entry point for initiating podcast generation.
- **`StatusDisplay.tsx`**: Live feedback for multi-step AI orchestration.
- **`PlayerScreen.tsx`**: Dedicated player and asset management dashboard.
- **`TranscriptViewer.tsx`**: Text-syncing component for transcript playback.
