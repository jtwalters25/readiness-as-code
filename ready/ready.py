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
    ready doctor                   Diagnose setup — validate config, JSON files, CI, adapters
    ready init                     Scaffold .readiness/ directory
    ready init --pack NAME         Use a specific checkpoint pack
    ready init --list-packs        List available checkpoint packs
    ready author --from FILE       Generate checkpoint prompt from a guideline doc
    ready decisions                Show all active and expired accepted risks
    ready history [BASELINES...]   Show readiness trend from baseline snapshots
    ready items --create           Propose + create work items
    ready items --verify           Cross-check work items vs code
    ready audit                    Audit exception health, definition staleness, and score health
    ready aggregate PATHS...       Cross-repo heatmap (CLI)
    ready aggregate PATHS... --html  Generate self-contained HTML heatmap report
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

from ready.validators import run_scan, Status, Severity


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
    "telemetry": (
        "telemetry",
        "Telemetry — logging, tracing, metrics, dashboards, and on-call registration",
    ),
}


def _find_examples_dir() -> str:
    """Locate the examples/ directory — bundled inside the package."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "examples"),        # installed via pip
        os.path.join(script_dir, "..", "examples"),  # legacy repo root location
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


VALID_SEVERITIES = {"red", "yellow"}
VALID_TYPES = {"code", "external", "hybrid"}
VALID_METHODS = {"file_exists", "glob", "grep", "grep_count", "file_count", "json_path", "external_attestation", "hybrid"}
VALID_CONFIDENCES = {"verified", "likely", "inconclusive"}


def _validate_definitions(path: str) -> list[str]:
    """
    Validate checkpoint-definitions.json for common mistakes.
    Returns a list of human-readable error strings (empty = valid).
    Does not require jsonschema — uses targeted field checks.
    """
    errors = []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON in {os.path.basename(path)}: {e}"]
    except IOError as e:
        return [f"Could not read {os.path.basename(path)}: {e}"]

    if not isinstance(data.get("checkpoints"), list):
        errors.append("Missing or invalid 'checkpoints' array at top level")
        return errors

    seen_ids: set[str] = set()
    for i, cp in enumerate(data["checkpoints"]):
        loc = f"checkpoint[{i}]"
        cp_id = cp.get("id", f"<index {i}>")
        loc = f"[{cp_id}]"

        # Required fields
        for field in ("id", "title", "severity", "type", "verification"):
            if field not in cp:
                errors.append(f"{loc} missing required field '{field}'")

        # Duplicate IDs
        if cp_id in seen_ids:
            errors.append(f"{loc} duplicate checkpoint id '{cp_id}'")
        seen_ids.add(cp_id)

        # severity must be lowercase "red" or "yellow"
        sev = cp.get("severity", "")
        if sev and sev not in VALID_SEVERITIES:
            hint = f" (did you mean '{sev.lower()}'?)" if sev.lower() in VALID_SEVERITIES else ""
            errors.append(f"{loc} invalid severity '{sev}'{hint} — must be 'red' or 'yellow'")

        # type must be code / external / hybrid
        cp_type = cp.get("type", "")
        if cp_type and cp_type not in VALID_TYPES:
            errors.append(f"{loc} invalid type '{cp_type}' — must be one of: {', '.join(sorted(VALID_TYPES))}")

        # verification block
        verification = cp.get("verification", {})
        if isinstance(verification, dict):
            method = verification.get("method", "")
            if method and method not in VALID_METHODS:
                errors.append(
                    f"{loc} unknown verification method '{method}' — "
                    f"valid methods: {', '.join(sorted(VALID_METHODS))}"
                )
            confidence = verification.get("confidence", "verified")
            if confidence not in VALID_CONFIDENCES:
                errors.append(
                    f"{loc} invalid confidence '{confidence}' — "
                    f"must be one of: {', '.join(sorted(VALID_CONFIDENCES))}"
                )
            # grep with no pattern
            if method in ("grep", "grep_count") and not verification.get("pattern"):
                errors.append(f"{loc} method '{method}' requires a 'pattern' field")
            # file_exists / glob with no pattern
            if method in ("file_exists", "glob") and not verification.get("pattern"):
                errors.append(f"{loc} method '{method}' requires a 'pattern' field")
            # json_path with no target or path
            if method == "json_path":
                if not verification.get("target"):
                    errors.append(f"{loc} method 'json_path' requires a 'target' field")
                if not verification.get("json_path"):
                    errors.append(f"{loc} method 'json_path' requires a 'json_path' field")

    return errors


def _validate_json_simple(path: str, expected_key: str) -> list[str]:
    """Validate that a JSON file loads and has the expected top-level key."""
    errors = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if expected_key not in data:
            errors.append(f"{os.path.basename(path)} missing '{expected_key}' key")
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in {os.path.basename(path)}: {e}")
    except IOError as e:
        errors.append(f"Could not read {os.path.basename(path)}: {e}")
    return errors


def cmd_doctor(args):
    """
    Diagnose your readiness-as-code setup.
    Checks JSON file validity, config, CI integration, and optional adapters.
    """
    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    all_errors: list[str] = []
    all_warnings: list[str] = []
    checks_passed = 0

    def ok(msg: str):
        nonlocal checks_passed
        checks_passed += 1
        print(f"  {GREEN}✓{RESET} {msg}")

    def warn(msg: str):
        all_warnings.append(msg)
        print(f"  {YELLOW}⚠{RESET} {msg}")

    def fail(msg: str):
        all_errors.append(msg)
        print(f"  {RED}✗{RESET} {msg}")

    def section(title: str):
        print(f"\n{BOLD}{title}{RESET}")

    print(f"\n{BOLD}ready doctor — {repo_root}{RESET}")

    # ── Python version ──────────────────────────────────────────────────────
    section("Python")
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        ok(f"Python {major}.{minor} (>= 3.10 required)")
    else:
        fail(f"Python {major}.{minor} — requires 3.10+. Upgrade your Python.")

    # ── .readiness/ directory ───────────────────────────────────────────────
    section(".readiness/")
    if not os.path.isdir(readiness_dir):
        fail(f"No .readiness/ directory found")
        print(f"\n  {CYAN}→ Run 'ready init' to scaffold one.{RESET}\n")
        # Can't check anything else
        _print_doctor_summary(checks_passed, all_errors, all_warnings)
        return 1 if all_errors else 0

    ok(".readiness/ exists")

    # checkpoint-definitions.json
    definitions_path = os.path.join(readiness_dir, DEFINITIONS_FILE)
    if not os.path.isfile(definitions_path):
        fail(f"Missing {DEFINITIONS_FILE}")
        print(f"    {CYAN}→ Run 'ready init' to recreate it.{RESET}")
    else:
        errs = _validate_definitions(definitions_path)
        if errs:
            for e in errs:
                fail(f"{DEFINITIONS_FILE}: {e}")
        else:
            try:
                with open(definitions_path) as f:
                    count = len(json.load(f).get("checkpoints", []))
                ok(f"{DEFINITIONS_FILE} valid ({count} checkpoints)")
            except Exception:
                ok(f"{DEFINITIONS_FILE} valid")

    # exceptions.json
    exceptions_path = os.path.join(readiness_dir, EXCEPTIONS_FILE)
    if os.path.isfile(exceptions_path):
        errs = _validate_json_simple(exceptions_path, "exceptions")
        if errs:
            for e in errs:
                fail(f"{EXCEPTIONS_FILE}: {e}")
        else:
            with open(exceptions_path) as f:
                count = len(json.load(f).get("exceptions", []))
            ok(f"{EXCEPTIONS_FILE} valid ({count} exceptions)")
    else:
        warn(f"{EXCEPTIONS_FILE} not found — that's fine if you have no accepted risks")

    # external-evidence.json
    evidence_path = os.path.join(readiness_dir, EVIDENCE_FILE)
    if os.path.isfile(evidence_path):
        errs = _validate_json_simple(evidence_path, "attestations")
        if errs:
            for e in errs:
                fail(f"{EVIDENCE_FILE}: {e}")
        else:
            with open(evidence_path) as f:
                count = len(json.load(f).get("attestations", []))
            ok(f"{EVIDENCE_FILE} valid ({count} attestations)")
    else:
        warn(f"{EVIDENCE_FILE} not found — needed for external/hybrid checkpoints")

    # config.json
    config_path = os.path.join(readiness_dir, "config.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            tags = cfg.get("service_tags", None)
            name = cfg.get("service_name", "")
            if tags is None:
                warn("config.json: 'service_tags' not set — all checks will run regardless of applicable_tags")
            elif not tags:
                warn("config.json: 'service_tags' is empty — service-specific checks will be skipped")
            else:
                ok(f"config.json valid (service: {name}, tags: {tags})")
        except (json.JSONDecodeError, IOError) as e:
            fail(f"config.json: {e}")
    else:
        warn("config.json not found — service tags won't be applied")

    # baseline
    baseline_path = os.path.join(readiness_dir, BASELINE_FILE)
    if os.path.isfile(baseline_path):
        ok(f"{BASELINE_FILE} exists (drift detection active)")
    else:
        warn(f"No {BASELINE_FILE} — run 'ready scan --baseline .readiness/{BASELINE_FILE}' to enable drift detection")

    # ── CI integration ──────────────────────────────────────────────────────
    section("CI integration")
    ci_found = False

    gh_workflows = os.path.join(repo_root, ".github", "workflows")
    if os.path.isdir(gh_workflows):
        yamls = [f for f in os.listdir(gh_workflows) if f.endswith((".yml", ".yaml"))]
        if yamls:
            ok(f"GitHub Actions: {len(yamls)} workflow(s) in .github/workflows/")
            ci_found = True

    for ci_file in ("azure-pipelines.yml", ".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml"):
        if os.path.isfile(os.path.join(repo_root, ci_file)):
            ok(f"CI config found: {ci_file}")
            ci_found = True

    if not ci_found:
        warn("No CI configuration found — copy a template from templates/ to enable PR gating")

    # ── Optional adapters ───────────────────────────────────────────────────
    section("Adapters (optional)")
    adapter_checks = [
        ("GitHub Issues",  [("GITHUB_TOKEN", "required"), ("GITHUB_REPOSITORY", "required")]),
        ("Azure DevOps",   [("AZURE_DEVOPS_ORG", "required"), ("AZURE_DEVOPS_PROJECT", "required"), ("AZURE_DEVOPS_PAT", "required")]),
        ("Jira",           [("JIRA_URL", "required"), ("JIRA_EMAIL", "required"), ("JIRA_API_TOKEN", "required"), ("JIRA_PROJECT", "required")]),
    ]

    any_adapter_configured = False
    for adapter_name, env_vars in adapter_checks:
        present = [(var, os.environ.get(var)) for var, _ in env_vars]
        set_vars = [var for var, val in present if val]
        if set_vars:
            any_adapter_configured = True
            missing = [var for var, val in present if not val]
            if missing:
                fail(f"{adapter_name}: partially configured — missing {', '.join(missing)}")
            else:
                ok(f"{adapter_name}: all required env vars set")

    if not any_adapter_configured:
        print(f"  {DIM}No adapters configured (GitHub Issues, Azure DevOps, Jira){RESET}")
        print(f"  {DIM}Set env vars to enable 'ready items' work item tracking.{RESET}")

    # ── MCP server ──────────────────────────────────────────────────────────
    section("MCP server (optional)")
    try:
        import importlib.util
        if importlib.util.find_spec("mcp") is not None:
            ok("mcp package installed — ready-mcp server available")
        else:
            print(f"  {DIM}mcp not installed — install with: pip install \"ready[mcp]\"{RESET}")
    except Exception:
        print(f"  {DIM}Could not check mcp installation{RESET}")

    _print_doctor_summary(checks_passed, all_errors, all_warnings)
    return 1 if all_errors else 0


def _print_doctor_summary(passed: int, errors: list[str], warnings: list[str]) -> None:
    print()
    if not errors and not warnings:
        print(f"{GREEN}✓ Everything looks good. ({passed} checks passed){RESET}")
    elif not errors:
        print(f"{YELLOW}⚠ {passed} checks passed, {len(warnings)} warning(s).{RESET}")
        print(f"{DIM}  Warnings won't break scanning but are worth reviewing.{RESET}")
    else:
        print(f"{RED}✗ {len(errors)} error(s) found.{RESET}  {passed} checks passed, {len(warnings)} warning(s).")
        print(f"{DIM}  Fix errors before running 'ready scan'.{RESET}")
    print()


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

    # Validate definitions before scanning — catch mistakes with helpful messages
    if os.path.isfile(definitions_path):
        validation_errors = _validate_definitions(definitions_path)
        if validation_errors:
            print(f"{RED}✗ Invalid checkpoint definitions — fix before scanning:{RESET}\n")
            for err in validation_errors:
                print(f"  {RED}•{RESET} {err}")
            print(f"\n{DIM}Run 'ready doctor' for a full setup check.{RESET}")
            return 1

    try:
        result = run_scan(
            repo_root=repo_root,
            definitions_path=definitions_path,
            evidence_path=evidence_path,
            exceptions_path=exceptions_path,
            service_tags=service_tags,
            service_name=service_name,
        )
    except json.JSONDecodeError as e:
        print(f"{RED}✗ JSON parse error in a .readiness/ file:{RESET}")
        print(f"  {e}")
        print(f"\n{DIM}Run 'ready doctor' to identify which file has the problem.{RESET}")
        return 1
    except Exception as e:
        print(f"{RED}✗ Scan failed unexpectedly:{RESET} {e}")
        print(f"\n{DIM}Run 'ready doctor' to check your setup, or 'ready scan --verbose' for more detail.{RESET}")
        return 1

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

        # Flag checkpoint definitions past their review_by date
        if os.path.isfile(definitions_path):
            try:
                with open(definitions_path) as _f:
                    _defs = json.load(_f)
                _today = datetime.date.today()
                _stale = [
                    cp for cp in _defs.get("checkpoints", [])
                    if cp.get("review_by") and datetime.date.fromisoformat(cp["review_by"]) < _today
                ]
                if _stale:
                    print(f"{YELLOW}definition review overdue ({len(_stale)}){RESET}")
                    for cp in _stale:
                        print(f"  {YELLOW}⏰{RESET} [{cp['id']}] {cp.get('title', '')}  {DIM}review_by {cp['review_by']}{RESET}")
                    print(f"  {DIM}Run 'ready audit' for a full health report.{RESET}")
                    print()
            except (ValueError, KeyError):
                pass

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
        from ready.adapters.github_issues import GitHubIssuesAdapter
        return GitHubIssuesAdapter()
    elif name in ("ado", "azure", "azuredevops"):
        from ready.adapters.ado import AzureDevOpsAdapter
        return AzureDevOpsAdapter()
    elif name == "jira":
        from ready.adapters.jira import JiraAdapter
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

    from ready.validators import run_scan, Status, Severity
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

            from ready.adapters import WorkItemDraft
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


def cmd_audit(args):
    """Audit exception health, definition staleness, and score health."""
    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)

    if not os.path.isdir(readiness_dir):
        print(f"{RED}✗ No {READINESS_DIR}/ found. Run 'ready init' first.{RESET}")
        return 1

    today = datetime.date.today()
    recommendations: list[str] = []
    has_critical = False

    # Load data
    exceptions_path = os.path.join(readiness_dir, EXCEPTIONS_FILE)
    definitions_path = os.path.join(readiness_dir, DEFINITIONS_FILE)
    baseline_path = os.path.join(readiness_dir, BASELINE_FILE)
    config_path = os.path.join(readiness_dir, "config.json")

    exceptions = []
    if os.path.isfile(exceptions_path):
        with open(exceptions_path) as f:
            exceptions = json.load(f).get("exceptions", [])

    checkpoints = []
    if os.path.isfile(definitions_path):
        with open(definitions_path) as f:
            checkpoints = json.load(f).get("checkpoints", [])

    baseline = None
    if os.path.isfile(baseline_path):
        with open(baseline_path) as f:
            baseline = json.load(f)

    service_name = os.path.basename(repo_root)
    if os.path.isfile(config_path):
        with open(config_path) as f:
            service_name = json.load(f).get("service_name", service_name)

    print(f"\n{BOLD}── Readiness Audit {'─' * 42}{RESET}")
    print(f"  Service: {BOLD}{service_name}{RESET}    As of: {today}")
    print()

    # ── Exception Health ──────────────────────────────────────────────────────
    print(f"{BOLD}Exception Health{RESET}")

    if not exceptions:
        print(f"  {GREEN}✓ No exceptions recorded.{RESET}")
    else:
        total_cp = len(checkpoints)
        total_exc = len(exceptions)
        exc_pct = round(total_exc / total_cp * 100) if total_cp else 0

        age_buckets: dict[str, list] = {"<30d": [], "30–90d": [], "90–180d": [], ">180d": [], "unknown": []}
        expiring_soon: list = []
        expired_list: list = []

        for exc in exceptions:
            accepted_str = exc.get("accepted_date", exc.get("created", ""))
            try:
                accepted = datetime.date.fromisoformat(accepted_str)
                age_days = (today - accepted).days
                if age_days < 30:
                    age_buckets["<30d"].append(exc)
                elif age_days < 90:
                    age_buckets["30–90d"].append(exc)
                elif age_days < 180:
                    age_buckets["90–180d"].append(exc)
                else:
                    age_buckets[">180d"].append(exc)
            except (ValueError, TypeError):
                age_buckets["unknown"].append(exc)

            expires_str = exc.get("expires", "")
            try:
                exp_date = datetime.date.fromisoformat(expires_str)
                days_left = (exp_date - today).days
                if days_left < 0:
                    expired_list.append(exc)
                elif days_left <= 30:
                    expiring_soon.append(exc)
            except (ValueError, TypeError):
                pass

        print(f"  Total: {BOLD}{total_exc}{RESET}  ({exc_pct}% of {total_cp} checkpoints excepted)")

        age_parts = []
        colors = {"<30d": GREEN, "30–90d": CYAN, "90–180d": YELLOW, ">180d": RED, "unknown": DIM}
        for bucket, color in colors.items():
            n = len(age_buckets[bucket])
            if n:
                age_parts.append(f"{color}{bucket}: {n}{RESET}")
        if age_parts:
            print(f"  Age distribution:  {' · '.join(age_parts)}")

        if expiring_soon:
            print(f"  {YELLOW}⚠  Expiring soon (≤30 days): {len(expiring_soon)}{RESET}")
            for exc in expiring_soon:
                cp_id = exc.get("checkpoint_id", "?")
                print(f"    {DIM}[{cp_id}] expires {exc.get('expires', '')}{RESET}")

        if expired_list:
            has_critical = True
            print(f"  {RED}✗  Expired (re-evaluation required): {len(expired_list)}{RESET}")
            for exc in expired_list:
                cp_id = exc.get("checkpoint_id", "?")
                print(f"    {DIM}[{cp_id}] expired {exc.get('expires', '')}{RESET}")
            recommendations.append(
                f"Re-evaluate {len(expired_list)} expired exception(s) — run 'ready decisions' to review them."
            )

        if len(age_buckets[">180d"]) > 0:
            recommendations.append(
                f"{len(age_buckets['>180d'])} exception(s) are >180 days old — verify they still reflect deliberate decisions."
            )

        if exc_pct > 30:
            recommendations.append(
                f"Exception rate is {exc_pct}% — high rates can hide systemic gaps. "
                "Consider addressing root causes rather than accepting indefinitely."
            )

    print()

    # ── Definition Health ─────────────────────────────────────────────────────
    print(f"{BOLD}Definition Health{RESET}")

    if not checkpoints:
        print(f"  {RED}✗ No checkpoint definitions found.{RESET}")
        recommendations.append("Add checkpoint definitions — run 'ready init' to scaffold a starter set.")
    else:
        total_cp = len(checkpoints)
        print(f"  Checkpoints: {BOLD}{total_cp}{RESET}")

        # File age
        if os.path.isfile(definitions_path):
            try:
                mtime = os.path.getmtime(definitions_path)
                mdate = datetime.date.fromtimestamp(mtime)
                age_days = (today - mdate).days
                color = GREEN if age_days < 90 else (YELLOW if age_days < 180 else RED)
                print(f"  Last modified: {color}{mdate}  ({age_days}d ago){RESET}")
                if age_days > 180:
                    recommendations.append(
                        f"Checkpoint definitions haven't been modified in {age_days} days — "
                        "review whether they still reflect current engineering standards."
                    )
            except OSError:
                pass

        # review_by coverage
        with_review_by = [cp for cp in checkpoints if cp.get("review_by")]
        past_review_by = []
        for cp in with_review_by:
            try:
                if datetime.date.fromisoformat(cp["review_by"]) < today:
                    past_review_by.append(cp)
            except (ValueError, TypeError):
                pass

        rb_pct = round(len(with_review_by) / total_cp * 100)
        rb_color = GREEN if rb_pct >= 80 else (YELLOW if rb_pct >= 40 else RED)
        print(f"  review_by coverage: {rb_color}{len(with_review_by)}/{total_cp} ({rb_pct}%){RESET}")

        if past_review_by:
            has_critical = True
            print(f"  {RED}✗  Past review_by date: {len(past_review_by)}{RESET}")
            for cp in past_review_by:
                print(f"    {DIM}[{cp['id']}] {cp.get('title', '')} — review_by {cp['review_by']}{RESET}")
            recommendations.append(
                f"{len(past_review_by)} checkpoint(s) are past their review_by date — "
                "update the definitions and set a new review_by date."
            )

        if rb_pct < 40:
            recommendations.append(
                f"Only {rb_pct}% of checkpoints have review_by dates — add review_by fields "
                "so definitions don't go stale silently."
            )

    print()

    # ── Score Health ──────────────────────────────────────────────────────────
    print(f"{BOLD}Score Health{RESET}")

    if not baseline:
        print(f"  {YELLOW}⚠ No baseline found.{RESET}")
        recommendations.append(
            "No committed baseline — run 'ready scan --baseline .readiness/review-baseline.json' "
            "and commit the file to enable drift tracking and audit history."
        )
    else:
        summary = baseline.get("summary", {})
        pct = summary.get("readiness_pct", 0)
        failing_red = summary.get("failing_red", 0)
        failing_yellow = summary.get("failing_yellow", 0)
        total = summary.get("total", 0)
        passing = summary.get("passing", 0)
        excepted_count = sum(1 for r in baseline.get("results", []) if r.get("status") == "exception")
        scan_time = baseline.get("scan_time", "unknown")[:10]

        pct_color = GREEN if pct >= 90 else (YELLOW if pct >= 70 else RED)
        print(f"  Score: {pct_color}{BOLD}{pct:.0f}%{RESET}   (baseline from {scan_time})")

        if failing_red:
            has_critical = True
            print(f"  {RED}Blocking failures: {failing_red}{RESET}")
            recommendations.append(
                f"{failing_red} blocking failure(s) in baseline — address these before going to review."
            )
        else:
            print(f"  {GREEN}✓ No blocking failures{RESET}")

        if failing_yellow:
            print(f"  {YELLOW}Warnings: {failing_yellow}{RESET}")

        if total > 0:
            exc_rate = round(excepted_count / total * 100)
            exc_color = GREEN if exc_rate <= 10 else (YELLOW if exc_rate <= 30 else RED)
            print(f"  Exception rate: {exc_color}{excepted_count}/{total} ({exc_rate}% accepted as risk){RESET}")
            passing_clean = passing - excepted_count if passing >= excepted_count else passing
            print(f"  Genuinely passing: {passing_clean}/{total}")

    print()

    # ── Recommendations ───────────────────────────────────────────────────────
    if recommendations:
        print(f"{BOLD}Recommendations{RESET}")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {CYAN}{i}.{RESET} {rec}")
        print()
    else:
        print(f"{GREEN}✓ No issues found — readiness system looks healthy.{RESET}")
        print()

    return 1 if has_critical else 0


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
    services = [b.get("service_name", f"service-{i}") for i, b in enumerate(all_results)]
    scores = {b.get("service_name", f"service-{i}"): b.get("summary", {}).get("readiness_pct", 0)
              for i, b in enumerate(all_results)}

    checkpoint_failures: dict[str, list[str]] = {}   # key -> [service, ...]
    checkpoint_titles: dict[str, str] = {}
    for baseline in all_results:
        svc = baseline.get("service_name", "unknown")
        for r in baseline.get("results", []):
            if r.get("status") in ("fail", "expired_exception"):
                cp_id = r.get("checkpoint_id", "")
                title = r.get("title", cp_id)
                key = cp_id
                checkpoint_titles[key] = title
                checkpoint_failures.setdefault(key, []).append(svc)

    total_services = len(all_results)

    if getattr(args, "html", False):
        return _aggregate_html(args, all_results, services, scores,
                               checkpoint_failures, checkpoint_titles, total_services)

    print(f"\n{BOLD}Cross-Repo Readiness Heatmap{RESET}")
    print(f"{DIM}{total_services} services analyzed{RESET}\n")

    if not checkpoint_failures:
        print(f"{GREEN}No systemic gaps found.{RESET}")
        return 0

    # Sort by most widespread
    sorted_gaps = sorted(
        checkpoint_failures.items(), key=lambda x: len(x[1]), reverse=True
    )

    for cp_id, failing_services in sorted_gaps:
        title = checkpoint_titles.get(cp_id, cp_id)
        count = len(failing_services)
        pct = round(count / total_services * 100)
        bar = "█" * count + "░" * (total_services - count)
        color = RED if pct > 50 else YELLOW
        print(f"  {color}{bar}{RESET} {count}/{total_services} ({pct}%) — {cp_id}: {title}")
        if args.verbose:
            for svc in failing_services:
                print(f"    {DIM}↳ {svc}{RESET}")

    print()
    return 0


def _aggregate_html(args, all_results, services, scores,
                    checkpoint_failures, checkpoint_titles, total_services) -> int:
    """Generate a self-contained HTML heatmap report."""
    output_file = getattr(args, "html_output", None) or "readiness-heatmap.html"

    # Sort checkpoints by most widespread failures
    sorted_checkpoints = sorted(
        checkpoint_failures.items(), key=lambda x: len(x[1]), reverse=True
    )

    # Build table data: for each checkpoint × service, was it a failure?
    def _cell_status(cp_id: str, svc: str) -> str:
        for baseline in all_results:
            if baseline.get("service_name") == svc:
                for r in baseline.get("results", []):
                    if r.get("checkpoint_id") == cp_id:
                        return r.get("status", "pass")
        return "pass"

    # Precompute all cell statuses
    cells: dict[tuple[str, str], str] = {}
    for baseline in all_results:
        svc = baseline.get("service_name", "unknown")
        for r in baseline.get("results", []):
            cp_id = r.get("checkpoint_id", "")
            cells[(cp_id, svc)] = r.get("status", "pass")

    def _svc_dot(pct: float) -> str:
        color = "#22c55e" if pct >= 90 else ("#f59e0b" if pct >= 70 else "#ef4444")
        return f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:4px;vertical-align:middle"></span>'

    # Build table rows
    rows_html = ""
    for cp_id, failing_svcs in sorted_checkpoints:
        title = checkpoint_titles.get(cp_id, cp_id)
        count = len(failing_svcs)
        pct_fail = round(count / total_services * 100)
        bar_color = "#ef4444" if pct_fail > 50 else "#f59e0b"
        bar_width = pct_fail

        cells_html = ""
        for svc in services:
            status = cells.get((cp_id, svc), "pass")
            if status in ("fail", "expired_exception"):
                cell_bg = "#fef2f2"
                cell_icon = '<span style="color:#ef4444;font-weight:bold">✗</span>'
            elif status == "exception":
                cell_bg = "#fffbeb"
                cell_icon = '<span style="color:#f59e0b">~</span>'
            elif status == "pass":
                cell_bg = "#f0fdf4"
                cell_icon = '<span style="color:#22c55e">✓</span>'
            else:
                cell_bg = "#f8fafc"
                cell_icon = '<span style="color:#94a3b8">—</span>'
            cells_html += f'<td style="background:{cell_bg};text-align:center;padding:6px 4px">{cell_icon}</td>'

        rows_html += f"""
        <tr>
          <td style="padding:6px 10px;white-space:nowrap">
            <span style="color:#64748b;font-size:11px">[{cp_id}]</span>
            <span style="margin-left:4px">{title}</span>
          </td>
          <td style="padding:6px 10px;text-align:center;font-size:12px;color:#64748b">{count}/{total_services}</td>
          <td style="padding:6px 10px;min-width:80px">
            <div style="background:#e2e8f0;border-radius:3px;height:8px;overflow:hidden">
              <div style="background:{bar_color};height:8px;width:{bar_width}%"></div>
            </div>
          </td>
          {cells_html}
        </tr>"""

    # Service header cells
    svc_headers = "".join(
        f'<th style="padding:8px 4px;text-align:center;font-size:12px;font-weight:500;'
        f'white-space:nowrap;max-width:90px;overflow:hidden;text-overflow:ellipsis" title="{svc}">'
        f'{_svc_dot(scores.get(svc, 0))}{svc[:14]}</th>'
        for svc in services
    )

    scan_date = datetime.date.today().isoformat()
    avg_score = round(sum(scores.values()) / len(scores)) if scores else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Readiness Heatmap — {scan_date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f8fafc; color: #1e293b; padding: 32px 24px; }}
  h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 13px; margin-bottom: 24px; }}
  .summary-cards {{ display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
           padding: 16px 20px; min-width: 140px; }}
  .card-label {{ font-size: 11px; color: #64748b; text-transform: uppercase;
                 letter-spacing: .05em; margin-bottom: 4px; }}
  .card-value {{ font-size: 28px; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;
           box-shadow: 0 1px 3px rgba(0,0,0,.06); font-size: 13px; }}
  thead th {{ background: #f1f5f9; padding: 10px 8px; text-align: left;
              font-weight: 600; border-bottom: 1px solid #e2e8f0; }}
  tbody tr:hover {{ background: #f8fafc; }}
  tbody tr {{ border-bottom: 1px solid #f1f5f9; }}
  .legend {{ display: flex; gap: 16px; margin-top: 16px; font-size: 12px;
             color: #64748b; }}
  .legend-item {{ display: flex; align-items: center; gap: 5px; }}
</style>
</head>
<body>
<h1>Cross-Repo Readiness Heatmap</h1>
<p class="meta">Generated {scan_date} &nbsp;·&nbsp; {total_services} services &nbsp;·&nbsp; {len(sorted_checkpoints)} gaps</p>

<div class="summary-cards">
  <div class="card">
    <div class="card-label">Services</div>
    <div class="card-value">{total_services}</div>
  </div>
  <div class="card">
    <div class="card-label">Avg Score</div>
    <div class="card-value" style="color:{'#22c55e' if avg_score >= 90 else ('#f59e0b' if avg_score >= 70 else '#ef4444')}">{avg_score}%</div>
  </div>
  <div class="card">
    <div class="card-label">Systemic Gaps</div>
    <div class="card-value" style="color:{'#ef4444' if sorted_checkpoints else '#22c55e'}">{len(sorted_checkpoints)}</div>
  </div>
  <div class="card">
    <div class="card-label">Most Widespread</div>
    <div class="card-value" style="font-size:16px;padding-top:6px">
      {'—' if not sorted_checkpoints else f'{round(len(sorted_checkpoints[0][1])/total_services*100)}% of services'}
    </div>
  </div>
</div>

<table>
  <thead>
    <tr>
      <th style="width:280px">Checkpoint</th>
      <th style="width:70px;text-align:center">Affected</th>
      <th style="width:90px">Spread</th>
      {svc_headers}
    </tr>
  </thead>
  <tbody>
    {rows_html if rows_html else '<tr><td colspan="100" style="text-align:center;padding:24px;color:#22c55e">No systemic gaps found</td></tr>'}
  </tbody>
</table>

<div class="legend">
  <div class="legend-item"><span style="color:#ef4444;font-weight:bold">✗</span> Failing</div>
  <div class="legend-item"><span style="color:#f59e0b">~</span> Accepted risk</div>
  <div class="legend-item"><span style="color:#22c55e">✓</span> Passing</div>
  <div class="legend-item"><span style="color:#94a3b8">—</span> Skipped / N/A</div>
</div>
</body>
</html>"""

    with open(output_file, "w") as f:
        f.write(html)

    print(f"\n{GREEN}✓ HTML heatmap written to {output_file}{RESET}")
    print(f"  {DIM}{total_services} services · {len(sorted_checkpoints)} systemic gaps · avg score {avg_score}%{RESET}")
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
        help="Checkpoint pack: starter, web-api, security-baseline, telemetry (default: starter)",
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

    # doctor
    subparsers.add_parser("doctor", help="Diagnose your setup — validate config, JSON files, CI, and adapters")

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

    # audit
    subparsers.add_parser("audit", help="Audit exception health, definition staleness, and score health")

    # aggregate
    agg_parser = subparsers.add_parser("aggregate", help="Cross-repo heatmap")
    agg_parser.add_argument("paths", nargs="*", help="Paths to baseline files")
    agg_parser.add_argument("--verbose", "-v", action="store_true")
    agg_parser.add_argument(
        "--html",
        dest="html",
        action="store_true",
        help="Generate self-contained HTML heatmap report",
    )
    agg_parser.add_argument(
        "--html-output",
        dest="html_output",
        type=str,
        default="readiness-heatmap.html",
        metavar="FILE",
        help="Output file for HTML report (default: readiness-heatmap.html)",
    )

    args = parser.parse_args()

    if args.command == "init":
        sys.exit(cmd_init(args))
    elif args.command == "doctor":
        sys.exit(cmd_doctor(args))
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
    elif args.command == "audit":
        sys.exit(cmd_audit(args))
    elif args.command == "aggregate":
        sys.exit(cmd_aggregate(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
