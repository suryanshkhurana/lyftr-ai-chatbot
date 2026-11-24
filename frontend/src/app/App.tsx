import { useCallback, useEffect, useRef, useState } from "react";
import { ChatComposer } from "../components/ChatComposer";
import { ChatHeader, type ServiceStatus } from "../components/ChatHeader";
import { ChatTranscript } from "../components/ChatTranscript";
import { SystemPromptControl } from "../components/SystemPromptControl";
import { ApiError, getHealth, sendChat } from "../services/chatApi";
import type { TranscriptItem } from "../types/chat";
import { createSessionId } from "../utils/sessionId";

let nextId = 0;
const uid = () => `m${++nextId}`;

export function App() {
  // Generated once per page load and kept only in memory.
  const [sessionId] = useState(createSessionId);
  const [items, setItems] = useState<TranscriptItem[]>([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [status, setStatus] = useState<ServiceStatus>("checking");
  const inFlight = useRef(false);

  useEffect(() => {
    const ctrl = new AbortController();
    getHealth(ctrl.signal)
      .then(() => setStatus("ready"))
      .catch(() => {
        if (!ctrl.signal.aborted) setStatus("unavailable");
      });
    return () => ctrl.abort();
  }, []);

  const send = useCallback(async () => {
    const message = input.trim();
    if (!message || inFlight.current) return;
    inFlight.current = true;
    setPendingMessage(message);
    try {
      const res = await sendChat({ session_id: sessionId, message, system_prompt: systemPrompt });
      setItems((prev) => [
        ...prev,
        { id: uid(), role: "user", content: message },
        { id: uid(), role: "assistant", content: res.reply, metadata: res.metadata },
      ]);
      setInput("");
      setStatus("ready");
    } catch (err) {
      const text = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
      // The failed turn is not part of the conversation; the typed text stays in the input for retry.
      setItems((prev) => [...prev, { id: uid(), role: "error", content: text }]);
    } finally {
      setPendingMessage(null);
      inFlight.current = false;
    }
  }, [input, sessionId, systemPrompt]);

  return (
    <div className="app">
      <ChatHeader status={status} />
      <main className="main">
        <ChatTranscript items={items} pendingMessage={pendingMessage} />
        <div className="composer-area">
          <SystemPromptControl value={systemPrompt} onChange={setSystemPrompt} />
          <ChatComposer value={input} onChange={setInput} onSend={send} pending={pendingMessage !== null} />
          <p className="helper composer-hint">Enter to send, Shift+Enter for a new line.</p>
        </div>
      </main>
    </div>
  );
}
