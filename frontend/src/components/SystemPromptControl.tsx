interface Props {
  value: string;
  onChange: (value: string) => void;
}

export function SystemPromptControl({ value, onChange }: Props) {
  return (
    <details className="system-prompt">
      <summary>System prompt{value.trim() ? " (custom)" : ""}</summary>
      <label htmlFor="system-prompt-input" className="helper">
        Applies to this session only. Leave empty to use the default assistant behavior.
      </label>
      <textarea
        id="system-prompt-input"
        data-testid="system-prompt-input"
        className="system-prompt-input"
        rows={2}
        placeholder="e.g. Answer clearly and briefly."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </details>
  );
}
