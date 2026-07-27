import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { podcastApi } from '../services/api';
import { cachePodcastFiles, getCachedPodcastBlobUrls } from '../services/localFileCache';
import {
  createPodcastTask,
  CREATE_PODCAST_FAILURE_MESSAGE,
  validateCreatePodcastInput,
} from '../services/podcastSubmission';
import {
  clearSession,
  loadSession,
  resolvePodcastFiles,
  saveSession,
  type PersistedSession,
} from '../services/podcastPersistence';
import { usePodcastStatus } from './usePodcastStatus';
import type { PodcastFiles, PodcastFormat, PodcastTaskStatus } from '../types/podcast';

export interface UsePodcastSessionOptions {
  user: User | null;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  refreshCloudHistory: () => void;
}

export interface UsePodcastSessionResult {
  persistedSession: PersistedSession | null;
  topic: string;
  setTopic: (v: string) => void;
  taskId: string | null;
  setTaskId: (id: string | null) => void;
  isSubmitting: boolean;
  setIsSubmitting: (v: boolean) => void;
  effectiveStatus: PodcastTaskStatus | null;
  restoredStatus: PodcastTaskStatus | null;
  setRestoredStatus: (s: PodcastTaskStatus | null) => void;
  liveStatus: PodcastTaskStatus | null;
  currentTime: number;
  setCurrentTime: (t: number) => void;
  resolvedFiles: PodcastFiles | null;
  pollingError: string | null;
  handleSubmit: () => Promise<void>;
  clearFileCache: () => void;
  resetSessionFields: () => void;
}

export const usePodcastSession = ({
  user,
  selectedFormat,
  selectedHostIds,
  refreshCloudHistory,
}: UsePodcastSessionOptions): UsePodcastSessionResult => {
  const persistedSession = useMemo(() => loadSession(), []);

  const [topic, setTopic] = useState(persistedSession?.topic ?? '');
  const [currentTime, setCurrentTime] = useState(persistedSession?.currentTime ?? 0);
  const [taskId, setTaskId] = useState<string | null>(() => {
    if (!persistedSession?.taskId) return null;
    if (
      persistedSession.status?.status === 'queued' ||
      persistedSession.status?.status === 'processing'
    ) {
      return persistedSession.taskId;
    }
    return null;
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [restoredStatus, setRestoredStatus] = useState<PodcastTaskStatus | null>(
    persistedSession?.status ?? null,
  );
  const [localFileUrls, setLocalFileUrls] = useState<Partial<PodcastFiles>>({});
  const objectUrlsRef = useRef<string[]>([]);

  const { status: liveStatus, pollingError } = usePodcastStatus(taskId);
  const effectiveStatus = liveStatus ?? restoredStatus;

  useEffect(() => {
    if (liveStatus) setRestoredStatus(liveStatus);
  }, [liveStatus]);

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

  useEffect(() => {
    const s = liveStatus ?? restoredStatus;
    if (!taskId && !topic.trim() && !s?.url) return;
    saveSession({
      topic,
      taskId,
      selectedFormat,
      selectedHostIds,
      currentTime,
      status: s,
    });
  }, [currentTime, restoredStatus, selectedFormat, selectedHostIds, liveStatus, taskId, topic]);

  useEffect(() => () => {
    for (const url of objectUrlsRef.current) URL.revokeObjectURL(url);
  }, []);

  // Revalidate the active task's status when the tab/window becomes visible
  // again — background timers throttle while hidden, so this gets a fresh
  // status immediately instead of waiting for the next poll tick.
  useEffect(() => {
    if (!taskId) return;
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      podcastApi.getStatus(taskId).then(setRestoredStatus).catch(console.error);
    };

    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);

    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [taskId]);

  const resolvedFiles = useMemo<PodcastFiles | null>(() => {
    if (!effectiveStatus?.url) return null;
    return resolvePodcastFiles(effectiveStatus.url, localFileUrls);
  }, [effectiveStatus, localFileUrls]);

  const clearFileCache = useCallback(() => {
    for (const url of objectUrlsRef.current) URL.revokeObjectURL(url);
    objectUrlsRef.current = [];
    setLocalFileUrls({});
  }, []);

  const handleSubmit = useCallback(async () => {
    const validation = validateCreatePodcastInput({ topic, selectedFormat, selectedHostIds });
    if (!validation.isValid) {
      alert(validation.message);
      return;
    }
    setIsSubmitting(true);
    setRestoredStatus(null);
    clearFileCache();
    try {
      const nextTaskId = await createPodcastTask({ topic, selectedFormat, selectedHostIds });
      setTaskId(nextTaskId);
      if (user) refreshCloudHistory();
    } catch (err) {
      console.error(err);
      alert(CREATE_PODCAST_FAILURE_MESSAGE);
    } finally {
      setIsSubmitting(false);
    }
  }, [topic, selectedFormat, selectedHostIds, user, refreshCloudHistory, clearFileCache]);

  const resetSessionFields = useCallback(() => {
    setTopic('');
    setTaskId(null);
    setIsSubmitting(false);
    setRestoredStatus(null);
    clearFileCache();
    clearSession();
  }, [clearFileCache]);

  return {
    persistedSession,
    topic,
    setTopic,
    taskId,
    setTaskId,
    isSubmitting,
    setIsSubmitting,
    effectiveStatus,
    restoredStatus,
    setRestoredStatus,
    liveStatus,
    currentTime,
    setCurrentTime,
    resolvedFiles,
    pollingError,
    handleSubmit,
    clearFileCache,
    resetSessionFields,
  };
};
