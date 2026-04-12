"""Backward-compatible facade for the scan engine.

The scan engine moved to `ready.engine` and verification methods moved
to `ready.plugins`. This module re-exports the public surface so
existing callers (`from ready.validators import run_scan, Status, ...`)
keep working unchanged.
"""

from ready.engine import (
    CheckResult,
    CheckType,
    ScanResult,
    Severity,
    Status,
    evaluate_checkpoint,
    get_registry,
    run_scan,
)
from ready.plugins.base import Confidence, PluginContext, VerificationPlugin, VerificationResult
from ready.plugins.utils import (
    SKIP_DIRS,
    grep_file_list,
    is_skipped,
    resolve_evidence_paths,
    resolve_glob,
)

# Legacy alias — some internal code imported the private name.
_is_skipped = is_skipped
_resolve_glob = resolve_glob
_resolve_evidence_paths = resolve_evidence_paths
_grep_file_list = grep_file_list

__all__ = [
    "CheckResult",
    "CheckType",
    "Confidence",
    "PluginContext",
    "ScanResult",
    "Severity",
    "Status",
    "VerificationPlugin",
    "VerificationResult",
    "SKIP_DIRS",
    "evaluate_checkpoint",
    "get_registry",
    "grep_file_list",
    "is_skipped",
    "resolve_evidence_paths",
    "resolve_glob",
    "run_scan",
]
