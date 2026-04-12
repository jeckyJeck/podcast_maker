import type { PodcastFormat } from '../types/podcast';

export const DEFAULT_HOST_IDS = ['sarah_curious', 'mike_expert'] as const;

export const FORMAT_MAX_HOSTS: Record<PodcastFormat, number> = {
  dialogue: 2,
  solo: 1,
};
