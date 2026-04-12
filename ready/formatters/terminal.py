"""Score-first coloured terminal output for ready scan results.

Extracted from cmd_scan() to keep the CLI layer thin. The public entry
point is `print_terminal()` which writes directly to stdout — the
terminal formatter is inherently side-effecting.
"""

import datetime
import json
import os

from ready.engine import ScanResult, Severity, Status

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_terminal(
    result: ScanResult,
    *,
    verbose: bool = False,
    auto_mode: bool = False,
    auto_pack: str | None = None,
    prev_baseline: dict | None = None,
    definitions_path: str | None = None,
) -> None:
    """Render scan results to the terminal.

    This reproduces the exact output that cmd_scan previously generated
    inline — same ANSI codes, same line structure, same collapse rules.
    """
    red_fails = [
        r for r in result.results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.RED
    ]
    yellow_fails = [
        r for r in result.results
        if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION)
        and r.severity == Severity.YELLOW
    ]
    passing = [r for r in result.results if r.status == Status.PASS]
    exceptions = [r for r in result.results if r.status == Status.EXCEPTION]
    needs_review = [r for r in result.results if r.status == Status.NEEDS_REVIEW]
    skipped = [r for r in result.results if r.status == Status.SKIP]

    # Drift delta
    drift_str = ""
    if prev_baseline:
        prev_pct = prev_baseline.get("summary", {}).get("readiness_pct", 0)
        delta = result.readiness_pct - prev_pct
        if abs(delta) >= 0.5:
            if delta > 0:
                drift_str = f"   {GREEN}▲ +{delta:.0f}%{RESET}"
            else:
                drift_str = f"   {RED}▼ {delta:.0f}%{RESET}"

    # Summary line
    pct = result.readiness_pct
    pct_color = GREEN if result.is_ready else RED
    if result.is_ready and not yellow_fails:
        status_str = f"{GREEN}✓{RESET}"
    else:
        parts = []
        if red_fails:
            parts.append(f"{RED}{len(red_fails)} blocking{RESET}")
        if yellow_fails:
            parts.append(
                f"{YELLOW}{len(yellow_fails)} warning{'s' if len(yellow_fails) != 1 else ''}{RESET}"
            )
        status_str = " · ".join(parts) if parts else ""

    print()
    print(
        f"{BOLD}ready? — {result.service_name}{RESET}   "
        f"{pct_color}{pct:.0f}%{RESET}   {status_str}{drift_str}"
    )

    if auto_mode:
        print(
            f"  {DIM}No .readiness/ found — running {auto_pack} defaults. "
            f"Run 'ready init' to customize.{RESET}"
        )

    # All clear — single line, done
    if (
        result.is_ready
        and not yellow_fails
        and not exceptions
        and not needs_review
        and not verbose
    ):
        print()
        return

    print()

    if verbose:
        _print_verbose(
            red_fails, yellow_fails, passing, exceptions,
            needs_review, skipped, definitions_path,
        )
    else:
        _print_compact(red_fails, yellow_fails, exceptions, needs_review)


def _print_verbose(red_fails, yellow_fails, passing, exceptions,
                   needs_review, skipped, definitions_path):
    if red_fails:
        print(f"{RED}blocking ({len(red_fails)}){RESET}")
        for r in red_fails:
            print(f"  {RED}✗{RESET} {r.title}")
            if r.message:
                print(f"    {DIM}{r.message}{RESET}")
            if r.fix_hint:
                print(f"    {CYAN}→ {r.fix_hint}{RESET}")
            if r.doc_link:
                print(f"    {DIM}{r.doc_link}{RESET}")
            if r.evidence:
                for e in r.evidence[:5]:
                    print(f"    {DIM}{e}{RESET}")
        print()

    if yellow_fails:
        print(f"{YELLOW}warnings ({len(yellow_fails)}){RESET}")
        for r in yellow_fails:
            print(f"  {YELLOW}○{RESET} {r.title}")
            if r.message:
                print(f"    {DIM}{r.message}{RESET}")
            if r.fix_hint:
                print(f"    {CYAN}→ {r.fix_hint}{RESET}")
            if r.evidence:
                for e in r.evidence[:3]:
                    print(f"    {DIM}{e}{RESET}")
        print()

    if passing:
        print(f"{GREEN}passing ({len(passing)}){RESET}")
        for r in passing:
            print(f"  {GREEN}✓{RESET} {r.title}")
        print()

    if exceptions:
        print(f"exceptions ({len(exceptions)})")
        for r in exceptions:
            print(f"  {DIM}~ {r.title}{RESET}")
            if r.message:
                print(f"    {DIM}{r.message}{RESET}")
        print()

    if needs_review:
        print(f"{CYAN}needs review ({len(needs_review)}){RESET}")
        for r in needs_review:
            print(f"  {CYAN}?{RESET} {r.title}")
        print()

    if skipped:
        print(f"{DIM}skipped ({len(skipped)}){RESET}")
        for r in skipped:
            print(f"  {DIM}  {r.title}{RESET}")
        print()

    # Stale definition warnings
    if definitions_path and os.path.isfile(definitions_path):
        try:
            with open(definitions_path) as _f:
                _defs = json.load(_f)
            _today = datetime.date.today()
            _stale = [
                cp
                for cp in _defs.get("checkpoints", [])
                if cp.get("review_by")
                and datetime.date.fromisoformat(cp["review_by"]) < _today
            ]
            if _stale:
                print(f"{YELLOW}definition review overdue ({len(_stale)}){RESET}")
                for cp in _stale:
                    print(
                        f"  {YELLOW}⏰{RESET} [{cp['id']}] {cp.get('title', '')}  "
                        f"{DIM}review_by {cp['review_by']}{RESET}"
                    )
                print(f"  {DIM}Run 'ready audit' for a full health report.{RESET}")
                print()
        except (ValueError, KeyError):
            pass


def _print_compact(red_fails, yellow_fails, exceptions, needs_review):
    if red_fails:
        for r in red_fails:
            print(f"  {RED}✗{RESET} {r.title}")
            if r.evidence:
                print(f"    {DIM}{r.evidence[0]}{RESET}")
            if r.fix_hint:
                print(f"    {CYAN}→ {r.fix_hint}{RESET}")
            print()

    hidden = []
    if yellow_fails:
        hidden.append(
            f"{len(yellow_fails)} warning{'s' if len(yellow_fails) != 1 else ''}"
        )
    if exceptions:
        hidden.append(
            f"{len(exceptions)} exception{'s' if len(exceptions) != 1 else ''}"
        )
    if needs_review:
        hidden.append(f"{len(needs_review)} needs review")
    if hidden:
        print(f"  {DIM}+ {', '.join(hidden)}   (ready scan --verbose){RESET}")
        print()
