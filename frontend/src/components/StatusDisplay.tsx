import React from 'react';
import { FaCheckCircle, FaExclamationCircle, FaSpinner } from 'react-icons/fa';
import type { TaskStatus } from '../types/podcast';

interface StatusDisplayProps {
  status: TaskStatus;
  checkpoint?: string; // last completed step: a stage id, 'audio', 'transcript', ...
  stages?: string[]; // the episode's pipeline stage ids, in order
  error?: string;
}

// Steps = the pipeline's stages (names come from its YAML) followed by the fixed audio step.
const progressOf = (checkpoint: string | undefined, stages: string[] | undefined) => {
  if (!stages || stages.length === 0) return null;
  const steps = [...stages, 'audio'];
  const stageIndex = checkpoint ? stages.indexOf(checkpoint) : -1;
  const done = stageIndex >= 0 ? stageIndex + 1 : checkpoint === 'audio' || checkpoint === 'transcript' ? steps.length : 0;
  return { steps, done, current: steps[Math.min(done, steps.length - 1)] };
};

export const StatusDisplay: React.FC<StatusDisplayProps> = ({ status, checkpoint, stages, error }) => {
  const progress = progressOf(checkpoint, stages);

  if (status === 'completed') {
    return (
      <div className="rounded-[1.75rem] border border-emerald-300/30 bg-emerald-400/10 p-7 text-center shadow-[0_0_50px_rgba(16,185,129,0.12)]">
        <FaCheckCircle className="mx-auto mb-4 text-emerald-200" size={44} />
        <h3 className="font-display text-2xl font-extrabold text-white">Podcast Ready</h3>
        <p className="mt-2 text-sm text-emerald-100/80">
          Your podcast has been created successfully and is available for playback.
        </p>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div className="rounded-[1.75rem] border border-red-300/30 bg-red-500/10 p-7 text-center shadow-[0_0_50px_rgba(239,68,68,0.12)]">
        <FaExclamationCircle className="mx-auto mb-4 text-red-200" size={44} />
        <h3 className="font-display text-2xl font-extrabold text-white">Error Creating Podcast</h3>
        <p className="mt-2 text-sm text-red-100/80">
          {error || 'An unexpected error occurred. Please try again.'}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-[1.75rem] border border-[#9bb8ff]/35 bg-[#141821] p-7 text-center shadow-[0_0_60px_rgba(77,142,255,0.18)]">
      <FaSpinner className="mx-auto mb-4 animate-spin text-[#b8c7ff]" size={44} />
      <h3 className="font-display text-2xl font-extrabold text-white">Processing Podcast</h3>
      <p className="mt-2 text-sm text-[#dbe3ff]">
        {progress
          ? `Step ${Math.min(progress.done + 1, progress.steps.length)} of ${progress.steps.length}: ${progress.current}`
          : 'Starting work on the podcast...'}
      </p>
      <div className="mt-6 h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full animate-pulse rounded-full bg-gradient-to-r from-[#4D8EFF] to-[#571BC1]"
          style={{ width: `${progress ? Math.max(8, (progress.done / progress.steps.length) * 100) : 20}%` }}
        />
      </div>
      <p className="mt-4 text-xs font-bold uppercase tracking-[0.18em] text-[#8f93a3]">
        Rendering may take a few minutes
      </p>
    </div>
  );
};
