"""Cross-repo leaderboard — ranked readiness comparison across services."""

import datetime


def generate_leaderboard_html(baselines: list[dict]) -> str:
    """Generate a self-contained HTML leaderboard from multiple baselines."""

    services = []
    for b in baselines:
        name = b.get("service_name", "unknown")
        s = b.get("summary", {})
        pct = s.get("readiness_pct", 0)
        passing = s.get("passing", 0)
        red = s.get("failing_red", 0)
        yellow = s.get("failing_yellow", 0)
        total = s.get("total", 0)
        services.append({
            "name": name,
            "pct": pct,
            "passing": passing,
            "red": red,
            "yellow": yellow,
            "total": total,
        })

    services.sort(key=lambda x: (-x["pct"], x["name"]))
    total_services = len(services)
    avg_score = round(sum(s["pct"] for s in services) / total_services) if total_services else 0
    ready_count = sum(1 for s in services if s["red"] == 0)
    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    avg_color = "#22c55e" if avg_score >= 90 else ("#f59e0b" if avg_score >= 70 else "#ef4444")

    rows = ""
    for rank, svc in enumerate(services, 1):
        pct = svc["pct"]
        color = "#22c55e" if pct >= 90 else ("#f59e0b" if pct >= 70 else "#ef4444")
        bar_w = round(pct)
        is_ready = "Ready" if svc["red"] == 0 else "Not Ready"
        ready_color = "#22c55e" if svc["red"] == 0 else "#ef4444"

        if rank == 1:
            medal = "🥇"
        elif rank == 2:
            medal = "🥈"
        elif rank == 3:
            medal = "🥉"
        else:
            medal = f'<span style="color:#64748b;font-size:12px">{rank}</span>'

        rows += f'''<tr>
          <td style="padding:10px 12px;text-align:center;font-size:16px;width:40px">{medal}</td>
          <td style="padding:10px 12px;font-weight:500">{svc["name"]}</td>
          <td style="padding:10px 12px;width:200px">
            <div style="display:flex;align-items:center;gap:8px">
              <div style="flex:1;background:#334155;border-radius:3px;height:8px;overflow:hidden">
                <div style="background:{color};height:8px;width:{bar_w}%;border-radius:3px"></div>
              </div>
              <span style="color:{color};font-weight:700;font-size:14px;min-width:42px;text-align:right">{pct:.0f}%</span>
            </div>
          </td>
          <td style="padding:10px 12px;text-align:center;font-size:13px;color:#22c55e">{svc["passing"]}</td>
          <td style="padding:10px 12px;text-align:center;font-size:13px;color:#ef4444">{svc["red"]}</td>
          <td style="padding:10px 12px;text-align:center;font-size:13px;color:#f59e0b">{svc["yellow"]}</td>
          <td style="padding:10px 12px;text-align:center">
            <span style="color:{ready_color};font-size:11px;font-weight:600">{is_ready}</span>
          </td>
        </tr>'''

    bottom_3 = services[-3:] if len(services) >= 3 else services
    bottom_names = ", ".join(s["name"] for s in bottom_3)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Readiness Leaderboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0f172a; color: #e2e8f0; padding: 32px 24px; }}
  .page {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 12px; margin-bottom: 24px; }}

  .kpi {{ display: flex; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }}
  .kpi-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px;
               padding: 14px 18px; flex: 1; min-width: 120px; }}
  .kpi-val {{ font-size: 26px; font-weight: 700; line-height: 1.1; }}
  .kpi-label {{ font-size: 10px; color: #64748b; text-transform: uppercase;
                letter-spacing: .05em; margin-top: 2px; }}

  table {{ width: 100%; border-collapse: collapse; background: #1e293b;
           border: 1px solid #334155; border-radius: 8px; overflow: hidden; }}
  thead th {{ background: #0f172a; padding: 10px 12px; text-align: left; font-weight: 600;
              font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }}
  tbody tr {{ border-bottom: 1px solid #0f172a; transition: background .15s; }}
  tbody tr:hover {{ background: #334155; }}
  .footer {{ text-align: center; color: #475569; font-size: 10px; margin-top: 28px; }}
</style>
</head>
<body>
<div class="page">
  <h1>Readiness Leaderboard</h1>
  <div class="meta">{timestamp} · {total_services} services ranked</div>

  <div class="kpi">
    <div class="kpi-card"><div class="kpi-val" style="color:{avg_color}">{avg_score}%</div><div class="kpi-label">Avg Score</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#22c55e">{ready_count}</div><div class="kpi-label">Ready</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#ef4444">{total_services - ready_count}</div><div class="kpi-label">Not Ready</div></div>
    <div class="kpi-card"><div class="kpi-val" style="color:#94a3b8">{total_services}</div><div class="kpi-label">Total Services</div></div>
  </div>

  <table>
    <thead>
      <tr>
        <th style="text-align:center">Rank</th>
        <th>Service</th>
        <th>Score</th>
        <th style="text-align:center">Pass</th>
        <th style="text-align:center">Block</th>
        <th style="text-align:center">Warn</th>
        <th style="text-align:center">Status</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <div class="footer">Generated by <strong>readiness-as-code</strong> · {timestamp}</div>
</div>
</body>
</html>'''
