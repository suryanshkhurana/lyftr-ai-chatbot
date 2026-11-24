/** A fresh id for each page load. Deliberately never persisted to localStorage/sessionStorage. */
export function createSessionId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return `s-${c.randomUUID()}`;
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
