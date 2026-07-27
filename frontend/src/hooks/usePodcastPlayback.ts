import { useCallback, useEffect, useRef, useState } from 'react';
import type { PodcastFiles } from '../types/podcast';
import type { PersistedSession } from '../services/podcastPersistence';

export interface UsePodcastPlaybackOptions {
  resolvedFiles: PodcastFiles | null;
  persistedSession: PersistedSession | null;
  setCurrentTime: (time: number) => void;
}

export interface UsePodcastPlaybackResult {
  audioRef: React.RefObject<HTMLAudioElement>;
  isPlaying: boolean;
  duration: number;
  playbackSpeed: number;
  togglePlay: () => void;
  seekTo: (time: number) => void;
  skipBy: (seconds: number) => void;
  changeSpeed: (speed: number) => void;
  resetPlayback: () => void;
}

export const usePodcastPlayback = ({
  resolvedFiles,
  persistedSession,
  setCurrentTime,
}: UsePodcastPlaybackOptions): UsePodcastPlaybackResult => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTime = () => setCurrentTime(audio.currentTime);
    const onMeta = () => setDuration(audio.duration);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => setIsPlaying(false);

    audio.addEventListener('timeupdate', onTime);
    audio.addEventListener('loadedmetadata', onMeta);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.addEventListener('ended', onEnded);

    return () => {
      audio.removeEventListener('timeupdate', onTime);
      audio.removeEventListener('loadedmetadata', onMeta);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.removeEventListener('ended', onEnded);
    };
  }, [setCurrentTime]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !resolvedFiles?.audio) return;
    if (audio.src === resolvedFiles.audio) return;
    audio.src = resolvedFiles.audio;
    audio.load();
    if (persistedSession && persistedSession.currentTime > 0) {
      const restoreTime = persistedSession.currentTime;
      audio.addEventListener('loadedmetadata', () => {
        audio.currentTime = restoreTime;
      }, { once: true });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedFiles?.audio]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || !resolvedFiles?.audio) return;
    if (isPlaying) audio.pause();
    else void audio.play();
  }, [isPlaying, resolvedFiles?.audio]);

  const seekTo = useCallback((time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const apply = () => { audio.currentTime = time; setCurrentTime(time); };
    if (audio.readyState >= 1) apply();
    else audio.addEventListener('loadedmetadata', apply, { once: true });
  }, [setCurrentTime]);

  const skipBy = useCallback((seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const newTime = Math.min(Math.max(0, audio.currentTime + seconds), audio.duration || 0);
    audio.currentTime = newTime;
    setCurrentTime(newTime);
  }, [setCurrentTime]);

  const changeSpeed = useCallback((speed: number) => {
    const audio = audioRef.current;
    if (audio) audio.playbackRate = speed;
    setPlaybackSpeed(speed);
  }, []);

  const resetPlayback = useCallback(() => {
    const audio = audioRef.current;
    if (audio) { audio.pause(); audio.src = ''; }
    setIsPlaying(false);
    setCurrentTime(0);
    setDuration(0);
  }, [setCurrentTime]);

  return {
    audioRef,
    isPlaying,
    duration,
    playbackSpeed,
    togglePlay,
    seekTo,
    skipBy,
    changeSpeed,
    resetPlayback,
  };
};
