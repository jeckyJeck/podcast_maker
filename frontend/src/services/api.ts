import axios from 'axios';
import type { CreatePodcastResponse, PodcastTaskStatus, AvailableHostsResponse } from '../types/podcast';

const API_BASE_URL = import.meta.env.VITE_API_URL;
const API_KEY = import.meta.env.VITE_API_KEY ;

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
  },
});

export const podcastApi = {
  createPodcast: async (topic: string, hostIds?: string[]): Promise<CreatePodcastResponse> => {
    const response = await apiClient.post<CreatePodcastResponse>('/create-podcast/', {
      topic,
      ...(hostIds && { host_ids: hostIds })
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
};
