"""
ready MCP server.

Exposes readiness scanning as MCP tools so any AI assistant can run scans,
inspect checkpoints, and aggregate results — without manual CLI usage.

Supported clients: Claude Desktop, Cursor, VS Code + Copilot, Continue,
any tool that implements the Model Context Protocol (MCP).

Usage:
    pip install "ready[mcp]"
    ready-mcp          # starts the stdio MCP server

Then configure your AI tool to launch this server. See mcp/README.md.
"""

import json
import os
import sys
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "MCP support requires the 'mcp' package.\n"
        "Install it with:  pip install \"ready[mcp]\"\n"
        "Or:               pip install mcp",
        file=sys.stderr,
    )
    sys.exit(1)

# Allow running from repo root or as installed package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ready.validators import run_scan, Status, Severity

mcp = FastMCP(
    "ready",
    instructions=(
        "You have access to ready — a tool for continuously evaluating "
        "whether a software service meets its engineering and operational review criteria. "
        "Use scan_repo to assess a codebase. Use list_checkpoints to see what's being checked. "
        "Use explain_checkpoint for detail on a specific check. Use aggregate_baselines to "
        "identify systemic gaps across multiple services."
    ),
)

READINESS_DIR = ".readiness"


def _find_repo_root(start_path: str) -> str:
    """Walk up from start_path to find .readiness/ or .git/"""
    current = os.path.abspath(start_path)
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while True:
        if os.path.isdir(os.path.join(current, READINESS_DIR)):
            return current
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start_path)
        current = parent


def _load_config(readiness_dir: str) -> tuple[str | None, list[str] | None]:
    """Load service_name and service_tags from config.json."""
    config_path = os.path.join(readiness_dir, "config.json")
    if os.path.isfile(config_path):
        with open(config_path) as f:
            config = json.load(f)
        return config.get("service_name"), config.get("service_tags")
    return None, None


@mcp.tool()
def scan_repo(repo_path: str = ".") -> str:
    """
    Run a full readiness scan on a repository.

    Evaluates all checkpoint definitions against the codebase and returns
    a structured Red/Yellow/Green report with evidence and fix hints.

    Args:
        repo_path: Path to the repository root (default: current directory).
                   The tool will walk up to find .readiness/ automatically.

    Returns:
        JSON string with scan summary and per-checkpoint results including
        status (pass/fail/exception/skip/needs_review), evidence, and fix hints.
    """
    repo_root = _find_repo_root(repo_path)
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    if not os.path.isdir(readiness_dir):
        return json.dumps({
            "error": f"No .readiness/ directory found at or above '{repo_path}'. "
                     "Run 'ready init' in the target repository first."
        })

    definitions_path = os.path.join(readiness_dir, "checkpoint-definitions.json")
    if not os.path.isfile(definitions_path):
        return json.dumps({
            "error": f"No checkpoint-definitions.json found in {readiness_dir}"
        })

    evidence_path = os.path.join(readiness_dir, "external-evidence.json")
    exceptions_path = os.path.join(readiness_dir, "exceptions.json")

    service_name, service_tags = _load_config(readiness_dir)

    try:
        result = run_scan(
            repo_root=repo_root,
            definitions_path=definitions_path,
            evidence_path=evidence_path if os.path.isfile(evidence_path) else None,
            exceptions_path=exceptions_path if os.path.isfile(exceptions_path) else None,
            service_tags=service_tags,
            service_name=service_name,
        )
    except Exception as e:
        return json.dumps({"error": f"Scan failed: {e}"})

    # Build a human-friendly summary alongside the raw data
    red_fails = [r for r in result.results if r.status in (Status.FAIL,) and r.severity == Severity.RED]
    yellow_fails = [r for r in result.results if r.status in (Status.FAIL,) and r.severity == Severity.YELLOW]

    summary_lines = [
        f"Readiness: {result.readiness_pct}% ({result.passing}/{result.total - result.skipped} passing)",
    ]
    if red_fails:
        summary_lines.append(f"RED (cannot ship): {len(red_fails)} failures")
    if yellow_fails:
        summary_lines.append(f"YELLOW (fix before launch): {len(yellow_fails)} failures")
    if result.passing:
        summary_lines.append(f"Passing: {result.passing} checks")
    if result.exceptions:
        summary_lines.append(f"Accepted exceptions: {result.exceptions}")
    if result.skipped:
        summary_lines.append(f"Skipped (not applicable): {result.skipped}")

    output = {
        "summary": " | ".join(summary_lines),
        "is_ready": result.is_ready,
        **result.to_dict(),
    }
    return json.dumps(output, indent=2)


@mcp.tool()
def list_checkpoints(repo_path: str = ".") -> str:
    """
    List all checkpoint definitions configured for a repository.

    Returns the full checkpoint catalog — what's being checked, why, and how.
    Useful for understanding what criteria a service is evaluated against before
    authoring new checkpoints or reviewing scan results.

    Args:
        repo_path: Path to the repository root (default: current directory).

    Returns:
        JSON string with all checkpoint definitions including id, title,
        severity, type, verification method, and fix hints.
    """
    repo_root = _find_repo_root(repo_path)
    definitions_path = os.path.join(repo_root, READINESS_DIR, "checkpoint-definitions.json")

    if not os.path.isfile(definitions_path):
        return json.dumps({
            "error": f"No checkpoint-definitions.json found. "
                     "Run 'ready init' to scaffold .readiness/ first."
        })

    try:
        with open(definitions_path) as f:
            definitions = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return json.dumps({"error": f"Could not read checkpoint definitions: {e}"})

    checkpoints = definitions.get("checkpoints", [])
    return json.dumps({
        "count": len(checkpoints),
        "checkpoints": [
            {
                "id": cp.get("id"),
                "title": cp.get("title"),
                "severity": cp.get("severity"),
                "type": cp.get("type"),
                "method": cp.get("verification", {}).get("method"),
                "applicable_tags": cp.get("applicable_tags", []),
                "fix_hint": cp.get("fix_hint", ""),
            }
            for cp in checkpoints
        ],
    }, indent=2)


@mcp.tool()
def explain_checkpoint(checkpoint_id: str, repo_path: str = ".") -> str:
    """
    Get full details about a specific checkpoint definition.

    Returns the complete checkpoint spec including its verification logic,
    fix guidance, guideline traceability, and confidence level. Use this
    when a scan flags a failure and you need to understand exactly what
    the check is looking for and how to fix it.

    Args:
        checkpoint_id: The checkpoint ID (e.g., "sec-001", "ops-007").
        repo_path: Path to the repository root (default: current directory).

    Returns:
        JSON string with the full checkpoint definition.
    """
    repo_root = _find_repo_root(repo_path)
    definitions_path = os.path.join(repo_root, READINESS_DIR, "checkpoint-definitions.json")

    if not os.path.isfile(definitions_path):
        return json.dumps({"error": "No checkpoint-definitions.json found."})

    try:
        with open(definitions_path) as f:
            definitions = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return json.dumps({"error": f"Could not read checkpoint definitions: {e}"})

    for cp in definitions.get("checkpoints", []):
        if cp.get("id") == checkpoint_id:
            return json.dumps(cp, indent=2)

    return json.dumps({
        "error": f"Checkpoint '{checkpoint_id}' not found.",
        "available_ids": [cp.get("id") for cp in definitions.get("checkpoints", [])],
    })


@mcp.tool()
def aggregate_baselines(baseline_paths: list[str]) -> str:
    """
    Aggregate baseline scan results across multiple repositories to identify systemic gaps.

    Takes a list of paths to review-baseline.json files (generated by 'ready scan --baseline')
    and produces a cross-repo heatmap showing which checkpoints are failing most widely.
    Use this to distinguish service-level issues from organization-level patterns.

    Args:
        baseline_paths: List of file paths to review-baseline.json files.

    Returns:
        JSON string with a heatmap of checkpoint failure rates across all services,
        sorted by prevalence (most widespread failures first).
    """
    if not baseline_paths:
        return json.dumps({"error": "Provide at least one baseline file path."})

    loaded = []
    errors = []
    for path in baseline_paths:
        if not os.path.isfile(path):
            errors.append(f"Not found: {path}")
            continue
        try:
            with open(path) as f:
                loaded.append(json.load(f))
        except (json.JSONDecodeError, IOError) as e:
            errors.append(f"Could not read {path}: {e}")

    if not loaded:
        return json.dumps({"error": "No valid baseline files found.", "details": errors})

    checkpoint_failures: dict[str, list[str]] = {}
    for baseline in loaded:
        service = baseline.get("service_name", "unknown")
        for r in baseline.get("results", []):
            if r.get("status") in ("fail", "expired_exception"):
                cp_id = r.get("checkpoint_id", "")
                title = r.get("title", cp_id)
                key = f"{cp_id}: {title}"
                checkpoint_failures.setdefault(key, []).append(service)

    total = len(loaded)
    heatmap = sorted(
        [
            {
                "checkpoint": k,
                "failing_count": len(v),
                "failing_pct": round(len(v) / total * 100),
                "services": v,
            }
            for k, v in checkpoint_failures.items()
        ],
        key=lambda x: x["failing_count"],
        reverse=True,
    )

    systemic = [h for h in heatmap if h["failing_pct"] > 50]

    result: dict = {
        "services_analyzed": total,
        "total_gap_types": len(heatmap),
        "systemic_gaps": len(systemic),
        "heatmap": heatmap,
    }
    if errors:
        result["load_errors"] = errors

    return json.dumps(result, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
