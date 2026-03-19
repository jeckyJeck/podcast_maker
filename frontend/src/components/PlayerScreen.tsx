import React, { useState } from 'react';
import JSZip from 'jszip';
import {
  FaPlay,
  FaPause,
  FaBackward,
  FaForward,
  FaDownload,
  FaTachometerAlt,
} from 'react-icons/fa';
import { usePodcast } from '../context/PodcastContext';
import TranscriptViewer from './TranscriptViewer';
import type { PodcastFiles } from '../types/podcast';

const PLAYBACK_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

// ── Helpers ───────────────────────────────────────────────────────────────────

const formatTime = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

// ── ZIP Download ──────────────────────────────────────────────────────────────

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
        const res = await fetch(url);
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

// ── Player Controls ───────────────────────────────────────────────────────────

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
    <div className="bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 px-4 py-3 space-y-2" dir="ltr">
      {/* Progress bar */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500 dark:text-gray-400 w-10 text-right tabular-nums">
          {formatTime(currentTime)}
        </span>
        <input
          type="range"
          min={0}
          max={duration || 0}
          value={currentTime}
          step={0.5}
          onChange={(e) => seekTo(parseFloat(e.target.value))}
          className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer accent-blue-500"
          style={{
            background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${progress * 100}%, #e5e7eb ${progress * 100}%, #e5e7eb 100%)`,
          }}
        />
        <span className="text-xs text-gray-500 dark:text-gray-400 w-10 tabular-nums">
          {formatTime(duration)}
        </span>
      </div>

      {/* Buttons row */}
      <div className="flex items-center justify-between">

        {/* Speed selector */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowSpeed((v) => !v)}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors text-sm font-medium"
          >
            <FaTachometerAlt size={13} />
            <span>{playbackSpeed}x</span>
          </button>
          {showSpeed && (
            <div className="absolute bottom-full mb-2 left-0 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden z-10">
              {PLAYBACK_SPEEDS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => { changeSpeed(s); setShowSpeed(false); }}
                  className={`block w-full px-4 py-2 text-sm text-right hover:bg-gray-100 dark:hover:bg-gray-700 ${
                    s === playbackSpeed
                      ? 'bg-blue-50 dark:bg-blue-900 text-blue-600 dark:text-blue-300 font-medium'
                      : 'text-gray-700 dark:text-gray-300'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Skip back */}
        <button
          type="button"
          onClick={() => skipBy(-15)}
          className="flex flex-col items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
          title="15 שניות אחורה"
        >
          <FaBackward size={18} />
          <span className="text-[9px] mt-0.5">15s</span>
        </button>

        {/* Play / Pause */}
        <button
          type="button"
          onClick={togglePlay}
          disabled={!resolvedFiles?.audio}
          className="w-12 h-12 rounded-full bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white flex items-center justify-center shadow-md transition-colors"
        >
          {isPlaying ? <FaPause size={18} /> : <FaPlay size={18} className="ml-0.5" />}
        </button>

        {/* Skip forward */}
        <button
          type="button"
          onClick={() => skipBy(15)}
          className="flex flex-col items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
          title="15 שניות קדימה"
        >
          <FaForward size={18} />
          <span className="text-[9px] mt-0.5">15s</span>
        </button>

        {/* Download ZIP */}
        <button
          type="button"
          onClick={handleDownload}
          disabled={!resolvedFiles || downloading}
          className="w-9 h-9 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-40 flex items-center justify-center transition-colors"
          title="הורד כל הקבצים (ZIP)"
        >
          {downloading ? (
            <span className="animate-spin inline-block w-4 h-4 border-2 border-gray-400 border-t-blue-500 rounded-full" />
          ) : (
            <FaDownload size={15} />
          )}
        </button>
      </div>
    </div>
  );
};

// ── Main PlayerScreen ─────────────────────────────────────────────────────────

export const PlayerScreen: React.FC = () => {
  const { topic, resolvedFiles, currentTime, seekTo, podcastReady, goToCreate, goToHistory } = usePodcast();

  return (
    <div className="max-w-2xl mx-auto w-full flex flex-col flex-1 min-h-0">
      {/* Top bar */}
      <div className="flex items-start justify-between gap-3 mb-4 px-1">
        <h2 className="text-lg font-bold text-gray-900 dark:text-white line-clamp-2 flex-1">
          {topic || 'Podcast Player'}
        </h2>
      </div>

      {/* Transcript */}
      <div className="flex-1 overflow-hidden rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900/50 mb-4 shadow-sm">
        {podcastReady && resolvedFiles?.transcript ? (
          <TranscriptViewer
            transcriptUrl={resolvedFiles.transcript}
            currentTime={currentTime}
            onSeek={seekTo}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-gray-400 gap-4 px-8">
            <div className="w-16 h-16 bg-gray-50 dark:bg-gray-800 rounded-full flex items-center justify-center mb-2">
              <FaPlay className="text-gray-300 dark:text-gray-600" size={24} />
            </div>
            <p className="text-center text-sm font-medium">No active podcast. Start by creating one or browse your history.</p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={goToCreate}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl transition-all shadow-sm font-medium text-sm"
              >
                Create New
              </button>
              <button
                type="button"
                onClick={goToHistory}
                className="px-5 py-2.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-xl transition-all font-medium text-sm"
              >
                Library
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Player controls */}
      <div className="rounded-2xl overflow-hidden border border-gray-100 dark:border-gray-800 shadow-lg bg-white dark:bg-gray-900">
        <PlayerControls />
      </div>
    </div>
  );
};
