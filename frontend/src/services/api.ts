import axios from 'axios';
import type {
  CreatePodcastResponse,
  PodcastTaskStatus,
  AvailableHostsResponse,
  PodcastFormat,
  UserPodcastsResponse,
  UserPreferencesResponse,
} from '../types/podcast';
import { supabase } from './supabase';

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
  headers: {
    'Content-Type': 'application/json',
  },
});

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
    const originalRequest = error.config as (typeof error.config & { _retried?: boolean }) | undefined;

    if (!originalRequest || originalRequest._retried || error?.response?.status !== 401) {
      return Promise.reject(error);
    }

    originalRequest._retried = true;

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
