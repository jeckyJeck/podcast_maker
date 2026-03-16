import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { podcastApi } from '../services/api';
import { usePodcastStatus } from '../hooks/usePodcastStatus';
import { cachePodcastFiles, getCachedPodcastBlobUrls } from '../services/localFileCache';
import { useAuth } from './AuthContext';
import type {
  HostProfile,
  PodcastFiles,
  PodcastFormat,
  PodcastTaskStatus,
  UserPodcastRecord,
} from '../types/podcast';

// ── Storage helpers ────────────────────────────────────────────────────────────

const PODCAST_SESSION_KEY = 'podcast-maker.session.v1';
const PODCAST_HISTORY_KEY = 'podcast-maker.history.v1';
const MAX_HISTORY = 5;

const FORMAT_MAX_HOSTS: Record<PodcastFormat, number> = {
  dialogue: 2,
  solo: 1,
};

const isValidHostSelection = (v: unknown): v is string[] =>
  Array.isArray(v) && v.length >= 1 && v.length <= 2;

export interface PodcastHistoryItem {
  id: string;
  topic: string;
  taskId: string | null;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  currentTime: number;
  status: PodcastTaskStatus;
  updatedAt: string;
}

interface PersistedSession {
  topic: string;
  taskId: string | null;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  currentTime: number;
  status: PodcastTaskStatus | null;
}

const loadSession = (): PersistedSession | null => {
  try {
    const raw = localStorage.getItem(PODCAST_SESSION_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as PersistedSession;
    return {
      topic: typeof p.topic === 'string' ? p.topic : '',
      taskId: typeof p.taskId === 'string' ? p.taskId : null,
      selectedFormat: p.selectedFormat === 'solo' ? 'solo' : 'dialogue',
      selectedHostIds: isValidHostSelection(p.selectedHostIds)
        ? p.selectedHostIds
        : ['sarah_curious', 'mike_expert'],
      currentTime: typeof p.currentTime === 'number' && p.currentTime >= 0 ? p.currentTime : 0,
      status: p.status ?? null,
    };
  } catch {
    return null;
  }
};

const saveSession = (s: PersistedSession) => {
  try {
    localStorage.setItem(PODCAST_SESSION_KEY, JSON.stringify(s));
  } catch { /* noop */ }
};

const clearSession = () => {
  try { localStorage.removeItem(PODCAST_SESSION_KEY); } catch { /* noop */ }
};

const loadHistory = (): PodcastHistoryItem[] => {
  try {
    const raw = localStorage.getItem(PODCAST_HISTORY_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as Partial<PodcastHistoryItem>[];
    if (!Array.isArray(arr)) return [];
    return arr
      .map((item): PodcastHistoryItem | null => {
        if (
          typeof item.id !== 'string' ||
          typeof item.topic !== 'string' ||
          !(typeof item.taskId === 'string' || item.taskId === null) ||
          !isValidHostSelection(item.selectedHostIds) ||
          typeof item.currentTime !== 'number' ||
          typeof item.updatedAt !== 'string' ||
          !item.status?.url
        ) return null;
        return {
          id: item.id,
          topic: item.topic,
          taskId: item.taskId,
          selectedFormat: item.selectedFormat === 'solo' ? 'solo' : 'dialogue',
          selectedHostIds: item.selectedHostIds,
          currentTime: item.currentTime,
          status: item.status,
          updatedAt: item.updatedAt,
        };
      })
      .filter((i): i is PodcastHistoryItem => i !== null);
  } catch {
    return [];
  }
};

const saveHistory = (items: PodcastHistoryItem[]) => {
  try {
    localStorage.setItem(PODCAST_HISTORY_KEY, JSON.stringify(items));
  } catch { /* noop */ }
};

const upsertHistory = (
  items: PodcastHistoryItem[],
  session: PersistedSession,
): PodcastHistoryItem[] => {
  if (!session.status?.url) return items;
  const identity = session.taskId ?? session.status.url.audio;
  const existing = items.find((i) => (i.taskId ?? i.status.url?.audio) === identity);
  const next: PodcastHistoryItem = {
    id: existing?.id ?? identity,
    topic: session.topic,
    taskId: session.taskId,
    selectedFormat: session.selectedFormat,
    selectedHostIds: session.selectedHostIds,
    currentTime: session.currentTime,
    status: session.status,
    updatedAt: new Date().toISOString(),
  };
  return [next, ...items.filter((i) => i.id !== next.id)].slice(0, MAX_HISTORY);
};

const mapCloudToHistory = (r: UserPodcastRecord): PodcastHistoryItem | null => {
  if (r.status !== 'completed' || !r.url) return null;
  return {
    id: r.id,
    topic: r.topic,
    taskId: r.task_id,
    selectedFormat: 'dialogue',
    selectedHostIds: isValidHostSelection(r.host_ids)
      ? r.host_ids
      : ['sarah_curious', 'mike_expert'],
    currentTime: 0,
    status: { status: r.status, url: r.url, error: r.error },
    updatedAt: r.updated_at ?? r.created_at ?? new Date().toISOString(),
  };
};

// ── Context type ───────────────────────────────────────────────────────────────

export interface PodcastContextValue {
  // Navigation
  currentScreen: 'create' | 'player' | 'history';
  goToPlayer: () => void;
  goToCreate: () => void;
  goToHistory: () => void;
  podcastReady: boolean;

  // Create form
  topic: string;
  setTopic: (v: string) => void;
  isSubmitting: boolean;
  handleSubmit: () => Promise<void>;
  handleReset: () => void;

  // Format
  selectedFormat: PodcastFormat;
  handleFormatChange: (format: PodcastFormat) => void;

  // Hosts
  hosts: HostProfile[];
  hostsLoading: boolean;
  selectedHostIds: string[];
  setSelectedHostIds: (ids: string[]) => void;
  hostPickerOpen: boolean;
  setHostPickerOpen: (v: boolean) => void;
  saveHostsPreference: (ids: string[]) => Promise<void>;

  // Status / result
  effectiveStatus: PodcastTaskStatus | null;
  resolvedFiles: PodcastFiles | null;

  // History
  displayHistory: PodcastHistoryItem[];
  cloudLoading: boolean;
  handleRestoreFromHistory: (item: PodcastHistoryItem) => void;
  historyOpen: boolean;
  setHistoryOpen: (v: boolean) => void;

  // Audio controls
  audioRef: React.RefObject<HTMLAudioElement>;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  playbackSpeed: number;
  togglePlay: () => void;
  seekTo: (time: number) => void;
  skipBy: (seconds: number) => void;
  changeSpeed: (speed: number) => void;
}

const PodcastContext = createContext<PodcastContextValue | null>(null);

export const usePodcast = (): PodcastContextValue => {
  const ctx = useContext(PodcastContext);
  if (!ctx) throw new Error('usePodcast must be used inside PodcastProvider');
  return ctx;
};

// ── Provider ───────────────────────────────────────────────────────────────────

export const PodcastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();

  // Session bootstrap
  const [persistedSession] = useState<PersistedSession | null>(() => loadSession());
  const [persistedHistory, setPersistedHistory] = useState<PodcastHistoryItem[]>(() => loadHistory());
  const [cloudHistory, setCloudHistory] = useState<PodcastHistoryItem[]>([]);
  const [cloudLoading, setCloudLoading] = useState(false);

  // Screen
  const [currentScreen, setCurrentScreen] = useState<'create' | 'player' | 'history'>('create');

  const goToPlayer = useCallback(() => {
    setCurrentScreen('player');
    setRestoredStatus(null);
  }, []);
  const goToCreate = useCallback(() => {
    setCurrentScreen('create');
    setRestoredStatus(null);
  }, []);
  const goToHistory = useCallback(() => {
    setCurrentScreen('history');
    setRestoredStatus(null);
  }, []);

  // Form
  const [topic, setTopic] = useState(persistedSession?.topic ?? '');
  const [taskId, setTaskId] = useState<string | null>(() => {
    if (!persistedSession?.taskId) {
      return null;
    }

    if (persistedSession.status?.status === 'processing') {
      return persistedSession.taskId;
    }

    return null;
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Format & Hosts
  const [selectedFormat, setSelectedFormat] = useState<PodcastFormat>(
    persistedSession?.selectedFormat ?? 'dialogue',
  );
  const [selectedHostIds, setSelectedHostIds] = useState<string[]>(
    persistedSession?.selectedHostIds ?? ['sarah_curious', 'mike_expert'],
  );
  const [hosts, setHosts] = useState<HostProfile[]>([]);
  const [hostsLoading, setHostsLoading] = useState(true);
  const [hostPickerOpen, setHostPickerOpen] = useState(false);

  // Status
  const [restoredStatus, setRestoredStatus] = useState<PodcastTaskStatus | null>(
    persistedSession?.status ?? null,
  );
  const [localFileUrls, setLocalFileUrls] = useState<Partial<PodcastFiles>>({});
  const [historyOpen, setHistoryOpen] = useState(false);
  const objectUrlsRef = useRef<string[]>([]);
  const lastCloudSyncRef = useRef<string | null>(null);

  // Audio element state
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(persistedSession?.currentTime ?? 0);
  const [duration, setDuration] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  const { status } = usePodcastStatus(taskId);
  const effectiveStatus = status ?? restoredStatus;

  // ── Load hosts ───────────────────────────────────────────────────────────────

  useEffect(() => {
    podcastApi
      .getAvailableHosts()
      .then((r) => setHosts(r.hosts))
      .catch(console.error)
      .finally(() => setHostsLoading(false));
  }, []);

  // ── Load cloud data on login ─────────────────────────────────────────────────

  useEffect(() => {
    if (!user) { setCloudHistory([]); return; }
    setCloudLoading(true);
    Promise.all([podcastApi.getUserPreferences(), podcastApi.getUserPodcasts()])
      .then(([prefs, pods]) => {
        if (isValidHostSelection(prefs.preferred_hosts)) {
          setSelectedHostIds(prefs.preferred_hosts);
        }
        setCloudHistory(
          pods.podcasts
            .map(mapCloudToHistory)
            .filter((i): i is PodcastHistoryItem => i !== null),
        );
      })
      .catch(console.error)
      .finally(() => setCloudLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  // ── Sync status → restoredStatus ─────────────────────────────────────────────

  useEffect(() => {
    if (status) setRestoredStatus(status);
  }, [status]);

  // ── Cache podcast files when complete ────────────────────────────────────────

  useEffect(() => {
    const files = effectiveStatus?.status === 'completed' ? effectiveStatus.url : null;
    if (!files) return;
    let canceled = false;
    (async () => {
      await cachePodcastFiles(files);
      const blobs = await getCachedPodcastBlobUrls(files);
      if (canceled) return;
      for (const url of objectUrlsRef.current) URL.revokeObjectURL(url);
      objectUrlsRef.current = Object.values(blobs).filter(
        (v): v is string => typeof v === 'string' && v.startsWith('blob:'),
      );
      setLocalFileUrls(blobs);
    })();
    return () => { canceled = true; };
  }, [effectiveStatus]);

  // ── Persist session ──────────────────────────────────────────────────────────

  useEffect(() => {
    const s = status ?? restoredStatus;
    if (!taskId && !topic.trim() && !s?.url) return;
    const session: PersistedSession = {
      topic, taskId, selectedFormat, selectedHostIds, currentTime, status: s,
    };
    saveSession(session);
    if (s?.status === 'completed' && s.url) {
      setPersistedHistory((prev) => {
        const updated = upsertHistory(prev, session);
        saveHistory(updated);
        return updated;
      });
    }
  }, [currentTime, restoredStatus, selectedFormat, selectedHostIds, status, taskId, topic]);

  // ── Refresh cloud history after completion ───────────────────────────────────

  useEffect(() => {
    if (!user || !taskId || effectiveStatus?.status !== 'completed') return;
    if (lastCloudSyncRef.current === taskId) return;
    lastCloudSyncRef.current = taskId;
    podcastApi
      .getUserPodcasts()
      .then((r) =>
        setCloudHistory(
          r.podcasts
            .map(mapCloudToHistory)
            .filter((i): i is PodcastHistoryItem => i !== null),
        ),
      )
      .catch(console.error);
  }, [effectiveStatus?.status, taskId, user]);

  // ── Audio element events ─────────────────────────────────────────────────────

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTime = () => setCurrentTime(audio.currentTime);
    const onMeta = () => setDuration(audio.duration);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => setIsPlaying(false);

    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('loadedmetadata', onMeta);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('ended', onEnded);

    return () => {
      audio.removeEventListener('timeupdate', onTime);
      audio.removeEventListener('loadedmetadata', onMeta);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('ended', onEnded);
    };
  }, []);

  // ── Update audio src when resolved files change ──────────────────────────────

  const resolvedFiles = useMemo<PodcastFiles | null>(() => {
    if (!effectiveStatus?.url) return null;
    return { ...effectiveStatus.url, ...localFileUrls } as PodcastFiles;
  }, [effectiveStatus, localFileUrls]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !resolvedFiles?.audio) return;
    if (audio.src === resolvedFiles.audio) return;
    audio.src = resolvedFiles.audio;
    audio.load();
    // Restore persisted time after load
    if (persistedSession && persistedSession.currentTime > 0) {
      const restoreTime = persistedSession.currentTime;
      audio.addEventListener('loadedmetadata', () => {
        audio.currentTime = restoreTime;
      }, { once: true });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedFiles?.audio]);

  // ── Cleanup blob URLs ────────────────────────────────────────────────────────

  useEffect(() => () => {
    for (const url of objectUrlsRef.current) URL.revokeObjectURL(url);
  }, []);

  // ── Audio controls ───────────────────────────────────────────────────────────

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !resolvedFiles?.audio) return;
    if (isPlaying) audio.pause();
    else void audio.play();
  }, [isPlaying, resolvedFiles?.audio]);

  const seekTo = useCallback((time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const apply = () => { audio.currentTime = time; setCurrentTime(time); };
    if (audio.readyState >= 1) apply();
    else audio.addEventListener('loadedmetadata', apply, { once: true });
  }, []);

  const skipBy = useCallback((seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const newTime = Math.min(Math.max(0, audio.currentTime + seconds), audio.duration || 0);
    audio.currentTime = newTime;
    setCurrentTime(newTime);
  }, []);

  const changeSpeed = useCallback((speed: number) => {
    const audio = audioRef.current;
    if (audio) audio.playbackRate = speed;
    setPlaybackSpeed(speed);
  }, []);

  // ── Navigation ───────────────────────────────────────────────────────────────

  const podcastReady = effectiveStatus?.status === 'completed' && Boolean(resolvedFiles?.audio);

  // ── Format change ─────────────────────────────────────────────────────────────

  const handleFormatChange = useCallback((fmt: PodcastFormat) => {
    const newMax = FORMAT_MAX_HOSTS[fmt];
    const prevMax = FORMAT_MAX_HOSTS[selectedFormat];
    setSelectedFormat(fmt);
    if (newMax < prevMax) {
      // Trim excess hosts (keep the last N selected)
      setSelectedHostIds((prev) => prev.slice(-newMax));
    } else if (newMax > selectedHostIds.length) {
      // Need more hosts — open picker automatically
      setHostPickerOpen(true);
    }
  }, [selectedFormat, selectedHostIds.length]);

  // ── Submit / Reset / Restore ─────────────────────────────────────────────────

  const handleSubmit = useCallback(async () => {
    if (!topic.trim()) { alert('אנא הכנס נושא לפודקאסט'); return; }
    const maxHosts = FORMAT_MAX_HOSTS[selectedFormat];
    if (selectedHostIds.length !== maxHosts) {
      alert(selectedFormat === 'dialogue'
        ? 'בפורמט שיחה צריך לבחור בדיוק 2 מארחים'
        : 'בפורמט סולו צריך לבחור בדיוק מארח אחד');
      return;
    }
    setIsSubmitting(true);
    setRestoredStatus(null);
    setLocalFileUrls({});
    for (const url of objectUrlsRef.current) URL.revokeObjectURL(url);
    objectUrlsRef.current = [];
    try {
      const res = await podcastApi.createPodcast(topic.trim(), selectedHostIds, selectedFormat);
      setTaskId(res.task_id);
    } catch (err) {
      console.error(err);
      alert('שגיאה ביצירת הפודקאסט. אנא נסה שוב.');
    } finally {
      setIsSubmitting(false);
    }
  }, [topic, selectedFormat, selectedHostIds]);

  const handleReset = useCallback(() => {
    const audio = audioRef.current;
    if (audio) { audio.pause(); audio.src = ''; }
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setTopic('');
    setTaskId(null);
    setSelectedFormat('dialogue');
    setIsSubmitting(false);
    setRestoredStatus(null);
    setLocalFileUrls({});
    for (const url of objectUrlsRef.current) URL.revokeObjectURL(url);
    objectUrlsRef.current = [];
    clearSession();
    setCurrentScreen('create');
  }, []);

  const handleRestoreFromHistory = useCallback((item: PodcastHistoryItem) => {
    setTopic(item.topic);
    setTaskId(null);
    setSelectedFormat(item.selectedFormat);
    setSelectedHostIds(item.selectedHostIds);
    setRestoredStatus(item.status);
    setCurrentTime(item.currentTime);
    setIsSubmitting(false);
    setCurrentScreen('player');
  }, []);

  const saveHostsPreference = useCallback(async (ids: string[]) => {
    setSelectedHostIds(ids);
    if (user) {
      try { await podcastApi.updateUserPreferences(ids); } catch { /* noop */ }
    }
  }, [user]);

  const displayHistory = cloudHistory.length > 0 ? cloudHistory : persistedHistory;

  // ── Value ─────────────────────────────────────────────────────────────────────

  const value: PodcastContextValue = {
    currentScreen, goToPlayer, goToCreate, goToHistory, podcastReady,
    topic, setTopic, isSubmitting, handleSubmit, handleReset,
    selectedFormat, handleFormatChange,
    hosts, hostsLoading, selectedHostIds, setSelectedHostIds,
    hostPickerOpen, setHostPickerOpen, saveHostsPreference,
    effectiveStatus, resolvedFiles,
    displayHistory, cloudLoading, handleRestoreFromHistory,
    historyOpen, setHistoryOpen,
    audioRef, isPlaying, currentTime, duration, playbackSpeed,
    togglePlay, seekTo, skipBy, changeSpeed,
  };

  return (
    <PodcastContext.Provider value={value}>
      {/* Always-mounted audio element — survives screen switches */}
      <audio ref={audioRef} preload="metadata" style={{ display: 'none' }} />
      {children}
    </PodcastContext.Provider>
  );
};
