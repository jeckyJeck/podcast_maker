import { useEffect, useRef, useState } from 'react';
import { TranscriptSegment } from '../types/podcast';
import { fetchWithRetry } from '../services/http';

interface TranscriptViewerProps {
  transcriptUrl: string;
  currentTime: number; // in seconds
  onSeek?: (timeInSeconds: number) => void;
}

const isTranscriptSegment = (value: unknown): value is TranscriptSegment => {
  if (!value || typeof value !== 'object') return false;

  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.startMs === 'number' &&
    typeof candidate.endMs === 'number' &&
    typeof candidate.speaker === 'string' &&
    typeof candidate.text === 'string'
  );
};

const parseTranscriptSegments = (value: unknown): TranscriptSegment[] => {
  if (!Array.isArray(value)) {
    throw new Error('Transcript payload is not an array');
  }

  if (!value.every(isTranscriptSegment)) {
    throw new Error('Transcript payload has invalid segment structure');
  }

  return value;
};

export default function TranscriptViewer({ transcriptUrl, currentTime, onSeek }: TranscriptViewerProps) {
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const activeSegmentRef = useRef<HTMLDivElement>(null);

  // Fetch transcript data
  useEffect(() => {
    const fetchTranscript = async () => {
      try {
        setLoading(true);
        const response = await fetchWithRetry(transcriptUrl);
        if (!response.ok) {
          throw new Error('Failed to fetch transcript');
        }
        const payload: unknown = await response.json();
        const data = parseTranscriptSegments(payload);
        setSegments(data);
        setError(null);
      } catch (err) {
        console.error('Error loading transcript:', err);
        setError(err instanceof Error ? err.message : 'Failed to load transcript');
      } finally {
        setLoading(false);
      }
    };

    if (transcriptUrl) {
      fetchTranscript();
    }
  }, [transcriptUrl]);

  // Update active segment based on current time
  useEffect(() => {
    const currentTimeMs = currentTime * 1000;
    const index = segments.findIndex(
      (seg) => currentTimeMs >= seg.startMs && currentTimeMs < seg.endMs
    );
    setActiveIndex(index);
  }, [currentTime, segments]);

  // Auto-scroll to active segment
  useEffect(() => {
    if (activeSegmentRef.current) {
      activeSegmentRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [activeIndex]);

  const handleSegmentClick = (segment: TranscriptSegment) => {
    if (onSeek) {
      onSeek(segment.startMs / 1000);
    }
  };

  const formatTime = (ms: number): string => {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const getSpeakerColor = (speaker: string): string => {
    return speaker === 'HOST_1' ? 'text-[#b8c7ff]' : 'text-[#c7a8ff]';
  };

  const getSpeakerBgColor = (speaker: string): string => {
    return speaker === 'HOST_1' ? 'bg-[#1a2030]' : 'bg-[#211a30]';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8 h-full" dir="ltr">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#4D8EFF]/30 border-t-[#b8c7ff]"></div>
        <span className="ml-3 text-sm text-[#8f93a3]">Loading transcript...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 flex items-center justify-center h-full" dir="ltr">
        <p className="text-sm text-red-300">Error loading transcript</p>
      </div>
    );
  }

  if (segments.length === 0) {
    return (
      <div className="p-8 flex items-center justify-center h-full" dir="ltr">
        <p className="text-sm italic text-[#8f93a3]">No transcript available</p>
      </div>
    );
  }

  return (
    <div className="h-[340px] overflow-y-auto scroll-smooth bg-transparent custom-scrollbar" dir="ltr">
      <div className="space-y-5 p-5 sm:p-7">
        {segments.map((segment, index) => {
          const isActive = index === activeIndex;
          return (
            <div
              key={index}
              ref={isActive ? activeSegmentRef : null}
              onClick={() => handleSegmentClick(segment)}
              className={`group cursor-pointer rounded-[1.5rem] border p-5 transition-all duration-500 ${
                isActive
                  ? `${getSpeakerBgColor(segment.speaker)} border-[#9bb8ff] opacity-100 shadow-[0_0_30px_rgba(77,142,255,0.18)]`
                  : 'border-transparent bg-[#111318]/45 opacity-55 hover:border-white/10 hover:bg-white/[0.04] hover:opacity-100'
              }`}
            >
              <div className="flex items-start gap-4">
                <span className={`mt-1 min-w-[46px] font-mono text-sm font-bold tabular-nums ${isActive ? 'text-[#b8c7ff]' : 'text-[#777b87]'}`}>
                  {formatTime(segment.startMs)}
                </span>
                <div className="flex-1">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className={`text-[10px] font-extrabold uppercase tracking-[0.22em] ${getSpeakerColor(segment.speaker)}`}>
                      {segment.speaker}
                    </span>
                    {isActive && (
                      <span className="rounded-full bg-[#b8c7ff]/15 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[#dbe3ff]">
                        Now Speaking
                      </span>
                    )}
                  </div>
                  <p className={`text-lg leading-8 transition-all duration-300 ${isActive ? 'font-semibold text-white' : 'font-normal text-[#a7aab8]'}`}>
                    {segment.text}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
