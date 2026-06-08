import JsonViewer from "./JsonViewer";
import { WorkflowEvent } from "../../types/workflow";

type Props = {
  event: WorkflowEvent;
};

function summarizeEvent(event: WorkflowEvent): string {
  const payload = event.payload ?? {};
  if (typeof payload.status === "string") {
    return `${payload.status}`;
  }
  if (typeof payload.question === "string") {
    return payload.question;
  }
  if (typeof payload.message === "string") {
    return payload.message;
  }
  if (typeof payload.action === "string") {
    return payload.action;
  }
  return "Event emitted";
}

function stageName(event: WorkflowEvent): string {
  const payload = event.payload ?? {};
  if (typeof payload.agent === "string") {
    return payload.agent;
  }
  if (typeof payload.action === "string") {
    return payload.action;
  }
  return "workflow";
}

export default function TimelineEvent({ event }: Props) {
  return (
    <article className="timeline-event">
      <div className="timeline-marker" />
      <div className="timeline-card">
        <header>
          <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
          <strong>{stageName(event)}</strong>
          <span className="event-badge">{event.type}</span>
        </header>
        <p className="event-summary">{summarizeEvent(event)}</p>
        <details>
          <summary>Details</summary>
          <JsonViewer value={event.payload} emptyText="No payload details" />
        </details>
      </div>
    </article>
  );
}
