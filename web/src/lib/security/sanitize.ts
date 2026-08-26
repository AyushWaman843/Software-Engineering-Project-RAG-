/**
 * Strip control characters and enforce length limits on user-supplied text.
 * Used before sending form data to the API (UX layer — server re-validates).
 */

const CONTROL_CHARS = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g;

export function sanitizeTextInput(raw: string, maxLength = 256): string {
  return raw.replace(CONTROL_CHARS, "").trim().slice(0, maxLength);
}
