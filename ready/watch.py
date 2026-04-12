"""Watch mode — continuous local dev feedback via polling.

`ready watch` runs an initial scan, then polls for file changes and
re-scans only when something relevant changed. Pure stdlib — no
watchdog, no external dependencies.
"""

import json
import os
import sys
import time
from pathlib import Path

from ready.engine import (
    ScanResult,
    Severity,
    Status,
    evaluate_checkpoint,
    get_registry,
    run_scan,
)
from ready.plugins.utils import SKIP_DIRS, resolve_glob

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _resolve_watched_files(checkpoints: list[dict], repo_root: str) -> set[str]:
    """Expand verification patterns from all checkpoints into concrete file paths."""
    watched: set[str] = set()
    for cp in checkpoints:
        verification = cp.get("verification", {})
        method = verification.get("method", "")
        cp_type = cp.get("type", "code")

        if cp_type == "external":
            continue

        if cp_type == "hybrid":
            verification = verification.get("code_verification", verification)
            method = verification.get("method", "")

        if method in ("grep", "grep_all", "grep_count"):
            evidence_paths = verification.get("evidence_paths")
            if evidence_paths is not None:
                if isinstance(evidence_paths, list):
                    for ep in evidence_paths:
                        watched.update(resolve_glob(str(ep), repo_root))
                else:
                    watched.update(resolve_glob(str(evidence_paths), repo_root))
            else:
                target = verification.get("target", "**/*")
                watched.update(resolve_glob(target, repo_root))
        elif method in ("file_exists", "glob", "glob_all", "file_count"):
            pattern = verification.get("pattern", "")
            if pattern:
                watched.update(resolve_glob(pattern, repo_root))
            for p in verification.get("patterns", []):
                watched.update(resolve_glob(p, repo_root))
        elif method == "json_path":
            target = verification.get("target", "")
            if target:
                full = os.path.join(repo_root, target)
                if os.path.isfile(full):
                    watched.add(full)

    return {f for f in watched if os.path.isfile(f)}


def _get_mtimes(files: set[str]) -> dict[str, float]:
    """Snapshot mtime for each file. Missing files are silently skipped."""
    mtimes: dict[str, float] = {}
    for f in files:
        try:
            mtimes[f] = os.stat(f).st_mtime
        except OSError:
            pass
    return mtimes


def _score_line(result: ScanResult) -> str:
    """Build the one-line score string (no ANSI newline)."""
    pct = result.readiness_pct
    pct_color = GREEN if result.is_ready else RED
    red_fails = sum(
        1 for r in result.results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.RED
    )
    yellow_fails = sum(
        1 for r in result.results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.YELLOW
    )
    if result.is_ready and not yellow_fails:
        status = f"{GREEN}✓{RESET}"
    else:
        parts = []
        if red_fails:
            parts.append(f"{RED}{red_fails} blocking{RESET}")
        if yellow_fails:
            parts.append(f"{YELLOW}{yellow_fails} warning{'s' if yellow_fails != 1 else ''}{RESET}")
        status = " · ".join(parts) if parts else ""
    return f"{BOLD}ready? — {result.service_name}{RESET}   {pct_color}{pct:.0f}%{RESET}   {status}"


def _diff_results(prev: ScanResult, curr: ScanResult) -> list[str]:
    """Return human-readable lines for checks that flipped status."""
    prev_map = {r.checkpoint_id: r for r in prev.results}
    lines: list[str] = []
    for r in curr.results:
        old = prev_map.get(r.checkpoint_id)
        if old is None:
            continue
        if old.status != r.status:
            if r.status == Status.PASS:
                lines.append(f"  {GREEN}↑{RESET} {r.title}  {DIM}{old.status.value} → pass{RESET}")
            elif r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION):
                lines.append(f"  {RED}↓{RESET} {r.title}  {DIM}{old.status.value} → {r.status.value}{RESET}")
            else:
                lines.append(f"  {CYAN}~{RESET} {r.title}  {DIM}{old.status.value} → {r.status.value}{RESET}")
    return lines


def cmd_watch(args) -> int:
    """Run continuous watch mode."""
    from ready.ready import find_repo_root, _find_examples_dir, _detect_pack, _validate_definitions
    from ready.ready import READINESS_DIR, DEFINITIONS_FILE, EVIDENCE_FILE, EXCEPTIONS_FILE, PACKS

    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)
    interval = getattr(args, "interval", 2.0)
    clear = getattr(args, "clear", False)

    # Resolve definitions path (same logic as cmd_scan)
    if not os.path.isdir(readiness_dir):
        auto_pack = _detect_pack(repo_root)
        examples_dir = _find_examples_dir()
        if not examples_dir:
            print(f"{RED}✗ No {READINESS_DIR}/ found. Run 'ready init' first.{RESET}")
            return 1
        pack_dir_name = PACKS[auto_pack][0]
        definitions_path = os.path.join(examples_dir, pack_dir_name, "checkpoint-definitions.json")
        evidence_path = os.path.join(readiness_dir, EVIDENCE_FILE)
        exceptions_path = os.path.join(readiness_dir, EXCEPTIONS_FILE)
        service_name = os.path.basename(repo_root)
        service_tags = None
    else:
        definitions_path = os.path.join(readiness_dir, DEFINITIONS_FILE)
        evidence_path = os.path.join(readiness_dir, EVIDENCE_FILE)
        exceptions_path = os.path.join(readiness_dir, EXCEPTIONS_FILE)
        config_path = os.path.join(readiness_dir, "config.json")
        service_tags = None
        service_name = None
        if os.path.isfile(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
                service_tags = cfg.get("service_tags")
                service_name = cfg.get("service_name")

    if not os.path.isfile(definitions_path):
        print(f"{RED}✗ No checkpoint definitions found.{RESET}")
        return 1

    with open(definitions_path, "r", encoding="utf-8") as f:
        definitions = json.load(f)
    checkpoints = definitions.get("checkpoints", [])

    # Initial scan
    print(f"{DIM}Watching for changes (every {interval}s) — Ctrl+C to stop{RESET}")
    print()

    prev_result = run_scan(
        repo_root=repo_root,
        definitions_path=definitions_path,
        evidence_path=evidence_path,
        exceptions_path=exceptions_path,
        service_tags=service_tags,
        service_name=service_name,
    )
    print(_score_line(prev_result))
    print()

    watched = _resolve_watched_files(checkpoints, repo_root)
    mtimes = _get_mtimes(watched)
    scan_count = 1

    try:
        while True:
            time.sleep(interval)

            # Check for changes
            current_mtimes = _get_mtimes(watched)

            # Also re-resolve patterns periodically to catch new files
            new_watched = _resolve_watched_files(checkpoints, repo_root)
            new_files = new_watched - watched
            if new_files:
                watched = new_watched
                current_mtimes.update(_get_mtimes(new_files))

            changed = False
            for f, mtime in current_mtimes.items():
                if mtimes.get(f) != mtime:
                    changed = True
                    break
            if not changed and not new_files:
                continue

            # Something changed — re-scan
            if clear:
                print("\033[2J\033[H", end="", flush=True)

            result = run_scan(
                repo_root=repo_root,
                definitions_path=definitions_path,
                evidence_path=evidence_path,
                exceptions_path=exceptions_path,
                service_tags=service_tags,
                service_name=service_name,
            )
            scan_count += 1

            # Show what flipped
            flips = _diff_results(prev_result, result)
            if flips:
                for line in flips:
                    print(line)

            # Delta
            delta = result.readiness_pct - prev_result.readiness_pct
            delta_str = ""
            if abs(delta) >= 0.5:
                if delta > 0:
                    delta_str = f"   {GREEN}▲ +{delta:.0f}%{RESET}"
                else:
                    delta_str = f"   {RED}▼ {delta:.0f}%{RESET}"

            print(f"{_score_line(result)}{delta_str}")
            print()

            prev_result = result
            mtimes = current_mtimes

    except KeyboardInterrupt:
        print(f"\n{DIM}──────────────────────────────────{RESET}")
        print(f"{BOLD}Watch summary{RESET}")
        print(f"  Scans: {scan_count}")
        print(f"  Final: {_score_line(prev_result)}")
        print()
        return 0
