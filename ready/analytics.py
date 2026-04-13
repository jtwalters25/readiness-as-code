"""Scan history and analytics — trend analysis, checkpoint health, MTTR.

`ready scan` appends a structured event to .readiness/scan-history.json
on every run. `ready trends` and `ready health` read that log to surface
actionable insights.
"""

import datetime
import json
import os
import subprocess
from collections import defaultdict

SCAN_HISTORY_FILE = "scan-history.json"

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _get_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _detect_trigger() -> str:
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or os.environ.get("TF_BUILD"):
        return "ci"
    return "local"


def append_scan_event(readiness_dir: str, scan_result, duration_ms: int = 0) -> None:
    """Append a scan event to the history log."""
    history_path = os.path.join(readiness_dir, SCAN_HISTORY_FILE)

    if os.path.isfile(history_path):
        with open(history_path) as f:
            history = json.load(f)
    else:
        history = []

    checkpoints = {}
    for r in scan_result.results:
        checkpoints[r.checkpoint_id] = {
            "status": r.status.value,
            "severity": r.severity.value,
        }

    event = {
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "branch": _get_branch(),
        "trigger": _detect_trigger(),
        "service_name": scan_result.service_name,
        "readiness_pct": scan_result.readiness_pct,
        "passing": scan_result.passing,
        "failing_red": scan_result.failing_red,
        "failing_yellow": scan_result.failing_yellow,
        "exceptions": scan_result.exceptions,
        "skipped": scan_result.skipped,
        "total": scan_result.total,
        "duration_ms": duration_ms,
        "checkpoints": checkpoints,
    }

    history.append(event)
    os.makedirs(readiness_dir, exist_ok=True)
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)


def load_history(readiness_dir: str) -> list[dict]:
    history_path = os.path.join(readiness_dir, SCAN_HISTORY_FILE)
    if os.path.isfile(history_path):
        with open(history_path) as f:
            return json.load(f)
    return []


def cmd_trends(args) -> int:
    """Show readiness trends from scan history."""
    from ready.ready import find_repo_root, READINESS_DIR

    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)
    history = load_history(readiness_dir)

    if not history:
        print(f"{YELLOW}No scan history found. Run 'ready scan' to start building history.{RESET}")
        return 0

    limit = getattr(args, "last", 20)
    recent = history[-limit:]

    print(f"\n{BOLD}Readiness Trends — {recent[0].get('service_name', 'unknown')}{RESET}")
    print(f"{DIM}{len(history)} total scans, showing last {len(recent)}{RESET}\n")

    # Score timeline
    print(f"{BOLD}Score Timeline{RESET}")
    max_bar = 40
    for event in recent:
        pct = event.get("readiness_pct", 0)
        ts = event.get("timestamp", "")[:16].replace("T", " ")
        branch = event.get("branch", "?")
        trigger = event.get("trigger", "?")
        bar_len = int(pct / 100 * max_bar)
        color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
        bar = f"{color}{'█' * bar_len}{'░' * (max_bar - bar_len)}{RESET}"
        print(f"  {DIM}{ts}{RESET}  {bar}  {color}{pct:5.1f}%{RESET}  {DIM}{branch} ({trigger}){RESET}")

    # Trajectory
    if len(recent) >= 2:
        first_pct = recent[0].get("readiness_pct", 0)
        last_pct = recent[-1].get("readiness_pct", 0)
        delta = last_pct - first_pct
        if delta > 1:
            trend = f"{GREEN}▲ Improving (+{delta:.0f}%){RESET}"
        elif delta < -1:
            trend = f"{RED}▼ Declining ({delta:.0f}%){RESET}"
        else:
            trend = f"{CYAN}— Stable{RESET}"
        print(f"\n  Trajectory: {trend}")

    # Per-checkpoint flip analysis
    print(f"\n{BOLD}Checkpoint Volatility{RESET}")
    flip_counts: dict[str, int] = defaultdict(int)
    for i in range(1, len(recent)):
        prev_cps = recent[i - 1].get("checkpoints", {})
        curr_cps = recent[i].get("checkpoints", {})
        for cp_id, curr in curr_cps.items():
            prev = prev_cps.get(cp_id)
            if prev and prev["status"] != curr["status"]:
                flip_counts[cp_id] += 1

    if flip_counts:
        sorted_flips = sorted(flip_counts.items(), key=lambda x: -x[1])[:10]
        for cp_id, count in sorted_flips:
            indicator = f"{RED}⚡{RESET}" if count >= 3 else f"{YELLOW}~{RESET}"
            label = "flapping" if count >= 3 else "changed"
            print(f"  {indicator} {cp_id}: {count} flip{'s' if count != 1 else ''} ({label})")
    else:
        print(f"  {DIM}No status changes detected in recent scans.{RESET}")

    print()
    return 0


def cmd_health(args) -> int:
    """Analyze checkpoint health from scan history."""
    from ready.ready import find_repo_root, READINESS_DIR

    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)
    history = load_history(readiness_dir)

    if not history:
        print(f"{YELLOW}No scan history found. Run 'ready scan' to start building history.{RESET}")
        return 0

    print(f"\n{BOLD}Checkpoint Health Analysis{RESET}")
    print(f"{DIM}Based on {len(history)} scan{'s' if len(history) != 1 else ''}{RESET}\n")

    # Collect per-checkpoint stats
    cp_stats: dict[str, dict] = defaultdict(lambda: {
        "pass_count": 0,
        "fail_count": 0,
        "total": 0,
        "severity": "yellow",
        "first_fail": None,
        "first_pass_after_fail": None,
        "statuses": [],
    })

    for event in history:
        ts = event.get("timestamp", "")
        for cp_id, cp_data in event.get("checkpoints", {}).items():
            stats = cp_stats[cp_id]
            status = cp_data["status"]
            stats["severity"] = cp_data.get("severity", "yellow")
            stats["total"] += 1
            stats["statuses"].append(status)

            if status == "pass":
                stats["pass_count"] += 1
                if stats["first_fail"] and not stats["first_pass_after_fail"]:
                    stats["first_pass_after_fail"] = ts
            elif status in ("fail", "expired_exception"):
                stats["fail_count"] += 1
                if not stats["first_fail"]:
                    stats["first_fail"] = ts

    # Chronic red — never passed
    chronic = [(cp, s) for cp, s in cp_stats.items()
               if s["pass_count"] == 0 and s["fail_count"] > 0 and s["severity"] == "red"]
    if chronic:
        print(f"{RED}{BOLD}Chronic Red ({len(chronic)}){RESET} {DIM}— never passed, blocking{RESET}")
        for cp_id, stats in sorted(chronic, key=lambda x: -x[1]["fail_count"]):
            print(f"  {RED}✗{RESET} {cp_id}  {DIM}failed {stats['fail_count']}/{stats['total']} scans{RESET}")
        print()

    # Flapping — status changed 3+ times
    flapping = []
    for cp_id, stats in cp_stats.items():
        flips = sum(1 for i in range(1, len(stats["statuses"]))
                    if stats["statuses"][i] != stats["statuses"][i - 1])
        if flips >= 3:
            flapping.append((cp_id, flips, stats))

    if flapping:
        print(f"{YELLOW}{BOLD}Flapping ({len(flapping)}){RESET} {DIM}— unstable, investigate root cause{RESET}")
        for cp_id, flips, stats in sorted(flapping, key=lambda x: -x[1]):
            print(f"  {YELLOW}⚡{RESET} {cp_id}  {DIM}{flips} status changes across {stats['total']} scans{RESET}")
        print()

    # Stale green — always passed (potential low-value check)
    stale_green = [(cp, s) for cp, s in cp_stats.items()
                   if s["pass_count"] == s["total"] and s["total"] >= 5]
    if stale_green:
        print(f"{GREEN}{BOLD}Always Passing ({len(stale_green)}){RESET} {DIM}— may be too lenient or already addressed{RESET}")
        for cp_id, stats in sorted(stale_green, key=lambda x: -x[1]["total"])[:10]:
            print(f"  {GREEN}✓{RESET} {cp_id}  {DIM}passed {stats['total']}/{stats['total']} scans{RESET}")
        print()

    # MTTR — mean time to remediate (first fail → first pass after fail)
    mttr_data = []
    for cp_id, stats in cp_stats.items():
        if stats["first_fail"] and stats["first_pass_after_fail"]:
            try:
                t_fail = datetime.datetime.fromisoformat(stats["first_fail"])
                t_pass = datetime.datetime.fromisoformat(stats["first_pass_after_fail"])
                delta = t_pass - t_fail
                mttr_data.append((cp_id, delta, stats["severity"]))
            except ValueError:
                pass

    if mttr_data:
        print(f"{BOLD}Time to Remediate{RESET}")
        red_mttrs = [d for _, d, s in mttr_data if s == "red"]
        yellow_mttrs = [d for _, d, s in mttr_data if s == "yellow"]

        if red_mttrs:
            avg_red = sum(d.total_seconds() for d in red_mttrs) / len(red_mttrs)
            print(f"  {RED}Red (blocking):{RESET}  avg {_format_duration(avg_red)} across {len(red_mttrs)} check{'s' if len(red_mttrs) != 1 else ''}")
        if yellow_mttrs:
            avg_yellow = sum(d.total_seconds() for d in yellow_mttrs) / len(yellow_mttrs)
            print(f"  {YELLOW}Yellow (warning):{RESET} avg {_format_duration(avg_yellow)} across {len(yellow_mttrs)} check{'s' if len(yellow_mttrs) != 1 else ''}")

        print(f"\n  {DIM}Slowest to fix:{RESET}")
        for cp_id, delta, sev in sorted(mttr_data, key=lambda x: -x[1].total_seconds())[:5]:
            sev_color = RED if sev == "red" else YELLOW
            print(f"    {sev_color}•{RESET} {cp_id}: {_format_duration(delta.total_seconds())}")
        print()

    # Summary
    total_cps = len(cp_stats)
    healthy = total_cps - len(chronic) - len(flapping)
    print(f"{BOLD}Summary{RESET}")
    print(f"  {total_cps} checkpoints tracked")
    print(f"  {GREEN}{healthy} healthy{RESET}  {RED}{len(chronic)} chronic{RESET}  {YELLOW}{len(flapping)} flapping{RESET}  {GREEN}{len(stale_green)} always-pass{RESET}")
    print()
    return 0


def cmd_predict(args) -> int:
    """Predict readiness trajectory and flag at-risk checkpoints."""
    from ready.ready import find_repo_root, READINESS_DIR

    repo_root = find_repo_root()
    readiness_dir = os.path.join(repo_root, READINESS_DIR)
    history = load_history(readiness_dir)

    if len(history) < 3:
        print(f"{YELLOW}Need at least 3 scans for predictions. Run 'ready scan' a few more times.{RESET}")
        return 0

    horizon_days = getattr(args, "days", 7)

    print(f"\n{BOLD}Readiness Forecast{RESET}")
    print(f"{DIM}Based on {len(history)} scans, projecting {horizon_days} days{RESET}\n")

    # --- 1. Drift velocity: linear regression on recent scores ---
    recent = history[-20:]
    timestamps = []
    scores = []
    for event in recent:
        try:
            ts = datetime.datetime.fromisoformat(event["timestamp"])
            timestamps.append(ts.timestamp())
            scores.append(event.get("readiness_pct", 0))
        except (ValueError, KeyError):
            pass

    drift_per_day = 0.0
    projected_score = scores[-1] if scores else 0
    if len(timestamps) >= 2:
        t_span = timestamps[-1] - timestamps[0]
        if t_span > 0:
            drift_per_day = (scores[-1] - scores[0]) / (t_span / 86400)
            projected_score = max(0, min(100, scores[-1] + drift_per_day * horizon_days))

    current = scores[-1] if scores else 0
    if abs(drift_per_day) < 0.1:
        drift_label = f"{CYAN}— Stable{RESET}"
    elif drift_per_day > 0:
        drift_label = f"{GREEN}▲ +{drift_per_day:.1f}%/day{RESET}"
    else:
        drift_label = f"{RED}▼ {drift_per_day:.1f}%/day{RESET}"

    proj_color = GREEN if projected_score >= 80 else YELLOW if projected_score >= 50 else RED
    print(f"  {BOLD}Score trajectory:{RESET}  {current:.0f}% → {proj_color}{projected_score:.0f}%{RESET} in {horizon_days}d  ({drift_label})")

    if projected_score < 80 and current >= 80:
        days_to_drop = (current - 80) / abs(drift_per_day) if drift_per_day < -0.1 else 0
        if days_to_drop > 0:
            print(f"  {RED}⚠  Score will drop below 80% in ~{days_to_drop:.0f} days{RESET}")

    # --- 2. Regression risk: checkpoints likely to fail again ---
    print(f"\n{BOLD}Regression Risk{RESET} {DIM}— currently passing but historically unstable{RESET}")

    cp_history: dict[str, list[str]] = defaultdict(list)
    for event in history:
        for cp_id, cp_data in event.get("checkpoints", {}).items():
            cp_history[cp_id].append(cp_data["status"])

    at_risk = []
    for cp_id, statuses in cp_history.items():
        if not statuses or statuses[-1] != "pass":
            continue
        flips = sum(1 for i in range(1, len(statuses)) if statuses[i] != statuses[i - 1])
        fail_rate = sum(1 for s in statuses if s in ("fail", "expired_exception")) / len(statuses)
        if flips >= 2 or fail_rate >= 0.3:
            recent_fails = sum(1 for s in statuses[-5:] if s in ("fail", "expired_exception"))
            risk_score = (flips * 0.4) + (fail_rate * 0.3) + (recent_fails * 0.3)
            at_risk.append((cp_id, flips, fail_rate, risk_score))

    at_risk.sort(key=lambda x: -x[3])
    if at_risk:
        for cp_id, flips, fail_rate, risk_score in at_risk[:8]:
            risk_color = RED if risk_score >= 1.5 else YELLOW
            risk_label = "HIGH" if risk_score >= 1.5 else "MEDIUM"
            print(f"  {risk_color}⚡{RESET} {cp_id}  {DIM}{flips} flips, {fail_rate:.0%} failure rate{RESET}  [{risk_color}{risk_label}{RESET}]")
    else:
        print(f"  {GREEN}No at-risk checkpoints. All passing checks have stable history.{RESET}")

    # --- 3. Stale green: always passing, may be too lenient ---
    print(f"\n{BOLD}Stale Green{RESET} {DIM}— always passing, check may need tightening{RESET}")

    stale = []
    for cp_id, statuses in cp_history.items():
        if len(statuses) >= 10 and all(s == "pass" for s in statuses):
            stale.append((cp_id, len(statuses)))

    stale.sort(key=lambda x: -x[1])
    if stale:
        for cp_id, count in stale[:5]:
            print(f"  {DIM}✓{RESET} {cp_id}  {DIM}passed {count}/{count} scans — review if check is still meaningful{RESET}")
    else:
        print(f"  {DIM}No stale checks detected.{RESET}")

    # --- 4. Chronic blockers: never passed, longest-running ---
    print(f"\n{BOLD}Chronic Blockers{RESET} {DIM}— never passed, longest-running{RESET}")

    chronic = []
    for cp_id, statuses in cp_history.items():
        if all(s in ("fail", "expired_exception") for s in statuses) and len(statuses) >= 2:
            first_ts = None
            for event in history:
                if cp_id in event.get("checkpoints", {}):
                    try:
                        first_ts = datetime.datetime.fromisoformat(event["timestamp"])
                    except ValueError:
                        pass
                    break
            days_open = 0
            if first_ts:
                days_open = (datetime.datetime.now(tz=datetime.timezone.utc) - first_ts).days
            chronic.append((cp_id, len(statuses), days_open))

    chronic.sort(key=lambda x: -x[2])
    if chronic:
        for cp_id, scans, days in chronic[:5]:
            age = f"{days}d" if days > 0 else "recent"
            print(f"  {RED}✗{RESET} {cp_id}  {DIM}failed {scans} scans, open {age}{RESET}")
    else:
        print(f"  {GREEN}No chronic blockers.{RESET}")

    # --- Summary line ---
    print(f"\n{BOLD}Forecast:{RESET}  {current:.0f}% → {proj_color}{projected_score:.0f}%{RESET} by {(datetime.datetime.now() + datetime.timedelta(days=horizon_days)).strftime('%b %d')}", end="")
    if at_risk:
        print(f"  ·  {len(at_risk)} check{'s' if len(at_risk) != 1 else ''} at risk", end="")
    if chronic:
        print(f"  ·  {len(chronic)} chronic blocker{'s' if len(chronic) != 1 else ''}", end="")
    print("\n")
    return 0


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}m"
    elif seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    else:
        return f"{seconds / 86400:.1f}d"
