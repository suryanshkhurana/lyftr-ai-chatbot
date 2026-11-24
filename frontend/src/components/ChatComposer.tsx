import type { FormEvent, KeyboardEvent } from "react";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  pending: boolean;
}

export function ChatComposer({ value, onChange, onSend, pending }: Props) {
  const canSend = !pending && value.trim().length > 0;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canSend) onSend();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (canSend) onSend();
    }
  };

  return (
    <form className="composer" onSubmit={submit}>
      <label htmlFor="chat-input" className="sr-only">
        Message
      </label>
      <textarea
        id="chat-input"
        data-testid="chat-input"
        className="composer-input"
        placeholder="Message Lyftr AI..."
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <button type="submit" className="send-button" data-testid="send-button" disabled={!canSend} aria-label="Send message">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
        <span className="send-label">Send</span>
      </button>
    </form>
  );
}
