import type { ChatRequest, ChatResponse, HealthResponse } from "../types/chat";

/** Backend base URL, injected at build time (VITE_API_BASE_URL). */
export const API_BASE_URL: string = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ValidationItem = { loc?: unknown[]; msg?: string };

/** Turn a backend `detail` (string or FastAPI validation list) into one readable sentence. */
export function readableDetail(status: number, detail: unknown): string {
  if (status === 503) {
    return "All providers are unavailable right now. Please try again in a moment.";
  }
  if (typeof detail === "string" && detail.trim()) {
    return status === 422 ? `Invalid request: ${detail}` : detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const parts = (detail as ValidationItem[]).map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
      const msg = (item.msg || "is invalid").replace(/^Value error, /, "");
      return field ? `${field}: ${msg}` : msg;
    });
    return `Invalid request: ${parts.join("; ")}`;
  }
  return `Request failed (HTTP ${status}).`;
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await res.json())?.detail;
  } catch {
    detail = undefined;
  }
  return new ApiError(res.status, readableDetail(res.status, detail));
}

export async function sendChat(request: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
  // Only the new message is sent; the backend rebuilds history from SQLite.
  const body: ChatRequest = { session_id: request.session_id, message: request.message };
  if (request.system_prompt && request.system_prompt.trim()) body.system_prompt = request.system_prompt;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as ChatResponse;
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, { signal });
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as HealthResponse;
}
