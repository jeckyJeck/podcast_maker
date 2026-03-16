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
- **Supabase**: Used for client-side authentication and real-time listeners.
- **JSZip**: For bundling multiple generated assets into a single ZIP for the user.

## 📂 Architecture

- `src/components/`: Modular UI components (Screens, Player, Transcript Viewer).
- `src/context/`: Global state management for Authentication and Podcast status.
- `src/hooks/`: Custom hooks for polling status and managing audio playback.
- `src/services/`: API abstractions for interaction with the FastAPI backend.
- `src/types/`: TypeScript interfaces and types for API responses and podcast metadata.

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
- **`CreateScreen.tsx`**: Main entry point for starting new podcast generations.
- **`StatusDisplay.tsx`**: Visual feedback for the multi-step AI process.
- **`PlayerScreen.tsx`**: Integrated player and management dashboard.
- **`TranscriptViewer.tsx`**: High-performance text-syncing component.

> **Note to user**: You can provide screenshots of the dynamic status tracker and the transcript viewer to be added here.

## מבנה הפרויקט

```
frontend/
├── src/
│   ├── components/           # קומפוננטות React
│   │   ├── AudioPlayer.tsx      # נגן אודיו מתקדם
│   │   ├── FileDownloader.tsx   # ניהול הורדות
│   │   ├── StatusDisplay.tsx    # תצוגת סטטוס
│   │   └── PodcastGenerator.tsx # קומפוננטה ראשית
│   ├── hooks/                # Custom hooks
│   │   └── usePodcastStatus.ts  # Hook לניהול polling
│   ├── services/             # שירותי API
│   │   └── api.ts               # HTTP client
│   ├── types/                # TypeScript types
│   │   └── podcast.ts           # ממשקים ו-types
│   ├── App.tsx               # קומפוננטת שורש
│   ├── main.tsx             # נקודת כניסה
│   └── index.css            # סגנונות גלובליים
├── index.html               # HTML ראשי (RTL)
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## טכנולוגיות

- **React 18** - ספריית UI
- **TypeScript** - Type safety
- **Vite** - Build tool מהיר
- **Tailwind CSS** - Framework לעיצוב
- **Axios** - HTTP client
- **React Icons** - אייקונים

## פיתוח עתידי

האפליקציה תוכננה להרחבה עתידית:

- תמיכה באימות משתמשים
- היסטוריית פודקאסטים
- עריכת תסריט לפני ייצור
- אפשרויות התאמה אישית (קולות, סגנון)
- שיתוף פודקאסטים
- ניהול פודקאסטים אישי

## פתרון בעיות

### שגיאת CORS

אם אתה מקבל שגיאת CORS, וודא ש:
1. השרת Backend רץ על `http://localhost:8000`
2. ה-CORS middleware מוגדר נכון ב-`backend/app/main.py`
3. הכתובת ב-`.env` תואמת לכתובת השרת

### הפודקאסט לא מתחיל להיות מעובד

1. בדוק שהשרת Backend רץ
2. פתח את ה-Console בדפדפן וחפש שגיאות
3. בדוק שיש חיבור לאינטרנט (נדרש עבור Google Cloud Services)

### הורדת קבצים לא עובדת

1. בדוק שה-signed URLs תקפים (תוקף: שעה)
2. נסה להוריד כל קובץ בנפרד
3. בדוק שהדפדפן לא חוסם הורדות

## רישיון

MIT

---

נוצר עם ❤️ על ידי Podcast Maker
