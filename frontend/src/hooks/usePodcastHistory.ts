import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { podcastApi } from '../services/api';
import {
  CREATE_PODCAST_FAILURE_MESSAGE,
} from '../services/podcastSubmission';
import {
  loadHistory,
  mapCloudToHistory,
  saveHistory,
  upsertHistory,
  type PodcastHistoryItem,
  type PersistedSession,
} from '../services/podcastPersistence';
import type { PodcastFormat, PodcastTaskStatus } from '../types/podcast';

const STALE_PROCESSING_TIMEOUT_MS = 15 * 60 * 1000;

const getStaleProcessingReason = (updatedAt: string): string | null => {
  const updatedAtMs = Date.parse(updatedAt);
  if (!Number.isFinite(updatedAtMs)) return null;

  if (Date.now() - updatedAtMs < STALE_PROCESSING_TIMEOUT_MS) return null;
  return 'Processing has not updated for more than 15 minutes.';
};

const normalizeDisplayHistoryItem = (item: PodcastHistoryItem): PodcastHistoryItem => {
  const staleReason =
    item.status.status === 'processing' ? getStaleProcessingReason(item.updatedAt) : null;

  if (!staleReason) return item;

  return {
    ...item,
    status: {
      ...item.status,
      status: 'failed',
    },
    canRetry: true,
    recoveryReason: staleReason,
  };
};

export interface UsePodcastHistoryOptions {
  user: User | null;
  taskId: string | null;
  pollingError: string | null;
  sessionSnapshot: {
    topic: string;
    taskId: string | null;
    selectedFormat: PodcastFormat;
    selectedHostIds: string[];
    currentTime: number;
    status: PodcastTaskStatus | null;
  };
  onRestore: (item: PodcastHistoryItem) => void;
  onRetryStart: (item: PodcastHistoryItem) => void;
  onRetrySuccess: (item: PodcastHistoryItem, newTaskId: string) => void;
  onRetryError: () => void;
}

export interface UsePodcastHistoryResult {
  displayHistory: PodcastHistoryItem[];
  cloudLoading: boolean;
  historyOpen: boolean;
  setHistoryOpen: (v: boolean) => void;
  handleRestoreFromHistory: (item: PodcastHistoryItem) => void;
  handleRetryPodcast: (item: PodcastHistoryItem) => Promise<void>;
  refreshCloudHistory: () => void;
}

export const usePodcastHistory = ({
  user,
  taskId,
  pollingError,
  sessionSnapshot,
  onRestore,
  onRetryStart,
  onRetrySuccess,
  onRetryError,
}: UsePodcastHistoryOptions): UsePodcastHistoryResult => {
  const [persistedHistory, setPersistedHistory] = useState<PodcastHistoryItem[]>(() => loadHistory());
  const [cloudHistory, setCloudHistory] = useState<PodcastHistoryItem[]>([]);
  const [cloudLoading, setCloudLoading] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const lastCloudSyncRef = useRef<string | null>(null);

  const historySource = cloudHistory.length > 0 ? cloudHistory : persistedHistory;
  const hasActiveHistoryItem = historySource.some(
    (item) => item.status.status === 'queued' || item.status.status === 'processing',
  );

  const refreshCloudHistory = useCallback(() => {
    if (!user) return;
    podcastApi
      .getUserPodcasts()
      .then((r) => {
        const updated = r.podcasts
          .map(mapCloudToHistory)
          .filter((i): i is PodcastHistoryItem => i !== null);
        setCloudHistory(updated);
        setPersistedHistory(updated);
        try { saveHistory(updated); } catch { /* noop */ }
      })
      .catch(console.error);
  }, [user]);

  useEffect(() => {
    if (!user) {
      setCloudHistory([]);
      return;
    }
    setCloudLoading(true);
    podcastApi
      .getUserPodcasts()
      .then((r) => {
        const updated = r.podcasts
          .map(mapCloudToHistory)
          .filter((i): i is PodcastHistoryItem => i !== null);
        setCloudHistory(updated);
        setPersistedHistory(updated);
        try { saveHistory(updated); } catch { /* noop */ }
      })
      .catch(console.error)
      .finally(() => setCloudLoading(false));
  }, [user]);

  useEffect(() => {
    if (!user || !hasActiveHistoryItem) return;

    refreshCloudHistory();
    const intervalId = setInterval(refreshCloudHistory, 60000);

    return () => {
      clearInterval(intervalId);
    };
  }, [hasActiveHistoryItem, refreshCloudHistory, user]);

  useEffect(() => {
    const s = sessionSnapshot.status;
    if (s?.status !== 'completed' || !s.url) return;
    const session: PersistedSession = {
      topic: sessionSnapshot.topic,
      taskId: sessionSnapshot.taskId,
      selectedFormat: sessionSnapshot.selectedFormat,
      selectedHostIds: sessionSnapshot.selectedHostIds,
      currentTime: sessionSnapshot.currentTime,
      status: s,
    };
    setPersistedHistory((prev) => {
      const updated = upsertHistory(prev, session);
      saveHistory(updated);
      return updated;
    });
  }, [
    sessionSnapshot.currentTime,
    sessionSnapshot.selectedFormat,
    sessionSnapshot.selectedHostIds,
    sessionSnapshot.status,
    sessionSnapshot.taskId,
    sessionSnapshot.topic,
  ]);

  useEffect(() => {
    if (!user || !taskId) return;
    const terminalStatus = sessionSnapshot.status?.status;
    if (terminalStatus !== 'completed' && terminalStatus !== 'failed') return;
    const syncKey = `${taskId}:${terminalStatus}`;
    if (lastCloudSyncRef.current === syncKey) return;
    lastCloudSyncRef.current = syncKey;
    refreshCloudHistory();
  }, [sessionSnapshot.status?.status, taskId, user, refreshCloudHistory]);

  // Revalidate cloud history when the tab/window becomes visible again —
  // lightweight background refresh so returning users see updated data
  // without a blocking spinner.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      refreshCloudHistory();
    };

    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);

    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [refreshCloudHistory]);

  const handleRestoreFromHistory = useCallback((item: PodcastHistoryItem) => {
    if (item.status.status !== 'completed' || !item.status.url?.audio) return;
    onRestore(item);
  }, [onRestore]);

  const handleRetryPodcast = useCallback(async (item: PodcastHistoryItem) => {
    if (item.status.status === 'completed') return;
    onRetryStart(item);
    try {
      const response = await podcastApi.retryPodcast(item.podcastId);
      onRetrySuccess(item, response.task_id);
      if (user) refreshCloudHistory();
    } catch (err) {
      console.error(err);
      alert(CREATE_PODCAST_FAILURE_MESSAGE);
      onRetryError();
    }
  }, [onRetryStart, onRetrySuccess, onRetryError, user, refreshCloudHistory]);

  const displayHistory = useMemo(() => {
    return historySource.map(normalizeDisplayHistoryItem).map((item) => {
      const canRetry =
        item.status.status === 'failed' ||
        Boolean(
          pollingError &&
          taskId &&
          item.taskId === taskId &&
          (item.status.status === 'queued' || item.status.status === 'processing'),
        );

      if (!canRetry) return item;

      return {
        ...item,
        canRetry,
        recoveryReason:
          item.status.status === 'failed'
            ? item.status.error
            : pollingError ?? 'Status polling failed.',
      };
    });
  }, [historySource, pollingError, taskId]);

  return {
    displayHistory,
    cloudLoading,
    historyOpen,
    setHistoryOpen,
    handleRestoreFromHistory,
    handleRetryPodcast,
    refreshCloudHistory,
  };
};
