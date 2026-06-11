import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";

import AppShell from "./components/studio/AppShell";
import HumanApprovalPanel from "./components/studio/HumanApprovalPanel";
import LatestOutputPanel from "./components/studio/LatestOutputPanel";
import ManualTestPanel from "./components/studio/ManualTestPanel";
import RagEvidencePanel from "./components/studio/RagEvidencePanel";
import RunMetadataPanel from "./components/studio/RunMetadataPanel";
import WorkflowHistorySidebar from "./components/studio/WorkflowHistorySidebar";
import WorkflowRunComposer from "./components/studio/WorkflowRunComposer";
import { getApiBase } from "./config";
import WorkflowTimeline from "./components/studio/WorkflowTimeline";
import {
  PendingApproval,
  WorkflowEvent,
  WorkflowRunDetails,
  WorkflowRunListItem,
  WorkflowRunListResponse,
  WorkflowStatus,
} from "./types/workflow";

const API_BASE = getApiBase();
const DEFAULT_MESSAGE =
  "Order ORD-1009 is delayed by 5 days. I need compensation.";

export default function App() {
  const hasAutoSelectedInitialRun = useRef(false);
  const hasUserInteractedWithRunSelection = useRef(false);
  const selectedThreadIdRef = useRef<string | null>(null);
  const selectionVersionRef = useRef(0);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [activeHistoryThreadId, setActiveHistoryThreadId] = useState<string | null>(
    null,
  );
  const [isComposingNewRun, setIsComposingNewRun] = useState(false);
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRunListItem[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
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
          page_size: String(pageSize),
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
        if (typeof data.page_size === "number" && data.page_size > 0) {
          setPageSize(data.page_size);
        }

        if (
          !hasAutoSelectedInitialRun.current &&
          !hasUserInteractedWithRunSelection.current
        ) {
          hasAutoSelectedInitialRun.current = true;
          if (!selectedThreadIdRef.current && data.items.length > 0) {
            selectionVersionRef.current += 1;
            selectedThreadIdRef.current = data.items[0].thread_id;
            setActiveHistoryThreadId(data.items[0].thread_id);
            setSelectedThreadId(data.items[0].thread_id);
          }
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

  const clearSelectedRunPanels = useCallback(() => {
    setSelectedWorkflowDetails(null);
    setEvents([]);
    setPendingApprovals([]);
    setLatestOutput(null);
  }, []);

  const loadWorkflowDetails = useCallback(
    async (
      threadId: string,
      expectedSelectionVersion = selectionVersionRef.current,
    ) => {
      setIsDetailsLoading(true);
      try {
        const response = await fetch(`${API_BASE}/api/workflows/${threadId}`);
        if (!response.ok) {
          throw new Error(
            `Unable to fetch workflow details (${response.status})`,
          );
        }
        const details = (await response.json()) as WorkflowRunDetails;
        if (
          selectedThreadIdRef.current !== threadId ||
          selectionVersionRef.current !== expectedSelectionVersion
        ) {
          return;
        }
        setSelectedWorkflowDetails(details);
        setEvents(details.events ?? []);
        setPendingApprovals(details.pending_approvals ?? []);
        setLatestOutput(details.latest_output ?? null);
      } finally {
        if (selectionVersionRef.current === expectedSelectionVersion) {
          setIsDetailsLoading(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    void loadWorkflowHistory(currentPage);
  }, [currentPage, loadWorkflowHistory]);

  useEffect(() => {
    if (isComposingNewRun || !selectedThreadId) {
      return;
    }
    void loadWorkflowDetails(selectedThreadId, selectionVersionRef.current);
  }, [isComposingNewRun, selectedThreadId, loadWorkflowDetails]);

  useEffect(() => {
    if (isComposingNewRun || !selectedThreadId || !selectedWorkflowDetails) {
      return;
    }
    if (
      !["running", "waiting_approval"].includes(selectedWorkflowDetails.status)
    ) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadWorkflowDetails(selectedThreadId, selectionVersionRef.current);
    }, 2500);

    return () => {
      window.clearInterval(timer);
    };
  }, [
    isComposingNewRun,
    selectedThreadId,
    selectedWorkflowDetails,
    loadWorkflowDetails,
  ]);

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
    if (!isComposingNewRun && selectedThreadId) {
      await loadWorkflowDetails(selectedThreadId, selectionVersionRef.current);
    }
  }, [
    currentPage,
    isComposingNewRun,
    loadWorkflowDetails,
    loadWorkflowHistory,
    selectedThreadId,
  ]);

  const startWorkflow = useCallback(async () => {
    if (!message.trim()) {
      return;
    }

    hasUserInteractedWithRunSelection.current = true;
    const selectionVersion = selectionVersionRef.current + 1;
    selectionVersionRef.current = selectionVersion;
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
      if (selectionVersionRef.current !== selectionVersion) {
        return;
      }
      setCurrentPage(1);
      clearSelectedRunPanels();
      selectedThreadIdRef.current = payload.thread_id;
      setActiveHistoryThreadId(payload.thread_id);
      setIsComposingNewRun(false);
      setSelectedThreadId(payload.thread_id);
      await loadWorkflowHistory(1);
      await loadWorkflowDetails(payload.thread_id, selectionVersion);
    } finally {
      setIsStartingWorkflow(false);
    }
  }, [clearSelectedRunPanels, loadWorkflowDetails, loadWorkflowHistory, message]);

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
          await loadWorkflowDetails(selectedThreadId, selectionVersionRef.current);
        }
        await loadWorkflowHistory(currentPage);
      } finally {
        setIsActionLoading(false);
      }
    },
    [currentPage, loadWorkflowDetails, loadWorkflowHistory, selectedThreadId],
  );

  const selectWorkflow = (threadId: string) => {
    hasUserInteractedWithRunSelection.current = true;
    clearSelectedRunPanels();
    selectionVersionRef.current += 1;
    selectedThreadIdRef.current = threadId;
    setActiveHistoryThreadId(threadId);
    setIsComposingNewRun(false);
    setSelectedThreadId(threadId);
  };

  const openWorkflow = useCallback(
    async (threadId: string) => {
      hasUserInteractedWithRunSelection.current = true;
      clearSelectedRunPanels();
      const selectionVersion = selectionVersionRef.current + 1;
      selectionVersionRef.current = selectionVersion;
      selectedThreadIdRef.current = threadId;
      setActiveHistoryThreadId(threadId);
      setIsComposingNewRun(false);
      setSelectedThreadId(threadId);
      await loadWorkflowHistory(1);
      await loadWorkflowDetails(threadId, selectionVersion);
    },
    [clearSelectedRunPanels, loadWorkflowDetails, loadWorkflowHistory],
  );

  const handleNewRun = () => {
    hasUserInteractedWithRunSelection.current = true;
    selectionVersionRef.current += 1;
    selectedThreadIdRef.current = null;
    flushSync(() => {
      setActiveHistoryThreadId(null);
      setIsComposingNewRun(true);
      setSelectedThreadId(null);
      clearSelectedRunPanels();
      setMessage(DEFAULT_MESSAGE);
    });
  };

  const totalPages = Math.max(1, Math.ceil(totalRuns / pageSize));
  const visibleSelectedThreadId = isComposingNewRun ? null : selectedThreadId;
  const visibleActiveHistoryThreadId = isComposingNewRun
    ? null
    : activeHistoryThreadId;

  return (
    <AppShell onNewRun={handleNewRun} onRefresh={() => void refreshAll()}>
      <WorkflowHistorySidebar
        runs={filteredRuns}
        selectedThreadId={visibleActiveHistoryThreadId}
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
        <ManualTestPanel
          onLoadPrompt={setMessage}
          onOpenWorkflow={openWorkflow}
        />
        <WorkflowTimeline
          events={events}
          hasSelectedWorkflow={Boolean(visibleSelectedThreadId)}
          isLoading={isDetailsLoading}
          onRefresh={async () => {
            if (visibleSelectedThreadId) {
              await loadWorkflowDetails(
                visibleSelectedThreadId,
                selectionVersionRef.current,
              );
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
        <RagEvidencePanel details={selectedWorkflowDetails} events={events} />
        <RunMetadataPanel
          metadata={selectedWorkflowDetails?.metadata ?? null}
        />
      </section>
    </AppShell>
  );
}
