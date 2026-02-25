import React, { useState, useEffect } from 'react';
import { FaTimes } from 'react-icons/fa';
import { podcastApi } from '../services/api';
import type { HostProfile } from '../types/podcast';

interface HostSelectorProps {
  isOpen: boolean;
  onClose: () => void;
  selectedHostIds: string[];
  onHostsSelected: (hostIds: string[]) => void;
}

export const HostSelector: React.FC<HostSelectorProps> = ({
  isOpen,
  onClose,
  selectedHostIds,
  onHostsSelected,
}) => {
  const [hosts, setHosts] = useState<HostProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [localSelected, setLocalSelected] = useState<string[]>(selectedHostIds);

  useEffect(() => {
    if (isOpen) {
      setLocalSelected(selectedHostIds);
    }
  }, [isOpen, selectedHostIds]);

  const fetchHosts = async () => {
    setLoading(true);
    try {
      const response = await podcastApi.getAvailableHosts();
      setHosts(response.hosts);
    } catch (error) {
      console.error('Failed to fetch hosts:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (hosts.length === 0) {
      fetchHosts();
    }
  }, []);

  const handleHostClick = (hostId: string) => {
    setLocalSelected((prev) => {
      const isSelected = prev.includes(hostId);
      if (isSelected) {
        // Deselect if already selected
        return prev.filter((id) => id !== hostId);
      } else {
        // Add new host, but keep only the last 2 selected
        const updated = [...prev, hostId];
        if (updated.length > 2) {
          return updated.slice(-2); // Keep last 2
        }
        return updated;
      }
    });
  };

  const handleConfirm = () => {
    if (localSelected.length === 2) {
      onHostsSelected(localSelected);
      onClose();
    }
  };

  const getHostImagePath = (hostId: string) => `/hosts/${hostId}/image.png`;
  const getHostAudioPath = (hostId: string) => `/hosts/${hostId}/sample.mp3`;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 z-10"
        >
          <FaTimes size={20} />
        </button>

        {/* Scrollable Content */}
        <div className="overflow-y-auto flex-1 p-4">
          {loading ? (
            <div className="text-center py-8">
              <p className="text-gray-500 dark:text-gray-400">טוען מארחים...</p>
            </div>
          ) : (
            <>
              {/* <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
                בחר בדיוק 2 מארחים
              </p> */}

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {hosts.map((host) => {
                  const isSelected = localSelected.includes(host.id);
                  return (
                    <div
                      key={host.id}
                      onClick={() => handleHostClick(host.id)}
                      className={`cursor-pointer rounded-lg transition-all ${
                        isSelected
                          ? 'ring-3 ring-blue-500 shadow-lg bg-blue-50 dark:bg-blue-900/30'
                          : 'bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600'
                      } p-2 border border-gray-200 dark:border-gray-600`}
                    >
                      {/* Host Image Placeholder */}
                      <div className="w-20 h-20 bg-gradient-to-br from-gray-300 to-gray-400 dark:from-gray-600 dark:to-gray-700 rounded-lg mb-2 flex items-center justify-center overflow-hidden flex-shrink-0 mx-auto">
                        <img
                          src={getHostImagePath(host.id)}
                          alt={host.name}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                          }}
                        />
                        <span className="text-gray-400 text-2xl font-bold">
                          {host.name.charAt(0)}
                        </span>
                      </div>

                      {/* Host Info */}
                      <h3 className="text-sm font-semibold text-gray-800 dark:text-white mb-1 truncate">
                        {host.name}
                      </h3>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-2 line-clamp-2 min-h-8">
                        {host.tone}
                      </p>

                      {/* Description */}
                      <p dir="ltr" className="text-ms text-gray-700 dark:text-gray-300 mb-2 line-clamp-none max-h-48 overflow-y-auto text-wrap break-words">
                        {host.personality || 'problem loading description...'}
                      </p>

                      {/* Voice Sample */}
                      <audio
                        controls
                        className="w-full h-6 mb-2 text-xs"
                        controlsList="nodownload"
                      >
                        <source src={getHostAudioPath(host.id)} type="audio/mpeg" />
                        הדפדפן לא תומך
                      </audio>

                      {/* Selection Indicator */}
                      {/* {isSelected && (
                        <div className="text-blue-600 dark:text-blue-400 font-semibold text-xs text-center">
                          ✓
                        </div>
                      )} */}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Sticky Footer */}
        <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 flex-shrink-0">
          {/* Selection Info */}
          <div className="text-sm text-gray-600 dark:text-gray-400 mb-3 p-2 bg-gray-100 dark:bg-gray-700 rounded text-center">
            {localSelected.length === 0 && 'בחר 2 מארחים'}
            {localSelected.length === 1 && `בחר עוד מארח אחד (${1} מתוך 2)`}
            {localSelected.length === 2 &&
              `נבחרו: ${localSelected
                .map((id) => hosts.find((h) => h.id === id)?.name)
                .join(' ו')} ✓`}
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2 justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-800 dark:text-white text-sm font-medium rounded-lg transition-colors"
            >
              בטל
            </button>
            <button
              onClick={handleConfirm}
              disabled={localSelected.length !== 2}
              className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white text-sm font-medium rounded-lg transition-colors disabled:cursor-not-allowed"
            >
              אישור
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
