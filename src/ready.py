#!/usr/bin/env python3
"""
ready — Know before you ship.

Usage:
    ready scan                     Red/Yellow/Green scan
    ready scan --verbose           Full checkpoint detail
    ready scan --calibrate         Report-only (no exit code failure)
    ready scan --json              Machine-readable output
    ready scan --baseline FILE     Write baseline snapshot
    ready scan --suggest-tuning    Show checkpoint tuning suggestions after scan
    ready init                     Scaffold .readiness/ directory
    ready init --pack NAME         Use a specific checkpoint pack
    ready init --list-packs        List available checkpoint packs
    ready author --from FILE       Generate checkpoint prompt from a guideline doc
    ready decisions                Show all active and expired accepted risks
    ready history [BASELINES...]   Show readiness trend from baseline snapshots
    ready items --create           Propose + create work items
    ready items --verify           Cross-check work items vs code
    ready aggregate PATHS...       Cross-repo heatmap
"""

import argparse
import datetime
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

# Available checkpoint packs: name -> (directory, description)
PACKS = {
    "starter": (
        "starter-pack",
        "Universal starter — 11 checks covering docs, CI, testing, secrets, and ops basics",
    ),
    "web-api": (
        "web-api",
        "REST/HTTP API — 17 checks for auth, rate limiting, error handling, logging, and resilience",
    ),
    "security-baseline": (
        "security-baseline",
        "Security baseline — hardcoded secrets, dependency hygiene, .gitignore, and security policy",
    ),
    "observability-baseline": (
        "observability-baseline",
        "Observability baseline — logging, tracing, metrics, dashboards, and on-call registration",
    ),
}


def _find_examples_dir() -> str:
    """Locate the examples/ directory relative to this file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "..", "examples"),
        os.path.join(script_dir, "examples"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return os.path.abspath(c)
    return ""


def _detect_pack(repo_root: str) -> str:
    """Detect the most appropriate pack based on project files in the repo root."""
    try:
        files = set(os.listdir(repo_root))
    except OSError:
        return "starter"

    # Node.js: check for web framework in package.json
    if "package.json" in files:
        try:
            with open(os.path.join(repo_root, "package.json")) as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            web_frameworks = {"express", "fastify", "koa", "hapi", "@hapi/hapi", "@nestjs/core", "restify", "polka"}
            if deps.keys() & web_frameworks:
                return "web-api"
        except Exception:
            pass

    # Python: check for web framework references
    for fname in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
        fpath = os.path.join(repo_root, fname)
        if os.path.isfile(fpath):
            try:
                with open(fpath) as f:
                    content = f.read().lower()
                if any(fw in content for fw in ("fastapi", "flask", "django", "starlette", "tornado", "sanic", "aiohttp")):
                    return "web-api"
            except Exception:
                pass

    # Go: check go.mod for web frameworks
    if "go.mod" in files:
        try:
            with open(os.path.join(repo_root, "go.mod")) as f:
                content = f.read()
            if any(fw in content for fw in ("gin-gonic", "echo", "fiber", "gorilla/mux", "chi")):
                return "web-api"
        except Exception:
            pass

    return "starter"

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
    # --list-packs: show available packs and exit
    if getattr(args, "list_packs", False):
        print(f"\n{BOLD}Available checkpoint packs{RESET}\n")
        for name, (_, description) in PACKS.items():
            print(f"  {CYAN}{name:<24}{RESET} {description}")
        print()
        print(f"Usage: {CYAN}ready init --pack <name>{RESET}")
        return 0

    pack_name = getattr(args, "pack", "starter") or "starter"
    if pack_name not in PACKS:
        print(f"{RED}✗ Unknown pack '{pack_name}'.{RESET}")
        print(f"  Run {CYAN}ready init --list-packs{RESET} to see available packs.")
        return 1

    pack_dir_name, pack_description = PACKS[pack_name]
    examples_dir = _find_examples_dir()
    if not examples_dir:
        print(f"{RED}✗ Could not locate examples/ directory.{RESET}")
        return 1
    pack_dir = os.path.join(examples_dir, pack_dir_name)

    target = os.path.join(os.getcwd(), READINESS_DIR)
    if os.path.exists(target):
        print(f"{YELLOW}⚠ {READINESS_DIR}/ already exists. Skipping.{RESET}")
        return 0

    print(f"  {DIM}Pack: {pack_name} — {pack_description}{RESET}")
    os.makedirs(target, exist_ok=True)

    files_to_copy = [
        (DEFINITIONS_FILE, "checkpoint-definitions.json"),
        (EXCEPTIONS_FILE, "exceptions.json"),
        (EVIDENCE_FILE, "external-evidence.json"),
    ]

    for dest_name, src_name in files_to_copy:
        src = os.path.join(pack_dir, src_name)
        dest = os.path.join(target, dest_name)
        if os.path.isfile(src):
            shutil.copy2(src, dest)
            print(f"  {GREEN}✓{RESET} {READINESS_DIR}/{dest_name}")
        else:
            # Create empty defaults for files not present in this pack
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
            "infrastructure",
        ],
        "_note": "Set service_tags to enable service-specific checks. Checks with applicable_tags will be skipped unless your service_tags match. See _available_tags for common values.",
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
    auto_mode = False
    auto_pack = None

    if not os.path.isdir(readiness_dir):
        # Zero-config: no .readiness/ — auto-detect project type and run from pack
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
        auto_mode = True
    else:
        definitions_path = os.path.join(readiness_dir, DEFINITIONS_FILE)
        evidence_path = os.path.join(readiness_dir, EVIDENCE_FILE)
        exceptions_path = os.path.join(readiness_dir, EXCEPTIONS_FILE)

        if not os.path.isfile(definitions_path):
            print(f"{RED}✗ No {DEFINITIONS_FILE} found in {READINESS_DIR}/{RESET}")
            return 1

        config_path = os.path.join(readiness_dir, "config.json")
        service_tags = None
        service_name = None
        if os.path.isfile(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
                service_tags = cfg.get("service_tags", None)
                service_name = cfg.get("service_name", None)

    # Load previous baseline for auto-drift (only in configured mode)
    prev_baseline = None
    if not auto_mode:
        prev_baseline_path = os.path.join(readiness_dir, BASELINE_FILE)
        if os.path.isfile(prev_baseline_path):
            with open(prev_baseline_path) as f:
                prev_baseline = json.load(f)

    result = run_scan(
        repo_root=repo_root,
        definitions_path=definitions_path,
        evidence_path=evidence_path,
        exceptions_path=exceptions_path,
        service_tags=service_tags,
        service_name=service_name,
    )

    # JSON output (early return — machine consumers get stable format)
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

    # Categorize results
    red_fails = [r for r in result.results if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION) and r.severity == Severity.RED]
    yellow_fails = [r for r in result.results if r.status in (Status.FAIL, Status.EXPIRED_EXCEPTION) and r.severity == Severity.YELLOW]
    passing = [r for r in result.results if r.status == Status.PASS]
    exceptions = [r for r in result.results if r.status == Status.EXCEPTION]
    needs_review = [r for r in result.results if r.status == Status.NEEDS_REVIEW]
    skipped = [r for r in result.results if r.status == Status.SKIP]

    # Drift delta (compare to last committed baseline)
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
            parts.append(f"{YELLOW}{len(yellow_fails)} warning{'s' if len(yellow_fails) != 1 else ''}{RESET}")
        status_str = " · ".join(parts) if parts else ""

    print()
    print(f"{BOLD}ready? — {result.service_name}{RESET}   {pct_color}{pct:.0f}%{RESET}   {status_str}{drift_str}")

    if auto_mode:
        print(f"  {DIM}No .readiness/ found — running {auto_pack} defaults. Run 'ready init' to customize.{RESET}")

    # All clear — single line output, we're done
    if result.is_ready and not yellow_fails and not exceptions and not needs_review and not args.verbose:
        print()
        return 0

    print()

    if args.verbose:
        # Full detail
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

    else:
        # Default: blocking items with first evidence + fix hint
        if red_fails:
            for r in red_fails:
                print(f"  {RED}✗{RESET} {r.title}")
                if r.evidence:
                    print(f"    {DIM}{r.evidence[0]}{RESET}")
                if r.fix_hint:
                    print(f"    {CYAN}→ {r.fix_hint}{RESET}")
                print()

        # Collapse everything else into one line
        hidden = []
        if yellow_fails:
            hidden.append(f"{len(yellow_fails)} warning{'s' if len(yellow_fails) != 1 else ''}")
        if exceptions:
            hidden.append(f"{len(exceptions)} exception{'s' if len(exceptions) != 1 else ''}")
        if needs_review:
            hidden.append(f"{len(needs_review)} needs review")
        if hidden:
            print(f"  {DIM}+ {', '.join(hidden)}   (ready scan --verbose){RESET}")
            print()

    # Tuning suggestions
    if getattr(args, "suggest_tuning", False):
        _print_tuning_suggestions(result, definitions_path)

    # Calibration mode
    if args.calibrate:
        print(f"{CYAN}Calibration mode — no enforcement, no exit code failure.{RESET}")
        print(f"{DIM}Review results with your team. When ready, remove --calibrate.{RESET}")
        print()
        return 0

    return 0 if result.is_ready else 1


def _print_tuning_suggestions(result, definitions_path: str) -> None:
    """Analyze scan results and print checkpoint tuning suggestions."""
    # Load definitions to get method info per checkpoint
    method_by_id: dict[str, str] = {}
    if os.path.isfile(definitions_path):
        with open(definitions_path) as f:
            defs = json.load(f)
        for cp in defs.get("checkpoints", []):
            verification = cp.get("verification", {})
            method_by_id[cp["id"]] = verification.get("method", "")

    suggestions: list[tuple[str, str, str]] = []  # (checkpoint_id, title, message)

    for r in result.results:
        method = method_by_id.get(r.checkpoint_id, "")
        confidence = r.confidence.value if hasattr(r.confidence, "value") else str(r.confidence)

        # Heuristic 1: failing grep with evidence hitting test/fixture paths
        if (
            r.status.value in ("fail",)
            and method in ("grep", "grep_count")
            and r.evidence
        ):
            test_hits = [
                e for e in r.evidence
                if any(kw in e.lower() for kw in ("/test", "/tests", "/spec", "/specs", "/fixture", "/fixtures", "/mock", "/mocks", "__test__"))
            ]
            if test_hits:
                example = test_hits[0]
                suggestions.append((
                    r.checkpoint_id,
                    r.title,
                    f"Pattern matching test/fixture paths (e.g. {example})\n"
                    f"     Consider scoping 'target' to exclude test directories, or add a separate exception.",
                ))

        # Heuristic 2: failing with zero evidence and confidence likely
        elif (
            r.status.value == "fail"
            and not r.evidence
            and confidence == "likely"
        ):
            suggestions.append((
                r.checkpoint_id,
                r.title,
                "No matches found — pattern may be too narrow or not applicable to this language stack.\n"
                "     Consider broadening the regex, expanding the target glob, or adding an exception if not applicable.",
            ))

        # Heuristic 3: passing with very high evidence count (>20)
        elif r.status.value == "pass" and len(r.evidence) > 20 and confidence == "likely":
            suggestions.append((
                r.checkpoint_id,
                r.title,
                f"Passing with {len(r.evidence)} matches — if this pattern is deterministic, "
                f"promote confidence to 'verified' to remove the 'likely' qualifier.",
            ))

        # Heuristic 4: needs_review — suggest external_attestation
        elif r.status.value == "needs_review":
            suggestions.append((
                r.checkpoint_id,
                r.title,
                "Cannot be determined from code alone. If a human is the right verifier, "
                "convert this to type 'external' with method 'external_attestation'.",
            ))

    print(f"── Tuning Suggestions {'─' * 44}")
    print()
    if not suggestions:
        print(f"  {GREEN}✓ No tuning suggestions — checkpoints look well-calibrated.{RESET}")
    else:
        for cp_id, title, message in suggestions:
            print(f"  {CYAN}[{cp_id}]{RESET} {title}")
            print(f"  {YELLOW}⚡{RESET} {message}")
            print()
        print(f"  {DIM}{len(suggestions)} suggestion(s) — run 'ready scan --verbose' to see full evidence.{RESET}")
    print()


def cmd_author(args):
    """Generate a ready-to-paste AI prompt from a guideline document."""
    guideline_path = args.guideline_file
    if not os.path.isfile(guideline_path):
        print(f"{RED}✗ File not found: {guideline_path}{RESET}")
        return 1

    # Locate the authoring skill instructions
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_candidates = [
        os.path.join(script_dir, "..", "ai-skills", "author-checkpoints.instructions.md"),
        os.path.join(script_dir, "ai-skills", "author-checkpoints.instructions.md"),
    ]
    skill_path = next((p for p in skill_candidates if os.path.isfile(p)), None)
    if not skill_path:
        print(f"{RED}✗ Could not locate ai-skills/author-checkpoints.instructions.md{RESET}")
        return 1

    with open(skill_path) as f:
        skill_instructions = f.read()

    with open(guideline_path) as f:
        guideline_content = f.read()

    guideline_name = os.path.basename(guideline_path)
    output_path = args.output

    prompt = f"""# Checkpoint Authoring Prompt
<!-- Generated by `ready author --from {guideline_name}` — paste into Claude, ChatGPT, Copilot, Cursor, or any AI -->

{skill_instructions}

---

## Guideline Document to Process: {guideline_name}

{guideline_content}

---

## Output Instructions

Generate checkpoint definitions from the guideline document above.
Follow all rules in the skill instructions. Present each checkpoint for human review.
When the user approves, write the final output to `.readiness/checkpoint-definitions.json`.
"""

    with open(output_path, "w") as f:
        f.write(prompt)

    rel_output = os.path.relpath(output_path)
    print(f"\n{GREEN}✓ Prompt written to {rel_output}{RESET}")
    print()
    print(f"  {BOLD}Next: paste this file into your AI assistant{RESET}")
    print()
    print(f"  {CYAN}Claude:{RESET}   \"Read {rel_output} and generate checkpoint definitions\"")
    print(f"  {CYAN}Cursor:{RESET}   @{rel_output}")
    print(f"  {CYAN}Copilot:{RESET}  #file:{rel_output}")
    print(f"  {CYAN}ChatGPT:{RESET}  Attach {rel_output} and ask it to generate checkpoints")
    print()
    return 0


def cmd_decisions(args):
    """Show all active and expired accepted risks."""
    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    if not os.path.isdir(readiness_dir):
        print(f"{RED}✗ No {READINESS_DIR}/ found. Run 'ready init' first.{RESET}")
        return 1

    exceptions_path = os.path.join(readiness_dir, EXCEPTIONS_FILE)
    definitions_path = os.path.join(readiness_dir, DEFINITIONS_FILE)
    config_path = os.path.join(readiness_dir, "config.json")

    service_name = os.path.basename(repo_root)
    if os.path.isfile(config_path):
        with open(config_path) as f:
            service_name = json.load(f).get("service_name", service_name)

    exceptions = []
    if os.path.isfile(exceptions_path):
        with open(exceptions_path) as f:
            exceptions = json.load(f).get("exceptions", [])

    if not exceptions:
        print(f"\n{GREEN}✓ No accepted risks recorded for {service_name}.{RESET}\n")
        return 0

    # Build checkpoint id → title lookup
    title_by_id: dict[str, str] = {}
    if os.path.isfile(definitions_path):
        with open(definitions_path) as f:
            for cp in json.load(f).get("checkpoints", []):
                title_by_id[cp["id"]] = cp.get("title", cp["id"])

    today = datetime.date.today()
    active, expiring_soon, expired = [], [], []

    for exc in exceptions:
        cp_id = exc.get("checkpoint_id", "")
        title = title_by_id.get(cp_id, cp_id)
        expires_str = exc.get("expires", "")
        try:
            expires = datetime.date.fromisoformat(expires_str)
            days_left = (expires - today).days
        except (ValueError, TypeError):
            expires = None
            days_left = None

        entry = {
            "id": cp_id,
            "title": title,
            "justification": exc.get("justification", ""),
            "accepted_by": exc.get("accepted_by", ""),
            "decision_reference": exc.get("decision_reference", ""),
            "expires": expires_str,
            "days_left": days_left,
        }

        if days_left is None or days_left > 30:
            active.append(entry)
        elif days_left >= 0:
            expiring_soon.append(entry)
        else:
            expired.append(entry)

    print(f"\n{BOLD}── Accepted Risks {'─' * 43}{RESET}")
    print(f"  Service: {BOLD}{service_name}{RESET}    As of: {today}")
    print()

    def _print_exception(e, color, icon):
        days = e["days_left"]
        expires_label = f"expires {e['expires']}" if days is not None and days >= 0 else f"expired {e['expires']}"
        days_label = f"({days}d)" if days is not None and days >= 0 else ""
        print(f"  {color}{icon} [{e['id']}]{RESET} {e['title']}")
        print(f"    {DIM}{expires_label} {days_label}{RESET}")
        if e["justification"]:
            print(f"    Justification: {e['justification']}")
        parts = []
        if e["accepted_by"]:
            parts.append(f"Accepted by: {e['accepted_by']}")
        if e["decision_reference"]:
            parts.append(f"Ref: {e['decision_reference']}")
        if parts:
            print(f"    {DIM}{' • '.join(parts)}{RESET}")
        print()

    if active:
        print(f"{GREEN}ACTIVE ({len(active)}){RESET}")
        for e in active:
            _print_exception(e, GREEN, "✓")

    if expiring_soon:
        print(f"{YELLOW}EXPIRING SOON — within 30 days ({len(expiring_soon)}){RESET}")
        for e in expiring_soon:
            _print_exception(e, YELLOW, "⚠")

    if expired:
        print(f"{RED}EXPIRED — re-evaluation required ({len(expired)}){RESET}")
        for e in expired:
            _print_exception(e, RED, "✗")
        print(f"  {DIM}Run 'ready scan' to see which expired exceptions are now blocking.{RESET}")
        print()
        return 1

    return 0


def cmd_history(args):
    """Show readiness trend from committed baseline snapshots."""
    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    # Collect baseline paths
    paths = list(getattr(args, "baselines", None) or [])
    if not paths:
        # Auto-discover in .readiness/
        candidates = []
        if os.path.isdir(readiness_dir):
            for fname in os.listdir(readiness_dir):
                if fname.endswith(".json") and "baseline" in fname:
                    candidates.append(os.path.join(readiness_dir, fname))
        paths = candidates

    if not paths:
        print(f"\n{YELLOW}No baseline files found.{RESET}")
        print()
        print(f"  Create baselines with: {CYAN}ready scan --baseline .readiness/review-baseline.json{RESET}")
        print(f"  Commit the file to build history over time.")
        print()
        return 0

    baselines = []
    for p in paths:
        if not os.path.isfile(p):
            print(f"{YELLOW}⚠ Skipping (not found): {p}{RESET}")
            continue
        with open(p) as f:
            baselines.append(json.load(f))

    if not baselines:
        print(f"{RED}✗ No valid baseline files could be read.{RESET}")
        return 1

    # Sort by scan_time ascending
    baselines.sort(key=lambda b: b.get("scan_time", ""))

    service_name = baselines[-1].get("service_name", "unknown")
    print(f"\n{BOLD}── Readiness History {'─' * 41}{RESET}")
    print(f"  Service: {BOLD}{service_name}{RESET}")
    print()

    if len(baselines) == 1:
        b = baselines[0]
        summary = b.get("summary", {})
        pct = summary.get("readiness_pct", 0)
        passing = summary.get("passing", 0)
        total = summary.get("total", 0)
        exceptions = summary.get("exceptions", 0)
        scan_date = b.get("scan_time", "")[:10]
        bar_filled = int(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        exc_label = f" + {exceptions} exception(s)" if exceptions else ""
        print(f"  {scan_date}   {pct:5.1f}%  {bar}  ({passing}/{total}{exc_label})")
        print()
        print(f"  {DIM}Only one snapshot. Commit more baselines to build history.{RESET}")
        print(f"  {DIM}run: ready scan --baseline .readiness/review-baseline.json{RESET}")
        print()
        return 0

    # Multi-baseline trend
    prev_pct = None
    all_failing_ids: list[set] = []
    for b in baselines:
        summary = b.get("summary", {})
        pct = summary.get("readiness_pct", 0)
        passing = summary.get("passing", 0)
        total = summary.get("total", 0)
        exceptions = summary.get("exceptions", 0)
        scan_date = b.get("scan_time", "")[:10]
        bar_filled = int(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        exc_label = f" + {exceptions} exc." if exceptions else ""

        if prev_pct is None:
            delta_label = ""
        else:
            delta = pct - prev_pct
            if delta > 0:
                delta_label = f"  {GREEN}▲ +{delta:.1f}%{RESET}"
            elif delta < 0:
                delta_label = f"  {RED}▼ {delta:.1f}%{RESET}"
            else:
                delta_label = f"  {DIM}─ 0%{RESET}"

        print(f"  {scan_date}   {pct:5.1f}%  {bar}  ({passing}/{total}{exc_label}){delta_label}")
        prev_pct = pct

        failing_ids = {
            r.get("checkpoint_id") for r in b.get("results", [])
            if r.get("status") in ("fail", "expired_exception")
        }
        all_failing_ids.append(failing_ids)

    print()

    # Summary: resolved and newly failing between first and last
    first_failing = all_failing_ids[0] if all_failing_ids else set()
    last_failing = all_failing_ids[-1] if all_failing_ids else set()
    resolved = first_failing - last_failing
    regressed = last_failing - first_failing

    first_pct = baselines[0].get("summary", {}).get("readiness_pct", 0)
    last_pct = baselines[-1].get("summary", {}).get("readiness_pct", 0)
    total_delta = last_pct - first_pct
    span_days = ""
    try:
        t0 = baselines[0].get("scan_time", "")[:10]
        t1 = baselines[-1].get("scan_time", "")[:10]
        d0 = datetime.date.fromisoformat(t0)
        d1 = datetime.date.fromisoformat(t1)
        span_days = f" over {(d1 - d0).days} days"
    except (ValueError, TypeError):
        pass

    delta_sign = "+" if total_delta >= 0 else ""
    color = GREEN if total_delta >= 0 else RED
    print(f"  {BOLD}Trend:{RESET} {color}{delta_sign}{total_delta:.1f}%{RESET}{span_days}")
    if resolved:
        print(f"  {GREEN}Resolved:{RESET} {', '.join(sorted(resolved))}")
    if regressed:
        print(f"  {RED}Regressed:{RESET} {', '.join(sorted(regressed))}")
    print()
    return 0


def cmd_badge(args):
    """Generate a README badge reflecting the current readiness score."""
    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    pct = None
    service_name = os.path.basename(repo_root)

    # Prefer committed baseline (reflects stable, reviewed state)
    baseline_path = os.path.join(readiness_dir, BASELINE_FILE)
    if os.path.isfile(baseline_path):
        with open(baseline_path) as f:
            baseline = json.load(f)
        pct = baseline.get("summary", {}).get("readiness_pct", 0)
        service_name = baseline.get("service_name", service_name)
    elif os.path.isdir(readiness_dir):
        # No baseline yet — run a live scan
        definitions_path = os.path.join(readiness_dir, DEFINITIONS_FILE)
        if not os.path.isfile(definitions_path):
            print(f"{RED}✗ No {DEFINITIONS_FILE} found. Run 'ready scan' first.{RESET}")
            return 1
        config_path = os.path.join(readiness_dir, "config.json")
        service_tags = None
        if os.path.isfile(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
                service_tags = cfg.get("service_tags")
                service_name = cfg.get("service_name", service_name)
        result = run_scan(
            repo_root=repo_root,
            definitions_path=definitions_path,
            evidence_path=os.path.join(readiness_dir, EVIDENCE_FILE),
            exceptions_path=os.path.join(readiness_dir, EXCEPTIONS_FILE),
            service_tags=service_tags,
            service_name=service_name,
        )
        pct = result.readiness_pct
    else:
        print(f"{RED}✗ No .readiness/ found. Run 'ready scan --baseline .readiness/review-baseline.json' first.{RESET}")
        return 1

    pct_int = int(pct)
    color = "brightgreen" if pct_int >= 80 else ("yellow" if pct_int >= 60 else "red")
    badge_url = f"https://img.shields.io/badge/ready-{pct_int}%25-{color}"
    markdown = f"[![ready]({badge_url})](.readiness/review-baseline.json)"

    print(f"\n{pct_color_for(pct_int)}{BOLD}ready{RESET}   {service_name}   {pct_int}%\n")
    print(f"  {BOLD}Markdown badge:{RESET}")
    print(f"  {markdown}")
    print()
    print(f"  {DIM}Paste at the top of your README.md next to other status badges.{RESET}")
    print(f"  {DIM}Score reflects the last committed baseline. Update with:{RESET}")
    print(f"  {DIM}  ready scan --baseline .readiness/review-baseline.json{RESET}")
    print()
    return 0


def pct_color_for(pct: int) -> str:
    if pct >= 80:
        return GREEN
    if pct >= 60:
        return YELLOW
    return RED


WORK_ITEMS_FILE = "work-items.json"


def _load_adapter(adapter_name: str):
    """Instantiate the requested work item adapter."""
    name = adapter_name.lower()
    if name in ("github", "github_issues"):
        from src.adapters.github_issues import GitHubIssuesAdapter
        return GitHubIssuesAdapter()
    elif name in ("ado", "azure", "azuredevops"):
        from src.adapters.ado import AzureDevOpsAdapter
        return AzureDevOpsAdapter()
    elif name == "jira":
        from src.adapters.jira import JiraAdapter
        return JiraAdapter()
    else:
        raise ValueError(f"Unknown adapter '{adapter_name}'. Choices: github, ado, jira")


def _load_work_items(readiness_dir: str) -> dict:
    """Load tracked work items from .readiness/work-items.json."""
    path = os.path.join(readiness_dir, WORK_ITEMS_FILE)
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return {"version": "1.0", "items": {}}


def _save_work_items(readiness_dir: str, data: dict) -> None:
    path = os.path.join(readiness_dir, WORK_ITEMS_FILE)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def cmd_items(args):
    """Work item management — create items for gaps, verify closed items vs code."""
    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    if not os.path.isdir(readiness_dir):
        print(f"{RED}✗ No {READINESS_DIR}/ found. Run 'ready init' first.{RESET}")
        return 1

    try:
        adapter = _load_adapter(args.adapter)
    except ValueError as e:
        print(f"{RED}✗ {e}{RESET}")
        return 1
    except Exception as e:
        print(f"{RED}✗ Could not initialize adapter: {e}{RESET}")
        return 1

    # Run scan to get current state
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

    from src.validators import run_scan, Status, Severity
    result = run_scan(
        repo_root=repo_root,
        definitions_path=definitions_path,
        evidence_path=evidence_path,
        exceptions_path=exceptions_path,
        service_tags=service_tags,
        service_name=service_name,
    )

    work_items = _load_work_items(readiness_dir)
    tracked = work_items.get("items", {})  # checkpoint_id -> {id, url, adapter}

    if args.create:
        # Propose work items for all failing checks without an existing item
        failures = [
            r for r in result.results
            if r.status.value in ("fail", "expired_exception")
        ]

        if not failures:
            print(f"{GREEN}✓ No gaps to create work items for.{RESET}")
            return 0

        print(f"\n{BOLD}Proposed work items for {result.service_name}{RESET}")
        print(f"{DIM}Adapter: {args.adapter} | {len(failures)} gap(s){RESET}\n")

        created = 0
        skipped = 0
        for r in failures:
            if r.checkpoint_id in tracked:
                print(f"  {DIM}~ [{r.checkpoint_id}] {r.title} — already tracked: {tracked[r.checkpoint_id]['url']}{RESET}")
                skipped += 1
                continue

            severity_color = RED if r.severity == Severity.RED else YELLOW
            print(f"  {severity_color}[{r.severity.value.upper()}]{RESET} [{r.checkpoint_id}] {r.title}")
            if r.fix_hint:
                print(f"    {DIM}Fix: {r.fix_hint}{RESET}")
            if r.evidence:
                for e in r.evidence[:3]:
                    print(f"    {DIM}evidence: {e}{RESET}")

            if not args.yes:
                answer = input(f"  Create work item? [y/N] ").strip().lower()
                if answer != "y":
                    print(f"    {DIM}Skipped.{RESET}")
                    continue

            from src.adapters import WorkItemDraft
            draft = WorkItemDraft(
                checkpoint_id=r.checkpoint_id,
                title=r.title,
                description=r.message or r.title,
                severity=r.severity.value,
                evidence=r.evidence,
                fix_hint=r.fix_hint,
                doc_link=r.doc_link,
                guideline=r.guideline,
                guideline_section=r.guideline_section,
                labels=[f"cp:{r.checkpoint_id}"],
            )
            try:
                item = adapter.create_draft(draft)
                tracked[r.checkpoint_id] = {
                    "id": item.id,
                    "url": item.url,
                    "adapter": args.adapter,
                }
                print(f"    {GREEN}✓ Created: {item.url}{RESET}")
                created += 1
            except Exception as e:
                print(f"    {RED}✗ Failed to create: {e}{RESET}")

        work_items["items"] = tracked
        _save_work_items(readiness_dir, work_items)
        print(f"\n{GREEN}✓ {created} work item(s) created, {skipped} already tracked.{RESET}")
        print(f"{DIM}Tracked in {READINESS_DIR}/{WORK_ITEMS_FILE}{RESET}")
        return 0

    elif args.verify:
        # Cross-check: regression (item closed but code still fails) or stale (code passes but item open)
        if not tracked:
            print(f"{YELLOW}No tracked work items found. Run 'ready items --create' first.{RESET}")
            return 0

        scan_by_id = {r.checkpoint_id: r for r in result.results}

        regressions = []
        stale = []
        ok = []

        print(f"\n{BOLD}Work item verification for {result.service_name}{RESET}\n")

        for cp_id, item_info in tracked.items():
            remote = adapter.get_status(item_info["id"])
            if not remote:
                print(f"  {YELLOW}⚠{RESET} [{cp_id}] Could not fetch item {item_info['id']} — skipping")
                continue

            scan_result = scan_by_id.get(cp_id)
            item_closed = remote.status.lower() in ("closed", "done", "resolved", "complete", "completed")
            code_failing = scan_result and scan_result.status.value in ("fail", "expired_exception")

            if item_closed and code_failing:
                regressions.append((cp_id, remote, scan_result))
            elif not item_closed and scan_result and scan_result.status.value == "pass":
                stale.append((cp_id, remote, scan_result))
            else:
                ok.append((cp_id, remote))

        if regressions:
            print(f"{RED}🔴 REGRESSIONS ({len(regressions)}) — item closed but code still fails{RESET}")
            for cp_id, remote, scan_r in regressions:
                print(f"   {RED}✗{RESET} [{cp_id}] {scan_r.title}")
                print(f"     {DIM}Work item: {remote.url} (status: {remote.status}){RESET}")
            print()

        if stale:
            print(f"{YELLOW}🟡 STALE ({len(stale)}) — code passes but work item still open{RESET}")
            for cp_id, remote, scan_r in stale:
                print(f"   {YELLOW}○{RESET} [{cp_id}] {scan_r.title}")
                print(f"     {DIM}Work item: {remote.url} (status: {remote.status}){RESET}")

                if args.yes or input(f"  Close work item {remote.id}? [y/N] ").strip().lower() == "y":
                    success = adapter.close(remote.id, "Resolved — readiness check now passing.")
                    if success:
                        print(f"     {GREEN}✓ Closed.{RESET}")
                        del tracked[cp_id]
                    else:
                        print(f"     {RED}✗ Could not close.{RESET}")
            print()

        if ok:
            print(f"{GREEN}✓ {len(ok)} work item(s) in sync{RESET}")

        work_items["items"] = tracked
        _save_work_items(readiness_dir, work_items)
        return 1 if regressions else 0

    else:
        print(f"{YELLOW}Specify --create or --verify.{RESET}")
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
    init_parser = subparsers.add_parser("init", help="Scaffold .readiness/ directory")
    init_parser.add_argument(
        "--pack",
        type=str,
        default="starter",
        metavar="NAME",
        help="Checkpoint pack: starter, web-api, security-baseline, observability-baseline (default: starter)",
    )
    init_parser.add_argument(
        "--list-packs",
        dest="list_packs",
        action="store_true",
        help="List available checkpoint packs",
    )

    # scan
    scan_parser = subparsers.add_parser("scan", help="Run readiness scan")
    scan_parser.add_argument("--verbose", "-v", action="store_true", help="Full detail")
    scan_parser.add_argument("--calibrate", action="store_true", help="Report-only mode")
    scan_parser.add_argument("--json", action="store_true", help="JSON output")
    scan_parser.add_argument("--baseline", type=str, help="Write baseline to file")
    scan_parser.add_argument(
        "--suggest-tuning",
        dest="suggest_tuning",
        action="store_true",
        help="Show checkpoint tuning suggestions after scan results",
    )

    # author
    author_parser = subparsers.add_parser(
        "author", help="Generate checkpoint definitions from a guideline document"
    )
    author_parser.add_argument(
        "--from",
        dest="guideline_file",
        required=True,
        metavar="FILE",
        help="Path to guideline document (markdown, txt, etc.)",
    )
    author_parser.add_argument(
        "--output",
        type=str,
        default="author-prompt.md",
        metavar="FILE",
        help="Output file for the generated prompt (default: author-prompt.md)",
    )

    # badge
    subparsers.add_parser("badge", help="Generate a README badge from the current readiness score")

    # decisions
    subparsers.add_parser("decisions", help="Show all active and expired accepted risks")

    # history
    history_parser = subparsers.add_parser(
        "history", help="Show readiness trend from committed baseline snapshots"
    )
    history_parser.add_argument(
        "baselines",
        nargs="*",
        help="Paths to baseline JSON files (default: auto-discovers in .readiness/)",
    )

    # items
    items_parser = subparsers.add_parser("items", help="Manage work items")
    items_parser.add_argument("--create", action="store_true", help="Create work items for gaps")
    items_parser.add_argument("--verify", action="store_true", help="Verify work items vs code")
    items_parser.add_argument("--adapter", type=str, default="github", help="Adapter: github, ado, jira")
    items_parser.add_argument("--yes", "-y", action="store_true", help="Auto-approve all prompts")

    # aggregate
    agg_parser = subparsers.add_parser("aggregate", help="Cross-repo heatmap")
    agg_parser.add_argument("paths", nargs="*", help="Paths to baseline files")
    agg_parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.command == "init":
        sys.exit(cmd_init(args))
    elif args.command == "scan":
        sys.exit(cmd_scan(args))
    elif args.command == "author":
        sys.exit(cmd_author(args))
    elif args.command == "badge":
        sys.exit(cmd_badge(args))
    elif args.command == "decisions":
        sys.exit(cmd_decisions(args))
    elif args.command == "history":
        sys.exit(cmd_history(args))
    elif args.command == "items":
        sys.exit(cmd_items(args))
    elif args.command == "aggregate":
        sys.exit(cmd_aggregate(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
