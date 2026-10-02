import { podcastApi } from './api';
import type { PodcastFormat } from '../types/podcast';

export const CREATE_PODCAST_FAILURE_MESSAGE = 'שגיאה ביצירת הפודקאסט. אנא נסה שוב.';

type ValidateCreatePodcastInputParams = {
  topic: string;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  maxHosts: number; // hosts the selected format needs
};

export const validateCreatePodcastInput = ({
  topic,
  selectedFormat,
  selectedHostIds,
  maxHosts,
}: ValidateCreatePodcastInputParams): { isValid: true } | { isValid: false; message: string } => {
  if (!topic.trim()) {
    return {
      isValid: false,
      message: 'אנא הכנס נושא לפודקאסט',
    };
  }

  if (!selectedFormat) {
    return { isValid: false, message: 'אנא בחר פורמט לפודקאסט' };
  }

  if (selectedHostIds.length !== maxHosts) {
    return {
      isValid: false,
      message: maxHosts === 1 ? 'בפורמט זה צריך לבחור בדיוק מארח אחד' : `בפורמט זה צריך לבחור בדיוק ${maxHosts} מארחים`,
    };
  }

  return { isValid: true };
};

export const createPodcastTask = async ({
  topic,
  selectedHostIds,
  selectedFormat,
}: ValidateCreatePodcastInputParams): Promise<string> => {
  const response = await podcastApi.createPodcast(topic.trim(), selectedHostIds, selectedFormat);
  return response.task_id;
};
