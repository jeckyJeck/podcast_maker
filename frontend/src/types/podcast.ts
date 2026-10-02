// URLs of an episode's files. Stage artifacts are keyed by the pipeline's stage ids (any names);
// `pipeline` is the saved pipeline YAML; `audio`, `transcript`, `transcript_vtt` are the fixed tail.
export interface PodcastFiles {
  pipeline?: string;
  audio?: string;
  transcript?: string;
  transcript_vtt?: string;
  [stageId: string]: string | undefined;
}

export interface TranscriptSegment {
  startMs: number;
  endMs: number;
  speaker: string;
  text: string;
}

export type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed';

// 'pipeline' (YAML saved), then a stage id per finished stage, then 'audio', 'transcript', 'completed'.
export type PodcastCheckpoint = string;

export interface PodcastTaskStatus {
  podcast_id?: string;
  task_id?: string;
  status: TaskStatus;
  url: PodcastFiles | null;
  checkpoint?: PodcastCheckpoint;
  stages?: string[] | null; // stage ids of this episode's pipeline, in order
  error?: string;
}

export interface CreatePodcastResponse {
  podcast_id: string;
  task_id: string;
  message: string;
}

// A format is a pipeline id (see GET /formats).
export type PodcastFormat = string;

export interface PodcastFormatInfo {
  id: PodcastFormat;
  name: string;
  description: string;
  host_count: number | null;
}

export interface FormatsResponse {
  formats: PodcastFormatInfo[];
}

export interface HostProfile {
  id: string;
  name: string;
  tone: string;
  role: 'primary' | 'secondary';
  gender: string;
  personality?: string;
}

export interface AvailableHostsResponse {
  hosts: HostProfile[];
}

export interface UserPreferencesResponse {
  preferred_hosts: string[];
}

export interface PodcastConfig {
  topic: string;
  host_ids: string[];
  format: PodcastFormat;
  stages?: string[];
}

export interface UserPodcastRecord {
  id: string;
  task_id: string;
  topic: string;
  host_ids: string[];
  format?: PodcastFormat;
  config?: PodcastConfig;
  status: TaskStatus;
  checkpoint?: PodcastCheckpoint;
  stages?: string[] | null;
  url: PodcastFiles | null;
  error?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UserPodcastsResponse {
  podcasts: UserPodcastRecord[];
}
