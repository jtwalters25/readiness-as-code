#!/usr/bin/env python3
"""
readiness-as-code — Continuous review compliance as a folder in your repo.

Usage:
    ready scan                     Red/Yellow/Green scan
    ready scan --verbose           Full checkpoint detail
    ready scan --calibrate         Report-only (no exit code failure)
    ready scan --json              Machine-readable output
    ready scan --baseline FILE     Write baseline snapshot
    ready init                     Scaffold .readiness/ directory
    ready items --create           Propose + create work items
    ready items --verify           Cross-check work items vs code
    ready aggregate PATHS...       Cross-repo heatmap
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Allow running from repo root or as installed package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.validators import run_scan, Status, Severity


READINESS_DIR = ".readiness"
DEFINITIONS_FILE = "checkpoint-definitions.json"
EXCEPTIONS_FILE = "exceptions.json"
EVIDENCE_FILE = "external-evidence.json"
BASELINE_FILE = "review-baseline.json"

# ANSI colors
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def find_repo_root() -> str:
    """Walk up from cwd to find .readiness/ or .git/"""
    current = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(current, READINESS_DIR)):
            return current
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.getcwd()
        current = parent


def cmd_init(args):
    """Scaffold .readiness/ directory with starter definitions."""
    target = os.path.join(os.getcwd(), READINESS_DIR)

    if os.path.exists(target):
        print(f"{YELLOW}⚠ {READINESS_DIR}/ already exists. Skipping.{RESET}")
        return 0

    # Find starter pack
    script_dir = os.path.dirname(os.path.abspath(__file__))
    starter_dir = os.path.join(script_dir, "..", "examples", "starter-pack")

    if not os.path.isdir(starter_dir):
        # Try relative to package install
        starter_dir = os.path.join(
            os.path.dirname(__file__), "examples", "starter-pack"
        )

    os.makedirs(target, exist_ok=True)

    files_to_copy = [
        (DEFINITIONS_FILE, "checkpoint-definitions.json"),
        (EXCEPTIONS_FILE, "exceptions.json"),
        (EVIDENCE_FILE, "external-evidence.json"),
    ]

    for dest_name, src_name in files_to_copy:
        src = os.path.join(starter_dir, src_name)
        dest = os.path.join(target, dest_name)
        if os.path.isfile(src):
            shutil.copy2(src, dest)
            print(f"  {GREEN}✓{RESET} {READINESS_DIR}/{dest_name}")
        else:
            # Create empty defaults
            default = {"version": "1.0"}
            if "checkpoint" in dest_name:
                default["checkpoints"] = []
            elif "exception" in dest_name:
                default["exceptions"] = []
            elif "evidence" in dest_name:
                default["attestations"] = []
            with open(dest, "w") as f:
                json.dump(default, f, indent=2)
            print(f"  {YELLOW}○{RESET} {READINESS_DIR}/{dest_name} (empty default)")

    # Create config.json with service metadata
    config_path = os.path.join(target, "config.json")
    service_name = os.path.basename(os.path.abspath(os.getcwd()))
    config = {
        "service_name": service_name,
        "service_tags": [],
        "_available_tags": [
            "web-api",
            "web-service",
            "background-service",
            "cli-tool",
            "library",
            "infrastructure"
        ],
        "_note": "Set service_tags to enable service-specific checks. Checks with applicable_tags will be skipped unless your service_tags match. See _available_tags for common values."
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  {GREEN}✓{RESET} {READINESS_DIR}/config.json")

    print(f"\n{GREEN}✓ Initialized {READINESS_DIR}/{RESET}")
    print()
    print(f"  {BOLD}Next steps:{RESET}")
    print(f"  1. Edit {CYAN}{READINESS_DIR}/config.json{RESET} to set your service_tags")
    print(f"     (e.g. [\"web-api\"] for a REST service, [] for a library)")
    print(f"  2. Run {CYAN}ready scan{RESET} to see your readiness score")
    return 0


def cmd_scan(args):
    """Run readiness scan."""
    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    if not os.path.isdir(readiness_dir):
        print(f"{RED}✗ No {READINESS_DIR}/ found. Run 'ready init' first.{RESET}")
        return 1

    definitions_path = os.path.join(readiness_dir, DEFINITIONS_FILE)
    evidence_path = os.path.join(readiness_dir, EVIDENCE_FILE)
    exceptions_path = os.path.join(readiness_dir, EXCEPTIONS_FILE)

    if not os.path.isfile(definitions_path):
        print(f"{RED}✗ No {DEFINITIONS_FILE} found in {READINESS_DIR}/{RESET}")
        return 1

    # Parse service tags from config if present
    config_path = os.path.join(readiness_dir, "config.json")
    service_tags = None
    service_name = None
    if os.path.isfile(config_path):
        with open(config_path) as f:
            config = json.load(f)
            service_tags = config.get("service_tags", None)
            service_name = config.get("service_name", None)

    result = run_scan(
        repo_root=repo_root,
        definitions_path=definitions_path,
        evidence_path=evidence_path,
        exceptions_path=exceptions_path,
        service_tags=service_tags,
        service_name=service_name,
    )

    # JSON output
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        if args.calibrate:
            return 0
        return 0 if result.is_ready else 1

    # Write baseline
    if args.baseline:
        baseline_path = args.baseline
        if not os.path.isabs(baseline_path):
            baseline_path = os.path.join(repo_root, baseline_path)
        with open(baseline_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"{DIM}Baseline written to {baseline_path}{RESET}\n")

    # Display results
    print()
    print(f"{BOLD}ready? — {result.service_name}{RESET}")
    print(f"Readiness: {BOLD}{result.readiness_pct}%{RESET}  ({result.passing}/{result.total - result.skipped} passing)")
    print()

    # Red failures
    red_fails = [
        r
        for r in result.results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.RED
    ]
    if red_fails:
        print(f"{RED}🔴 RED — cannot ship ({len(red_fails)}){RESET}")
        for r in red_fails:
            print(f"   {RED}✗{RESET} [{r.checkpoint_id}] {r.title}")
            if args.verbose:
                if r.message:
                    print(f"     {DIM}{r.message}{RESET}")
                if r.fix_hint:
                    print(f"     {CYAN}Fix: {r.fix_hint}{RESET}")
                if r.doc_link:
                    print(f"     {DIM}Docs: {r.doc_link}{RESET}")
                if r.evidence:
                    for e in r.evidence[:5]:
                        print(f"     {DIM}evidence: {e}{RESET}")
        print()

    # Yellow failures
    yellow_fails = [
        r
        for r in result.results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.YELLOW
    ]
    if yellow_fails:
        print(f"{YELLOW}🟡 YELLOW — fix before launch ({len(yellow_fails)}){RESET}")
        for r in yellow_fails:
            print(f"   {YELLOW}○{RESET} [{r.checkpoint_id}] {r.title}")
            if args.verbose:
                if r.message:
                    print(f"     {DIM}{r.message}{RESET}")
                if r.fix_hint:
                    print(f"     {CYAN}Fix: {r.fix_hint}{RESET}")
        print()

    # Passing
    passing = [r for r in result.results if r.status == Status.PASS]
    if passing:
        print(f"{GREEN}🟢 {len(passing)} checks passing{RESET}")
        if args.verbose:
            for r in passing:
                print(f"   {GREEN}✓{RESET} [{r.checkpoint_id}] {r.title}")
        print()

    # Exceptions
    exceptions = [r for r in result.results if r.status == Status.EXCEPTION]
    if exceptions:
        print(f"⚠️  EXCEPTIONS ({len(exceptions)})")
        for r in exceptions:
            print(f"   {DIM}~ [{r.checkpoint_id}] {r.title}{RESET}")
            if args.verbose and r.message:
                print(f"     {DIM}{r.message}{RESET}")
        print()

    # Needs review
    needs_review = [r for r in result.results if r.status == Status.NEEDS_REVIEW]
    if needs_review:
        print(f"{CYAN}🔍 NEEDS REVIEW ({len(needs_review)}){RESET}")
        for r in needs_review:
            print(f"   {CYAN}?{RESET} [{r.checkpoint_id}] {r.title}")
        print()

    # Skipped
    if args.verbose:
        skipped = [r for r in result.results if r.status == Status.SKIP]
        if skipped:
            print(f"{DIM}⊘ SKIPPED ({len(skipped)}){RESET}")
            for r in skipped:
                print(f"   {DIM}  [{r.checkpoint_id}] {r.title}{RESET}")
            print()

    # Calibration mode
    if args.calibrate:
        print(f"{CYAN}📊 Calibration mode — no enforcement, no exit code failure.{RESET}")
        print(f"   Review results with your team. When ready, remove --calibrate.{RESET}")
        return 0

    return 0 if result.is_ready else 1


def cmd_items(args):
    """Work item management."""
    print(f"{YELLOW}Work item management requires an adapter configuration.")
    print(f"See: ready items --help{RESET}")
    return 0


def cmd_aggregate(args):
    """Aggregate baselines from multiple repos."""
    if not args.paths:
        print(f"{RED}Provide paths to baseline files.{RESET}")
        return 1

    all_results = []
    for path in args.paths:
        if os.path.isfile(path):
            with open(path) as f:
                all_results.append(json.load(f))

    if not all_results:
        print(f"{RED}No valid baseline files found.{RESET}")
        return 1

    # Build checkpoint-level heatmap
    checkpoint_failures: dict[str, list[str]] = {}
    for baseline in all_results:
        service = baseline.get("service_name", "unknown")
        for r in baseline.get("results", []):
            if r.get("status") in ("fail", "expired_exception"):
                cp_id = r.get("checkpoint_id", "")
                title = r.get("title", cp_id)
                key = f"{cp_id}: {title}"
                checkpoint_failures.setdefault(key, []).append(service)

    total_services = len(all_results)
    print(f"\n{BOLD}Cross-Repo Readiness Heatmap{RESET}")
    print(f"{DIM}{total_services} services analyzed{RESET}\n")

    if not checkpoint_failures:
        print(f"{GREEN}No systemic gaps found.{RESET}")
        return 0

    # Sort by most widespread
    sorted_gaps = sorted(
        checkpoint_failures.items(), key=lambda x: len(x[1]), reverse=True
    )

    for checkpoint, services in sorted_gaps:
        count = len(services)
        pct = round(count / total_services * 100)
        bar = "█" * count + "░" * (total_services - count)
        color = RED if pct > 50 else YELLOW
        print(f"  {color}{bar}{RESET} {count}/{total_services} ({pct}%) — {checkpoint}")
        if args.verbose:
            for svc in services:
                print(f"    {DIM}↳ {svc}{RESET}")

    print()
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="ready",
        description="Continuous review compliance — as a folder in your repo.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # init
    subparsers.add_parser("init", help="Scaffold .readiness/ directory")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Run readiness scan")
    scan_parser.add_argument("--verbose", "-v", action="store_true", help="Full detail")
    scan_parser.add_argument("--calibrate", action="store_true", help="Report-only mode")
    scan_parser.add_argument("--json", action="store_true", help="JSON output")
    scan_parser.add_argument("--baseline", type=str, help="Write baseline to file")

    # items
    items_parser = subparsers.add_parser("items", help="Manage work items")
    items_parser.add_argument("--create", action="store_true", help="Create work items")
    items_parser.add_argument("--verify", action="store_true", help="Verify work items vs code")
    items_parser.add_argument("--adapter", type=str, default="github", help="Adapter: github, ado")

    # aggregate
    agg_parser = subparsers.add_parser("aggregate", help="Cross-repo heatmap")
    agg_parser.add_argument("paths", nargs="*", help="Paths to baseline files")
    agg_parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.command == "init":
        sys.exit(cmd_init(args))
    elif args.command == "scan":
        sys.exit(cmd_scan(args))
    elif args.command == "items":
        sys.exit(cmd_items(args))
    elif args.command == "aggregate":
        sys.exit(cmd_aggregate(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
