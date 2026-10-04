import { podcastApi } from './api';
import { buildInputsPayload, inputLabel, type FormatInputFormValues } from '../config/podcast';
import type { FormatInput, PodcastFormat } from '../types/podcast';

export const CREATE_PODCAST_FAILURE_MESSAGE = 'שגיאה ביצירת הפודקאסט. אנא נסה שוב.';

type ValidateCreatePodcastInputParams = {
  topic: string;
  selectedFormat: PodcastFormat;
  selectedHostIds: string[];
  maxHosts: number; // hosts the selected format needs
  formInputs: FormatInput[]; // the selected format's extra inputs
  inputValues: FormatInputFormValues;
};

export const validateCreatePodcastInput = ({
  topic,
  selectedFormat,
  selectedHostIds,
  maxHosts,
  formInputs,
  inputValues,
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

  const inputs = buildInputsPayload(formInputs, inputValues);
  if (!inputs.ok) {
    return inputs.missing
      ? { isValid: false, message: `אנא מלא את השדה: ${inputLabel(inputs.missing)}` }
      : { isValid: false, message: `השדה ${inputLabel(inputs.invalidNumber ?? '')} חייב להיות מספר` };
  }

  return { isValid: true };
};

export const createPodcastTask = async ({
  topic,
  selectedHostIds,
  selectedFormat,
  formInputs,
  inputValues,
}: ValidateCreatePodcastInputParams): Promise<string> => {
  const inputs = buildInputsPayload(formInputs, inputValues);
  const response = await podcastApi.createPodcast(
    topic.trim(),
    selectedHostIds,
    selectedFormat,
    inputs.ok ? inputs.inputs : undefined,
  );
  return response.task_id;
};
