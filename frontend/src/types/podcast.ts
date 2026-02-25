export interface PodcastFiles {
  blueprint: string;
  research: string;
  outline: string;
  script: string;
  audio: string;
  transcript?: string;
  transcript_vtt?: string;
}

export interface TranscriptSegment {
  startMs: number;
  endMs: number;
  speaker: string;
  text: string;
}

export type TaskStatus = 'processing' | 'completed' | 'failed';

export interface PodcastTaskStatus {
  status: TaskStatus;
  url: PodcastFiles | null;
  error?: string;
}

export interface CreatePodcastResponse {
  task_id: string;
  message: string;
}

export interface FileInfo {
  name: string;
  url: string;
  type: 'audio' | 'json' | 'markdown' | 'text';
  displayName: string;
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
