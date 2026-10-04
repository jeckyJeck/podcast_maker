import type { FormatInput, PodcastFormat, PodcastFormatInfo, PodcastInputValues } from '../types/podcast';

export const DEFAULT_HOST_IDS = ['sarah_curious', 'mike_expert'] as const;

// How many hosts a format needs, from the format list the backend serves (the pipeline YAML decides).
export const maxHostsFor = (formats: PodcastFormatInfo[], format: PodcastFormat): number =>
  formats.find((f) => f.id === format)?.host_count ?? DEFAULT_HOST_IDS.length;

// What the user edits on the create screen: text and number fields hold the typed string, toggles a boolean.
export type FormatInputFormValues = Record<string, string | boolean>;

// The format's extra inputs the create screen shows as fields. `json` inputs have no form field.
export const formInputsFor = (formats: PodcastFormatInfo[], format: PodcastFormat): FormatInput[] =>
  (formats.find((f) => f.id === format)?.inputs ?? []).filter((input) => input.type !== 'json');

export const defaultFormValues = (inputs: FormatInput[]): FormatInputFormValues =>
  Object.fromEntries(
    inputs.map((input) => [
      input.name,
      input.type === 'boolean' ? input.default === true : input.default == null ? '' : String(input.default),
    ]),
  );

// "show_name" -> "Show name"
export const inputLabel = (name: string): string => {
  const words = name.replace(/[_-]+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

// The request's `inputs`: only values the user set. A blank field is left out so the pipeline's default applies.
export const buildInputsPayload = (
  inputs: FormatInput[],
  values: FormatInputFormValues,
): { ok: true; inputs: PodcastInputValues } | { ok: false; missing?: string; invalidNumber?: string } => {
  const payload: PodcastInputValues = {};
  for (const input of inputs) {
    const value = values[input.name];
    if (input.type === 'boolean') {
      if (typeof value === 'boolean' && value !== (input.default === true)) payload[input.name] = value;
      continue;
    }
    const text = typeof value === 'string' ? value.trim() : '';
    if (!text) {
      if (input.required) return { ok: false, missing: input.name };
      continue;
    }
    if (input.type === 'number') {
      const num = Number(text);
      if (!Number.isFinite(num)) return { ok: false, invalidNumber: input.name };
      if (num !== input.default) payload[input.name] = num;
    } else if (text !== input.default) {
      payload[input.name] = text;
    }
  }
  return { ok: true, inputs: payload };
};
