import type { ScanStatusResponse } from "@/lib/types";

const POLL_INTERVAL_MS = 900;
const MAX_TRANSIENT_RETRIES = 10;
const RETRY_BASE_MS = 1500;

function isTransientStatus(status: number): boolean {
  return status === 0 || status === 502 || status === 503 || status === 504;
}

function retryDelay(attempt: number): number {
  return RETRY_BASE_MS + attempt * 400;
}

export type ScanPollCallbacks = {
  onProgress: (data: ScanStatusResponse) => void;
  onRetry: (message: string) => void;
  onComplete: (data: ScanStatusResponse) => void;
  onError: (message: string) => void;
};

export async function pollScanStatus(
  fetchStatus: () => Promise<Response>,
  callbacks: ScanPollCallbacks,
  attempt = 0,
): Promise<void> {
  try {
    const res = await fetchStatus();

    let data: ScanStatusResponse & { error?: string };
    try {
      data = (await res.json()) as ScanStatusResponse & { error?: string };
    } catch {
      if (attempt < MAX_TRANSIENT_RETRIES && isTransientStatus(res.status)) {
        callbacks.onRetry(`Server busy — reconnecting (${attempt + 1}/${MAX_TRANSIENT_RETRIES})…`);
        window.setTimeout(() => void pollScanStatus(fetchStatus, callbacks, attempt + 1), retryDelay(attempt));
        return;
      }
      callbacks.onError(
        "Lost connection to the scanner. If this keeps happening, try PDF upload instead of a URL scan.",
      );
      return;
    }

    if (!res.ok) {
      if (res.status === 404) {
        callbacks.onError(
          data.error ||
            "Scan session was lost (the server may have restarted). Please run a new assessment.",
        );
        return;
      }
      if (attempt < MAX_TRANSIENT_RETRIES && isTransientStatus(res.status)) {
        callbacks.onRetry(`Connection interrupted — retrying (${attempt + 1}/${MAX_TRANSIENT_RETRIES})…`);
        window.setTimeout(() => void pollScanStatus(fetchStatus, callbacks, attempt + 1), retryDelay(attempt));
        return;
      }
      callbacks.onError(data.error || "Unable to retrieve scan status.");
      return;
    }

    callbacks.onProgress(data);

    if (data.status === "complete") {
      callbacks.onComplete(data);
      return;
    }

    if (data.status === "error") {
      callbacks.onError(
        data.error ||
          "The assessment failed. On free hosting, URL scans can run out of memory — try uploading a PDF instead.",
      );
      return;
    }

    window.setTimeout(() => void pollScanStatus(fetchStatus, callbacks, 0), POLL_INTERVAL_MS);
  } catch {
    if (attempt < MAX_TRANSIENT_RETRIES) {
      callbacks.onRetry(`Reconnecting to scanner (${attempt + 1}/${MAX_TRANSIENT_RETRIES})…`);
      window.setTimeout(() => void pollScanStatus(fetchStatus, callbacks, attempt + 1), retryDelay(attempt));
      return;
    }
    callbacks.onError(
      "Unable to retrieve scan status after several retries. Wait a moment and try again, or use PDF upload.",
    );
  }
}
