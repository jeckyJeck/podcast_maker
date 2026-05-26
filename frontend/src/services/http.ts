export const HTTP_REQUEST_TIMEOUT_MS = 180_000;
export const HTTP_RETRY_COUNT = 3;

export const getRetryDelayMs = (attempt: number): number => 1000 * 2 ** attempt;

export const isRetriableStatus = (status?: number): boolean => {
  return status === 408 || status === 429 || status === 502 || status === 503 || status === 504;
};

const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

const isAbortError = (error: unknown): boolean => {
  return error instanceof DOMException && error.name === 'AbortError';
};

const isNetworkFetchError = (error: unknown): boolean => {
  return error instanceof TypeError || isAbortError(error);
};

export const fetchWithRetry = async (
  input: RequestInfo | URL,
  init: RequestInit = {},
  {
    retries = HTTP_RETRY_COUNT,
    timeoutMs = HTTP_REQUEST_TIMEOUT_MS,
  }: { retries?: number; timeoutMs?: number } = {}
): Promise<Response> => {
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(input, {
        ...init,
        signal: controller.signal,
      });

      if (attempt < retries && isRetriableStatus(response.status)) {
        await delay(getRetryDelayMs(attempt));
        continue;
      }

      return response;
    } catch (error) {
      if (attempt >= retries || !isNetworkFetchError(error)) {
        throw error;
      }

      await delay(getRetryDelayMs(attempt));
    } finally {
      window.clearTimeout(timeout);
    }
  }

  throw new Error('Fetch retry loop exited unexpectedly');
};
