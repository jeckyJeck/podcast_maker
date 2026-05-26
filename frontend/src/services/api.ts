import axios, { type AxiosError, type AxiosRequestConfig } from 'axios';
import type {
  CreatePodcastResponse,
  PodcastTaskStatus,
  AvailableHostsResponse,
  PodcastFormat,
  UserPodcastsResponse,
  UserPreferencesResponse,
} from '../types/podcast';
import { supabase } from './supabase';
import { HTTP_REQUEST_TIMEOUT_MS, HTTP_RETRY_COUNT, getRetryDelayMs, isRetriableStatus } from './http';

const API_BASE_URL = import.meta.env.VITE_API_URL;
let accessTokenProvider: (() => Promise<string | null>) | null = null;

const getAccessToken = async (): Promise<string | null> => {
  if (accessTokenProvider) {
    const token = await accessTokenProvider();
    if (token) {
      return token;
    }
  }

  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
};

export const setAccessTokenProvider = (provider: (() => Promise<string | null>) | null) => {
  accessTokenProvider = provider;
};

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: HTTP_REQUEST_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
});

type RetriableRequestConfig = AxiosRequestConfig & {
  _authRetried?: boolean;
  _retryCount?: number;
};

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

const isRetryableMethod = (method?: string): boolean => {
  return ['get', 'head', 'options', 'put', 'delete'].includes((method ?? 'get').toLowerCase());
};

const isRetryableAxiosError = (error: AxiosError, request?: RetriableRequestConfig): boolean => {
  if (!isRetryableMethod(request?.method)) {
    return false;
  }

  if (error.response) {
    return isRetriableStatus(error.response.status);
  }

  return error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK' || error.message.toLowerCase().includes('timeout');
};

apiClient.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const axiosError = error as AxiosError;
    const originalRequest = axiosError.config as RetriableRequestConfig | undefined;

    if (!originalRequest) {
      return Promise.reject(error);
    }

    if (!originalRequest._authRetried && axiosError.response?.status === 401) {
      originalRequest._authRetried = true;

      const token = await getAccessToken();
      if (token) {
        originalRequest.headers = {
          ...(originalRequest.headers ?? {}),
          Authorization: `Bearer ${token}`,
        };
        return apiClient(originalRequest);
      }

      return Promise.reject(error);
    }

    const retryCount = originalRequest._retryCount ?? 0;
    if (retryCount < HTTP_RETRY_COUNT && isRetryableAxiosError(axiosError, originalRequest)) {
      originalRequest._retryCount = retryCount + 1;
      await sleep(getRetryDelayMs(retryCount));
      return apiClient(originalRequest);
    }

    return Promise.reject(error);
  }
);

export const podcastApi = {
  createPodcast: async (
    topic: string,
    hostIds?: string[],
    format?: PodcastFormat
  ): Promise<CreatePodcastResponse> => {
    const response = await apiClient.post<CreatePodcastResponse>('/create-podcast/', {
      topic,
      ...(hostIds && { host_ids: hostIds }),
      ...(format && { format })
    });
    return response.data;
  },

  getAvailableHosts: async (): Promise<AvailableHostsResponse> => {
    const response = await apiClient.get<AvailableHostsResponse>('/available-hosts/');
    return response.data;
  },

  getStatus: async (taskId: string): Promise<PodcastTaskStatus> => {
    const response = await apiClient.get<PodcastTaskStatus>(`/status/${taskId}`);
    return response.data;
  },

  retryPodcast: async (podcastId: string): Promise<CreatePodcastResponse> => {
    const response = await apiClient.post<CreatePodcastResponse>(`/podcasts/${podcastId}/retry`);
    return response.data;
  },

  getUserPreferences: async (): Promise<UserPreferencesResponse> => {
    const response = await apiClient.get<UserPreferencesResponse>('/me/preferences');
    return response.data;
  },

  updateUserPreferences: async (preferredHosts: string[]): Promise<UserPreferencesResponse> => {
    const response = await apiClient.put<UserPreferencesResponse>('/me/preferences', {
      preferred_hosts: preferredHosts,
    });
    return response.data;
  },

  getUserPodcasts: async (): Promise<UserPodcastsResponse> => {
    const response = await apiClient.get<UserPodcastsResponse>('/me/podcasts');
    return response.data;
  },
};
