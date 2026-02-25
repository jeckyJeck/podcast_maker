import React, { useState } from 'react';
import { 
  FaDownload, 
  FaFileAudio, 
  FaFileCode, 
  FaFileAlt,
  FaCheckCircle,
  FaSpinner
} from 'react-icons/fa';
import type { PodcastFiles, FileInfo } from '../types/podcast';

interface FileDownloaderProps {
  files: PodcastFiles;
}

export const FileDownloader: React.FC<FileDownloaderProps> = ({ files }) => {
  const [downloadingFiles, setDownloadingFiles] = useState<Set<string>>(new Set());
  const [downloadedFiles, setDownloadedFiles] = useState<Set<string>>(new Set());

  const fileInfoList: FileInfo[] = [
    {
      name: 'blueprint',
      url: files.blueprint,
      type: 'json',
      displayName: 'מבנה הפודקאסט (Blueprint)',
    },
    {
      name: 'research',
      url: files.research,
      type: 'markdown',
      displayName: 'מחקר (Research)',
    },
    {
      name: 'outline',
      url: files.outline,
      type: 'json',
      displayName: 'קווי מתאר (Outline)',
    },
    {
      name: 'script',
      url: files.script,
      type: 'text',
      displayName: 'תסריט (Script)',
    },
    {
      name: 'audio',
      url: files.audio,
      type: 'audio',
      displayName: 'קובץ אודיו (Podcast Audio)',
    },
    ...(files.transcript ? [{
      name: 'transcript',
      url: files.transcript,
      type: 'json' as const,
      displayName: 'תמלול (Transcript JSON)',
    }] : []),
    ...(files.transcript_vtt ? [{
      name: 'transcript_vtt',
      url: files.transcript_vtt,
      type: 'text' as const,
      displayName: 'כתוביות (Transcript VTT)',
    }] : []),
  ];

  const getFileIcon = (type: FileInfo['type']) => {
    switch (type) {
      case 'audio':
        return <FaFileAudio className="text-purple-500" size={24} />;
      case 'json':
        return <FaFileCode className="text-yellow-500" size={24} />;
      case 'markdown':
      case 'text':
        return <FaFileAlt className="text-blue-500" size={24} />;
      default:
        return <FaFileAlt className="text-gray-500" size={24} />;
    }
  };

  const getFileExtension = (type: FileInfo['type'], fileName?: string): string => {
    // Special case for VTT files
    if (fileName === 'transcript_vtt') {
      return '.vtt';
    }
    
    switch (type) {
      case 'audio':
        return '.mp3';
      case 'json':
        return '.json';
      case 'markdown':
        return '.md';
      case 'text':
        return '.txt';
      default:
        return '';
    }
  };

  const downloadFile = async (fileInfo: FileInfo) => {
    try {
      setDownloadingFiles((prev) => new Set(prev).add(fileInfo.name));

      const response = await fetch(fileInfo.url);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${fileInfo.name}${getFileExtension(fileInfo.type, fileInfo.name)}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      setDownloadingFiles((prev) => {
        const newSet = new Set(prev);
        newSet.delete(fileInfo.name);
        return newSet;
      });
      setDownloadedFiles((prev) => new Set(prev).add(fileInfo.name));
    } catch (error) {
      console.error('Error downloading file:', error);
      setDownloadingFiles((prev) => {
        const newSet = new Set(prev);
        newSet.delete(fileInfo.name);
        return newSet;
      });
      alert(`שגיאה בהורדת ${fileInfo.displayName}`);
    }
  };

  const downloadAllFiles = async () => {
    for (const fileInfo of fileInfoList) {
      if (!downloadedFiles.has(fileInfo.name) && !downloadingFiles.has(fileInfo.name)) {
        await downloadFile(fileInfo);
        // Small delay between downloads to prevent browser blocking
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
  };

  const isDownloading = (name: string) => downloadingFiles.has(name);
  const isDownloaded = (name: string) => downloadedFiles.has(name);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 w-full">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
          קבצים להורדה
        </h3>
        <button
          onClick={downloadAllFiles}
          disabled={downloadingFiles.size > 0}
          className="flex items-center gap-2 px-4 py-2 bg-green-500 hover:bg-green-600 disabled:bg-gray-400 text-white rounded-lg transition-colors font-medium"
        >
          <FaDownload />
          <span>הורד הכל</span>
        </button>
      </div>

      <div className="space-y-3">
        {fileInfoList.map((fileInfo) => (
          <div
            key={fileInfo.name}
            className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
          >
            <div className="flex items-center gap-3">
              {getFileIcon(fileInfo.type)}
              <div>
                <p className="font-medium text-gray-800 dark:text-white">
                  {fileInfo.displayName}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {fileInfo.name}{getFileExtension(fileInfo.type)}
                </p>
              </div>
            </div>

            <button
              onClick={() => downloadFile(fileInfo)}
              disabled={isDownloading(fileInfo.name)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white rounded-lg transition-colors"
            >
              {isDownloading(fileInfo.name) ? (
                <>
                  <FaSpinner className="animate-spin" />
                  <span>מוריד...</span>
                </>
              ) : isDownloaded(fileInfo.name) ? (
                <>
                  <FaCheckCircle />
                  <span>הורד שוב</span>
                </>
              ) : (
                <>
                  <FaDownload />
                  <span>הורד</span>
                </>
              )}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
