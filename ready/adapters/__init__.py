"""
Abstract work item adapter interface.

Implement this to integrate with your project tracker.
Ships with GitHub Issues and Azure DevOps adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class WorkItemDraft:
    checkpoint_id: str
    title: str
    description: str
    severity: str
    evidence: list[str]
    fix_hint: str
    doc_link: str
    guideline: str
    guideline_section: str
    labels: list[str]


@dataclass
class WorkItemResult:
    id: str
    url: str
    status: str
    checkpoint_id: str


class WorkItemAdapter(ABC):
    """Interface for work item integrations."""

    @abstractmethod
    def create_draft(self, draft: WorkItemDraft) -> WorkItemResult:
        """Create a work item from a draft. Returns the created item."""
        ...

    @abstractmethod
    def get_status(self, item_id: str) -> Optional[WorkItemResult]:
        """Get the current status of a work item."""
        ...

    @abstractmethod
    def list_open(self, label: str | None = None) -> list[WorkItemResult]:
        """List open work items, optionally filtered by label."""
        ...

    @abstractmethod
    def close(self, item_id: str, reason: str = "Resolved by scan") -> bool:
        """Close a work item."""
        ...

    @abstractmethod
    def reopen(self, item_id: str, reason: str = "Regression detected by scan") -> bool:
        """Reopen a previously closed work item."""
        ...
