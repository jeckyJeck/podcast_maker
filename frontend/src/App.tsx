import { useCallback, useEffect, useMemo, useRef } from 'react';
import { FaCompass, FaHistory, FaMicrophone, FaPlay } from 'react-icons/fa';
import { FaArrowRightFromBracket } from 'react-icons/fa6';
import { useAuth } from './context/AuthContext';
import { setAccessTokenProvider } from './services/api';
import { usePodcastNavigation, type PodcastScreen } from './hooks/usePodcastNavigation';
import { usePodcastHosts } from './hooks/usePodcastHosts';
import { usePodcastSession } from './hooks/usePodcastSession';
import { usePodcastHistory } from './hooks/usePodcastHistory';
import { usePodcastPlayback } from './hooks/usePodcastPlayback';
import type { PodcastHistoryItem } from './services/podcastPersistence';
import { CreateScreen } from './components/CreateScreen';
import { PlayerScreen } from './components/PlayerScreen';
import { HistoryScreen } from './components/HistoryScreen';
import './index.css';

// ── Inner app (composes the podcast hooks; no Context — screens get props) ──

function AppInner() {
  const { user } = useAuth();

  const nav = usePodcastNavigation();
  const hosts = usePodcastHosts(user);

  // usePodcastHistory needs session state, usePodcastSession needs history's
  // refreshCloudHistory — neither depends on the other's *values* at call
  // time (refreshCloudHistory only needs `user`), so a ref breaks the cycle.
  const refreshCloudHistoryRef = useRef<() => void>(() => {});
  const refreshCloudHistory = useCallback(() => refreshCloudHistoryRef.current(), []);

  const session = usePodcastSession({
    user,
    selectedFormat: hosts.selectedFormat,
    selectedHostIds: hosts.selectedHostIds,
    refreshCloudHistory,
  });

  const onRestore = useCallback((item: PodcastHistoryItem) => {
    hosts.applyHostConfig(item.selectedFormat, item.selectedHostIds);
    session.setTopic(item.topic);
    session.setTaskId(null);
    session.setRestoredStatus(item.status);
    session.setCurrentTime(item.currentTime);
    session.setIsSubmitting(false);
    nav.goToPlayer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hosts, session, nav]);

  const onRetryStart = useCallback((item: PodcastHistoryItem) => {
    session.setIsSubmitting(true);
    session.setRestoredStatus({ ...item.status, status: 'queued', error: undefined });
    session.clearFileCache();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  const onRetrySuccess = useCallback((item: PodcastHistoryItem, newTaskId: string) => {
    session.setTopic(item.topic);
    session.setTaskId(newTaskId);
    hosts.applyHostConfig(item.selectedFormat, item.selectedHostIds);
    session.setIsSubmitting(false);
    nav.goToHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, hosts, nav]);

  const onRetryError = useCallback(() => {
    session.setIsSubmitting(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  const sessionSnapshot = useMemo(() => ({
    topic: session.topic,
    taskId: session.taskId,
    selectedFormat: hosts.selectedFormat,
    selectedHostIds: hosts.selectedHostIds,
    currentTime: session.currentTime,
    status: session.effectiveStatus,
  }), [
    session.topic,
    session.taskId,
    hosts.selectedFormat,
    hosts.selectedHostIds,
    session.currentTime,
    session.effectiveStatus,
  ]);

  const history = usePodcastHistory({
    user,
    taskId: session.taskId,
    pollingError: session.pollingError,
    sessionSnapshot,
    onRestore,
    onRetryStart,
    onRetrySuccess,
    onRetryError,
  });

  refreshCloudHistoryRef.current = history.refreshCloudHistory;

  const playback = usePodcastPlayback({
    resolvedFiles: session.resolvedFiles,
    persistedSession: session.persistedSession,
    setCurrentTime: session.setCurrentTime,
  });

  const podcastReady = session.effectiveStatus?.status === 'completed' && Boolean(session.resolvedFiles?.audio);

  const handleReset = useCallback(() => {
    playback.resetPlayback();
    session.resetSessionFields();
    nav.goToCreate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playback, session, nav]);

  const screens: Record<PodcastScreen, JSX.Element> = {
    create: (
      <CreateScreen
        hosts={hosts.hosts}
        hostsLoading={hosts.hostsLoading}
        selectedFormat={hosts.selectedFormat}
        selectedHostIds={hosts.selectedHostIds}
        hostPickerOpen={hosts.hostPickerOpen}
        setHostPickerOpen={hosts.setHostPickerOpen}
        saveHostsPreference={hosts.saveHostsPreference}
        handleFormatChange={hosts.handleFormatChange}
        topic={session.topic}
        setTopic={session.setTopic}
        isSubmitting={session.isSubmitting}
        handleSubmit={session.handleSubmit}
        handleReset={handleReset}
        effectiveStatus={session.effectiveStatus}
        podcastReady={podcastReady}
        goToPlayer={nav.goToPlayer}
      />
    ),
    player: (
      <PlayerScreen
        topic={session.topic}
        resolvedFiles={session.resolvedFiles}
        isPlaying={playback.isPlaying}
        currentTime={session.currentTime}
        duration={playback.duration}
        playbackSpeed={playback.playbackSpeed}
        togglePlay={playback.togglePlay}
        seekTo={playback.seekTo}
        skipBy={playback.skipBy}
        changeSpeed={playback.changeSpeed}
        podcastReady={podcastReady}
        goToCreate={nav.goToCreate}
        goToHistory={nav.goToHistory}
      />
    ),
    history: (
      <HistoryScreen
        displayHistory={history.displayHistory}
        cloudLoading={history.cloudLoading}
        handleRestoreFromHistory={history.handleRestoreFromHistory}
        handleRetryPodcast={history.handleRetryPodcast}
      />
    ),
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col relative">
      {/* Always-mounted audio element — survives screen switches */}
      <audio ref={playback.audioRef} preload="metadata" style={{ display: 'none' }} />

      <div className="flex-1 flex flex-col pb-28">
        {screens[nav.currentScreen]}
      </div>

      <div className="fixed bottom-0 left-0 right-0 z-30 px-4 pb-4 pt-8 bg-gradient-to-t from-[#0d0d0d] via-[#0d0d0d]/95 to-transparent">
        <nav className="mx-auto flex w-full max-w-2xl items-center justify-around rounded-[2rem] border border-white/5 bg-[#1a1a1a]/90 px-4 py-3 shadow-[0_-20px_70px_rgba(0,0,0,0.65)] backdrop-blur-xl">
        <button
          type="button"
          onClick={nav.goToCreate}
          className={`group flex min-w-20 items-center flex-col gap-1.5 transition-all duration-300 ${
            nav.currentScreen === 'create'
              ? 'text-white'
              : 'text-[#8f93a3] hover:text-white'
          }`}
        >
          <div className={`flex h-10 w-10 items-center justify-center rounded-full transition-all ${nav.currentScreen === 'create' ? 'bg-gradient-to-br from-[#4D8EFF] to-[#571BC1] shadow-[0_0_28px_rgba(77,142,255,0.45)]' : 'bg-transparent'}`}>
            <FaCompass size={18} />
          </div>
          <span className="text-[11px] font-semibold tracking-wide">Explore</span>
        </button>

        <button
          type="button"
          onClick={nav.currentScreen === 'player' ? undefined : nav.goToPlayer}
          aria-current={nav.currentScreen === 'player' ? 'page' : undefined}
          className={`group -mt-8 flex min-w-20 items-center flex-col gap-1.5 transition-all duration-300 ${
            nav.currentScreen === 'player'
              ? 'text-white'
              : 'text-[#8f93a3] hover:text-white'
          }`}
        >
          <div className={`flex h-16 w-16 items-center justify-center rounded-full transition-all ${nav.currentScreen === 'player' ? 'bg-gradient-to-br from-[#4D8EFF] to-[#571BC1] shadow-[0_0_36px_rgba(87,27,193,0.65)]' : 'bg-[#25252a]'}`}>
            <FaPlay size={18} className="ml-0.5" />
          </div>
          <span className="text-[11px] font-semibold tracking-wide">Playing</span>
        </button>

        <button
          type="button"
          onClick={nav.goToHistory}
          className={`group flex min-w-20 items-center flex-col gap-1.5 transition-all duration-300 ${
            nav.currentScreen === 'history'
              ? 'text-white'
              : 'text-[#8f93a3] hover:text-white'
          }`}
        >
          <div className={`flex h-10 w-10 items-center justify-center rounded-full transition-all ${nav.currentScreen === 'history' ? 'bg-gradient-to-br from-[#4D8EFF] to-[#571BC1] shadow-[0_0_28px_rgba(77,142,255,0.45)]' : 'bg-transparent'}`}>
            <FaHistory size={18} />
          </div>
          <span className="text-[11px] font-semibold tracking-wide">Library</span>
        </button>
        </nav>
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
      <div className="min-h-screen bg-[#0D0D0D] flex items-center justify-center">
        <p className="text-[#b8c7ff]">Loading...</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-[#0D0D0D] text-white flex items-center justify-center px-4 studio-shell">
        <div className="w-full max-w-md rounded-[2rem] border border-white/10 bg-white/[0.06] p-8 text-center shadow-[0_30px_90px_rgba(0,0,0,0.5)] backdrop-blur-xl">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-[#4D8EFF] to-[#571BC1] shadow-[0_0_36px_rgba(77,142,255,0.35)]">
              <FaMicrophone size={24} />
            </div>
            <h1 className="font-display text-3xl font-extrabold">Podcast Maker</h1>
          </div>
          <p className="text-[#a7aab8] mb-6">
            Sign in with Google to access your podcasts and saved preferences.
          </p>
          <button
            type="button"
            onClick={() => void signInWithGoogle()}
            className="w-full rounded-full bg-gradient-to-r from-[#4D8EFF] to-[#571BC1] px-4 py-3 font-bold uppercase tracking-[0.18em] text-white shadow-[0_18px_45px_rgba(77,142,255,0.25)] transition-transform hover:-translate-y-0.5"
          >
            Continue with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0D0D0D] text-white flex flex-col studio-shell">
      <header className="sticky top-0 z-40 border-b border-white/[0.04] bg-[#0D0D0D]/86 px-4 py-4 backdrop-blur-2xl">
        <div className="w-full sm:max-w-2xl sm:mx-auto flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="h-11 w-11 shrink-0 overflow-hidden rounded-full border border-[#4D8EFF]/30 bg-[#181a20] shadow-[0_0_24px_rgba(77,142,255,0.14)]">
              <div className="grid h-full w-full place-items-center bg-gradient-to-br from-[#1f2937] to-[#060606] text-[#b8c7ff]">
                <FaMicrophone size={17} />
              </div>
            </div>
            <span className="font-display truncate text-xl font-extrabold text-[#d6ddff]">Podcast Maker</span>
          </div>
          <div className="flex items-center gap-3">
            <p className="hidden max-w-48 truncate text-xs text-[#8f93a3] sm:block">{user.email}</p>
            <button
              type="button"
              onClick={() => void signOut()}
              className="grid h-10 w-10 place-items-center rounded-full border border-white/10 bg-white/[0.04] text-[#cbd3ee] transition-all hover:border-[#9bb8ff]/50 hover:text-white"
              title="Sign out"
            >
              <FaArrowRightFromBracket size={16} />
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 px-4 py-6 flex flex-col">
        <div className="w-full sm:max-w-2xl sm:mx-auto flex flex-col flex-1">
          <AppInner />
        </div>
      </main>
    </div>
  );
}

export default App;
