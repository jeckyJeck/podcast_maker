import { podcastApi } from './api';
import { FORMAT_MAX_HOSTS } from '../config/podcast';
import type { PodcastFormat } from '../types/podcast';

export const CREATE_PODCAST_FAILURE_MESSAGE = 'שגיאה ביצירת הפודקאסט. אנא נסה שוב.';

type ValidateCreatePodcastInputParams = {
  topic: string;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
};

export const validateCreatePodcastInput = ({
  topic,
  selectedFormat,
  selectedHostIds,
}: ValidateCreatePodcastInputParams): { isValid: true } | { isValid: false; message: string } => {
  if (!topic.trim()) {
    return {
      isValid: false,
      message: 'אנא הכנס נושא לפודקאסט',
    };
  }

  const maxHosts = FORMAT_MAX_HOSTS[selectedFormat];
  if (selectedHostIds.length !== maxHosts) {
    return {
      isValid: false,
      message:
        selectedFormat === 'dialogue'
          ? 'בפורמט שיחה צריך לבחור בדיוק 2 מארחים'
          : 'בפורמט סולו צריך לבחור בדיוק מארח אחד',
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
