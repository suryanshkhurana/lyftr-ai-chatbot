import type { ChatMetadata } from "../types/chat";
import { MessageMetadata } from "./MessageMetadata";

export function UserMessage({ content }: { content: string }) {
  return (
    <div className="row row-user">
      <div className="bubble bubble-user" aria-label="Your message">
        {content}
      </div>
    </div>
  );
}

export function AssistantMessage({ content, metadata }: { content: string; metadata: ChatMetadata }) {
  return (
    <div className="row row-assistant">
      <article className="bubble bubble-assistant" data-testid="assistant-message" aria-label="Assistant reply">
        <div className="assistant-text">{content}</div>
        <MessageMetadata metadata={metadata} />
      </article>
    </div>
  );
}
