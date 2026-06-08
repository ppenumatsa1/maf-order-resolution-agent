import { useCallback, useEffect, useMemo, useState } from "react";

import AppShell from "./components/studio/AppShell";
import HumanApprovalPanel from "./components/studio/HumanApprovalPanel";
import LatestOutputPanel from "./components/studio/LatestOutputPanel";
import RunMetadataPanel from "./components/studio/RunMetadataPanel";
import WorkflowHistorySidebar from "./components/studio/WorkflowHistorySidebar";
import WorkflowRunComposer from "./components/studio/WorkflowRunComposer";
import WorkflowTimeline from "./components/studio/WorkflowTimeline";
import {
  PendingApproval,
  WorkflowEvent,
  WorkflowRunDetails,
  WorkflowRunListItem,
  WorkflowRunListResponse,
  WorkflowStatus,
} from "./types/workflow";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const DEFAULT_MESSAGE =
  "Order ORD-1009 is delayed by 5 days. I need compensation.";

export default function App() {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRunListItem[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(10);
  const [totalRuns, setTotalRuns] = useState(0);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [selectedWorkflowDetails, setSelectedWorkflowDetails] =
    useState<WorkflowRunDetails | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>(
    [],
  );
  const [latestOutput, setLatestOutput] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [statusFilter, setStatusFilter] = useState<"all" | WorkflowStatus>(
    "all",
  );
  const [searchTerm, setSearchTerm] = useState("");
  const [isStartingWorkflow, setIsStartingWorkflow] = useState(false);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [isDetailsLoading, setIsDetailsLoading] = useState(false);

  const loadWorkflowHistory = useCallback(
    async (page: number) => {
      setIsHistoryLoading(true);
      setHistoryError(null);
      try {
        const params = new URLSearchParams({
          page: String(page),
          pageSize: String(pageSize),
        });
        if (statusFilter !== "all") {
          params.set("status", statusFilter);
        }
        const response = await fetch(
          `${API_BASE}/api/workflows?${params.toString()}`,
        );
        if (!response.ok) {
          throw new Error(
            `Unable to fetch workflow history (${response.status})`,
          );
        }

        const data = (await response.json()) as WorkflowRunListResponse;
        setWorkflowRuns(data.items);
        setTotalRuns(data.total);

        if (!selectedThreadId && data.items.length > 0) {
          setSelectedThreadId(data.items[0].thread_id);
        }
      } catch (error) {
        setHistoryError(
          error instanceof Error ? error.message : "Unexpected history error",
        );
      } finally {
        setIsHistoryLoading(false);
      }
    },
    [pageSize, selectedThreadId, statusFilter],
  );

  const loadWorkflowDetails = useCallback(async (threadId: string) => {
    setIsDetailsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/workflows/${threadId}`);
      if (!response.ok) {
        throw new Error(
          `Unable to fetch workflow details (${response.status})`,
        );
      }
      const details = (await response.json()) as WorkflowRunDetails;
      setSelectedWorkflowDetails(details);
      setEvents(details.events ?? []);
      setPendingApprovals(details.pending_approvals ?? []);
      setLatestOutput(details.latest_output ?? null);
    } finally {
      setIsDetailsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorkflowHistory(currentPage);
  }, [currentPage, loadWorkflowHistory]);

  useEffect(() => {
    if (!selectedThreadId) {
      return;
    }
    void loadWorkflowDetails(selectedThreadId);
  }, [selectedThreadId, loadWorkflowDetails]);

  useEffect(() => {
    if (!selectedThreadId || !selectedWorkflowDetails) {
      return;
    }
    if (
      !["running", "waiting_approval"].includes(selectedWorkflowDetails.status)
    ) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadWorkflowDetails(selectedThreadId);
    }, 2500);

    return () => {
      window.clearInterval(timer);
    };
  }, [selectedThreadId, selectedWorkflowDetails, loadWorkflowDetails]);

  const filteredRuns = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    if (!query) {
      return workflowRuns;
    }
    return workflowRuns.filter((run) => {
      return (
        run.thread_id.toLowerCase().includes(query) ||
        run.input_summary.toLowerCase().includes(query)
      );
    });
  }, [workflowRuns, searchTerm]);

  const refreshAll = useCallback(async () => {
    await loadWorkflowHistory(currentPage);
    if (selectedThreadId) {
      await loadWorkflowDetails(selectedThreadId);
    }
  }, [currentPage, loadWorkflowDetails, loadWorkflowHistory, selectedThreadId]);

  const startWorkflow = useCallback(async () => {
    if (!message.trim()) {
      return;
    }

    setIsStartingWorkflow(true);
    try {
      const response = await fetch(`${API_BASE}/api/chat/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (!response.ok) {
        throw new Error(`Unable to start workflow (${response.status})`);
      }

      const payload = (await response.json()) as { thread_id: string };
      setCurrentPage(1);
      setSelectedThreadId(payload.thread_id);
      await loadWorkflowHistory(1);
      await loadWorkflowDetails(payload.thread_id);
    } finally {
      setIsStartingWorkflow(false);
    }
  }, [loadWorkflowDetails, loadWorkflowHistory, message]);

  const submitHitlDecision = useCallback(
    async (
      approval: PendingApproval,
      decision: "approve" | "reject",
      comment: string,
    ) => {
      setIsActionLoading(true);
      try {
        await fetch(`${API_BASE}/api/hitl/respond`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            checkpoint_id: approval.checkpoint_id,
            decision,
            reviewer: "demo-user",
            comments: comment,
          }),
        });

        if (selectedThreadId) {
          await loadWorkflowDetails(selectedThreadId);
        }
        await loadWorkflowHistory(currentPage);
      } finally {
        setIsActionLoading(false);
      }
    },
    [currentPage, loadWorkflowDetails, loadWorkflowHistory, selectedThreadId],
  );

  const selectWorkflow = (threadId: string) => {
    setSelectedThreadId(threadId);
  };

  const handleNewRun = () => {
    setSelectedThreadId(null);
    setSelectedWorkflowDetails(null);
    setEvents([]);
    setPendingApprovals([]);
    setLatestOutput(null);
    setMessage(DEFAULT_MESSAGE);
  };

  const totalPages = Math.max(1, Math.ceil(totalRuns / pageSize));

  return (
    <AppShell onNewRun={handleNewRun} onRefresh={() => void refreshAll()}>
      <WorkflowHistorySidebar
        runs={filteredRuns}
        selectedThreadId={selectedThreadId}
        statusFilter={statusFilter}
        searchTerm={searchTerm}
        page={currentPage}
        pageSize={pageSize}
        total={totalRuns}
        isLoading={isHistoryLoading}
        error={historyError}
        onSelect={selectWorkflow}
        onStatusFilterChange={(value) => {
          setStatusFilter(value);
          setCurrentPage(1);
        }}
        onSearchChange={setSearchTerm}
        onPreviousPage={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
        onNextPage={() =>
          setCurrentPage((prev) => Math.min(totalPages, prev + 1))
        }
      />

      <section className="center-column">
        <WorkflowRunComposer
          message={message}
          isSubmitting={isStartingWorkflow}
          onMessageChange={setMessage}
          onSubmit={startWorkflow}
          onClear={() => setMessage("")}
        />
        <WorkflowTimeline
          events={events}
          isLoading={isDetailsLoading}
          onRefresh={async () => {
            if (selectedThreadId) {
              await loadWorkflowDetails(selectedThreadId);
            }
          }}
        />
      </section>

      <section className="right-column">
        <HumanApprovalPanel
          approvals={pendingApprovals}
          isSubmitting={isActionLoading}
          onDecision={submitHitlDecision}
        />
        <LatestOutputPanel
          output={latestOutput}
          status={selectedWorkflowDetails?.status ?? null}
        />
        <RunMetadataPanel
          metadata={selectedWorkflowDetails?.metadata ?? null}
        />
      </section>
    </AppShell>
  );
}
