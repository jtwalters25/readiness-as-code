"""Base types for verification plugins.

A plugin implements a single `verification.method` value (e.g. "grep",
"file_exists") and returns a `VerificationResult`. The engine resolves
each checkpoint's method to a plugin via the registry.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ready.plugins.registry import PluginRegistry


class Confidence(Enum):
    VERIFIED = "verified"
    LIKELY = "likely"
    INCONCLUSIVE = "inconclusive"


@dataclass
class PluginContext:
    """Runtime context passed to every plugin's verify() call.

    Plugins that only look at the repo use `context.repo_root`. Plugins
    that compose other plugins (hybrid) use `context.registry` to
    dispatch nested verification methods. External plugins read
    `context.evidence_registry` for attestations.
    """

    repo_root: str
    evidence_registry: dict = field(default_factory=dict)
    registry: Optional["PluginRegistry"] = None


@dataclass
class VerificationResult:
    """Return value from a plugin's verify() call."""

    passed: bool
    evidence: list[str] = field(default_factory=list)
    confidence: Optional[Confidence] = None


class VerificationPlugin:
    """Base class for all verification plugins.

    Subclasses must set `method_name` and implement `verify()`. A single
    module may export multiple plugin classes (e.g. grep + grep_all).
    """

    method_name: str = ""

    def verify(
        self, checkpoint: dict, context: PluginContext
    ) -> VerificationResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement verify()"
        )
