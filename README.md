# 🎙️ Podcast Maker

מערכת אוטומטית מלאה ליצירת פודקאסטים באיכות גבוהה מכל נושא שתבחר.

## 🌟 תכונות

### Backend (FastAPI)
- 🤖 **יצירה אוטומטית מלאה** - מחקר, תסריט ויצירת אודיו באמצעות AI
- 🧠 **Google Generative AI** - יצירת תוכן חכם ונתוני מחקר עמוקים
- ☁️ **Google Cloud Storage** - אחסון בענן עם signed URLs
- 🎤 **Google Text-to-Speech** - המרת טקסט לדיבור טבעי באיכות גבוהה
- 🎙️ **בחירת Hosts** - בחר מהמנחים הזמינים או תשתמש בברירת המחדל
- 🔄 **מיקרוסרוויסים** - Architect, Researcher, Outliner, Scriptwriter
- 📊 **מעקב סטטוס בזמן אמת** - עדכוני תהליך העיבוד אנטי-ממציא

### Frontend (React + TypeScript)
- 📝 **ממשק אינטואיטיבי** - הכנסת נושא וברירת hosts פשוטה וברורה
- 🎤 **בחירת מנחים** - בחר מהמנחים הזמינים עם פרופילים מלאים
- 📋 **מציג תמלול** - צפה בתמלול מלא עם סנכרון זמן על האודיו
- 🔄 **רענון אוטומטי** - מעקב סטטוס בזמן אמת כל שנייה
- 🎧 **נגן אודיו מתקדם**:
  - מהירות השמעה משתנה (0.5x-2x)
  - סרגל התקדמות עם דילוג חופשי
  - בקרת עוצמת קול ספציפית
  - תצוגת זמן מלאה וכרונומטר
  - השהיה וחזרה
- 💾 **הורדת קבצים מלאה**:
  - Blueprint (JSON) - תוכן מובנה
  - Research (Markdown) - מידע מחקרי
  - Outline (JSON) - מבנה הפרק
  - Script (Text) - הטקסט המלא של הפודקאסט
  - Audio (MP3) - האודיו של הפודקאסט
  - Transcript (VTT) - תמלול סטנדרטי
- 📱 **עיצוב רספונסיבי** - תמיכה מלאה במובייל וטאבלט
- 🌙 **מצב כהה** - תמיכה אוטומטית עם Tailwind CSS

## 🚀 התחלה מהירה

### דרישות מקדימות
- Python 3.8+
- Node.js 18+
- חשבון Google Cloud עם הרשאות:
  - Google Cloud Storage (gsutil)
  - Google Text-to-Speech
  - Google Generative AI (Gemini)

### הקמה

1. **Clone הפרויקט**:
```bash
git clone <repository-url>
cd podcastMaker
```

2. **הגדר Backend**:
```bash
cd backend
pip install -r requirements.txt

# צור קובץ .env עם:
BUCKET_NAME=your-gcs-bucket-name
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json
```

### משתנים סביבתיים (Environment Variables)

| משתנה | תיאור | דוגמה |
|--------|--------|--------|
| `BUCKET_NAME` | שם ה-bucket ב-Google Cloud Storage | `my-podcast-bucket` |
| `GOOGLE_APPLICATION_CREDENTIALS` | נתיב לקובץ JSON של Google Cloud | `/app/creds.json` |

3. **הגדר Frontend**:
```bash
cd ../frontend
npm install
```

### הרצה

**אפשרות 1: באמצעות סקריפטים**
```powershell
# בטרמינל אחד:
.\start-backend.ps1

# בטרמינל שני:
.\start-frontend.ps1
```

**אפשרות 2: ידני**
```bash
# Terminal 1 - Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev
```

האתר יהיה זמין ב: **http://localhost:5173**

## 🐳 Docker Deployment (Production)

### Build Docker Image
```bash
cd backend
docker build -t podcast-app .
```

### Run with Docker
```bash
docker run --rm -p 8080:8080 \
  --env-file .env \
  -v /path/to/credentials.json:/app/creds.json \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/creds.json \
  podcast-app
```

### Docker Compose (Optional)
```bash
docker-compose up --build
```

כשאתה יוצר פודקאסט, המערכת עוברת בתהליך הבא:

1. **Research (מחקר)** 🔍
   - Generative AI ממחקה את הנושא
   - איסוף מידע רלוונטי

2. **Architecture (ארכיטקטורה)** 🏗️
   - יצירת Blueprint מובנה
   - תכנון זרימת התוכן

3. **Outline (מתאר)** 📋
   - יצירת מבנה הפודקאסט
   - הגדרת סעיפים וינטריות

4. **Script Writing (כתיבת תסריט)** ✍️
   - כתיבת דיאלוג בין המנחים
   - שילוב המידע בצורה טבעית

5. **Audio Generation (יצירת אודיו)** 🎤
   - המרת תסריט לדיבור בעזרת Google TTS
   - שילוב קולות של המנחים

6. **Transcript Generation (יצירת תמלול)** 📝
   - יצירת תמלול בצורמט VTT
   - סנכרון זמן עם האודיו

7. **Storage & Delivery (אחסון והפצה)** ☁️
   - אחסון בGoogle Cloud Storage
   - Signed URLs לאנטי-ממציא הורדה

## 📖 שימוש - מדריך שלב-אחר-שלב

1. פתח את הדפדפן ב-**http://localhost:5173**

2. הכנס נושא לפודקאסט:
   - דוגמאות: "ההיסטוריה של בינה מלאכותית", "טיפים בתכנות", "עתיד הטכנולוגיה"

3. בחר מנחים (אופציונלי):
   - לחץ על כפתור "בחירת מנחים"
   - בחר מהמנחים הזמינים
   - כל מנחה בעל טון וסגנון ייחודי

4. לחץ "צור פודקאסט" וחכה:
   - המערכת תעבוד בחו"ל (~2-5 דקות לפי מורכבות הנושא)
   - צפה בעדכוני הסטטוס בזמן אמת

5. כשהפודקאסט מוכן:
   - **הצג בנגן האודיו** - האזן ישירות בדפדפן
   - **צפה בתמלול** - קרא את הטקסט המלא עם סנכרון זמן
   - **הורד קבצים** - כל הקבצים (Blueprint, Research, Outline, Script, Audio, Transcript)

## 🏗️ מבנה הפרויקט

```
podcastMaker/
├── backend/                     # FastAPI Server
│   ├── app/
│   │   └── main.py             # API endpoints, CORS, task management
│   ├── podcast_maker/
│   │   ├── core/               # Business logic microservices
│   │   │   ├── architect.py    # Blueprint generation
│   │   │   ├── researcher.py   # Research content generation
│   │   │   ├── outliner.py     # Outline creation
│   │   │   ├── scriptwriter.py # Script generation
│   │   │   ├── orchestrator.py # Process orchestration
│   │   │   ├── hosts_config.py # Host profiles management
│   │   │   ├── prompt_manager.py
│   │   │   └── logging_config.py
│   │   └── services/           # External service integrations
│   │       ├── google_cloud_storage_provider.py
│   │       ├── GoogleTTS.py
│   │       └── transcript_formatter.py
│   ├── prompts/                # LLM prompts for content generation
│   ├── output/                 # Generated podcast outputs
│   ├── requirements.txt
│   └── podcast-creator-<id>.json # Google Cloud credentials
│
├── frontend/                    # React Application
│   ├── src/
│   │   ├── components/         # UI Components
│   │   │   ├── AudioPlayer.tsx
│   │   │   ├── FileDownloader.tsx
│   │   │   ├── HostSelector.tsx        # בחירת מנחים
│   │   │   ├── StatusDisplay.tsx
│   │   │   ├── TranscriptViewer.tsx    # תצוגת תמלול
│   │   │   └── PodcastGenerator.tsx    # קומפוננטת ראשית
│   │   ├── hooks/              # Custom Hooks
│   │   │   └── usePodcastStatus.ts
│   │   ├── services/           # API Client
│   │   │   └── api.ts
│   │   ├── types/              # TypeScript Definitions
│   │   │   └── podcast.ts
│   │   └── App.tsx
│   ├── package.json
│   └── README.md
│
├── start-backend.ps1            # PowerShell script
├── start-frontend.ps1           # PowerShell script
├── SETUP_INSTRUCTIONS.md        # הוראות מפורטות
└── README.md                    # המסמך הזה
```

## 🛠️ טכנולוגיות

### Backend Stack
- **FastAPI** - Modern Python web framework
- **Google Cloud Storage** - File storage ו-CDN
- **Google Text-to-Speech** - Audio synthesis עם תמיכה בשפות מרובות
- **Google Generative AI (Gemini)** - AI-powered content generation
- **Python-dotenv** - Environment configuration
- **Pydantic** - Data validation ו-parsing
- **CORS Middleware** - Cross-origin request handling

### Frontend Stack
- **React 18** - UI library עם hooks ו-state management
- **TypeScript** - Type safety וDeveloper experience משופר
- **Vite** - Build tool & dev server עם HMR
- **Tailwind CSS** - Utility-first CSS ו-dark mode support
- **Axios** - HTTP client עם interceptors
- **React Icons** - Icon library רחבה
- **React Components** - Custom components: AudioPlayer, StatusDisplay, TranscriptViewer, HostSelector

## 📋 API Endpoints

### POST `/create-podcast/`
יצירת פודקאסט חדש
```json
Request Body: {
  "topic": "string (required)",
  "host_ids": "array of strings (optional, default: ['sarah_curious', 'mike_expert'])"
}

Response: { "task_id": "uuid", "message": "string" }
```

### GET `/status/{task_id}`
בדיקת סטטוס עיבוד הפודקאסט
```json
Response: {
  "status": "processing" | "completed" | "failed",
  "url": {
    "blueprint": "signed_url_to_blueprint_json",
    "research": "signed_url_to_research_md",
    "outline": "signed_url_to_outline_json",
    "script": "signed_url_to_script_txt",
    "audio": "signed_url_to_audio_mp3",
    "transcript": "signed_url_to_transcript_vtt"
  } | null,
  "error": "string (optional, if status is failed)"
}
```

### GET `/available-hosts/`
קבלת רשימת כל המנחים הזמינים
```json
Response: {
  "hosts": [
    {
      "id": "host_id",
      "name": "Display Name",
      "tone": "host_tone",
      "role": "primary|secondary",
      "gender": "male|female",
      "personality": "personality_description"
    }
  ]
}
```

## 🎙️ פרופילי המנחים

המערכת מגיעה עם מנחים קדומים עם אישיויות שונות:

| שם | תפקיד | טון | תיאור |
|-----|-------|------|-------|
| **Sarah Curious** | Primary | Curious & Engaging | שואלת שאלות חכמות, מעניינת בפרטים |
| **Mike Expert** | Primary | Authoritative & Knowledgeable | בעל ידע עמוק, מספק הסברים מדעיים |
| **Alex Skeptic** | Secondary | Critical & Analytical | מאתגר את ההנחות, חושב בביקורתיות |
| **Emma Enthusiast** | Secondary | Passionate & Excited | מביעה התלהבות, מחברת אנושית |

אתה יכול לבחור כל צירוף של מנחים כדי ליצור דיאלוג ייחודי!

## 🔧 ארכיטקטורת LLM Provider

הפרויקט כולל ארכיטקטורה מודולרית להחלפת ספקי AI:

### מבנה
- **Interface**: [backend/podcast_maker/services/llm_provider.py](backend/podcast_maker/services/llm_provider.py) - Abstract Base Class (ABC) עם מתודות `generate_text` ו-`generate_json`
- **Gemini Implementation**: [backend/podcast_maker/services/gemini_adapter.py](backend/podcast_maker/services/gemini_adapter.py) - מימוש עבור Google Gemini
- **מחלקות צרכן**: `Architect`, `Researcher`, `Outliner`, `ScriptWriter` - כולן מקבלות `LLMProvider` דרך dependency injection

### החלפת ספק AI
כדי להוסיף ספק חדש (לדוגמה: OpenAI, Claude, Azure OpenAI):

1. צור מחלקה חדשה שיורשת מ-`LLMProvider`:
```python
# backend/podcast_maker/services/openai_adapter.py
from podcast_maker.services.llm_provider import LLMProvider, LLMResponse

class OpenAIAdapter(LLMProvider):
    def generate_text(self, prompt, model, temperature=0.7, tools=None, metadata=None):
        # מימוש עם OpenAI API
        ...
    
    def generate_json(self, prompt, model, temperature=0.7, metadata=None):
        # מימוש עם OpenAI API
        ...
```

2. עדכן את [backend/podcast_maker/core/orchestrator.py](backend/podcast_maker/core/orchestrator.py#L48-L50):
```python
# החלף מ:
self.llm_provider = GeminiAdapter(client)

# ל:
self.llm_provider = OpenAIAdapter(api_key=os.getenv("OPENAI_API_KEY"))
```

**הערות חשובות**:
- Interface תומך ב-provider-specific tools (למשל GoogleSearch ב-Researcher)
- מדיניות שגיאות: fail-fast בשלבים קריטיים, fallback בשלבים אחרים
- כל קריאה לוגו אוטומטית עם מטריקות usage (tokens, stage, timing)

- **CORS** מוגדר לפורטים הספציפיים של development
- **Signed URLs** מ-Google Cloud Storage (תוקף: שעה)
- לייצור: הוסף אימות משתמשים ו-rate limiting

## 🐛 פתרון בעיות

### Backend לא עולה
- ✅ בדוק התקנת חבילות: `pip install -r requirements.txt`
- ✅ ודא קיום קובץ `.env` עם משתנים נכונים
- ✅ בדוק גישה ל-Google Cloud credentials

### Frontend לא עולה
- ✅ הרץ `npm install` שוב
- ✅ בדוק גרסת Node.js: `node --version` (צריך 18+)
- ✅ נקה cache: `npm cache clean --force`

### שגיאת CORS
- ✅ ודא Backend רץ על פורט 8000
- ✅ בדוק `main.py` - CORS middleware צריך לכלול את הפורט של Frontend
- ✅ רענן את הדפדפן

### הפודקאסט תקוע ב-Processing
- ✅ בדוק לוגים בטרמינל של Backend
- ✅ ודא חיבור אינטרנט פעיל
- ✅ בדוק מכסת Google Cloud APIs

## 💡 טיפים וטריקים

### עדכון Hosts Profiles
אם תרצה להוסיף מנחים חדשים או לשנות את הקיימים, עדכן את:
- [backend/podcast_maker/core/hosts.json](backend/podcast_maker/core/hosts.json)

### שינוי Prompts
כדי להשפיע על איכות התוכן, שנה את ה-prompts ב:
- [backend/prompts/](backend/prompts/) - researcher.md, architect.md, outliner.md, scriptwriter.md

### DebugLogging
לוגים מלאים זמינים בטרמינל של Backend. כדי לשנות רמת logging:
```python
# backend/podcast_maker/core/logging_config.py
LOG_LEVEL = "DEBUG"  # או INFO, WARNING, ERROR
```

### ביצועים
- הפודקאסט בדרך כלל לוקח **2-5 דקות** תלוי בנושא
- אם זה לוקח יותר זמן, בדוק מכסת Google Cloud API
- אפשר להגדיל את מהירות הייצור על ידי עדכון Prompts

## 🚧 תכונות עתידיות

- [x] **בחירת Hosts** ✅ - כבר מחובר ופעיל
- [x] **תצוגת Transcript** ✅ - כבר מחובר ופעיל
- [ ] אימות משתמשים (Firebase/Auth0)
- [ ] היסטוריית פודקאסטים (localStorage/database)
- [ ] עריכת תסריט לפני ייצור
- [ ] הורדת קול מותאם (הפקה קסטום)
- [ ] תמיכה בשפות מרובות (עברית, אנגלית, וכו')
- [ ] פרקים מרובים לפודקאסט אחד
- [ ] שיתוף פודקאסטים ברשתות חברתיות
- [ ] אפליקציה ניידת (React Native / Flutter)
- [ ] מערכת תשלומים (Stripe/PayPal)
- [ ] Dashboard ניהולי עם סטטיסטיקות
- [ ] עריכה שיתופית של תוכן
- [ ] מזנוני TTS מרובים (ElevenLabs, Azure, וכו')

## 📄 רישיון

MIT License - ראה קובץ LICENSE לפרטים

## 🤝 תרומה

Pull requests מתקבלים בברכה! לשינויים גדולים, אנא פתח issue תחילה.

## 📧 יצירת קשר

נוצר עם ❤️ בעזרת AI

---

**גרסה**: 2.0.0  
**עדכון אחרון**: פברואר 2026

✨ **עדכונים בגרסה 2.0.0**:
- ✅ בחירת Hosts מתקדמת
- ✅ מציג Transcript בזמן אמת
- ✅ Google Generative AI ליצירת תוכן
- ✅ API שופר עם מידע מפורט
- ✅ תיעוד מלא וברור
