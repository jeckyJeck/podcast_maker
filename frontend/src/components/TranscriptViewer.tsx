import { useEffect, useRef, useState } from 'react';
import { TranscriptSegment } from '../types/podcast';

interface TranscriptViewerProps {
  transcriptUrl: string;
  currentTime: number; // in seconds
  onSeek?: (timeInSeconds: number) => void;
}

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
        const response = await fetch(transcriptUrl);
        if (!response.ok) {
          throw new Error('Failed to fetch transcript');
        }
        const data: TranscriptSegment[] = await response.json();
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
    return speaker === 'HOST_1' ? 'text-blue-600 dark:text-blue-400' : 'text-purple-600 dark:text-purple-400';
  };

  const getSpeakerBgColor = (speaker: string): string => {
    return speaker === 'HOST_1' ? 'bg-blue-50/50 dark:bg-blue-900/20' : 'bg-purple-50/50 dark:bg-purple-900/20';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8 h-full" dir="ltr">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-500 text-sm">Loading transcript...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 flex items-center justify-center h-full" dir="ltr">
        <p className="text-red-500 text-sm">Error loading transcript</p>
      </div>
    );
  }

  if (segments.length === 0) {
    return (
      <div className="p-8 flex items-center justify-center h-full" dir="ltr">
        <p className="text-gray-400 text-sm italic">No transcript available</p>
      </div>
    );
  }

  return (
    <div className="bg-transparent h-[300px] overflow-y-auto scroll-smooth custom-scrollbar" dir="ltr">
      <div className="p-6 space-y-1">
        {segments.map((segment, index) => {
          const isActive = index === activeIndex;
          return (
            <div
              key={index}
              ref={isActive ? activeSegmentRef : null}
              onClick={() => handleSegmentClick(segment)}
              className={`p-4 rounded-2xl transition-all duration-500 cursor-pointer border-l-4 ${
                isActive
                  ? `${getSpeakerBgColor(segment.speaker)} border-blue-500 dark:border-blue-400 opacity-100`
                  : 'hover:bg-gray-50 dark:hover:bg-gray-800/50 border-transparent opacity-60 hover:opacity-100'
              }`}
            >
              <div className="flex items-start gap-4">
                <span className={`text-[10px] font-mono mt-1 opacity-50 min-w-[40px] ${isActive ? 'text-blue-600 dark:text-blue-400 opacity-100' : 'text-gray-500'}`}>
                  {formatTime(segment.startMs)}
                </span>
                <div className="flex-1">
                  <span className={`text-[11px] font-bold uppercase tracking-wider ${getSpeakerColor(segment.speaker)}`}>
                    {segment.speaker}
                  </span>
                  <p className={`text-gray-800 dark:text-gray-200 mt-1 leading-relaxed text-base transition-all duration-300 ${isActive ? 'font-medium' : 'font-normal'}`}>
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
