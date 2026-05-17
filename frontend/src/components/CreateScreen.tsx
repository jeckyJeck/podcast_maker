import React from 'react';
import { FaCheck, FaComments, FaPen, FaPlay, FaUser, FaVolumeUp } from 'react-icons/fa';
import { FaWandMagicSparkles } from 'react-icons/fa6';
import { FORMAT_MAX_HOSTS } from '../config/podcast';
import { usePodcast } from '../context/PodcastContext';
import { StatusDisplay } from './StatusDisplay';
import type { PodcastFormat } from '../types/podcast';

const FORMAT_OPTIONS: { value: PodcastFormat; title: string; description: string; meta: string }[] = [
  {
    value: 'dialogue',
    title: 'Dialogue',
    description: 'Dynamic conversation between two AI hosts with natural banter.',
    meta: '2 hosts',
  },
  {
    value: 'solo',
    title: 'Solo',
    description: 'A focused monologue built for storytelling and analysis.',
    meta: '1 host',
  },
];

const traitForTone = (tone: string) => {
  const value = tone.toLowerCase();
  if (value.includes('skeptic')) return 'Skeptical';
  if (value.includes('curious') || value.includes('creative')) return 'Creative';
  if (value.includes('expert') || value.includes('analytical')) return 'Analytical';
  return tone || 'Voice';
};

const InlineHostPicker: React.FC = () => {
  const {
    hosts, hostsLoading, selectedHostIds, selectedFormat,
    hostPickerOpen, setHostPickerOpen, saveHostsPreference,
  } = usePodcast();

  const [localSelected, setLocalSelected] = React.useState<string[]>(selectedHostIds);
  const maxHosts = FORMAT_MAX_HOSTS[selectedFormat];

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
    <div className={`overflow-hidden transition-all duration-500 ${hostPickerOpen ? 'mt-5 max-h-[620px] opacity-100' : 'max-h-0 opacity-0'}`}>
      <div className="rounded-[1.75rem] border border-white/10 bg-white/[0.055] p-4 shadow-[0_24px_70px_rgba(0,0,0,0.25)] backdrop-blur-xl">
        {hostsLoading ? (
          <p className="py-8 text-center text-sm text-[#8f93a3]">Loading hosts...</p>
        ) : (
          <>
            <div className="mb-4 flex items-center justify-between gap-3">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#b8c7ff]">
                {localSelected.length}/{maxHosts} selected
              </p>
              <p className="text-xs text-[#8f93a3]">Tap a portrait to select a host.</p>
            </div>

            <div className="flex gap-4 overflow-x-auto pb-3 custom-scrollbar">
              {hosts.map((host) => {
                const isSelected = localSelected.includes(host.id);
                return (
                  <button
                    key={host.id}
                    type="button"
                    onClick={() => handleToggle(host.id)}
                    className={`w-64 shrink-0 rounded-[1.5rem] border p-4 text-left transition-all duration-300 ${
                      isSelected
                        ? 'border-[#9bb8ff] bg-[#171a24] shadow-[0_0_32px_rgba(77,142,255,0.24)]'
                        : 'border-white/10 bg-[#171717] hover:border-[#4D8EFF]/60 hover:bg-[#1d1d22]'
                    }`}
                  >
                    <div className="mb-4 flex items-center gap-3">
                      <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-full border border-white/15 bg-[#23242a]">
                        <img
                          src={`/hosts/${host.id}/image.png`}
                          alt={host.name}
                          className="h-full w-full object-cover"
                          onError={(e) => { e.currentTarget.style.display = 'none'; }}
                        />
                        <span className="absolute inset-0 grid place-items-center text-xl font-bold text-[#8f93a3]">
                          {host.name.charAt(0)}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <h3 className="truncate font-display text-lg font-extrabold text-white">{host.name}</h3>
                        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#b8c7ff]">{traitForTone(host.tone)}</p>
                      </div>
                      {isSelected && (
                        <span className="ml-auto grid h-7 w-7 place-items-center rounded-full bg-[#b8c7ff] text-[#0D0D0D]">
                          <FaCheck size={12} />
                        </span>
                      )}
                    </div>
                    <p dir="ltr" className="mb-4 max-h-24 overflow-y-auto text-sm leading-6 text-[#b8bac7] custom-scrollbar">
                      {host.personality || 'Host profile is loading.'}
                    </p>
                    <audio
                      controls
                      className="h-8 w-full"
                      controlsList="nodownload"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <source src={`/hosts/${host.id}/sample.mp3`} type="audio/mpeg" />
                    </audio>
                  </button>
                );
              })}
            </div>

            <div className="mt-4 flex justify-end gap-3 border-t border-white/10 pt-4">
              <button
                type="button"
                onClick={() => setHostPickerOpen(false)}
                className="rounded-full px-5 py-2 text-sm font-semibold text-[#b8bac7] transition-colors hover:text-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={localSelected.length === 0 || localSelected.length > maxHosts}
                className="rounded-full bg-white px-6 py-2 text-sm font-bold text-[#0D0D0D] transition-all hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:bg-white/20 disabled:text-white/50"
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

const SelectedHostsStrip: React.FC = () => {
  const { hosts, hostsLoading, selectedHostIds, hostPickerOpen, setHostPickerOpen, selectedFormat } = usePodcast();

  const selectedHosts = selectedHostIds
    .map((id) => hosts.find((h) => h.id === id))
    .filter(Boolean);

  return (
    <div>
      <div className="flex items-start gap-6 overflow-x-auto pb-2 custom-scrollbar">
        {hostsLoading ? (
          <div className="h-20 w-20 rounded-full bg-white/10 animate-pulse" />
        ) : selectedHosts.length === 0 ? (
          <button
            type="button"
            onClick={() => setHostPickerOpen(true)}
            className="rounded-full border border-dashed border-[#9bb8ff]/50 px-5 py-3 text-sm font-semibold text-[#b8c7ff]"
          >
            Select host
          </button>
        ) : selectedHosts.map((host) => host && (
          <button
            key={host.id}
            type="button"
            onClick={() => setHostPickerOpen(!hostPickerOpen)}
            className="group flex shrink-0 flex-col items-center gap-3 text-center"
          >
            <div className="relative h-20 w-20 rounded-full bg-gradient-to-br from-[#4D8EFF] to-[#571BC1] p-[2px] shadow-[0_0_28px_rgba(77,142,255,0.28)]">
              <div className="h-full w-full overflow-hidden rounded-full bg-[#171717]">
                <img
                  src={`/hosts/${host.id}/image.png`}
                  alt={host.name}
                  className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                  onError={(e) => { e.currentTarget.style.display = 'none'; }}
                />
              </div>
              <span className="absolute bottom-0 right-0 grid h-7 w-7 place-items-center rounded-full border-2 border-[#0D0D0D] bg-[#b8c7ff] text-[#0D0D0D]">
                <FaCheck size={11} />
              </span>
            </div>
            <div>
              <p className="max-w-24 truncate text-sm font-bold text-white">{host.name}</p>
              <p className="max-w-24 truncate text-[9px] font-bold uppercase tracking-[0.2em] text-[#b8c7ff]">{traitForTone(host.tone)}</p>
            </div>
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setHostPickerOpen(!hostPickerOpen)}
        className="mt-3 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-bold uppercase tracking-[0.18em] text-[#b8c7ff] transition-all hover:border-[#9bb8ff]/50"
      >
        {hostPickerOpen ? 'Close hosts' : `Edit ${FORMAT_MAX_HOSTS[selectedFormat]} host${FORMAT_MAX_HOSTS[selectedFormat] > 1 ? 's' : ''}`}
      </button>
    </div>
  );
};

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
    <div className="w-full max-w-2xl mx-auto flex flex-col gap-9">
      <section className="pt-2">
        <h1 className="font-display text-4xl font-extrabold leading-tight text-white sm:text-5xl">
          Create your next <span className="text-[#b8c7ff]">Podcast</span>
        </h1>
        <p className="mt-3 max-w-lg text-base leading-7 text-[#c4c6d0]">
          Choose the format, select hosts, and define the topic.
        </p>
      </section>

      <section>
        <p className="mb-5 text-xs font-bold uppercase tracking-[0.24em] text-[#b8c7ff]">01. Choose format</p>
        <div className="grid gap-5 sm:grid-cols-2">
          {FORMAT_OPTIONS.map((opt) => {
            const isSelected = selectedFormat === opt.value;
            const Icon = opt.value === 'dialogue' ? FaComments : FaUser;
            return (
              <button
                key={opt.value}
                type="button"
                disabled={isSubmitting || showStatus}
                onClick={() => handleFormatChange(opt.value)}
                className={`group min-h-64 rounded-[1.75rem] border p-7 text-left transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-50 ${
                  isSelected
                    ? 'border-[#7e61ff] bg-[radial-gradient(circle_at_80%_20%,rgba(77,142,255,0.15),rgba(255,255,255,0.045)_45%,rgba(18,18,20,0.94)_100%)] shadow-[0_0_0_1px_rgba(77,142,255,0.45),0_24px_80px_rgba(87,27,193,0.18)]'
                    : 'border-white/8 bg-white/[0.065] hover:border-[#4D8EFF]/45 hover:bg-white/[0.08]'
                }`}
              >
                <Icon className={isSelected ? 'text-[#b8c7ff]' : 'text-[#a7aab8]'} size={28} />
                <div className="mt-8">
                  <h2 className="font-display text-2xl font-extrabold text-white">{opt.title}</h2>
                  <p className="mt-3 min-h-12 text-sm leading-6 text-[#d8d9e0]">{opt.description}</p>
                </div>
                <p className="mt-10 text-[10px] font-bold uppercase tracking-[0.22em] text-white">{opt.meta}</p>
              </button>
            );
          })}
        </div>
      </section>

      <section>
        <p className="mb-5 text-xs font-bold uppercase tracking-[0.24em] text-[#b8c7ff]">02. Select hosts</p>
        <SelectedHostsStrip />
        <InlineHostPicker />
      </section>

      {showForm && (
        <section>
          <p className="mb-5 text-xs font-bold uppercase tracking-[0.24em] text-[#b8c7ff]">03. Define topic</p>
          <div className="flex items-center gap-2 rounded-full bg-white/[0.07] p-2 shadow-[0_18px_55px_rgba(0,0,0,0.2)]">
            <input
              id="topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="The future of decentralized AI in 2030"
              className="min-w-0 flex-1 bg-transparent px-4 py-3 text-base text-white outline-none placeholder:text-[#777b87]"
              disabled={isSubmitting}
              autoFocus
            />
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={isSubmitting || !topic.trim()}
              aria-label={isSubmitting ? 'Generating podcast' : 'Generate podcast'}
              title={isSubmitting ? 'Generating...' : 'Generate'}
              className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#4D8EFF] to-[#571BC1] text-white shadow-[0_0_28px_rgba(77,142,255,0.35)] transition-all hover:scale-105 disabled:cursor-not-allowed disabled:grayscale"
            >
              <FaWandMagicSparkles aria-hidden="true" />
            </button>
          </div>
          <div>
            {effectiveStatus?.status === 'failed' && (
              <button
                type="button"
                onClick={handleReset}
                className="mt-4 w-full rounded-full border border-white/10 px-6 py-3 text-sm font-bold uppercase tracking-[0.16em] text-white transition-all hover:border-[#9bb8ff]/60"
              >
                Try Again
              </button>
            )}
          </div>
        </section>
      )}

      {showStatus && (
        <StatusDisplay
          status={effectiveStatus?.status ?? 'failed'}
          error={effectiveStatus?.error}
        />
      )}

      {podcastReady && (
        <section className="rounded-[1.75rem] border border-[#9bb8ff]/40 bg-[#141821] p-6 text-center shadow-[0_0_50px_rgba(77,142,255,0.18)]">
          <FaVolumeUp className="mx-auto mb-4 text-[#b8c7ff]" size={34} />
          <h2 className="font-display text-2xl font-extrabold text-white">Podcast Ready</h2>
          <p className="mt-2 text-sm text-[#b8bac7]">Your podcast is ready for playback.</p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <button
              type="button"
              onClick={goToPlayer}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-[#4D8EFF] to-[#571BC1] px-8 py-3 font-bold uppercase tracking-[0.16em] text-white"
            >
              <FaPlay />
              Play
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center justify-center gap-2 rounded-full border border-white/10 px-8 py-3 font-bold uppercase tracking-[0.16em] text-[#d8d9e0]"
            >
              <FaPen />
              New Episode
            </button>
          </div>
        </section>
      )}
    </div>
  );
};
