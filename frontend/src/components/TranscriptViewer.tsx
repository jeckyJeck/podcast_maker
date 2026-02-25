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
    return speaker === 'HOST_1' ? 'text-blue-600' : 'text-purple-600';
  };

  const getSpeakerBgColor = (speaker: string): string => {
    return speaker === 'HOST_1' ? 'bg-blue-50' : 'bg-purple-50';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8" dir="ltr">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-600">Loading transcript...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg" dir="ltr">
        <p className="text-red-600">Error loading transcript: {error}</p>
      </div>
    );
  }

  if (segments.length === 0) {
    return (
      <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg" dir="ltr">
        <p className="text-gray-600">No transcript available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6 max-h-[600px] overflow-y-auto" dir="ltr">
      <h3 className="text-lg font-semibold mb-4 text-gray-800">Transcript</h3>
      <div className="space-y-2">
        {segments.map((segment, index) => {
          const isActive = index === activeIndex;
          return (
            <div
              key={index}
              ref={isActive ? activeSegmentRef : null}
              onClick={() => handleSegmentClick(segment)}
              className={`p-3 rounded-lg transition-all duration-200 cursor-pointer ${
                isActive
                  ? `${getSpeakerBgColor(segment.speaker)} shadow-md ring-2 ring-offset-2 ${
                      segment.speaker === 'HOST_1' ? 'ring-blue-500' : 'ring-purple-500'
                    }`
                  : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="text-xs text-gray-500 font-mono min-w-[45px]">
                  {formatTime(segment.startMs)}
                </span>
                <div className="flex-1">
                  <span className={`font-semibold text-sm ${getSpeakerColor(segment.speaker)}`}>
                    {segment.speaker}:
                  </span>
                  <p className={`text-gray-700 mt-1 ${isActive ? 'font-medium' : ''}`}>
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
