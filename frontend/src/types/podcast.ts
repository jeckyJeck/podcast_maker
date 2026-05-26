export interface PodcastFiles {
  blueprint?: string;
  research?: string;
  outline?: string;
  script?: string;
  audio?: string;
  transcript?: string;
  transcript_vtt?: string;
}

export interface TranscriptSegment {
  startMs: number;
  endMs: number;
  speaker: string;
  text: string;
}

export type TaskStatus = 'queued' | 'processing' | 'completed' | 'failed';

export type PodcastCheckpoint =
  | 'requested'
  | 'blueprint'
  | 'research'
  | 'outline'
  | 'script'
  | 'audio'
  | 'transcript'
  | 'completed';

export interface PodcastTaskStatus {
  podcast_id?: string;
  task_id?: string;
  status: TaskStatus;
  url: PodcastFiles | null;
  checkpoint?: PodcastCheckpoint;
  error?: string;
}

export interface CreatePodcastResponse {
  podcast_id: string;
  task_id: string;
  message: string;
}

export type PodcastFormat = 'dialogue' | 'solo';

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
  url: PodcastFiles | null;
  error?: string;
  created_at?: string;
  updated_at?: string;
}

export interface UserPodcastsResponse {
  podcasts: UserPodcastRecord[];
}
