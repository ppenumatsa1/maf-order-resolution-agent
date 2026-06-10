from __future__ import annotations

from app.maf.workflows.order_resolution import OrderResolutionWorkflow
from app.modules.order_resolution.models import WorkflowContext


class MafSdkSequentialWorkflow(OrderResolutionWorkflow):
    """Compatibility wrapper for the MAF SDK order resolution workflow."""


__all__ = ["MafSdkSequentialWorkflow", "WorkflowContext"]
