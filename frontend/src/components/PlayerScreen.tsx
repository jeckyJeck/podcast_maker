import React, { useState } from 'react';
import JSZip from 'jszip';
import {
  FaBackward,
  FaDownload,
  FaForward,
  FaHeadphones,
  FaPause,
  FaPlay,
  FaTachometerAlt,
} from 'react-icons/fa';
import { usePodcast } from '../context/PodcastContext';
import TranscriptViewer from './TranscriptViewer';
import type { PodcastFiles } from '../types/podcast';
import { fetchWithRetry } from '../services/http';

const PLAYBACK_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

const formatTime = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const FILE_META: { key: keyof PodcastFiles; filename: string }[] = [
  { key: 'audio',          filename: 'podcast.mp3' },
  { key: 'script',         filename: 'script.txt' },
  { key: 'research',       filename: 'research.md' },
  { key: 'blueprint',      filename: 'blueprint.json' },
  { key: 'outline',        filename: 'outline.json' },
  { key: 'transcript',     filename: 'transcript.json' },
  { key: 'transcript_vtt', filename: 'transcript.vtt' },
];

const downloadZip = async (
  files: PodcastFiles,
  topic: string,
  onStart: () => void,
  onDone: () => void,
) => {
  onStart();
  try {
    const zip = new JSZip();
    const folder = zip.folder(topic.slice(0, 40).replace(/[^a-zA-Z0-9 _-]/g, '_') || 'podcast');
    if (!folder) throw new Error('Failed to create folder');

    await Promise.all(
      FILE_META.map(async ({ key, filename }) => {
        const url = files[key];
        if (!url) return;
        const res = await fetchWithRetry(url);
        if (!res.ok) {
          throw new Error(`Failed to download ${filename}`);
        }
        const blob = await res.blob();
        folder.file(filename, blob);
      }),
    );

    const content = await zip.generateAsync({ type: 'blob' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(content);
    link.download = `${topic.slice(0, 40) || 'podcast'}.zip`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  } catch (err) {
    console.error('ZIP download failed', err);
    alert('Error downloading files');
  } finally {
    onDone();
  }
};

const PlayerControls: React.FC = () => {
  const {
    topic, resolvedFiles,
    isPlaying, currentTime, duration, playbackSpeed,
    togglePlay, seekTo, skipBy, changeSpeed,
  } = usePodcast();

  const [showSpeed, setShowSpeed] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const progress = duration > 0 ? currentTime / duration : 0;

  const handleDownload = () => {
    if (!resolvedFiles || downloading) return;
    void downloadZip(
      resolvedFiles,
      topic,
      () => setDownloading(true),
      () => setDownloading(false),
    );
  };

  return (
    <div className="rounded-[2rem] border border-white/10 bg-white/[0.065] p-5 shadow-[0_28px_90px_rgba(0,0,0,0.45)] backdrop-blur-xl" dir="ltr">
      <input
        type="range"
        min={0}
        max={duration || 0}
        value={currentTime}
        step={0.5}
        onChange={(e) => seekTo(parseFloat(e.target.value))}
        className="sonic-range w-full"
        style={{
          background: `linear-gradient(to right, #4D8EFF 0%, #571BC1 ${progress * 100}%, rgba(255,255,255,0.13) ${progress * 100}%, rgba(255,255,255,0.13) 100%)`,
        }}
      />
      <div className="mt-3 flex items-center justify-between text-sm tabular-nums text-[#dbe3ff]">
        <span>{formatTime(currentTime)}</span>
        <span>{formatTime(duration)}</span>
      </div>

      <div className="mt-7 flex items-center justify-between gap-2 sm:gap-3">
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowSpeed((v) => !v)}
            className="player-icon-button"
            title="Playback speed"
          >
            <FaTachometerAlt size={18} />
            <span className="text-[10px] font-bold">{playbackSpeed}x</span>
          </button>
          {showSpeed && (
            <div className="absolute bottom-full left-0 z-20 mb-3 overflow-hidden rounded-2xl border border-white/10 bg-[#191a20] p-1 shadow-2xl">
              {PLAYBACK_SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => { changeSpeed(s); setShowSpeed(false); }}
                  className={`block w-full rounded-xl px-5 py-2 text-left text-sm transition-colors ${
                    s === playbackSpeed
                      ? 'bg-[#4D8EFF] text-white'
                      : 'text-[#dbe3ff] hover:bg-white/10'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => skipBy(-15)}
          className="player-icon-button"
          title="15 seconds back"
        >
          <FaBackward size={18} />
          <span className="text-[10px] font-bold">15</span>
        </button>

        <button
          type="button"
          onClick={togglePlay}
          disabled={!resolvedFiles?.audio}
          className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#4D8EFF] to-[#571BC1] text-white shadow-[0_0_46px_rgba(77,142,255,0.42)] transition-all hover:scale-105 disabled:cursor-not-allowed disabled:grayscale sm:h-20 sm:w-20"
        >
          {isPlaying ? <FaPause size={26} /> : <FaPlay size={24} className="ml-1" />}
        </button>

        <button
          type="button"
          onClick={() => skipBy(15)}
          className="player-icon-button"
          title="15 seconds forward"
        >
          <FaForward size={18} />
          <span className="text-[10px] font-bold">15</span>
        </button>

        <button
          type="button"
          onClick={handleDownload}
          disabled={!resolvedFiles || downloading}
          className="player-icon-button disabled:cursor-not-allowed disabled:opacity-40"
          title="Download all files (ZIP)"
        >
          {downloading ? (
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
          ) : (
            <FaDownload size={18} />
          )}
          <span className="text-[10px] font-bold">ZIP</span>
        </button>
      </div>
    </div>
  );
};

export const PlayerScreen: React.FC = () => {
  const { topic, resolvedFiles, currentTime, seekTo, podcastReady, goToCreate, goToHistory } = usePodcast();

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-7">
      <section>
        <div className="mb-5 flex items-center justify-between gap-4">
          <h1 className="font-display text-4xl font-extrabold text-white">Live Transcript</h1>
          <div className="flex items-center gap-3 text-xs font-bold uppercase tracking-[0.22em] text-[#b8c7ff]">
            <span className="h-3 w-3 rounded-full bg-[#9bb8ff]" />
            Syncing
          </div>
        </div>

        <div className="min-h-[340px] overflow-hidden rounded-[2rem] border border-white/8 bg-[#14171d]/85 shadow-[0_28px_90px_rgba(0,0,0,0.35)]">
          {podcastReady && resolvedFiles?.transcript ? (
            <TranscriptViewer
              transcriptUrl={resolvedFiles.transcript}
              currentTime={currentTime}
              onSeek={seekTo}
            />
          ) : (
            <div className="flex min-h-[340px] flex-col items-center justify-center gap-5 px-8 text-center text-[#8f93a3]">
              <div className="grid h-20 w-20 place-items-center rounded-full bg-white/[0.05]">
                <FaPlay className="text-[#b8c7ff]" size={24} />
              </div>
              <p className="max-w-sm text-sm font-medium leading-6">
                No active podcast. Start by creating one or browse your library.
              </p>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={goToCreate}
                  className="rounded-full bg-white px-5 py-3 text-sm font-bold text-[#0D0D0D]"
                >
                  Create New
                </button>
                <button
                  type="button"
                  onClick={goToHistory}
                  className="rounded-full border border-white/10 px-5 py-3 text-sm font-bold text-white"
                >
                  Library
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="relative overflow-hidden rounded-[2rem] bg-[#101010] p-7 shadow-[0_28px_90px_rgba(0,0,0,0.45)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_60%_20%,rgba(77,142,255,0.3),transparent_34%),linear-gradient(180deg,transparent,rgba(0,0,0,0.72))]" />
        <div className="relative z-10">
          <div className="my-7 grid place-items-center">
            <div className="grid h-40 w-40 place-items-center rounded-full border border-[#67f3ff]/25 bg-[radial-gradient(circle,#2f8a92,rgba(29,94,103,0.3)_55%,transparent_56%)] shadow-[0_0_65px_rgba(103,243,255,0.2)]">
              <FaHeadphones size={82} className="text-[#9be8ef]/70" />
            </div>
          </div>
          <h2 className="font-display text-3xl font-extrabold leading-none text-white sm:text-4xl">
            {topic || 'Podcast Player'}
          </h2>
        </div>
      </section>

      <PlayerControls />
    </div>
  );
};
