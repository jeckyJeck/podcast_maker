import { useEffect } from 'react';
import { FaMicrophone, FaPlay, FaHistory } from 'react-icons/fa';
import { useAuth } from './context/AuthContext';
import { PodcastProvider, usePodcast } from './context/PodcastContext';
import { setAccessTokenProvider } from './services/api';
import { CreateScreen } from './components/CreateScreen';
import { PlayerScreen } from './components/PlayerScreen';
import { HistoryScreen } from './components/HistoryScreen';
import './index.css';

// ── Inner app (inside PodcastProvider) ───────────────────────────────────────

function AppInner() {
  const { currentScreen, goToCreate, goToPlayer, goToHistory } = usePodcast();

  const screens = {
    create: <CreateScreen />,
    player: <PlayerScreen />,
    history: <HistoryScreen />,
  };

  return (
    <div className="flex flex-col min-h-0 flex-1 relative">
      <div className="flex-1 flex flex-col pt-2 pb-6">
        {screens[currentScreen]}
      </div>

      {/* Navigation Bar - Static Top/Bottom Grid */}
      <div className="border-t border-gray-100 dark:border-gray-800 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm px-6 py-4 flex items-center justify-around gap-4 sticky bottom-0 z-20">
        <button
          type="button"
          onClick={goToCreate}
          className={`group flex items-center flex-col gap-1.5 transition-all duration-200 ${
            currentScreen === 'create'
              ? 'text-blue-600 dark:text-blue-400'
              : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-200'
          }`}
        >
          <div className={`p-2 rounded-xl transition-all ${currentScreen === 'create' ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
            <FaMicrophone size={20} />
          </div>
          <span className="text-[10px] font-bold uppercase tracking-widest hidden sm:block">Explore</span>
        </button>

        <button
          type="button"
          onClick={goToPlayer}
          className={`group flex items-center flex-col gap-1.5 transition-all duration-200 ${
            currentScreen === 'player'
              ? 'text-blue-600 dark:text-blue-400'
              : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-200'
          }`}
        >
          <div className={`p-2 rounded-xl transition-all ${currentScreen === 'player' ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
            <FaPlay size={18} />
          </div>
          <span className="text-[10px] font-bold uppercase tracking-widest hidden sm:block">Now Playing</span>
        </button>

        <button
          type="button"
          onClick={goToHistory}
          className={`group flex items-center flex-col gap-1.5 transition-all duration-200 ${
            currentScreen === 'history'
              ? 'text-blue-600 dark:text-blue-400'
              : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-200'
          }`}
        >
          <div className={`p-2 rounded-xl transition-all ${currentScreen === 'history' ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
            <FaHistory size={20} />
          </div>
          <span className="text-[10px] font-bold uppercase tracking-widest hidden sm:block">Library</span>
        </button>
      </div>
    </div>
  );
}

// ── Root App ──────────────────────────────────────────────────────────────────

function App() {
  const { user, session, loading, signInWithGoogle, signOut } = useAuth();

  useEffect(() => {
    setAccessTokenProvider(async () => session?.access_token ?? null);
    return () => setAccessTokenProvider(null);
  }, [session]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <p className="text-gray-700 dark:text-gray-200">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center px-4">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
          <div className="flex items-center justify-center gap-3 mb-4">
            <FaMicrophone className="text-blue-500" size={36} />
            <h1 className="text-2xl font-bold text-gray-800 dark:text-white">Podcast Maker</h1>
          </div>
          <p className="text-gray-600 dark:text-gray-300 mb-6">
            Sign in with Google to access your podcasts and saved preferences.
          </p>
          <button
            type="button"
            onClick={() => void signInWithGoogle()}
            className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-medium transition-colors"
          >
            Continue with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <PodcastProvider>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col">
        {/* Header */}
        <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3">
          <div className="max-w-2xl mx-auto flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <FaMicrophone className="text-blue-500" size={20} />
              <span className="font-semibold text-gray-800 dark:text-white text-base">Podcast Maker</span>
            </div>
            <div className="flex items-center gap-3">
              <p className="text-sm text-gray-500 dark:text-gray-400 hidden sm:block">{user.email}</p>
              <button
                type="button"
                onClick={() => void signOut()}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 transition-colors"
              >
                Sign Out
              </button>
            </div>
          </div>
        </header>

        {/* Main */}
        <main className="flex-1 px-4 py-6 flex flex-col">
          <div className="max-w-2xl mx-auto w-full flex flex-col flex-1">
            <AppInner />
          </div>
        </main>
      </div>
    </PodcastProvider>
  );
}

export default App;
