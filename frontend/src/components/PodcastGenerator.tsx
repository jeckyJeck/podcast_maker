import React, { useState, useEffect, useMemo, useRef } from 'react';
import { FaMicrophone, FaRedo, FaUsers } from 'react-icons/fa';
import { podcastApi } from '../services/api';
import { usePodcastStatus } from '../hooks/usePodcastStatus';
import { StatusDisplay } from './StatusDisplay';
import { AudioPlayer } from './AudioPlayer';
import { FileDownloader } from './FileDownloader';
import { HostSelector } from './HostSelector';
import TranscriptViewer from './TranscriptViewer';
import { cachePodcastFiles, getCachedPodcastBlobUrls } from '../services/localFileCache';
import type { HostProfile, PodcastFiles } from '../types/podcast';
import type { PodcastTaskStatus } from '../types/podcast';

const PODCAST_SESSION_STORAGE_KEY = 'podcast-maker.session.v1';
const PODCAST_HISTORY_STORAGE_KEY = 'podcast-maker.history.v1';
const MAX_HISTORY_ITEMS = 5;

interface PersistedPodcastSession {
  topic: string;
  taskId: string | null;
  selectedHostIds: string[];
  currentTime: number;
  status: PodcastTaskStatus | null;
}

interface PodcastHistoryItem extends PersistedPodcastSession {
  id: string;
  updatedAt: string;
}

const loadPersistedSession = (): PersistedPodcastSession | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(PODCAST_SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as PersistedPodcastSession;
    return {
      topic: typeof parsed.topic === 'string' ? parsed.topic : '',
      taskId: typeof parsed.taskId === 'string' ? parsed.taskId : null,
      selectedHostIds: Array.isArray(parsed.selectedHostIds) && parsed.selectedHostIds.length === 2
        ? parsed.selectedHostIds
        : ['sarah_curious', 'mike_expert'],
      currentTime: typeof parsed.currentTime === 'number' && parsed.currentTime >= 0 ? parsed.currentTime : 0,
      status: parsed.status ?? null,
    };
  } catch (error) {
    console.error('Failed to load persisted podcast session:', error);
    return null;
  }
};

const savePersistedSession = (session: PersistedPodcastSession) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(PODCAST_SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch (error) {
    console.error('Failed to persist podcast session:', error);
  }
};

const clearPersistedSession = () => {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.removeItem(PODCAST_SESSION_STORAGE_KEY);
};

const loadPersistedHistory = (): PodcastHistoryItem[] => {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(PODCAST_HISTORY_STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw) as PodcastHistoryItem[];
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.filter((item) => {
      return (
        typeof item.id === 'string' &&
        typeof item.topic === 'string' &&
        (typeof item.taskId === 'string' || item.taskId === null) &&
        Array.isArray(item.selectedHostIds) &&
        item.selectedHostIds.length === 2 &&
        typeof item.currentTime === 'number' &&
        typeof item.updatedAt === 'string' &&
        Boolean(item.status?.url)
      );
    });
  } catch (error) {
    console.error('Failed to load podcast history:', error);
    return [];
  }
};

const savePersistedHistory = (items: PodcastHistoryItem[]) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(PODCAST_HISTORY_STORAGE_KEY, JSON.stringify(items));
  } catch (error) {
    console.error('Failed to save podcast history:', error);
  }
};

const upsertHistoryItem = (
  items: PodcastHistoryItem[],
  session: PersistedPodcastSession
): PodcastHistoryItem[] => {
  if (!session.status?.url) {
    return items;
  }

  const identity = session.taskId ?? session.status.url.audio;
  const existingItem = items.find((item) => (item.taskId ?? item.status?.url?.audio) === identity);
  const now = new Date().toISOString();

  const nextItem: PodcastHistoryItem = {
    id: existingItem?.id ?? identity,
    topic: session.topic,
    taskId: session.taskId,
    selectedHostIds: session.selectedHostIds,
    currentTime: session.currentTime,
    status: session.status,
    updatedAt: now,
  };

  const remainingItems = items.filter((item) => item.id !== nextItem.id);
  return [nextItem, ...remainingItems].slice(0, MAX_HISTORY_ITEMS);
};

export const PodcastGenerator: React.FC = () => {
  const [persistedSession] = useState<PersistedPodcastSession | null>(() => loadPersistedSession());
  const [persistedHistory, setPersistedHistory] = useState<PodcastHistoryItem[]>(() => loadPersistedHistory());
  const [topic, setTopic] = useState(persistedSession?.topic ?? '');
  const [taskId, setTaskId] = useState<string | null>(persistedSession?.taskId ?? null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isHostSelectorOpen, setIsHostSelectorOpen] = useState(false);
  const [selectedHostIds, setSelectedHostIds] = useState<string[]>(persistedSession?.selectedHostIds ?? ['sarah_curious', 'mike_expert']);
  const [hosts, setHosts] = useState<HostProfile[]>([]);
  const [hostsLoading, setHostsLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(persistedSession?.currentTime ?? 0);
  const [seekToTime, setSeekToTime] = useState<number | undefined>(
    persistedSession && persistedSession.currentTime > 0 ? persistedSession.currentTime : undefined
  );
  const [localFileUrls, setLocalFileUrls] = useState<Partial<PodcastFiles>>({});
  const [restoredStatus, setRestoredStatus] = useState<PodcastTaskStatus | null>(persistedSession?.status ?? null);
  const objectUrlsRef = useRef<string[]>([]);
  const { status } = usePodcastStatus(taskId);
  const effectiveStatus = status ?? restoredStatus;

  const replaceLocalBlobUrls = (nextBlobUrls: Partial<PodcastFiles>) => {
    for (const url of objectUrlsRef.current) {
      URL.revokeObjectURL(url);
    }

    objectUrlsRef.current = Object.values(nextBlobUrls).filter(
      (value): value is string => typeof value === 'string' && value.startsWith('blob:')
    );
    setLocalFileUrls(nextBlobUrls);
  };

  // Load hosts on component mount
  useEffect(() => {
    const loadHosts = async () => {
      try {
        const response = await podcastApi.getAvailableHosts();
        setHosts(response.hosts);
      } catch (error) {
        console.error('Failed to load hosts:', error);
      } finally {
        setHostsLoading(false);
      }
    };
    loadHosts();
  }, []);

  const getHostNames = (hostIds: string[]): string => {
    return hostIds
      .map((id) => hosts.find((h) => h.id === id)?.name)
      .filter(Boolean)
      .join(' ו');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!topic.trim()) {
      alert('אנא הכנס נושא לפודקאסט');
      return;
    }

    if (selectedHostIds.length !== 2) {
      alert('אנא בחר בדיוק 2 מארחים');
      return;
    }

    setIsSubmitting(true);
    setRestoredStatus(null);
    setCurrentTime(0);
    setSeekToTime(undefined);
    replaceLocalBlobUrls({});
    
    try {
      const response = await podcastApi.createPodcast(topic.trim(), selectedHostIds);
      setTaskId(response.task_id);
    } catch (error) {
      console.error('Error creating podcast:', error);
      alert('שגיאה ביצירת הפודקאסט. אנא נסה שוב.');
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    setTopic('');
    setTaskId(null);
    setIsSubmitting(false);
    setRestoredStatus(null);
    setCurrentTime(0);
    setSeekToTime(undefined);
    replaceLocalBlobUrls({});
    clearPersistedSession();
  };

  const handleRestoreFromHistory = (item: PodcastHistoryItem) => {
    setTopic(item.topic);
    setTaskId(item.taskId);
    setSelectedHostIds(item.selectedHostIds);
    setRestoredStatus(item.status);
    setCurrentTime(item.currentTime);
    setSeekToTime(item.currentTime > 0 ? item.currentTime : undefined);
    setIsSubmitting(false);
  };

  const handleSeek = (timeInSeconds: number) => {
    setSeekToTime(timeInSeconds);
  };

  useEffect(() => {
    if (status) {
      setRestoredStatus(status);
    }
  }, [status]);

  useEffect(() => {
    return () => {
      for (const url of objectUrlsRef.current) {
        URL.revokeObjectURL(url);
      }
    };
  }, []);

  useEffect(() => {
    const completedFiles = effectiveStatus?.status === 'completed' ? effectiveStatus.url : null;
    if (!completedFiles) {
      return;
    }

    let canceled = false;

    const loadFromDeviceCache = async () => {
      await cachePodcastFiles(completedFiles);
      const cachedBlobUrls = await getCachedPodcastBlobUrls(completedFiles);
      if (!canceled) {
        replaceLocalBlobUrls(cachedBlobUrls);
      }
    };

    loadFromDeviceCache();

    return () => {
      canceled = true;
    };
  }, [effectiveStatus]);

  useEffect(() => {
    const statusToPersist = status ?? restoredStatus;
    const hasSessionData = Boolean(taskId) || Boolean(topic.trim()) || Boolean(statusToPersist?.url);

    if (!hasSessionData) {
      return;
    }

    savePersistedSession({
      topic,
      taskId,
      selectedHostIds,
      currentTime,
      status: statusToPersist,
    });

    if (statusToPersist?.status === 'completed' && statusToPersist.url) {
      setPersistedHistory((prev) => {
        const updated = upsertHistoryItem(prev, {
          topic,
          taskId,
          selectedHostIds,
          currentTime,
          status: statusToPersist,
        });
        savePersistedHistory(updated);
        return updated;
      });
    }
  }, [currentTime, restoredStatus, selectedHostIds, status, taskId, topic]);

  const formatHistoryDate = (isoDate: string): string => {
    try {
      return new Date(isoDate).toLocaleString('he-IL');
    } catch {
      return isoDate;
    }
  };

  const formatTime = (timeInSeconds: number): string => {
    if (!Number.isFinite(timeInSeconds) || timeInSeconds < 0) {
      return '0:00';
    }

    const minutes = Math.floor(timeInSeconds / 60);
    const seconds = Math.floor(timeInSeconds % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const resolvedFiles = useMemo(() => {
    if (!effectiveStatus?.url) {
      return null;
    }

    return {
      ...effectiveStatus.url,
      ...localFileUrls,
    };
  }, [effectiveStatus, localFileUrls]);

  const showInputForm = !taskId || (effectiveStatus?.status === 'failed');
  const showStatus = taskId && effectiveStatus && effectiveStatus.status !== 'completed';
  const showResults = effectiveStatus?.status === 'completed' && effectiveStatus.url;

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="flex items-center justify-center gap-3 mb-4">
          <FaMicrophone className="text-blue-500" size={48} />
          <h1 className="text-4xl font-bold text-gray-800 dark:text-white">
            Podcast Maker
          </h1>
        </div>
        <p className="text-gray-600 dark:text-gray-400 text-lg">
          הכנס נושא וקבל פודקאסט מוכן תוך דקות ספורות
        </p>
      </div>

      {persistedHistory.length > 0 && (
        <div className="mb-8 bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">פודקאסטים אחרונים</h2>
          <div className="space-y-3">
            {persistedHistory.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => handleRestoreFromHistory(item)}
                className="w-full text-right p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                <p className="font-semibold text-gray-900 dark:text-white truncate">{item.topic || 'ללא נושא'}</p>
                <div className="mt-1 text-sm text-gray-600 dark:text-gray-400 flex flex-wrap gap-x-4 gap-y-1">
                  <span>עודכן: {formatHistoryDate(item.updatedAt)}</span>
                  <span>המשך מ: {formatTime(item.currentTime)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Form */}
      {showInputForm && (
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            {/* Host Selection Display & Button */}
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex-1">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">מארחים נבחרים</p>
                <p className="text-base font-semibold text-gray-800 dark:text-white">
                  {hostsLoading ? 'טוען...' : getHostNames(selectedHostIds)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsHostSelectorOpen(true)}
                className="flex items-center gap-2 px-3 py-2 bg-purple-500 hover:bg-purple-600 text-white text-sm font-medium rounded-lg transition-colors flex-shrink-0"
              >
                <FaUsers size={16} />
                <span>שנה</span>
              </button>
            </div>

            <label 
              htmlFor="topic" 
              className="block text-lg font-medium text-gray-700 dark:text-gray-300 mb-3"
            >
              מה נושא הפודקאסט?
            </label>
            <input
              id="topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="לדוגמה: ההיסטוריה של שפת C"
              className="w-full px-4 py-3 text-lg border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              disabled={isSubmitting}
              autoFocus
            />
            <button
              type="submit"
              disabled={isSubmitting || !topic.trim() || selectedHostIds.length !== 2}
              className="w-full mt-4 px-6 py-3 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors text-lg"
            >
              {isSubmitting ? 'שולח...' : 'צור פודקאסט'}
            </button>
            
            {effectiveStatus?.status === 'failed' && (
              <button
                type="button"
                onClick={handleReset}
                className="w-full mt-3 px-6 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 font-medium rounded-lg transition-colors"
              >
                נסה שוב
              </button>
            )}
          </div>
        </form>
      )}

      {/* Host Selector Modal */}
      <HostSelector
        isOpen={isHostSelectorOpen}
        onClose={() => setIsHostSelectorOpen(false)}
        selectedHostIds={selectedHostIds}
        onHostsSelected={setSelectedHostIds}
      />

      {/* Status Display */}
      {showStatus && (
        <div className="mb-8">
          <StatusDisplay 
            status={effectiveStatus.status} 
            error={effectiveStatus.error} 
          />
        </div>
      )}

      {/* Results - Audio Player & File Downloader */}
      {showResults && (
        <div className="space-y-6">
          <div className="flex justify-end">
            <button
              onClick={handleReset}
              className="flex items-center gap-2 px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 font-medium rounded-lg transition-colors"
            >
              <FaRedo />
              <span>צור פודקאסט חדש</span>
            </button>
          </div>

          <StatusDisplay status={effectiveStatus.status} />
          
          {resolvedFiles && resolvedFiles.transcript && (
            <TranscriptViewer
              transcriptUrl={resolvedFiles.transcript}
              currentTime={currentTime}
              onSeek={handleSeek}
            />
          )}

          {resolvedFiles && resolvedFiles.audio && (
            <AudioPlayer 
              audioUrl={resolvedFiles.audio}
              transcriptVttUrl={resolvedFiles.transcript_vtt}
              onTimeUpdate={setCurrentTime}
              seekToTime={seekToTime}
            />
          )}
          
          {resolvedFiles && (
            <FileDownloader files={resolvedFiles} />
          )}
        </div>
      )}
    </div>
  );
};
