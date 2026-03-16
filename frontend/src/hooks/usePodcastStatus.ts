import { useState, useEffect, useRef } from 'react';
import { podcastApi } from '../services/api';
import type { PodcastTaskStatus } from '../types/podcast';

export const usePodcastStatus = (taskId: string | null) => {
  const [status, setStatus] = useState<PodcastTaskStatus | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!taskId) {
      setStatus(null);
      setIsPolling(false);
      return;
    }

    setIsPolling(true);

    const pollStatus = async () => {
      try {
        const response = await podcastApi.getStatus(taskId);
        setStatus(response);

        // Stop polling if completed or failed
        if (response.status === 'completed' || response.status === 'failed') {
          setIsPolling(false);
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (error) {
        const statusCode =
          typeof error === 'object' &&
          error !== null &&
          'response' in error &&
          typeof (error as { response?: { status?: number } }).response?.status === 'number'
            ? (error as { response?: { status?: number } }).response?.status
            : undefined;

        if (statusCode === 404) {
          setIsPolling(false);
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          return;
        }

        console.error('Error polling status:', error);
        setStatus({
          status: 'failed',
          url: null,
          error: 'Failed to fetch status',
        });
        setIsPolling(false);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    };

    // Initial poll
    pollStatus();

    // Set up interval for subsequent polls (every 5 seconds)
    intervalRef.current = setInterval(pollStatus, 5000);

    // Cleanup on unmount or when taskId changes
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [taskId]);

  return { status, isPolling };
};
