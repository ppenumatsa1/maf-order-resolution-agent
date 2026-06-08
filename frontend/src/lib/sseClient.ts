export type WorkflowEvent = {
  id: string;
  type: string;
  thread_id: string;
  timestamp: string;
  payload: Record<string, unknown>;
};

export function openThreadStream(
  apiBase: string,
  threadId: string,
  onEvent: (event: WorkflowEvent) => void,
): EventSource {
  const source = new EventSource(`${apiBase}/api/chat/stream/${threadId}`);
  source.onmessage = (msg) => {
    const parsed = JSON.parse(msg.data) as WorkflowEvent;
    onEvent(parsed);
  };
  return source;
}
