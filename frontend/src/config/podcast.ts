import type { PodcastFormat, PodcastFormatInfo } from '../types/podcast';

export const DEFAULT_HOST_IDS = ['sarah_curious', 'mike_expert'] as const;

// How many hosts a format needs, from the format list the backend serves (the pipeline YAML decides).
export const maxHostsFor = (formats: PodcastFormatInfo[], format: PodcastFormat): number =>
  formats.find((f) => f.id === format)?.host_count ?? DEFAULT_HOST_IDS.length;
