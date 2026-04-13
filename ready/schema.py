"""Canonical scan result schema and normalization utilities.

All tools that store, aggregate, or compare scan results should consume
the schema defined here.  ``normalize_legacy_scan`` is idempotent and
converts old-format dicts (pre-v0.8) so code written against the new
schema works transparently on historical data.

Canonical top-level fields
--------------------------
scan_id        str          UUID for this scan run
timestamp      str          ISO-8601 UTC timestamp (alias for legacy scan_time)
repo           str          Repository slug (from remote origin or directory name)
branch         str          Branch name at scan time
commit_sha     str          Short commit hash (empty if not in a git repo)
trigger        str          "ci" | "local" | "manual"
duration_ms    int          Total wall time for the scan
readiness_pct  float        0.0–100.0

totals         dict
  total        int          All evaluated + skipped checkpoints
  passing      int          Checkpoints with status == pass
  failing      int          failing_red + failing_yellow (combined)
  p0           int          Blocking (red) failures only

checkpoint_results  list[dict]   Lightweight per-checkpoint rows
  checkpoint_id     str
  status            str          pass | fail | warn | skip | …
  severity          str          red | yellow
  evidence_count    int
  duration_ms       int

Legacy fields (retained for backward compatibility)
---------------------------------------------------
service_name   str          Same as repo in most cases
scan_time      str          Same as timestamp
summary        dict         Old summary block; use totals for new code
results        list[dict]   Full checkpoint detail; use checkpoint_results for summaries
"""

from __future__ import annotations

import uuid


SCHEMA_VERSION = "1.0"


def normalize_legacy_scan(d: dict) -> dict:
    """Return a copy of *d* with all Phase-1 schema fields populated.

    Safe to call on both legacy dicts and already-normalized dicts —
    existing fields are never overwritten.
    """
    out = dict(d)
    summary = out.get("summary", {})

    # Identity
    if "scan_id" not in out:
        out["scan_id"] = str(uuid.uuid4())
    if "timestamp" not in out:
        out["timestamp"] = out.get("scan_time", "")
    if "repo" not in out:
        out["repo"] = out.get("service_name", "")
    if "branch" not in out:
        out["branch"] = ""
    if "commit_sha" not in out:
        out["commit_sha"] = ""
    if "trigger" not in out:
        out["trigger"] = "local"
    if "duration_ms" not in out:
        out["duration_ms"] = 0
    if "readiness_pct" not in out:
        out["readiness_pct"] = summary.get("readiness_pct", 0.0)

    # Normalized totals
    if "totals" not in out:
        out["totals"] = {
            "total": summary.get("total", 0),
            "passing": summary.get("passing", 0),
            "failing": summary.get("failing_red", 0) + summary.get("failing_yellow", 0),
            "p0": summary.get("failing_red", 0),
        }

    # Lightweight checkpoint summary
    if "checkpoint_results" not in out:
        out["checkpoint_results"] = _checkpoint_results_from_results(
            out.get("results", [])
        )

    return out


def _checkpoint_results_from_results(results: list[dict]) -> list[dict]:
    """Build the lightweight ``checkpoint_results`` array from a full results list."""
    return [
        {
            "checkpoint_id": r.get("checkpoint_id", ""),
            "status": r.get("status", ""),
            "severity": r.get("severity", ""),
            "evidence_count": r.get("evidence_count", len(r.get("evidence", []))),
            "duration_ms": r.get("duration_ms", 0),
        }
        for r in results
    ]
