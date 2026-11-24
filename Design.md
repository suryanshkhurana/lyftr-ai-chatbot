# Design Specification

## 1. Design direction

Create a clean, modern AI chat interface that feels calm, dependable, and technical without looking like an admin dashboard. The conversation is the primary focus. Metadata should be easy for an evaluator to inspect but visually secondary to the assistant's answer.

**Experience principles**

- Clarity over decoration.
- Keep the current conversation visually dominant.
- Make source, model, latency, and tokens scannable beside every assistant response.
- Use clear loading, success, cache, and error states.
- Work well on desktop and mobile.
- Do not add decorative features that obscure the assignment requirements.

## 2. Color palette

Use a light neutral base with a restrained indigo accent.

| Token | Hex | Usage |
|---|---|---|
| `--color-page` | `#F7F8FC` | Main application background |
| `--color-surface` | `#FFFFFF` | Header, message surfaces, composer |
| `--color-surface-muted` | `#F1F3F9` | Assistant message background and subtle panels |
| `--color-text` | `#172033` | Main text |
| `--color-text-muted` | `#687386` | Secondary text, timestamps, helper copy |
| `--color-border` | `#E3E7EF` | Dividers, inputs, message outlines |
| `--color-accent` | `#5558D9` | Primary button, focus ring, links |
| `--color-accent-hover` | `#4548C7` | Primary button hover |
| `--color-live` | `#2563EB` | `LIVE_INFERENCE` label |
| `--color-cache` | `#0F766E` | `LLM_CACHE` label |
| `--color-success` | `#15803D` | Healthy/ready status |
| `--color-warning` | `#B45309` | Non-blocking warning state |
| `--color-error` | `#B42318` | API error state |
| `--color-error-bg` | `#FEF3F2` | Error message background |

Use semantic colors consistently. `LIVE_INFERENCE` and `LLM_CACHE` must remain visible as exact text, not only as color or icons.

## 3. Typography

- **Preferred font:** Inter.
- **Fallback:** `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`.
- **Page title:** 20-24 px, 600-700 weight.
- **Message body:** 15-16 px, 400 weight, line-height 1.6.
- **Metadata:** 12-13 px, 500 weight, line-height 1.4.
- **Input text:** 15-16 px.
- **Helper / empty-state text:** 13-14 px.

Use sentence case. Avoid oversized headings, all-caps decorative labels, and long blocks of low-contrast text.

## 4. Layout and dimensions

### Desktop

- App fills the viewport height.
- Header: approximately 64-72 px high, full width, with a subtle bottom border.
- Main chat column: maximum width approximately 900-960 px, centered.
- Transcript: flexible vertical area with its own scroll behavior.
- Message text width: approximately 70-78 characters per line; do not stretch long responses edge-to-edge.
- Composer: anchored at the bottom of the main column with comfortable padding and a visible border/shadow separation.
- Keep the system-prompt control compact and secondary, preferably collapsible or placed above the composer.

### Mobile

- Use the full available width with 16 px side padding.
- Header remains compact.
- Message bubbles use nearly full width and wrap long model names safely.
- Composer remains reachable without horizontal scrolling.
- Metadata may wrap into multiple rows; never hide required fields on narrow screens.

## 5. Conversation design

### Empty state

- Show a concise welcome message such as **"What would you like to explore?"**
- Add one line explaining that the assistant can answer follow-up questions.
- Optional example prompts may be shown as text suggestions, but they must not be inserted as fake messages or trigger a backend request automatically.

### User message

- Align to the right on desktop and visually distinguish from assistant content.
- Use a soft accent-tinted surface or subtle neutral surface; maintain strong text contrast.
- Preserve line breaks and wrap long text.

### Assistant message

- Align to the left.
- Use a white or muted-neutral surface with a subtle border.
- Show assistant reply text first.
- Render request metadata immediately beneath the reply, inside the same `assistant-message` container.

### Metadata row

Display all five required values for every assistant response:

1. source (`LIVE_INFERENCE` or `LLM_CACHE`);
2. model name;
3. latency in milliseconds;
4. input token count;
5. output token count.

Recommended compact presentation:

```text
LIVE_INFERENCE  provider/model-name  812 ms  In 42 tokens  Out 9 tokens
```

The labels can be visually shortened, but the values must remain clear. Use wrapping/flex layout on mobile. Keep exact source text in the DOM for the evaluator and attach the exact `data-testid` attributes specified in `PRD.md`.

Do not use a single test ID for the whole metadata row. Each metadata value has its own test ID and all of them belong to the same assistant reply container.

Required frontend test IDs (exact spelling):

- `assistant-message`
- `meta-source`
- `meta-model`
- `meta-latency`
- `meta-input-tokens`
- `meta-output-tokens`

## 6. Composer design

- Use a multiline textarea with a clear border and rounded corners.
- Placeholder: `Message Lyftr AI...` or similarly concise copy.
- Primary send button uses the accent color and a clear send icon plus accessible label.
- Disable the send button while a request is pending or when the trimmed message is empty.
- Enter sends the message; Shift+Enter inserts a newline.
- Clear the textarea after a successful send.
- Preserve the typed message on a failed request so the user can retry.
- Show a small pending indicator or `Thinking...` label while the backend is responding.
- Ensure the textarea and button remain keyboard accessible.

Required test IDs:

- textarea: `chat-input`
- button: `send-button`

## 7. System prompt control (optional feature)

If included:

- Use a small expandable section labeled `System prompt` or `Customize assistant`.
- Provide a textarea with `data-testid="system-prompt-input"`.
- Explain that the prompt applies to the current session.
- Do not make it visually compete with the chat composer.
- Send it as `system_prompt` on the chat request when the user sets/changes it; backend persistence is responsible for the session-level behavior.
- Never show the system prompt in the conversation history endpoint or as a chat bubble.

If the feature adds risk or delays the mandatory requirements, omit it. It is optional in the assignment.

## 8. Loading, error, and connection states

### Loading

- Show an inline loading state near the newest assistant position.
- Prevent duplicate sends until the current request resolves.
- Keep prior conversation messages visible and stable.

### Error

- Display a compact inline error notice in the conversation, using the error color tokens.
- Present the backend's readable `detail` or a safe friendly message.
- Do not show stack traces, raw provider output, secrets, or raw API key information.
- Do not render an error as an assistant reply or attach fabricated metadata.
- A 422 or 503 response must not break the page.

### Connection / health

A small neutral status label may show that the service is ready, but do not add a new backend health route. The frontend may call `GET /health` if the implementation needs to show readiness; avoid polling aggressively.

## 9. Iconography and interaction

- Use a consistent outline icon set (Lucide is acceptable) or simple inline SVGs.
- Keep icons functional and paired with accessible labels where needed.
- Buttons need visible hover, focus, active, and disabled states.
- Use a clear focus ring for keyboard navigation.
- Avoid unnecessary animation. Short fades or subtle loading motion are sufficient; respect reduced-motion preferences.

## 10. Accessibility and responsive behavior

- Maintain readable contrast for body text and metadata.
- Use semantic buttons, textareas, headings, and message regions.
- Provide accessible labels for inputs and buttons.
- Ensure metadata is accessible to screen readers and not conveyed by color alone.
- Keep tab order logical.
- Do not trap keyboard focus.
- Wrap long model names and long user messages without horizontal page overflow.
- Respect `prefers-reduced-motion`.

## 11. Visual quality checklist

- [ ] The conversation is the primary focus.
- [ ] Assistant and user messages are visually distinct.
- [ ] Every assistant response shows the exact source, model, latency, input tokens, and output tokens.
- [ ] The five metadata fields remain readable on mobile.
- [ ] Loading state is visible and duplicate sends are prevented.
- [ ] 422/503 errors are readable, inline, and non-fatal.
- [ ] Composer clears after a successful response.
- [ ] System prompt is secondary and session-scoped if implemented.
- [ ] All required `data-testid` values are attached to the correct elements.
- [ ] Focus, hover, disabled, and responsive states are implemented.
