from __future__ import annotations

from workflows.order_resolution.state import WorkflowContext
from workflows.order_resolution.workflow import OrderResolutionWorkflow


class MafSdkSequentialWorkflow(OrderResolutionWorkflow):
    """Compatibility wrapper for the MAF SDK order resolution workflow."""


__all__ = ["MafSdkSequentialWorkflow", "WorkflowContext"]
