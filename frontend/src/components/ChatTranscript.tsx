import { useEffect, useRef } from "react";
import type { TranscriptItem } from "../types/chat";
import { ErrorNotice } from "./ErrorNotice";
import { AssistantMessage, UserMessage } from "./MessageBubble";

interface Props {
  items: TranscriptItem[];
  pendingMessage: string | null;
}

export function ChatTranscript({ items, pendingMessage }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [items, pendingMessage]);

  const empty = items.length === 0 && pendingMessage === null;

  return (
    <section className="transcript" aria-label="Conversation" aria-live="polite">
      <div className="transcript-inner">
        {empty ? (
          <div className="empty-state">
            <h2>What would you like to explore?</h2>
            <p>Ask anything. The assistant remembers earlier messages in this conversation, so feel free to follow up.</p>
          </div>
        ) : null}
        {items.map((item) => {
          if (item.role === "user") return <UserMessage key={item.id} content={item.content} />;
          if (item.role === "assistant")
            return <AssistantMessage key={item.id} content={item.content} metadata={item.metadata} />;
          return <ErrorNotice key={item.id} message={item.content} />;
        })}
        {pendingMessage !== null ? (
          <>
            <UserMessage content={pendingMessage} />
            <div className="row row-assistant">
              <div className="thinking" role="status">
                <span className="dot" aria-hidden="true" />
                <span className="dot" aria-hidden="true" />
                <span className="dot" aria-hidden="true" />
                <span>Thinking...</span>
              </div>
            </div>
          </>
        ) : null}
        <div ref={endRef} />
      </div>
    </section>
  );
}
