import { useEffect, useRef } from "react";

import TimelineEvent from "./TimelineEvent";
import { WorkflowEvent } from "../../types/workflow";

type Props = {
  events: WorkflowEvent[];
  onRefresh: () => Promise<void>;
  isLoading: boolean;
};

export default function WorkflowTimeline({
  events,
  onRefresh,
  isLoading,
}: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events]);

  return (
    <section className="panel panel-timeline">
      <header className="panel-head">
        <h2>Event Timeline</h2>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={isLoading}
          onClick={onRefresh}
        >
          Refresh
        </button>
      </header>

      {events.length === 0 ? (
        <p className="muted">No events available for this workflow.</p>
      ) : (
        <div className="timeline-list">
          {events.map((event) => (
            <TimelineEvent key={event.id} event={event} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </section>
  );
}
