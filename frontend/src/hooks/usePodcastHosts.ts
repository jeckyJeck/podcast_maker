import { useCallback, useEffect, useMemo, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { DEFAULT_HOST_IDS, FORMAT_MAX_HOSTS } from '../config/podcast';
import { podcastApi } from '../services/api';
import { isValidHostSelection, loadSession } from '../services/podcastPersistence';
import type { HostProfile, PodcastFormat } from '../types/podcast';

export interface UsePodcastHostsResult {
  hosts: HostProfile[];
  hostsLoading: boolean;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  setSelectedHostIds: React.Dispatch<React.SetStateAction<string[]>>;
  setSelectedFormat: React.Dispatch<React.SetStateAction<PodcastFormat>>;
  hostPickerOpen: boolean;
  setHostPickerOpen: (v: boolean) => void;
  handleFormatChange: (format: PodcastFormat) => void;
  saveHostsPreference: (ids: string[]) => Promise<void>;
  applyHostConfig: (format: PodcastFormat, hostIds: string[]) => void;
}

export const usePodcastHosts = (user: User | null): UsePodcastHostsResult => {
  const persistedSession = useMemo(() => loadSession(), []);

  const [selectedFormat, setSelectedFormat] = useState<PodcastFormat>(
    persistedSession?.selectedFormat ?? 'dialogue',
  );
  const [selectedHostIds, setSelectedHostIds] = useState<string[]>(
    persistedSession?.selectedHostIds ?? [...DEFAULT_HOST_IDS],
  );
  const [hosts, setHosts] = useState<HostProfile[]>([]);
  const [hostsLoading, setHostsLoading] = useState(true);
  const [hostPickerOpen, setHostPickerOpen] = useState(false);

  useEffect(() => {
    podcastApi
      .getAvailableHosts()
      .then((r) => setHosts(r.hosts))
      .catch(console.error)
      .finally(() => setHostsLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    podcastApi
      .getUserPreferences()
      .then((prefs) => {
        if (isValidHostSelection(prefs.preferred_hosts)) {
          setSelectedHostIds(prefs.preferred_hosts);
        }
      })
      .catch(console.error);
  }, [user]);

  const handleFormatChange = useCallback((fmt: PodcastFormat) => {
    const newMax = FORMAT_MAX_HOSTS[fmt];
    const prevMax = FORMAT_MAX_HOSTS[selectedFormat];
    setSelectedFormat(fmt);
    if (newMax < prevMax) {
      setSelectedHostIds((prev) => prev.slice(-newMax));
    } else if (newMax > selectedHostIds.length) {
      setHostPickerOpen(true);
    }
  }, [selectedFormat, selectedHostIds.length]);

  const saveHostsPreference = useCallback(async (ids: string[]) => {
    setSelectedHostIds(ids);
    if (user) {
      try { await podcastApi.updateUserPreferences(ids); } catch { /* noop */ }
    }
  }, [user]);

  const applyHostConfig = useCallback((format: PodcastFormat, hostIds: string[]) => {
    setSelectedFormat(format);
    setSelectedHostIds(hostIds);
  }, []);

  return {
    hosts,
    hostsLoading,
    selectedFormat,
    selectedHostIds,
    setSelectedHostIds,
    setSelectedFormat,
    hostPickerOpen,
    setHostPickerOpen,
    handleFormatChange,
    saveHostsPreference,
    applyHostConfig,
  };
};
