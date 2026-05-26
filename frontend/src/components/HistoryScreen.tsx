import React, { useEffect, useState } from 'react';
import { FaClock, FaExclamationCircle, FaFolder, FaHistory, FaPlay, FaRedo, FaSpinner } from 'react-icons/fa';
import { usePodcast } from '../context/PodcastContext';

const formatTime = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const formatDate = (iso: string): string => {
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
};

const EpisodeProgress: React.FC<{ audioUrl?: string; currentTime: number }> = ({ audioUrl, currentTime }) => {
  const [duration, setDuration] = useState<number | null>(null);

  useEffect(() => {
    if (!audioUrl) {
      setDuration(null);
      return;
    }

    const audio = new Audio();
    const handleMetadata = () => {
      setDuration(Number.isFinite(audio.duration) ? audio.duration : null);
    };

    audio.preload = 'metadata';
    audio.addEventListener('loadedmetadata', handleMetadata);
    audio.src = audioUrl;

    return () => {
      audio.removeEventListener('loadedmetadata', handleMetadata);
      audio.src = '';
    };
  }, [audioUrl]);

  const percent = duration && duration > 0
    ? Math.min(100, Math.max(0, (currentTime / duration) * 100))
    : currentTime > 0 ? 8 : 0;

  return (
    <>
      <div className="flex min-w-0 items-center justify-between gap-3 text-xs font-bold uppercase tracking-[0.16em] text-[#dbe3ff]">
        <span className="inline-flex min-w-0 items-center gap-2 truncate">
          <FaClock size={12} className="shrink-0" />
          {duration ? formatTime(duration) : 'Length unavailable'}
        </span>
        <span className="shrink-0 text-right">
          {currentTime > 0
            ? duration
              ? `${Math.round(percent)}% listened`
              : `${formatTime(currentTime)} listened`
            : 'Not started'}
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/12">
        <div
          className="h-full rounded-full bg-gradient-to-r from-[#4D8EFF] to-[#571BC1]"
          style={{ width: `${percent}%` }}
        />
      </div>
    </>
  );
};

export const HistoryScreen: React.FC = () => {
  const { displayHistory, cloudLoading, handleRestoreFromHistory, handleRetryPodcast } = usePodcast();

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8">
      <section>
        <div className="mb-3 flex items-center gap-3 text-xs font-extrabold uppercase tracking-[0.22em] text-[#b8c7ff]">
          <FaHistory size={14} />
          Archive
        </div>
        <h1 className="font-display text-5xl font-extrabold text-white">Your Library</h1>
      </section>

      {cloudLoading ? (
        <div className="grid h-64 place-items-center text-[#8f93a3]">
          <div className="animate-pulse">Loading history...</div>
        </div>
      ) : displayHistory.length === 0 ? (
        <div className="grid min-h-72 place-items-center rounded-[2rem] border border-dashed border-white/12 bg-white/[0.045] p-8 text-center">
          <div>
            <div className="mx-auto mb-5 grid h-20 w-20 place-items-center rounded-[1.5rem] bg-white/[0.08] text-[#b8c7ff]">
              <FaFolder size={34} />
            </div>
            <p className="font-display text-2xl font-extrabold text-white">No podcasts found</p>
            <p className="mt-2 text-sm text-[#8f93a3]">Create your first episode to start building the archive.</p>
          </div>
        </div>
      ) : (
        <div className="grid gap-5">
          {displayHistory.map((item) => {
            const isCompleted = item.status.status === 'completed' && Boolean(item.status.url?.audio);
            const isFailed = item.status.status === 'failed';
            const isWorking = item.status.status === 'queued' || item.status.status === 'processing';
            const canRetry = Boolean(item.canRetry || isFailed);
            const statusLabel = isCompleted
              ? 'Ready to play'
              : canRetry && !isFailed
                ? 'Creation needs attention'
                : isFailed
                ? `Failed${item.status.checkpoint ? ` at ${item.status.checkpoint}` : ''}`
                : `Creating${item.status.checkpoint ? `: ${item.status.checkpoint}` : ''}`;

            return (
              <div
                key={item.id}
                onClick={() => {
                  if (isCompleted) handleRestoreFromHistory(item);
                }}
                className={`group w-full max-w-full overflow-hidden rounded-[2rem] border border-white/8 bg-white/[0.065] p-6 text-left shadow-[0_24px_80px_rgba(0,0,0,0.22)] transition-all duration-300 ${
                  isCompleted
                    ? 'cursor-pointer hover:-translate-y-0.5 hover:border-[#9bb8ff]/45 hover:bg-white/[0.085]'
                    : 'cursor-default'
                }`}
              >
                <div className="mb-7 flex items-start gap-5">
                  <div className="grid h-16 w-16 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-white to-[#a7aab8] text-[#0D0D0D] shadow-[0_10px_32px_rgba(255,255,255,0.08)]">
                    {canRetry ? <FaExclamationCircle size={26} /> : isWorking ? <FaSpinner className="animate-spin" size={24} /> : <FaFolder size={26} />}
                  </div>
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <h2 className="line-clamp-2 max-w-full break-words font-display text-2xl font-extrabold leading-tight text-white [overflow-wrap:anywhere]">
                      {item.topic || 'Untitled Podcast'}
                    </h2>
                    <p className="mt-2 text-sm text-[#d8d9e0]">Updated: {formatDate(item.updatedAt)}</p>
                    <p className={`mt-2 text-sm font-bold ${canRetry ? 'text-red-200' : 'text-[#b8c7ff]'}`}>
                      {statusLabel}
                    </p>
                    {canRetry && (item.recoveryReason || item.status.error) ? (
                      <p className="mt-2 line-clamp-2 text-sm text-red-100/75">{item.recoveryReason || item.status.error}</p>
                    ) : null}
                  </div>
                  {canRetry ? (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleRetryPodcast(item);
                      }}
                      className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-red-200 text-[#2b0707] transition-all hover:bg-white"
                      title="Retry podcast creation"
                    >
                      <FaRedo size={15} />
                    </button>
                  ) : (
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white/[0.06] text-[#b8c7ff] opacity-70 transition-all group-hover:bg-[#b8c7ff] group-hover:text-[#0D0D0D] group-hover:opacity-100">
                      {isWorking ? <FaSpinner className="animate-spin" size={15} /> : <FaPlay size={15} className="ml-0.5" />}
                    </span>
                  )}
                </div>

                {isCompleted ? (
                  <EpisodeProgress audioUrl={item.status.url?.audio} currentTime={item.currentTime} />
                ) : (
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/12">
                    <div className={`h-full rounded-full ${canRetry ? 'w-1/3 bg-red-300/70' : 'w-2/3 animate-pulse bg-[#b8c7ff]'}`} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
