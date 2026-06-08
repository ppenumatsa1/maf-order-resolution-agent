import { ReactNode } from "react";

type Props = {
  onNewRun: () => void;
  onRefresh: () => void;
  children: ReactNode;
};

export default function AppShell({ onNewRun, onRefresh, children }: Props) {
  return (
    <main className="studio-shell">
      <header className="studio-header">
        <div>
          <h1>MAF Workflow Studio</h1>
          <p>Run, observe, approve, and resume multi-agent workflows</p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn btn-primary" onClick={onNewRun}>
            New Run
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onRefresh}
          >
            Refresh
          </button>
        </div>
      </header>
      <section className="studio-main">{children}</section>
    </main>
  );
}
