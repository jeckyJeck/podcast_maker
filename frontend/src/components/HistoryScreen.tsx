import React from 'react';
import { FaHistory, FaPlay } from 'react-icons/fa';
import { usePodcast } from '../context/PodcastContext';

const formatTime = (seconds: number): string => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const formatDate = (iso: string): string => {
  try { return new Date(iso).toLocaleString('en-US'); } catch { return iso; }
};

export const HistoryScreen: React.FC = () => {
  const { displayHistory, cloudLoading, handleRestoreFromHistory } = usePodcast();

  return (
    <div className="flex-1 flex flex-col p-4 max-w-2xl mx-auto w-full">
      <div className="flex items-center gap-3 mb-6">
        <FaHistory className="text-blue-500" size={24} />
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Your History</h2>
      </div>

      {cloudLoading ? (
        <div className="flex justify-center items-center h-64 text-gray-400">
          <div className="animate-pulse">Loading history...</div>
        </div>
      ) : displayHistory.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-gray-400 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm border-dashed">
          <p className="font-medium text-lg">No podcasts found</p>
          <p className="text-sm">Start by creating your first episode!</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {displayHistory.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => handleRestoreFromHistory(item)}
              className="w-full text-left p-4 bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl hover:shadow-md hover:border-blue-200 dark:hover:border-blue-900 transition-all flex items-center gap-4 group shadow-sm"
            >
              <div className="w-12 h-12 rounded-xl bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center text-blue-500 group-hover:bg-blue-500 group-hover:text-white transition-colors">
                <FaPlay size={16} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-bold text-gray-900 dark:text-white truncate">
                  {item.topic || 'Untitled Podcast'}
                </p>
                <div className="flex items-center gap-3 mt-1 text-xs text-gray-500 dark:text-gray-400">
                  <span>{formatDate(item.updatedAt)}</span>
                  {item.currentTime > 0 && (
                    <span className="text-blue-500 font-medium">
                      Resume from {formatTime(item.currentTime)}
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
