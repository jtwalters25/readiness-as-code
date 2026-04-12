"""Scan engine — orchestrates checkpoint evaluation via the plugin registry.

This module owns the scan lifecycle:
- load definitions / evidence / exceptions
- apply tag filtering and exception handling
- dispatch each checkpoint to the right plugin
- aggregate results into a `ScanResult`

Verification methods live in `ready/plugins/`. Adding a new method =
one new plugin file; this engine does not change.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from ready.plugins.base import Confidence, PluginContext, VerificationPlugin
from ready.plugins.registry import PluginRegistry, build_default_registry


class Severity(Enum):
    RED = "red"
    YELLOW = "yellow"


class CheckType(Enum):
    CODE = "code"
    EXTERNAL = "external"
    HYBRID = "hybrid"


class Status(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"
    EXCEPTION = "exception"
    EXPIRED_EXCEPTION = "expired_exception"
    NEEDS_REVIEW = "needs_review"


@dataclass
class CheckResult:
    checkpoint_id: str
    title: str
    status: Status
    severity: Severity
    check_type: CheckType
    confidence: Confidence = Confidence.VERIFIED
    evidence: list[str] = field(default_factory=list)
    message: str = ""
    fix_hint: str = ""
    doc_link: str = ""
    guideline: str = ""
    guideline_section: str = ""

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "title": self.title,
            "status": self.status.value,
            "severity": self.severity.value,
            "type": self.check_type.value,
            "confidence": self.confidence.value,
            "evidence": self.evidence,
            "message": self.message,
            "fix_hint": self.fix_hint,
            "doc_link": self.doc_link,
            "guideline": self.guideline,
            "guideline_section": self.guideline_section,
        }


@dataclass
class ScanResult:
    service_name: str
    scan_time: str
    total: int
    passing: int
    failing_red: int
    failing_yellow: int
    exceptions: int
    skipped: int
    readiness_pct: float
    results: list[CheckResult]

    def to_dict(self) -> dict:
        return {
            "service_name": self.service_name,
            "scan_time": self.scan_time,
            "summary": {
                "total": self.total,
                "passing": self.passing,
                "failing_red": self.failing_red,
                "failing_yellow": self.failing_yellow,
                "exceptions": self.exceptions,
                "skipped": self.skipped,
                "readiness_pct": self.readiness_pct,
            },
            "results": [r.to_dict() for r in self.results],
        }

    @property
    def is_ready(self) -> bool:
        return self.failing_red == 0


# Module-level registry, built once on first access
_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """Return the default plugin registry, building it on first call."""
    global _registry
    if _registry is None:
        _registry = build_default_registry()
    return _registry


def _check_exception(
    checkpoint_id: str, exceptions_data: dict
) -> Optional[dict]:
    for exc in exceptions_data.get("exceptions", []):
        if exc.get("checkpoint_id") == checkpoint_id:
            return exc
    return None


def evaluate_checkpoint(
    checkpoint: dict,
    repo_root: str,
    evidence_registry: dict,
    exceptions_data: dict,
    service_tags: list[str] | None = None,
) -> CheckResult:
    """Evaluate a single checkpoint and return a `CheckResult`.

    Tag filtering, exception handling, and confidence demotion are
    owned by the engine; the actual verification is delegated to a
    plugin selected from the default registry.
    """
    cp_id = checkpoint["id"]
    title = checkpoint.get("title", cp_id)
    severity = Severity(checkpoint.get("severity", "yellow"))
    check_type = CheckType(checkpoint.get("type", "code"))
    verification = checkpoint.get("verification", {})
    confidence = Confidence(verification.get("confidence", "verified"))

    applicable_tags = checkpoint.get("applicable_tags", [])
    if applicable_tags and service_tags is not None:
        if not any(tag in service_tags for tag in applicable_tags):
            return CheckResult(
                checkpoint_id=cp_id,
                title=title,
                status=Status.SKIP,
                severity=severity,
                check_type=check_type,
                message="Not applicable to this service's tags",
            )

    exception = _check_exception(cp_id, exceptions_data)
    if exception:
        expires = exception.get("expires", "")
        try:
            exp_date = datetime.strptime(expires, "%Y-%m-%d").date()
            if exp_date >= date.today():
                return CheckResult(
                    checkpoint_id=cp_id,
                    title=title,
                    status=Status.EXCEPTION,
                    severity=severity,
                    check_type=check_type,
                    message=f"Accepted risk: {exception.get('justification', '')} (expires {expires})",
                    evidence=[
                        f"Exception by {exception.get('accepted_by')} — ref: {exception.get('decision_reference', 'none')}"
                    ],
                )
            else:
                return CheckResult(
                    checkpoint_id=cp_id,
                    title=title,
                    status=Status.EXPIRED_EXCEPTION,
                    severity=severity,
                    check_type=check_type,
                    message=f"Exception expired on {expires}. Re-evaluate: {exception.get('justification', '')}",
                    fix_hint=checkpoint.get("fix_hint", ""),
                    doc_link=checkpoint.get("doc_link", ""),
                )
        except ValueError:
            pass

    registry = get_registry()
    context = PluginContext(
        repo_root=repo_root,
        evidence_registry=evidence_registry,
        registry=registry,
    )

    method = verification.get("method", "")

    if check_type == CheckType.CODE:
        plugin: Optional[VerificationPlugin] = registry.get(method)
        if plugin is None:
            return CheckResult(
                checkpoint_id=cp_id,
                title=title,
                status=Status.WARN,
                severity=severity,
                check_type=check_type,
                message=f"Unknown verification method: {method}",
            )
        result = plugin.verify(checkpoint, context)
        passed = result.passed
        evidence = result.evidence

    elif check_type == CheckType.EXTERNAL:
        external_plugin = registry.get("external_attestation")
        if external_plugin is None:
            return CheckResult(
                checkpoint_id=cp_id,
                title=title,
                status=Status.WARN,
                severity=severity,
                check_type=check_type,
                message="External plugin not registered",
            )
        result = external_plugin.verify(checkpoint, context)
        passed = result.passed
        evidence = result.evidence

    elif check_type == CheckType.HYBRID:
        hybrid_plugin = registry.get("hybrid")
        if hybrid_plugin is None:
            return CheckResult(
                checkpoint_id=cp_id,
                title=title,
                status=Status.WARN,
                severity=severity,
                check_type=check_type,
                message="Hybrid plugin not registered",
            )
        result = hybrid_plugin.verify(checkpoint, context)
        passed = result.passed
        evidence = result.evidence
        if result.confidence is not None:
            confidence = result.confidence

    else:
        return CheckResult(
            checkpoint_id=cp_id,
            title=title,
            status=Status.WARN,
            severity=severity,
            check_type=check_type,
            message=f"Unknown check type: {check_type}",
        )

    if passed:
        status = Status.PASS
        message = "Passing"
    elif confidence == Confidence.INCONCLUSIVE:
        status = Status.NEEDS_REVIEW
        message = "Inconclusive — needs human review"
    elif confidence == Confidence.LIKELY:
        status = Status.FAIL
        message = "Likely failing (pattern-based — verify manually if unexpected)"
    else:
        status = Status.FAIL
        message = "Failing"

    return CheckResult(
        checkpoint_id=cp_id,
        title=title,
        status=status,
        severity=severity,
        check_type=check_type,
        confidence=confidence,
        evidence=evidence,
        message=message,
        fix_hint=checkpoint.get("fix_hint", ""),
        doc_link=checkpoint.get("doc_link", ""),
        guideline=checkpoint.get("guideline", ""),
        guideline_section=checkpoint.get("guideline_section", ""),
    )


def run_scan(
    repo_root: str,
    definitions_path: str,
    evidence_path: str | None = None,
    exceptions_path: str | None = None,
    service_tags: list[str] | None = None,
    service_name: str | None = None,
    on_progress: "callable | None" = None,
) -> ScanResult:
    """Run a full scan against a repo and return structured results."""

    with open(definitions_path, "r", encoding="utf-8") as f:
        definitions = json.load(f)

    evidence_registry = {"version": "1.0", "attestations": []}
    if evidence_path and os.path.isfile(evidence_path):
        with open(evidence_path, "r", encoding="utf-8") as f:
            evidence_registry = json.load(f)

    exceptions_data = {"version": "1.0", "exceptions": []}
    if exceptions_path and os.path.isfile(exceptions_path):
        with open(exceptions_path, "r", encoding="utf-8") as f:
            exceptions_data = json.load(f)

    if not service_name:
        service_name = os.path.basename(os.path.abspath(repo_root))

    results: list[CheckResult] = []
    checkpoints = definitions.get("checkpoints", [])
    total = len(checkpoints)
    for i, checkpoint in enumerate(checkpoints, 1):
        if on_progress:
            on_progress(i, total, checkpoint.get("title", checkpoint.get("id", "")))
        result = evaluate_checkpoint(
            checkpoint, repo_root, evidence_registry, exceptions_data, service_tags
        )
        results.append(result)

    passing = sum(1 for r in results if r.status == Status.PASS)
    failing_red = sum(
        1
        for r in results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.RED
    )
    failing_yellow = sum(
        1
        for r in results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.YELLOW
    )
    exceptions_count = sum(1 for r in results if r.status == Status.EXCEPTION)
    skipped = sum(1 for r in results if r.status == Status.SKIP)

    evaluated = len(results) - skipped
    readiness_pct = round(
        (passing / evaluated * 100) if evaluated > 0 else 0, 1
    )

    return ScanResult(
        service_name=service_name,
        scan_time=datetime.now(tz=timezone.utc).isoformat(),
        total=len(results),
        passing=passing,
        failing_red=failing_red,
        failing_yellow=failing_yellow,
        exceptions=exceptions_count,
        skipped=skipped,
        readiness_pct=readiness_pct,
        results=results,
    )
