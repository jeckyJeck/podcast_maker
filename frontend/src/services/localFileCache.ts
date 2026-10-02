import type { PodcastFiles } from '../types/podcast';
import { fetchWithRetry } from './http';

const PODCAST_FILES_CACHE_NAME = 'podcast-maker-files-v1';

// Every file the episode has; stage artifact keys depend on the pipeline.
const fileKeys = (files: PodcastFiles): string[] => Object.keys(files);

const canUseCacheApi = (): boolean => {
  return typeof window !== 'undefined' && 'caches' in window;
};

export const cachePodcastFiles = async (files: PodcastFiles): Promise<void> => {
  if (!canUseCacheApi()) {
    return;
  }

  const cache = await window.caches.open(PODCAST_FILES_CACHE_NAME);

  await Promise.all(
    fileKeys(files).map(async (key) => {
      const url = files[key];
      if (!url) {
        return;
      }

      try {
        const existing = await cache.match(url);
        if (existing) {
          return;
        }

        const response = await fetchWithRetry(url);
        if (!response.ok) {
          return;
        }

        await cache.put(url, response.clone());
      } catch (error) {
        console.error(`Failed to cache file for ${key}:`, error);
      }
    })
  );
};

export const getCachedPodcastBlobUrls = async (
  files: PodcastFiles
): Promise<Partial<PodcastFiles>> => {
  if (!canUseCacheApi()) {
    return {};
  }

  const cache = await window.caches.open(PODCAST_FILES_CACHE_NAME);
  const cachedBlobUrls: Partial<PodcastFiles> = {};

  await Promise.all(
    fileKeys(files).map(async (key) => {
      const sourceUrl = files[key];
      if (!sourceUrl) {
        return;
      }

      try {
        const cachedResponse = await cache.match(sourceUrl);
        if (!cachedResponse) {
          return;
        }

        const blob = await cachedResponse.blob();
        cachedBlobUrls[key] = URL.createObjectURL(blob);
      } catch (error) {
        console.error(`Failed to load cached blob for ${key}:`, error);
      }
    })
  );

  return cachedBlobUrls;
};
