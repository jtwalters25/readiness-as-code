"""One-page executive scorecard — predict + dashboard + trends in a single artifact."""

import datetime
from collections import defaultdict


def generate_scorecard(
    scan_result: dict,
    history: list[dict],
    *,
    service_name: str = "",
    horizon_days: int = 7,
) -> str:
    summary = scan_result.get("summary", {})
    results = scan_result.get("results", [])
    pct = summary.get("readiness_pct", 0)
    passing = summary.get("passing", 0)
    failing_red = summary.get("failing_red", 0)
    failing_yellow = summary.get("failing_yellow", 0)
    exc_count = summary.get("exceptions", 0)
    total = summary.get("total", 0)
    skipped = summary.get("skipped", 0)
    evaluated = total - skipped

    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ring_color = "#22c55e" if pct >= 90 else ("#f59e0b" if pct >= 70 else "#ef4444")
    status_label = "Ready" if pct >= 90 else ("At Risk" if pct >= 70 else "Not Ready")

    # --- Drift velocity ---
    drift_per_day = 0.0
    projected = pct
    if len(history) >= 2:
        recent = history[-20:]
        timestamps = []
        scores = []
        for e in recent:
            try:
                ts = datetime.datetime.fromisoformat(e["timestamp"])
                timestamps.append(ts.timestamp())
                scores.append(e.get("readiness_pct", 0))
            except (ValueError, KeyError):
                pass
        if len(timestamps) >= 2:
            t_span = timestamps[-1] - timestamps[0]
            if t_span > 0:
                drift_per_day = (scores[-1] - scores[0]) / (t_span / 86400)
                projected = max(0, min(100, scores[-1] + drift_per_day * horizon_days))

    proj_color = "#22c55e" if projected >= 80 else ("#f59e0b" if projected >= 50 else "#ef4444")
    if abs(drift_per_day) < 0.1:
        drift_html = '<span style="color:#94a3b8">Stable</span>'
    elif drift_per_day > 0:
        drift_html = f'<span style="color:#22c55e">+{drift_per_day:.1f}%/day</span>'
    else:
        drift_html = f'<span style="color:#ef4444">{drift_per_day:.1f}%/day</span>'

    forecast_date = (datetime.datetime.now() + datetime.timedelta(days=horizon_days)).strftime("%b %d")

    # --- Sparkline ---
    spark_points = [e.get("readiness_pct", 0) for e in history[-30:]]
    spark_svg = ""
    if len(spark_points) >= 2:
        w, h = 280, 48
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
        lx, ly = points[-1].split(",")
        spark_svg = f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="overflow:visible">
          <polyline points="{polyline}" fill="none" stroke="{ring_color}" stroke-width="2" stroke-linejoin="round"/>
          <circle cx="{lx}" cy="{ly}" r="3" fill="{ring_color}"/>
        </svg>'''

    # --- Regression risk ---
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

    risk_rows = ""
    for cp_id, flips, fail_rate, score in at_risk[:5]:
        level = "HIGH" if score >= 1.5 else "MEDIUM"
        lcolor = "#ef4444" if score >= 1.5 else "#f59e0b"
        risk_rows += f'''<tr>
          <td style="padding:6px 10px;font-family:monospace;font-size:12px">{cp_id}</td>
          <td style="padding:6px 10px;text-align:center;font-size:12px;color:#94a3b8">{flips} flips</td>
          <td style="padding:6px 10px;text-align:center;font-size:12px;color:#94a3b8">{fail_rate:.0%}</td>
          <td style="padding:6px 10px;text-align:center"><span style="color:{lcolor};font-weight:600;font-size:11px">{level}</span></td>
        </tr>'''

    # --- Blocking gaps ---
    blocking = [r for r in results
                if r.get("status") in ("fail", "expired_exception")
                and r.get("severity") == "red"]
    blocking_rows = ""
    for gap in blocking[:6]:
        title = gap.get("title", gap.get("checkpoint_id", ""))
        fix = gap.get("fix_hint", "")
        blocking_rows += f'''<tr>
          <td style="padding:6px 10px"><span style="color:#ef4444;font-weight:600;font-size:11px;margin-right:6px">BLOCKING</span>{title}</td>
          <td style="padding:6px 10px;color:#94a3b8;font-size:12px">{fix}</td>
        </tr>'''

    # --- Chronic blockers ---
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

    chronic_rows = ""
    for cp_id, scans, days in chronic[:5]:
        age = f"{days}d" if days > 0 else "new"
        chronic_rows += f'''<tr>
          <td style="padding:6px 10px;font-family:monospace;font-size:12px">{cp_id}</td>
          <td style="padding:6px 10px;text-align:center;font-size:12px;color:#94a3b8">{scans} scans</td>
          <td style="padding:6px 10px;text-align:center;font-size:12px;color:#ef4444">{age}</td>
        </tr>'''

    # --- MTTR ---
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

    avg_mttr_str = "—"
    if mttr_items:
        avg_h = sum(h for _, h, _ in mttr_items) / len(mttr_items)
        avg_mttr_str = f"{avg_h:.1f}h" if avg_h < 24 else f"{avg_h/24:.1f}d"

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Readiness Scorecard — {service_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0f172a; color: #e2e8f0; padding: 32px 24px; }}
  .page {{ max-width: 900px; margin: 0 auto; }}
  .header {{ display: flex; align-items: center; gap: 28px; margin-bottom: 28px; flex-wrap: wrap; }}
  .ring {{ width: 120px; height: 120px; border-radius: 50%;
           background: conic-gradient({ring_color} {pct * 3.6}deg, #1e293b {pct * 3.6}deg);
           display: flex; align-items: center; justify-content: center; }}
  .ring-inner {{ width: 94px; height: 94px; border-radius: 50%; background: #0f172a;
                 display: flex; align-items: center; justify-content: center; flex-direction: column; }}
  .ring-pct {{ font-size: 28px; font-weight: 700; color: {ring_color}; line-height: 1; }}
  .ring-sub {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: .08em; }}
  .header-right {{ flex: 1; min-width: 200px; }}
  h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 2px; }}
  .meta {{ color: #64748b; font-size: 12px; margin-bottom: 10px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px;
            font-weight: 600; background: {ring_color}22; color: {ring_color};
            text-transform: uppercase; letter-spacing: .05em; margin-left: 8px; }}

  .kpi {{ display: flex; gap: 10px; margin-bottom: 24px; flex-wrap: wrap; }}
  .kpi-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px;
               padding: 12px 16px; flex: 1; min-width: 100px; }}
  .kpi-val {{ font-size: 22px; font-weight: 700; line-height: 1.1; }}
  .kpi-label {{ font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }}

  .forecast {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px;
               padding: 16px 20px; margin-bottom: 24px; display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }}
  .forecast-left {{ text-align: center; }}
  .forecast-arrow {{ font-size: 24px; font-weight: 700; }}
  .forecast-right {{ flex: 1; min-width: 200px; }}

  .section {{ margin-bottom: 20px; }}
  .section-title {{ font-size: 12px; font-weight: 600; text-transform: uppercase;
                    letter-spacing: .06em; color: #94a3b8; margin-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b;
           border: 1px solid #334155; border-radius: 8px; overflow: hidden; font-size: 13px; }}
  thead th {{ background: #0f172a; padding: 8px 10px; text-align: left; font-weight: 600;
              font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }}
  tbody tr {{ border-bottom: 1px solid #1e293b; }}
  tbody tr:hover {{ background: #334155; }}
  .empty {{ color: #64748b; font-size: 12px; font-style: italic; padding: 12px; }}
  .footer {{ text-align: center; color: #475569; font-size: 10px; margin-top: 28px; }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <div class="ring"><div class="ring-inner">
      <div class="ring-pct">{pct:.0f}%</div>
      <div class="ring-sub">readiness</div>
    </div></div>
    <div class="header-right">
      <h1>{service_name}<span class="badge">{status_label}</span></h1>
      <div class="meta">{timestamp} · {passing}/{evaluated} passing · {len(history)} scans</div>
      {spark_svg}
    </div>
  </div>

  <div class="kpi">
    <div class="kpi-card"><div class="kpi-val" style="color:#22c55e">{passing}</div><div class="kpi-label">Passing</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#ef4444">{failing_red}</div><div class="kpi-label">Blocking</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#f59e0b">{failing_yellow}</div><div class="kpi-label">Warnings</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#3b82f6">{exc_count}</div><div class="kpi-label">Exceptions</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#94a3b8">{avg_mttr_str}</div><div class="kpi-label">Avg MTTR</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#94a3b8">{len(at_risk)}</div><div class="kpi-label">At Risk</div></div>
  </div>

  <div class="forecast">
    <div class="forecast-left">
      <div class="forecast-arrow" style="color:{ring_color}">{pct:.0f}%</div>
      <div style="font-size:11px;color:#64748b">now</div>
    </div>
    <div style="font-size:20px;color:#475569">→</div>
    <div class="forecast-left">
      <div class="forecast-arrow" style="color:{proj_color}">{projected:.0f}%</div>
      <div style="font-size:11px;color:#64748b">{forecast_date}</div>
    </div>
    <div class="forecast-right">
      <div style="font-size:13px;margin-bottom:4px">Drift: {drift_html}</div>
      <div style="font-size:12px;color:#64748b">{horizon_days}-day forecast based on {len(history)} scans</div>
    </div>
  </div>

  {'<div class="section"><div class="section-title">Blocking Gaps (' + str(len(blocking)) + ')</div><table><thead><tr><th>Checkpoint</th><th>Fix</th></tr></thead><tbody>' + blocking_rows + '</tbody></table></div>' if blocking_rows else ''}

  {'<div class="section"><div class="section-title">Regression Risk (' + str(len(at_risk)) + ')</div><table><thead><tr><th>Checkpoint</th><th>Flips</th><th>Fail Rate</th><th>Risk</th></tr></thead><tbody>' + risk_rows + '</tbody></table></div>' if risk_rows else ''}

  {'<div class="section"><div class="section-title">Chronic Blockers (' + str(len(chronic)) + ')</div><table><thead><tr><th>Checkpoint</th><th>Scans</th><th>Age</th></tr></thead><tbody>' + chronic_rows + '</tbody></table></div>' if chronic_rows else ''}

  <div class="footer">Generated by <strong>readiness-as-code</strong> · {timestamp}</div>
</div>
</body>
</html>'''
