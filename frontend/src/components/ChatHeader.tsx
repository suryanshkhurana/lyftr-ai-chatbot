export type ServiceStatus = "checking" | "ready" | "unavailable";

const LABELS: Record<ServiceStatus, string> = {
  checking: "Checking service",
  ready: "Service ready",
  unavailable: "Service unavailable",
};

export function ChatHeader({ status }: { status: ServiceStatus }) {
  return (
    <header className="header">
      <div className="header-inner">
        <h1 className="title">Lyftr AI</h1>
        <span className={`status status-${status}`}>
          <span className="status-dot" aria-hidden="true" />
          {LABELS[status]}
        </span>
      </div>
    </header>
  );
}
