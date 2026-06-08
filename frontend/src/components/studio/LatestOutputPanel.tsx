import JsonViewer from "./JsonViewer";
import StatusBadge from "./StatusBadge";
import { WorkflowStatus } from "../../types/workflow";

type Props = {
  output: Record<string, unknown> | null;
  status: WorkflowStatus | null;
};

export default function LatestOutputPanel({ output, status }: Props) {
  const copyOutput = async () => {
    if (!output) {
      return;
    }
    await navigator.clipboard.writeText(JSON.stringify(output, null, 2));
  };

  return (
    <section className="panel panel-output">
      <header className="panel-head">
        <h2>Latest Output</h2>
        <div className="output-head-right">
          {status ? <StatusBadge status={status} /> : null}
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!output}
            onClick={copyOutput}
          >
            Copy
          </button>
        </div>
      </header>
      <JsonViewer value={output} emptyText="Waiting for workflow output..." />
    </section>
  );
}
