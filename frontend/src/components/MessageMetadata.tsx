import type { ChatMetadata } from "../types/chat";

/** Each test-id element holds only its value; labels sit outside so textContent is exact. */
export function MessageMetadata({ metadata }: { metadata: ChatMetadata }) {
  const isCache = metadata.resolution_source === "LLM_CACHE";
  return (
    <dl className="meta" aria-label="Response details">
      <div className="meta-item">
        <dt className="sr-only">Source</dt>
        <dd>
          <span className={`meta-source ${isCache ? "is-cache" : "is-live"}`} data-testid="meta-source">
            {metadata.resolution_source}
          </span>
        </dd>
      </div>
      <div className="meta-item">
        <dt className="sr-only">Model</dt>
        <dd className="meta-model" data-testid="meta-model">
          {metadata.model}
        </dd>
      </div>
      <div className="meta-item">
        <dt className="sr-only">Latency</dt>
        <dd data-testid="meta-latency">{metadata.latency_ms} ms</dd>
      </div>
      <div className="meta-item">
        <dt>In</dt>
        <dd>
          <span data-testid="meta-input-tokens">{metadata.input_tokens}</span> tokens
        </dd>
      </div>
      <div className="meta-item">
        <dt>Out</dt>
        <dd>
          <span data-testid="meta-output-tokens">{metadata.output_tokens}</span> tokens
        </dd>
      </div>
      {metadata.key_id && metadata.fallback_attempts > 0 ? (
        <div className="meta-item meta-fallback">
          <dt className="sr-only">Failover</dt>
          <dd>
            via {metadata.key_id} after {metadata.fallback_attempts} failed{" "}
            {metadata.fallback_attempts === 1 ? "key" : "keys"}
          </dd>
        </div>
      ) : null}
    </dl>
  );
}
