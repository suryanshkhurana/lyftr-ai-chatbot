import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMetadata } from "../types/chat";
import { App } from "./App";

const META: ChatMetadata = {
  resolution_source: "LIVE_INFERENCE",
  model: "gemini/gemini-3.5-flash-lite",
  latency_ms: 812,
  input_tokens: 42,
  output_tokens: 9,
  key_id: "key_1",
  fallback_attempts: 0,
};

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

let chatHandler: Handler;
const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input);
  if (url.endsWith("/health")) return json(200, { status: "ok", keys_configured: 2, cache_enabled: true });
  return chatHandler(url, init);
});

function chatBodies(): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(([u]) => String(u).endsWith("/chat"))
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

beforeEach(() => {
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
  chatHandler = (_url, init) => {
    const body = JSON.parse(String(init?.body));
    return json(200, { session_id: body.session_id, reply: `Echo: ${body.message}`, metadata: META });
  };
});

afterEach(() => vi.unstubAllGlobals());

async function sendMessage(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByTestId("chat-input"), text);
  await user.click(screen.getByTestId("send-button"));
}

describe("App", () => {
  it("renders the required inputs and an empty state", async () => {
    render(<App />);
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    expect(screen.getByTestId("send-button")).toBeInTheDocument();
    expect(screen.getByTestId("system-prompt-input")).toBeInTheDocument();
    expect(screen.getByText("What would you like to explore?")).toBeInTheDocument();
    expect(screen.queryAllByTestId("assistant-message")).toHaveLength(0);
    await screen.findByText("Service ready");
  });

  it("sends only the new message and renders reply with all metadata inside the assistant container", async () => {
    render(<App />);
    await sendMessage("What is the capital of France?");

    const msg = await screen.findByTestId("assistant-message");
    expect(within(msg).getByText("Echo: What is the capital of France?")).toBeInTheDocument();
    expect(within(msg).getByTestId("meta-source")).toHaveTextContent(/^LIVE_INFERENCE$/);
    expect(within(msg).getByTestId("meta-model")).toHaveTextContent(/^gemini\/gemini-3\.5-flash-lite$/);
    expect(within(msg).getByTestId("meta-latency")).toHaveTextContent(/^812 ms$/);
    expect(within(msg).getByTestId("meta-input-tokens")).toHaveTextContent(/^42$/);
    expect(within(msg).getByTestId("meta-output-tokens")).toHaveTextContent(/^9$/);
    expect(screen.getByTestId("chat-input")).toHaveValue("");

    const [body] = chatBodies();
    expect(Object.keys(body).sort()).toEqual(["message", "session_id"]);
    expect(body.message).toBe("What is the capital of France?");
    expect(typeof body.session_id).toBe("string");
    expect((body.session_id as string).length).toBeGreaterThan(0);
    expect((body.session_id as string).length).toBeLessThanOrEqual(128);
  });

  it("keeps one session id per page load and sends only the latest message each turn", async () => {
    render(<App />);
    await sendMessage("first");
    await screen.findByText("Echo: first");
    await sendMessage("second");
    await screen.findByText("Echo: second");

    const bodies = chatBodies();
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual({ session_id: bodies[0].session_id, message: "second" });
    const messages = screen.getAllByTestId("assistant-message");
    expect(messages).toHaveLength(2);
    for (const m of messages) {
      for (const id of ["meta-source", "meta-model", "meta-latency", "meta-input-tokens", "meta-output-tokens"]) {
        expect(within(m).getByTestId(id)).toBeInTheDocument();
      }
    }
  });

  it("shows LLM_CACHE exactly", async () => {
    chatHandler = () =>
      json(200, {
        session_id: "x",
        reply: "Cached",
        metadata: { ...META, resolution_source: "LLM_CACHE", key_id: null, fallback_attempts: 0 },
      });
    render(<App />);
    await sendMessage("hi");
    expect(await screen.findByTestId("meta-source")).toHaveTextContent(/^LLM_CACHE$/);
  });

  it("starts a new session on every page load without browser storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const first = render(<App />);
    await sendMessage("a");
    await screen.findByText("Echo: a");
    first.unmount();
    render(<App />);
    await sendMessage("b");
    await screen.findByText("Echo: b");
    const [a, b] = chatBodies();
    expect(a.session_id).not.toEqual(b.session_id);
    expect(setItem).not.toHaveBeenCalled();
  });

  it("shows a readable 503 error, keeps the typed text and adds no assistant reply", async () => {
    chatHandler = () => json(503, { detail: "all providers unavailable" });
    render(<App />);
    await sendMessage("will fail");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/providers are unavailable/i);
    expect(screen.queryAllByTestId("assistant-message")).toHaveLength(0);
    expect(screen.getByTestId("chat-input")).toHaveValue("will fail");
    expect(screen.getByTestId("send-button")).toBeEnabled();
  });

  it("shows a readable 422 validation error", async () => {
    chatHandler = () =>
      json(422, {
        detail: [{ type: "value_error", loc: ["body", "message"], msg: "Value error, message must be at most 4000 characters" }],
      });
    render(<App />);
    await sendMessage("too long");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid request: message: message must be at most 4000 characters",
    );
  });

  it("shows a readable error when the server is unreachable", async () => {
    chatHandler = () => {
      throw new TypeError("Failed to fetch");
    };
    render(<App />);
    await sendMessage("offline");
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't reach the server/i);
  });

  it("Enter sends, Shift+Enter inserts a newline", async () => {
    const user = userEvent.setup();
    render(<App />);
    const input = screen.getByTestId("chat-input");
    await user.type(input, "line one{Shift>}{Enter}{/Shift}line two");
    expect(input).toHaveValue("line one\nline two");
    expect(chatBodies()).toHaveLength(0);
    await user.type(input, "{Enter}");
    await screen.findByTestId("assistant-message");
    expect(chatBodies()[0].message).toBe("line one\nline two");
  });

  it("disables send for empty input and prevents duplicate sends while pending", async () => {
    let release!: () => void;
    chatHandler = (_u, init) =>
      new Promise<Response>((resolve) => {
        release = () => {
          const body = JSON.parse(String(init?.body));
          resolve(json(200, { session_id: body.session_id, reply: "done", metadata: META }));
        };
      });
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByTestId("send-button")).toBeDisabled();
    await user.type(screen.getByTestId("chat-input"), "   ");
    expect(screen.getByTestId("send-button")).toBeDisabled();
    await user.clear(screen.getByTestId("chat-input"));
    await user.type(screen.getByTestId("chat-input"), "hello");
    await user.click(screen.getByTestId("send-button"));
    expect(await screen.findByText("Thinking...")).toBeInTheDocument();
    expect(screen.getByTestId("send-button")).toBeDisabled();
    await user.type(screen.getByTestId("chat-input"), "{Enter}");
    expect(chatBodies()).toHaveLength(1);
    release();
    await screen.findByText("done");
    await waitFor(() => expect(screen.queryByText("Thinking...")).not.toBeInTheDocument());
  });

  it("sends the session system prompt when set", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByText(/System prompt/));
    await user.type(screen.getByTestId("system-prompt-input"), "Be brief.");
    await sendMessage("hi");
    await screen.findByTestId("assistant-message");
    expect(chatBodies()[0]).toMatchObject({ message: "hi", system_prompt: "Be brief." });
  });
});
