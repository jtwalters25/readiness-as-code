"""
Deterministic scan engine for ready.

Evaluates checkpoint definitions against a codebase and produces
structured results with pass/fail, evidence, and confidence levels.
"""

import glob
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


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


class Confidence(Enum):
    VERIFIED = "verified"
    LIKELY = "likely"
    INCONCLUSIVE = "inconclusive"


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


SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", ".env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "bin", "obj", "out", "target",
    ".idea", ".vscode", ".vs",
    "vendor", "third_party", "bower_components",
}


def _is_skipped(path: str) -> bool:
    """Return True if any path component is in SKIP_DIRS."""
    return any(part in SKIP_DIRS for part in Path(path).parts)


def _resolve_glob(pattern: str, repo_root: str) -> list[str]:
    """Resolve a glob pattern against the repo, supporting brace expansion.
    Automatically excludes dependency and tooling directories."""
    # Handle brace expansion: {a,b,c} -> expand to multiple patterns
    if "{" in pattern and "}" in pattern:
        brace_match = re.search(r"\{([^}]+)\}", pattern)
        if brace_match:
            alternatives = brace_match.group(1).split(",")
            prefix = pattern[: brace_match.start()]
            suffix = pattern[brace_match.end() :]
            results = []
            for alt in alternatives:
                expanded = prefix + alt.strip() + suffix
                results.extend(_resolve_glob(expanded, repo_root))
            return results

    full_pattern = os.path.join(repo_root, pattern)
    matches = glob.glob(full_pattern, recursive=True)
    repo_root_abs = os.path.abspath(repo_root)
    return [
        m for m in matches
        if not _is_skipped(os.path.relpath(m, repo_root_abs))
    ]


def _verify_file_exists(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    pattern = verification.get("pattern", "")
    matches = _resolve_glob(pattern, repo_root)
    return len(matches) > 0, [os.path.relpath(m, repo_root) for m in matches]


def _verify_glob(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    pattern = verification.get("pattern", "")
    min_matches = verification.get("min_matches", 1)
    matches = _resolve_glob(pattern, repo_root)
    return len(matches) >= min_matches, [os.path.relpath(m, repo_root) for m in matches]


def _resolve_evidence_paths(verification: dict, repo_root: str, default: str = "**/*") -> list[str]:
    """Resolve file paths from evidence_paths (string or list) or target (string).

    evidence_paths takes precedence over target. When evidence_paths is a list,
    each element is resolved as a separate glob — users never need brace syntax.
    """
    evidence_paths = verification.get("evidence_paths")
    if evidence_paths is not None:
        if isinstance(evidence_paths, list):
            result: list[str] = []
            for ep in evidence_paths:
                result.extend(_resolve_glob(str(ep), repo_root))
            return result
        return _resolve_glob(str(evidence_paths), repo_root)
    target = verification.get("target", default)
    return _resolve_glob(target, repo_root)


def _grep_files(pattern: str, target: str, repo_root: str) -> list[str]:
    """Shared helper: grep a pattern across target files, return rel-path:line evidence."""
    target_files = _resolve_glob(target, repo_root)
    return _grep_file_list(pattern, target_files, repo_root)


def _grep_file_list(pattern: str, target_files: list[str], repo_root: str) -> list[str]:
    """Grep a pattern across a pre-resolved list of files."""
    evidence = []
    for filepath in target_files:
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        evidence.append(f"{os.path.relpath(filepath, repo_root)}:{line_num}")
        except (IOError, OSError):
            continue
    return evidence


def _verify_grep(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    pattern = verification.get("pattern", "")
    min_matches = verification.get("min_matches", 1)
    pass_condition = verification.get("pass_condition", "present")

    target_files = _resolve_evidence_paths(verification, repo_root)
    evidence = _grep_file_list(pattern, target_files, repo_root)

    # pass_condition: "absent" — pattern must NOT be found (negative check)
    if pass_condition == "absent":
        return len(evidence) == 0, evidence

    # Legacy: min_matches=0 was used for secrets detection
    if min_matches == 0:
        return len(evidence) == 0, evidence

    return len(evidence) >= min_matches, evidence


def _verify_grep_all(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    """All patterns in `patterns` must be found — used for SDL gate checks."""
    patterns = verification.get("patterns", [])
    target_files = _resolve_evidence_paths(verification, repo_root)
    all_evidence = []

    for pattern in patterns:
        hits = _grep_file_list(pattern, target_files, repo_root)
        if not hits:
            return False, [f"Pattern not found: {pattern}"]
        all_evidence.extend(hits)

    return True, all_evidence


def _verify_glob_all(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    """All patterns in `patterns` must match at least one file."""
    patterns = verification.get("patterns", [])
    all_evidence = []

    for pattern in patterns:
        matches = _resolve_glob(pattern, repo_root)
        if not matches:
            return False, [f"No files found matching: {pattern}"]
        all_evidence.extend(os.path.relpath(m, repo_root) for m in matches)

    return True, all_evidence


def _verify_grep_count(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    return _verify_grep(verification, repo_root)


def _verify_file_count(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    return _verify_glob(verification, repo_root)


def _verify_json_path(verification: dict, repo_root: str) -> tuple[bool, list[str]]:
    target = verification.get("target", "")
    json_path_expr = verification.get("json_path", "")
    expected = verification.get("expected_value")

    target_path = os.path.join(repo_root, target)
    if not os.path.isfile(target_path):
        return False, [f"File not found: {target}"]

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Simple dot-path navigation (no full JSONPath library needed)
        keys = json_path_expr.strip("$.").split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                current = current[int(key)]
            else:
                return False, [f"Path {json_path_expr} not found in {target}"]

        if expected is not None:
            return current == expected, [f"{target}: {json_path_expr} = {current}"]
        else:
            return current is not None, [f"{target}: {json_path_expr} = {current}"]

    except (json.JSONDecodeError, IOError) as e:
        return False, [f"Error reading {target}: {e}"]


def _verify_external(
    verification: dict, evidence_registry: dict
) -> tuple[bool, list[str]]:
    key = verification.get("attestation_key", "")
    attestations = evidence_registry.get("attestations", [])

    for att in attestations:
        if att.get("checkpoint_id") == key or att.get("attestation_key") == key:
            # Check expiry
            expires = att.get("expires")
            if expires:
                try:
                    exp_date = datetime.strptime(expires, "%Y-%m-%d").date()
                    if exp_date < date.today():
                        return False, [
                            f"Attestation by {att.get('attested_by')} expired on {expires}"
                        ]
                except ValueError:
                    pass
            return True, [
                f"Attested by {att.get('attested_by')} on {att.get('attested_date')}: {att.get('evidence_link', 'no link')}"
            ]

    return False, [f"No attestation found for '{key}' in external-evidence.json"]


VERIFICATION_METHODS = {
    "file_exists": _verify_file_exists,
    "glob": _verify_glob,
    "glob_all": _verify_glob_all,
    "grep": _verify_grep,
    "grep_all": _verify_grep_all,
    "grep_count": _verify_grep_count,
    "file_count": _verify_file_count,
    "json_path": _verify_json_path,
}


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
    """Evaluate a single checkpoint and return a result."""
    cp_id = checkpoint["id"]
    title = checkpoint.get("title", cp_id)
    severity = Severity(checkpoint.get("severity", "yellow"))
    check_type = CheckType(checkpoint.get("type", "code"))
    verification = checkpoint.get("verification", {})
    confidence = Confidence(verification.get("confidence", "verified"))

    # Check applicability
    # - applicable_tags = [] → checkpoint applies to all services
    # - applicable_tags = ["web-api"] → only applies if service has that tag
    # - service_tags = None → tags not configured, run all checks
    # - service_tags = [] → tags declared as empty, skip service-specific checks
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

    # Check exceptions
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

    # Evaluate based on type
    method = verification.get("method", "")

    if check_type == CheckType.CODE:
        verifier = VERIFICATION_METHODS.get(method)
        if not verifier:
            return CheckResult(
                checkpoint_id=cp_id,
                title=title,
                status=Status.WARN,
                severity=severity,
                check_type=check_type,
                message=f"Unknown verification method: {method}",
            )
        passed, evidence = verifier(verification, repo_root)

    elif check_type == CheckType.EXTERNAL:
        passed, evidence = _verify_external(verification, evidence_registry)

    elif check_type == CheckType.HYBRID:
        code_ver = verification.get("code_verification", {})
        code_method = code_ver.get("method", "")
        code_verifier = VERIFICATION_METHODS.get(code_method)

        # Inherit confidence from nested code_verification when the outer verification
        # block does not specify its own confidence. Hybrid checkpoints typically carry
        # confidence on the code check (e.g. "likely" for pattern-based greps), not on
        # the outer wrapper — the scanner must recurse into the nested block to pick it up.
        if "confidence" not in verification and "confidence" in code_ver:
            confidence = Confidence(code_ver.get("confidence", "verified"))

        code_passed, code_evidence = (
            code_verifier(code_ver, repo_root)
            if code_verifier
            else (False, [f"Unknown code verification method: '{code_method or '(none)'}'. "
                          "Hybrid checkpoints require a 'code_verification' block with a "
                          "valid method (grep, glob, file_exists, etc.)."])
        )
        ext_passed, ext_evidence = _verify_external(verification, evidence_registry)

        passed = code_passed and ext_passed
        evidence = [f"[code] {e}" for e in code_evidence] + [
            f"[external] {e}" for e in ext_evidence
        ]
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
    exceptions = sum(1 for r in results if r.status == Status.EXCEPTION)
    skipped = sum(1 for r in results if r.status == Status.SKIP)

    evaluated = len(results) - skipped
    readiness_pct = round((passing / evaluated * 100) if evaluated > 0 else 0, 1)

    return ScanResult(
        service_name=service_name,
        scan_time=datetime.now(tz=__import__('datetime').timezone.utc).isoformat(),
        total=len(results),
        passing=passing,
        failing_red=failing_red,
        failing_yellow=failing_yellow,
        exceptions=exceptions,
        skipped=skipped,
        readiness_pct=readiness_pct,
        results=results,
    )
