"""Self-contained HTML dashboard for a single service.

Generates a one-file dashboard from scan results + scan history that
can be opened in any browser, attached to a PR, or projected in a review.
"""

import datetime
import json


def generate_dashboard(
    scan_result: dict,
    history: list[dict],
    *,
    service_name: str = "",
    definitions: dict | None = None,
    exceptions: list[dict] | None = None,
) -> str:
    """Return a complete HTML string for the readiness dashboard."""
    exceptions = exceptions or []
    definitions = definitions or {}
    summary = scan_result.get("summary", {})
    results = scan_result.get("results", [])
    pct = summary.get("readiness_pct", 0)
    passing = summary.get("passing", 0)
    failing_red = summary.get("failing_red", 0)
    failing_yellow = summary.get("failing_yellow", 0)
    exc_count = summary.get("exceptions", 0)
    skipped = summary.get("skipped", 0)
    total = summary.get("total", 0)
    evaluated = total - skipped

    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    # Color ring
    if pct >= 90:
        ring_color = "#22c55e"
        status_label = "Ready"
    elif pct >= 70:
        ring_color = "#f59e0b"
        status_label = "At Risk"
    else:
        ring_color = "#ef4444"
        status_label = "Not Ready"

    # Blocking gaps
    blocking = [r for r in results
                if r.get("status") in ("fail", "expired_exception")
                and r.get("severity") == "red"]
    warnings = [r for r in results
                if r.get("status") in ("fail", "expired_exception")
                and r.get("severity") == "yellow"]

    # Sparkline data
    spark_points = [e.get("readiness_pct", 0) for e in history[-30:]]

    # Flapping analysis
    flip_counts: dict[str, int] = {}
    for i in range(1, len(history)):
        prev_cps = history[i - 1].get("checkpoints", {})
        curr_cps = history[i].get("checkpoints", {})
        for cp_id, curr in curr_cps.items():
            prev = prev_cps.get(cp_id)
            if prev and prev["status"] != curr["status"]:
                flip_counts[cp_id] = flip_counts.get(cp_id, 0) + 1
    flapping = sorted(
        [(k, v) for k, v in flip_counts.items() if v >= 2],
        key=lambda x: -x[1],
    )[:8]

    # MTTR
    cp_times: dict[str, dict] = {}
    for event in history:
        ts = event.get("timestamp", "")
        for cp_id, cp_data in event.get("checkpoints", {}).items():
            if cp_id not in cp_times:
                cp_times[cp_id] = {"first_fail": None, "first_pass_after_fail": None, "severity": cp_data.get("severity", "yellow")}
            entry = cp_times[cp_id]
            if cp_data["status"] in ("fail", "expired_exception"):
                if not entry["first_fail"]:
                    entry["first_fail"] = ts
            elif cp_data["status"] == "pass":
                if entry["first_fail"] and not entry["first_pass_after_fail"]:
                    entry["first_pass_after_fail"] = ts

    mttr_items = []
    for cp_id, t in cp_times.items():
        if t["first_fail"] and t["first_pass_after_fail"]:
            try:
                delta = (datetime.datetime.fromisoformat(t["first_pass_after_fail"])
                         - datetime.datetime.fromisoformat(t["first_fail"]))
                hours = delta.total_seconds() / 3600
                mttr_items.append((cp_id, hours, t["severity"]))
            except ValueError:
                pass
    mttr_items.sort(key=lambda x: -x[1])

    # Build HTML sections
    blocking_cards = ""
    for gap in blocking:
        title = gap.get("title", gap.get("checkpoint_id", ""))
        fix = gap.get("fix_hint", "")
        section = gap.get("guideline_section", "")
        evidence = gap.get("evidence", [])
        ev_html = "".join(f'<div class="ev">{e}</div>' for e in evidence[:3])
        blocking_cards += f'''
        <div class="gap-card red">
          <div class="gap-header">
            <span class="gap-severity">BLOCKING</span>
            <span class="gap-section">{section}</span>
          </div>
          <div class="gap-title">{title}</div>
          {f'<div class="gap-fix">{fix}</div>' if fix else ''}
          {ev_html}
        </div>'''

    warning_cards = ""
    for gap in warnings[:6]:
        title = gap.get("title", gap.get("checkpoint_id", ""))
        fix = gap.get("fix_hint", "")
        warning_cards += f'''
        <div class="gap-card yellow">
          <div class="gap-header">
            <span class="gap-severity warn">WARNING</span>
          </div>
          <div class="gap-title">{title}</div>
          {f'<div class="gap-fix">{fix}</div>' if fix else ''}
        </div>'''

    # Flapping section
    flapping_html = ""
    if flapping:
        for cp_id, flips in flapping:
            bar_w = min(flips * 12, 100)
            flapping_html += f'''
            <div class="flap-row">
              <span class="flap-id">{cp_id}</span>
              <div class="flap-bar-bg"><div class="flap-bar" style="width:{bar_w}%"></div></div>
              <span class="flap-count">{flips}x</span>
            </div>'''
    else:
        flapping_html = '<div class="empty">No flapping checks detected.</div>'

    # MTTR section
    mttr_html = ""
    if mttr_items:
        for cp_id, hours, sev in mttr_items[:5]:
            sev_class = "red" if sev == "red" else "yellow"
            if hours < 1:
                time_str = f"{hours * 60:.0f}m"
            elif hours < 24:
                time_str = f"{hours:.1f}h"
            else:
                time_str = f"{hours / 24:.1f}d"
            mttr_html += f'''
            <div class="mttr-row">
              <span class="mttr-dot {sev_class}"></span>
              <span class="mttr-id">{cp_id}</span>
              <span class="mttr-time">{time_str}</span>
            </div>'''
    else:
        mttr_html = '<div class="empty">Not enough history to calculate MTTR.</div>'

    # Sparkline SVG
    spark_svg = ""
    if len(spark_points) >= 2:
        w, h = 240, 48
        n = len(spark_points)
        min_v = max(0, min(spark_points) - 5)
        max_v = min(100, max(spark_points) + 5)
        rng = max_v - min_v or 1
        points = []
        for i, v in enumerate(spark_points):
            x = i / (n - 1) * w
            y = h - ((v - min_v) / rng * h)
            points.append(f"{x:.1f},{y:.1f}")
        polyline = " ".join(points)
        last_x, last_y = points[-1].split(",")
        spark_svg = f'''
        <svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="overflow:visible">
          <polyline points="{polyline}" fill="none" stroke="{ring_color}" stroke-width="2" stroke-linejoin="round"/>
          <circle cx="{last_x}" cy="{last_y}" r="3" fill="{ring_color}"/>
        </svg>'''

    # Trajectory
    trajectory_html = ""
    if len(spark_points) >= 2:
        delta = spark_points[-1] - spark_points[0]
        if delta > 1:
            trajectory_html = f'<span class="trend up">▲ +{delta:.0f}%</span>'
        elif delta < -1:
            trajectory_html = f'<span class="trend down">▼ {delta:.0f}%</span>'
        else:
            trajectory_html = '<span class="trend flat">— Stable</span>'

    # Passing by section
    passing_items = [r for r in results if r.get("status") == "pass"]
    sections: dict[str, int] = {}
    for r in passing_items:
        sec = r.get("guideline_section", "Other")
        sections[sec] = sections.get(sec, 0) + 1

    passing_section_html = ""
    for sec in sorted(sections.keys()):
        cnt = sections[sec]
        passing_section_html += f'<div class="pass-row"><span class="pass-sec">{sec}</span><span class="pass-cnt">{cnt}</span></div>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Readiness Dashboard — {service_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0f172a; color: #e2e8f0; padding: 32px 24px; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}

  /* Header */
  .header {{ display: flex; align-items: center; gap: 32px; margin-bottom: 32px; flex-wrap: wrap; }}
  .hero {{ text-align: center; min-width: 160px; }}
  .ring {{ width: 140px; height: 140px; border-radius: 50%;
           background: conic-gradient({ring_color} {pct * 3.6}deg, #1e293b {pct * 3.6}deg);
           display: flex; align-items: center; justify-content: center; margin: 0 auto 8px; }}
  .ring-inner {{ width: 110px; height: 110px; border-radius: 50%; background: #0f172a;
                 display: flex; align-items: center; justify-content: center;
                 flex-direction: column; }}
  .ring-pct {{ font-size: 32px; font-weight: 700; color: {ring_color}; line-height: 1; }}
  .ring-label {{ font-size: 11px; color: #94a3b8; text-transform: uppercase;
                 letter-spacing: .08em; margin-top: 2px; }}
  .status-badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px;
                   font-size: 11px; font-weight: 600; background: {ring_color}22;
                   color: {ring_color}; text-transform: uppercase; letter-spacing: .05em; }}
  .header-right {{ flex: 1; min-width: 240px; }}
  h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
  .spark-box {{ margin-bottom: 8px; }}
  .trend {{ font-size: 13px; font-weight: 600; }}
  .trend.up {{ color: #22c55e; }}
  .trend.down {{ color: #ef4444; }}
  .trend.flat {{ color: #94a3b8; }}

  /* Summary cards */
  .cards {{ display: flex; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px;
           padding: 14px 18px; flex: 1; min-width: 120px; }}
  .card-num {{ font-size: 28px; font-weight: 700; line-height: 1.1; }}
  .card-label {{ font-size: 11px; color: #64748b; text-transform: uppercase;
                 letter-spacing: .05em; margin-top: 4px; }}
  .c-green {{ color: #22c55e; }}
  .c-red {{ color: #ef4444; }}
  .c-yellow {{ color: #f59e0b; }}
  .c-blue {{ color: #3b82f6; }}

  /* Grid layout */
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 700px) {{ .grid {{ grid-template-columns: 1fr; }} }}

  .panel {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; }}
  .panel-title {{ font-size: 13px; font-weight: 600; text-transform: uppercase;
                  letter-spacing: .06em; color: #94a3b8; margin-bottom: 14px; }}
  .panel-full {{ grid-column: 1 / -1; }}

  /* Gap cards */
  .gap-card {{ background: #0f172a; border-radius: 6px; padding: 12px 14px; margin-bottom: 10px; }}
  .gap-card.red {{ border-left: 3px solid #ef4444; }}
  .gap-card.yellow {{ border-left: 3px solid #f59e0b; }}
  .gap-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
  .gap-severity {{ font-size: 10px; font-weight: 700; color: #ef4444;
                   text-transform: uppercase; letter-spacing: .08em; }}
  .gap-severity.warn {{ color: #f59e0b; }}
  .gap-section {{ font-size: 11px; color: #64748b; }}
  .gap-title {{ font-size: 14px; font-weight: 500; margin-bottom: 4px; }}
  .gap-fix {{ font-size: 12px; color: #94a3b8; margin-top: 4px; }}
  .ev {{ font-size: 11px; color: #64748b; font-family: monospace; margin-top: 2px; }}

  /* Flapping */
  .flap-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .flap-id {{ font-size: 12px; color: #94a3b8; min-width: 120px; font-family: monospace; }}
  .flap-bar-bg {{ flex: 1; height: 6px; background: #334155; border-radius: 3px; overflow: hidden; }}
  .flap-bar {{ height: 6px; background: #f59e0b; border-radius: 3px; }}
  .flap-count {{ font-size: 12px; color: #f59e0b; font-weight: 600; min-width: 30px; text-align: right; }}

  /* MTTR */
  .mttr-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .mttr-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
  .mttr-dot.red {{ background: #ef4444; }}
  .mttr-dot.yellow {{ background: #f59e0b; }}
  .mttr-id {{ font-size: 12px; color: #94a3b8; flex: 1; font-family: monospace; }}
  .mttr-time {{ font-size: 14px; font-weight: 600; color: #e2e8f0; }}

  /* Passing */
  .pass-row {{ display: flex; justify-content: space-between; padding: 4px 0;
               border-bottom: 1px solid #334155; }}
  .pass-sec {{ font-size: 13px; }}
  .pass-cnt {{ font-size: 13px; color: #22c55e; font-weight: 600; }}

  .empty {{ color: #64748b; font-size: 13px; font-style: italic; }}
  .footer {{ text-align: center; color: #475569; font-size: 11px; margin-top: 32px; }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="hero">
      <div class="ring"><div class="ring-inner">
        <div class="ring-pct">{pct:.0f}%</div>
        <div class="ring-label">readiness</div>
      </div></div>
      <div class="status-badge">{status_label}</div>
    </div>
    <div class="header-right">
      <h1>{service_name}</h1>
      <div class="meta">{timestamp} &middot; {passing}/{evaluated} checks passing &middot; {len(history)} scans recorded</div>
      <div class="spark-box">{spark_svg}</div>
      {trajectory_html}
    </div>
  </div>

  <!-- Summary Cards -->
  <div class="cards">
    <div class="card"><div class="card-num c-green">{passing}</div><div class="card-label">Passing</div></div>
    <div class="card"><div class="card-num c-red">{failing_red}</div><div class="card-label">Blocking</div></div>
    <div class="card"><div class="card-num c-yellow">{failing_yellow}</div><div class="card-label">Warnings</div></div>
    <div class="card"><div class="card-num c-blue">{exc_count}</div><div class="card-label">Exceptions</div></div>
  </div>

  <!-- Main Grid -->
  <div class="grid">

    <!-- Blocking Gaps -->
    <div class="panel panel-full">
      <div class="panel-title">Blocking Gaps ({len(blocking)})</div>
      {blocking_cards if blocking_cards else '<div class="empty">No blocking issues. Ship it.</div>'}
    </div>

    <!-- Warnings -->
    <div class="panel">
      <div class="panel-title">Warnings ({len(warnings)})</div>
      {warning_cards if warning_cards else '<div class="empty">No warnings.</div>'}
    </div>

    <!-- Passing by Section -->
    <div class="panel">
      <div class="panel-title">Passing by Section</div>
      {passing_section_html if passing_section_html else '<div class="empty">No passing checks.</div>'}
    </div>

    <!-- Flapping -->
    <div class="panel">
      <div class="panel-title">Flapping Checks</div>
      {flapping_html}
    </div>

    <!-- MTTR -->
    <div class="panel">
      <div class="panel-title">Time to Remediate</div>
      {mttr_html}
    </div>

  </div>

  <div class="footer">Generated by <strong>readiness-as-code</strong> &middot; {timestamp}</div>
</div>
</body>
</html>'''
