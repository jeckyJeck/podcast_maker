import { useCallback, useEffect, useMemo, useState } from 'react';
import type { User } from '@supabase/supabase-js';
import { DEFAULT_HOST_IDS, maxHostsFor } from '../config/podcast';
import { podcastApi } from '../services/api';
import { isValidHostSelection, loadSession } from '../services/podcastPersistence';
import type { HostProfile, PodcastFormat, PodcastFormatInfo } from '../types/podcast';

export interface UsePodcastHostsResult {
  hosts: HostProfile[];
  hostsLoading: boolean;
  formats: PodcastFormatInfo[];
  maxHosts: number;
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
    persistedSession?.selectedFormat ?? '',
  );
  const [formats, setFormats] = useState<PodcastFormatInfo[]>([]);
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
    podcastApi
      .getFormats()
      .then((r) => {
        setFormats(r.formats);
        // Keep the remembered format if it still exists; otherwise pick the one written for the current hosts.
        setSelectedFormat((prev) =>
          r.formats.some((f) => f.id === prev)
            ? prev
            : (r.formats.find((f) => f.host_count === selectedHostIds.length) ?? r.formats[0])?.id ?? '',
        );
      })
      .catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    const newMax = maxHostsFor(formats, fmt);
    const prevMax = maxHostsFor(formats, selectedFormat);
    setSelectedFormat(fmt);
    if (newMax < prevMax) {
      setSelectedHostIds((prev) => prev.slice(-newMax));
    } else if (newMax > selectedHostIds.length) {
      setHostPickerOpen(true);
    }
  }, [formats, selectedFormat, selectedHostIds.length]);

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
    formats,
    maxHosts: maxHostsFor(formats, selectedFormat),
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
