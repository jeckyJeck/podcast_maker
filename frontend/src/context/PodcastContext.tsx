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
import { DEFAULT_HOST_IDS, FORMAT_MAX_HOSTS } from '../config/podcast';
import { usePodcastStatus } from '../hooks/usePodcastStatus';
import { cachePodcastFiles, getCachedPodcastBlobUrls } from '../services/localFileCache';
import {
  createPodcastTask,
  CREATE_PODCAST_FAILURE_MESSAGE,
  validateCreatePodcastInput,
} from '../services/podcastSubmission';
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

const isValidHostSelection = (v: unknown): v is string[] =>
  Array.isArray(v) && v.length >= 1 && v.length <= 2;

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const isPodcastFiles = (value: unknown): value is PodcastFiles => {
  if (!isObjectRecord(value)) return false;

  const requiredStringKeys: Array<keyof PodcastFiles> = [
    'blueprint',
    'research',
    'outline',
    'script',
    'audio',
  ];

  for (const key of requiredStringKeys) {
    if (typeof value[key] !== 'string') return false;
  }

  if (value.transcript !== undefined && typeof value.transcript !== 'string') return false;
  if (value.transcript_vtt !== undefined && typeof value.transcript_vtt !== 'string') return false;

  return true;
};

const isTaskStatus = (value: unknown): value is PodcastTaskStatus['status'] =>
  value === 'processing' || value === 'completed' || value === 'failed';

const isPodcastTaskStatus = (value: unknown): value is PodcastTaskStatus => {
  if (!isObjectRecord(value)) return false;

  if (!isTaskStatus(value.status)) return false;
  if (value.url !== null && !isPodcastFiles(value.url)) return false;
  if (value.error !== undefined && typeof value.error !== 'string') return false;

  return true;
};

const resolvePodcastFiles = (
  statusFiles: PodcastFiles,
  cachedFiles: Partial<PodcastFiles>,
): PodcastFiles => ({
  blueprint: cachedFiles.blueprint ?? statusFiles.blueprint,
  research: cachedFiles.research ?? statusFiles.research,
  outline: cachedFiles.outline ?? statusFiles.outline,
  script: cachedFiles.script ?? statusFiles.script,
  audio: cachedFiles.audio ?? statusFiles.audio,
  transcript: cachedFiles.transcript ?? statusFiles.transcript,
  transcript_vtt: cachedFiles.transcript_vtt ?? statusFiles.transcript_vtt,
});

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

    const parsed: unknown = JSON.parse(raw);
    if (!isObjectRecord(parsed)) return null;

    return {
      topic: typeof parsed.topic === 'string' ? parsed.topic : '',
      taskId: typeof parsed.taskId === 'string' ? parsed.taskId : null,
      selectedFormat: parsed.selectedFormat === 'solo' ? 'solo' : 'dialogue',
      selectedHostIds: isValidHostSelection(parsed.selectedHostIds)
        ? parsed.selectedHostIds
        : [...DEFAULT_HOST_IDS],
      currentTime:
        typeof parsed.currentTime === 'number' && parsed.currentTime >= 0
          ? parsed.currentTime
          : 0,
      status: isPodcastTaskStatus(parsed.status) ? parsed.status : null,
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

    const arr: unknown = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];

    return arr
      .map((item): PodcastHistoryItem | null => {
        if (!isObjectRecord(item)) return null;

        if (
          typeof item.id !== 'string' ||
          typeof item.topic !== 'string' ||
          !(typeof item.taskId === 'string' || item.taskId === null) ||
          !isValidHostSelection(item.selectedHostIds) ||
          typeof item.currentTime !== 'number' ||
          typeof item.updatedAt !== 'string' ||
          !isPodcastTaskStatus(item.status) ||
          !item.status.url
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
      : [...DEFAULT_HOST_IDS],
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
    persistedSession?.selectedHostIds ?? [...DEFAULT_HOST_IDS],
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
    return resolvePodcastFiles(effectiveStatus.url, localFileUrls);
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
    const validation = validateCreatePodcastInput({ topic, selectedFormat, selectedHostIds });
    if (!validation.isValid) {
      alert(validation.message);
      return;
    }
    setIsSubmitting(true);
    setRestoredStatus(null);
    setLocalFileUrls({});
    for (const url of objectUrlsRef.current) URL.revokeObjectURL(url);
    objectUrlsRef.current = [];
    try {
      const nextTaskId = await createPodcastTask({ topic, selectedFormat, selectedHostIds });
      setTaskId(nextTaskId);
    } catch (err) {
      console.error(err);
      alert(CREATE_PODCAST_FAILURE_MESSAGE);
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
