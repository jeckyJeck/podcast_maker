import React from 'react';
import { FaPlay } from 'react-icons/fa';
import { usePodcast } from '../context/PodcastContext';
import { StatusDisplay } from './StatusDisplay';
import type { PodcastFormat } from '../types/podcast';

const FORMAT_OPTIONS: { value: PodcastFormat; title: string; description: string }[] = [
  {
    value: 'dialogue',
    title: 'Dialogue',
    description: 'A conversation between 2 hosts with Q&A dynamics.',
  },
  {
    value: 'solo',
    title: 'Solo',
    description: 'A single host presenting content as a continuous monologue.',
  },
];

const FORMAT_MAX_HOSTS: Record<PodcastFormat, number> = { dialogue: 2, solo: 1 };

// ── Inline host picker ────────────────────────────────────────────────────────

const InlineHostPicker: React.FC = () => {
  const {
    hosts, hostsLoading, selectedHostIds, selectedFormat,
    hostPickerOpen, setHostPickerOpen, saveHostsPreference,
  } = usePodcast();

  const [localSelected, setLocalSelected] = React.useState<string[]>(selectedHostIds);
  const maxHosts = FORMAT_MAX_HOSTS[selectedFormat];

  // Sync local selection when picker opens
  React.useEffect(() => {
    if (hostPickerOpen) setLocalSelected(selectedHostIds);
  }, [hostPickerOpen, selectedHostIds]);

  const handleToggle = (hostId: string) => {
    setLocalSelected((prev) => {
      if (prev.includes(hostId)) return prev.filter((id) => id !== hostId);
      const next = [...prev, hostId];
      return next.length > maxHosts ? next.slice(-maxHosts) : next;
    });
  };

  const handleSave = async () => {
    await saveHostsPreference(localSelected);
    setHostPickerOpen(false);
  };

  return (
    <div
      className={`overflow-hidden transition-all duration-300 ease-in-out ${
        hostPickerOpen ? 'max-h-[420px] opacity-100 mt-3' : 'max-h-0 opacity-0'
      }`}
    >
      <div className="border border-gray-200 dark:border-gray-700 rounded-xl bg-gray-50 dark:bg-gray-700/50 p-3">
        {hostsLoading ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">Loading hosts...</p>
        ) : (
          <>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              {localSelected.length}/{maxHosts} selected — click a card to select/unselect
            </p>
            {/* Horizontal scroll row */}
            <div className="flex gap-3 overflow-x-auto pb-2" style={{ scrollbarWidth: 'thin' }}>
              {hosts.map((host) => {
                const isSelected = localSelected.includes(host.id);
                return (
                  <div
                    key={host.id}
                    onClick={() => handleToggle(host.id)}
                    className={`flex-shrink-0 w-72 cursor-pointer rounded-lg transition-all border select-none ${
                      isSelected
                        ? 'ring-2 ring-blue-500 shadow-lg bg-blue-50 dark:bg-blue-900/30 border-blue-300 dark:border-blue-600'
                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
                  >
                    <div className="p-3">
                    <div className="w-20 h-20 bg-gradient-to-br from-gray-300 to-gray-400 dark:from-gray-600 dark:to-gray-700 rounded-lg mb-2 flex items-center justify-center overflow-hidden flex-shrink-0 mx-auto">
                      <img
                        src={`/hosts/${host.id}/image.png`}
                        alt={host.name}
                        className="w-full h-full object-cover"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                      <span className="text-gray-400 text-2xl font-bold">
                        {host.name.charAt(0)}
                      </span>
                    </div>

                    <h3 className="text-sm font-semibold text-gray-800 dark:text-white mb-1 truncate text-center">
                      {host.name}
                    </h3>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mb-2 line-clamp-2 min-h-8 text-center">
                      {host.tone}
                    </p>

                    <p dir="ltr" className="text-xs text-gray-700 dark:text-gray-300 mb-2 line-clamp-none max-h-36 overflow-y-auto text-wrap break-words">
                      {host.personality || 'problem loading description...'}
                    </p>

                    <audio
                      controls
                      className="w-full h-6"
                      controlsList="nodownload"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <source src={`/hosts/${host.id}/sample.mp3`} type="audio/mpeg" />
                    </audio>
                    </div>
                  </div>
                );
              })}
            </div>
            {/* Save row */}
            <div className="flex justify-end gap-2 mt-3 pt-3 border-t border-gray-200 dark:border-gray-600">
              <button
                type="button"
                onClick={() => setHostPickerOpen(false)}
                className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={localSelected.length === 0 || localSelected.length > maxHosts}
                className="px-4 py-1.5 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Save
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// ── Selected host cards strip ─────────────────────────────────────────────────

const SelectedHostsStrip: React.FC = () => {
  const { hosts, hostsLoading, selectedHostIds, hostPickerOpen, setHostPickerOpen } = usePodcast();

  const selectedHosts = selectedHostIds
    .map((id) => hosts.find((h) => h.id === id))
    .filter(Boolean);

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Host cards */}
      <div className="flex gap-2">
        {hostsLoading
          ? <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse" />
          : selectedHosts.map((host) => host && (
            <div key={host.id} className="flex items-center gap-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 shadow-sm">
              <div className="w-8 h-8 rounded-full overflow-hidden bg-gradient-to-br from-gray-300 to-gray-400 dark:from-gray-600 dark:to-gray-700 flex items-center justify-center relative flex-shrink-0">
                <img
                  src={`/hosts/${host.id}/image.png`}
                  alt={host.name}
                  className="w-full h-full object-cover"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
                <span className="absolute text-gray-400 text-sm font-bold">{host.name.charAt(0)}</span>
              </div>
              <span className="text-sm font-medium text-gray-800 dark:text-white">{host.name}</span>
            </div>
          ))
        }
      </div>

      {/* Edit button */}
      <button
        type="button"
        onClick={() => setHostPickerOpen(!hostPickerOpen)}
        title={hostPickerOpen ? 'Close' : 'Edit'}
        className="px-2.5 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-500 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors flex-shrink-0"
      >
        {hostPickerOpen ? '▲' : '✏️'}
      </button>
    </div>
  );
};

// ── Main CreateScreen ─────────────────────────────────────────────────────────

export const CreateScreen: React.FC = () => {
  const {
    topic, setTopic,
    selectedFormat, handleFormatChange,
    isSubmitting, handleSubmit, handleReset,
    effectiveStatus, podcastReady,
    goToPlayer,
  } = usePodcast();

  const showStatus = Boolean(
    effectiveStatus && effectiveStatus.status !== 'completed',
  );
  const showForm = !effectiveStatus || effectiveStatus.status === 'failed';

  return (
    <div className="max-w-2xl mx-auto w-full flex flex-col gap-5">

      {/* ── Format selector ──────────────────────────────────────────────── */}
      <div>
        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
          Episode Format
        </p>
        <div className="grid grid-cols-2 gap-3">
          {FORMAT_OPTIONS.map((opt) => {
            const isSelected = selectedFormat === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                disabled={isSubmitting || showStatus}
                onClick={() => handleFormatChange(opt.value)}
                className={`text-left rounded-xl border-2 p-4 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                  isSelected
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 bg-white dark:bg-gray-800'
                }`}
              >
                <div className="text-base font-bold text-gray-900 dark:text-white">
                  {opt.title}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                  {opt.description}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Selected hosts + inline picker ───────────────────────────────── */}
      <div>
        <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
          Hosts
        </p>
        <SelectedHostsStrip />
        <InlineHostPicker />
      </div>

      {/* ── Topic input + submit ──────────────────────────────────────────── */}
      {showForm && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center gap-2">
            <input
              id="topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Enter a topic..."
              className="flex-1 px-4 py-2.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              disabled={isSubmitting}
              autoFocus
            />
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={isSubmitting || !topic.trim()}
              className="px-4 py-2.5 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors text-sm whitespace-nowrap"
            >
              {isSubmitting ? 'Sending...' : 'Generate'}
            </button>
          </div>
          {effectiveStatus?.status === 'failed' && (
            <button
              type="button"
              onClick={handleReset}
              className="w-full mt-2 px-6 py-2 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 font-medium rounded-xl transition-colors text-sm"
            >
              Try Again
            </button>
          )}
        </div>
      )}

      {/* ── Status display ────────────────────────────────────────────────── */}
      {showStatus && (
        <StatusDisplay
          status={effectiveStatus!.status}
          error={effectiveStatus!.error}
        />
      )}

      {/* ── Ready to play ─────────────────────────────────────────────────── */}
      {podcastReady && (
        <div className="bg-green-50 dark:bg-green-900/30 border-2 border-green-400 dark:border-green-600 rounded-xl p-5 flex flex-col items-center gap-3">
          <p className="text-green-800 dark:text-green-200 font-semibold text-lg">
            🎉 Podcast Ready!
          </p>
          <button
            type="button"
            onClick={goToPlayer}
            className="flex items-center gap-2 px-8 py-3 bg-green-500 hover:bg-green-600 text-white font-bold rounded-xl text-lg transition-colors shadow-md"
          >
            <FaPlay />
            <span>Play</span>
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="text-sm text-green-700 dark:text-green-400 underline hover:no-underline"
          >
            Create another podcast
          </button>
        </div>
      )}
    </div>
  );
};
