export type ResolutionSource = "LIVE_INFERENCE" | "LLM_CACHE";

export interface ChatRequest {
  session_id: string;
  message: string;
  system_prompt?: string;
}

export interface ChatMetadata {
  resolution_source: ResolutionSource;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  key_id: string | null;
  fallback_attempts: number;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  metadata: ChatMetadata;
}

export interface HealthResponse {
  status: string;
  keys_configured: number;
  cache_enabled: boolean;
}

export type TranscriptItem =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; content: string; metadata: ChatMetadata }
  | { id: string; role: "error"; content: string };
