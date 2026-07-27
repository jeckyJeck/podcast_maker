import { DEFAULT_HOST_IDS } from '../config/podcast';
import type {
  PodcastFiles,
  PodcastFormat,
  PodcastTaskStatus,
  UserPodcastRecord,
} from '../types/podcast';

const PODCAST_SESSION_KEY = 'podcast-maker.session.v1';
const PODCAST_HISTORY_KEY = 'podcast-maker.history.v1';
const MAX_HISTORY = 5;

export const isValidHostSelection = (v: unknown): v is string[] =>
  Array.isArray(v) && v.length >= 1 && v.length <= 2;

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const isPodcastFiles = (value: unknown): value is PodcastFiles => {
  if (!isObjectRecord(value)) return false;

  const fileKeys: Array<keyof PodcastFiles> = [
    'blueprint',
    'research',
    'outline',
    'script',
    'audio',
    'transcript',
    'transcript_vtt',
  ];

  for (const key of fileKeys) {
    if (value[key] !== undefined && typeof value[key] !== 'string') return false;
  }

  return true;
};

const isTaskStatus = (value: unknown): value is PodcastTaskStatus['status'] =>
  value === 'queued' || value === 'processing' || value === 'completed' || value === 'failed';

const isPodcastTaskStatus = (value: unknown): value is PodcastTaskStatus => {
  if (!isObjectRecord(value)) return false;

  if (!isTaskStatus(value.status)) return false;
  if (value.url !== null && !isPodcastFiles(value.url)) return false;
  if (value.error !== undefined && typeof value.error !== 'string') return false;

  return true;
};

export const resolvePodcastFiles = (
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
  podcastId: string;
  topic: string;
  taskId: string | null;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  currentTime: number;
  status: PodcastTaskStatus;
  updatedAt: string;
  canRetry?: boolean;
  recoveryReason?: string;
}

export interface PersistedSession {
  topic: string;
  taskId: string | null;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  currentTime: number;
  status: PodcastTaskStatus | null;
}

export const loadSession = (): PersistedSession | null => {
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

export const saveSession = (s: PersistedSession) => {
  try {
    localStorage.setItem(PODCAST_SESSION_KEY, JSON.stringify(s));
  } catch { /* noop */ }
};

export const clearSession = () => {
  try { localStorage.removeItem(PODCAST_SESSION_KEY); } catch { /* noop */ }
};

export const loadHistory = (): PodcastHistoryItem[] => {
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
          !isPodcastTaskStatus(item.status)
        ) return null;

        return {
          id: item.id,
          podcastId: typeof item.podcastId === 'string' ? item.podcastId : item.id,
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

export const saveHistory = (items: PodcastHistoryItem[]) => {
  try {
    localStorage.setItem(PODCAST_HISTORY_KEY, JSON.stringify(items));
  } catch { /* noop */ }
};

export const upsertHistory = (
  items: PodcastHistoryItem[],
  session: PersistedSession,
): PodcastHistoryItem[] => {
  if (!session.status?.url) return items;
  const identity = session.taskId ?? session.status.url.audio ?? session.status.url.script;
  if (!identity) return items;
  const existing = items.find((i) => (i.taskId ?? i.status.url?.audio) === identity);
  const next: PodcastHistoryItem = {
    id: existing?.id ?? identity,
    podcastId: existing?.podcastId ?? identity,
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

export const mapCloudToHistory = (r: UserPodcastRecord): PodcastHistoryItem | null => {
  const config = r.config;
  const hostIds = isValidHostSelection(config?.host_ids)
    ? config.host_ids
    : isValidHostSelection(r.host_ids)
      ? r.host_ids
      : [...DEFAULT_HOST_IDS];

  return {
    id: r.id,
    podcastId: r.id,
    topic: config?.topic || r.topic,
    taskId: r.task_id,
    selectedFormat: config?.format || r.format || (hostIds.length === 1 ? 'solo' : 'dialogue'),
    selectedHostIds: hostIds,
    currentTime: 0,
    status: { status: r.status, url: r.url, checkpoint: r.checkpoint, error: r.error },
    updatedAt: r.updated_at ?? r.created_at ?? new Date().toISOString(),
  };
};
