# Getting Started

This guide walks you from zero to continuous readiness scanning in under 30 minutes.

## Prerequisites

- Python 3.10+
- A git repository you want to scan

## Step 1: Install (1 minute)

```bash
pip install readiness-as-code
```

Or clone the repo directly:

```bash
git clone https://github.com/jtwalters25/readiness-as-code.git
```

## Step 2: Initialize (1 minute)

Navigate to your repo and run:

```bash
cd your-repo
ready init
```

This creates a `.readiness/` directory with:

| File | Purpose |
|------|---------|
| `checkpoint-definitions.json` | 15 universal checks that apply to any codebase |
| `exceptions.json` | Empty — add accepted risks here |
| `external-evidence.json` | Empty — add attestations for non-code artifacts here |

## Step 3: First Scan (10 seconds)

```bash
ready scan
```

You'll see output like:

```
ready? — your-repo
Readiness: 73%  (11/15 passing)

🔴 RED — cannot ship (2)
   ✗ [sec-001] Security policy exists
   ✗ [ext-001] Monitoring dashboard configured

🟡 YELLOW — fix before launch (2)
   ○ [gen-002] License file exists
   ○ [ops-002] Logging configured

🟢 11 checks passing
```

Share this with your team — it's a starting point, not a report card.

## Step 4: Calibrate (1-2 weeks)

Run in report-only mode so nothing blocks PRs:

```bash
ready scan --calibrate
```

Walk through results with your team:

**Red items that are intentional?** Add an exception:

```json
// .readiness/exceptions.json
{
  "version": "1.0",
  "exceptions": [
    {
      "checkpoint_id": "ops-004",
      "justification": "CLI tool, not a containerized service",
      "accepted_by": "jwalters",
      "accepted_date": "2026-04-01",
      "expires": "2027-04-01"
    }
  ]
}
```

**External items you've already done?** Add attestation:

```json
// .readiness/external-evidence.json
{
  "version": "1.0",
  "attestations": [
    {
      "checkpoint_id": "monitoring_dashboard",
      "attested_by": "jwalters",
      "attested_date": "2026-04-01",
      "evidence_link": "https://grafana.internal/d/my-service",
      "expires": "2026-07-01"
    }
  ]
}
```

**Checks that don't apply?** Configure service tags in `.readiness/config.json`:

```json
{
  "service_name": "my-cli-tool",
  "service_tags": ["cli-tool"]
}
```

Checks tagged with `applicable_tags: ["web-api"]` will be automatically skipped.

## Step 5: Add Custom Checkpoints

The starter pack covers universal basics. Add your own team's requirements:

**Option A: Write them by hand**

See [Checkpoint Authoring Guide](checkpoint-authoring.md) for the full schema.

**Option B: Use the LLM skill**

If you use GitHub Copilot, Cursor, or Claude:

```
"Read our operational review guidelines at docs/ops-review.md 
and generate checkpoint definitions for each requirement."
```

The LLM skill at `copilot-skills/author-checkpoints.instructions.md` guides the model to produce properly structured JSON.

## Step 6: Enable PR Gating

When your team is calibrated and the noise is gone:

**GitHub Actions:**

```yaml
# .github/workflows/readiness.yml
name: Readiness Check
on: [pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install readiness-as-code
      - run: ready scan
```

**Azure Pipelines:**

```yaml
- script: |
    pip install readiness-as-code
    ready scan
  displayName: 'Readiness scan'
```

Red failures now block the PR. Yellow items are informational. Your team can't accidentally drift from what was reviewed.

## Step 7: Track Baselines Over Time

Write baselines on each scan:

```bash
ready scan --baseline .readiness/review-baseline.json
```

Commit the baseline to git. Now you have an auditable history of your compliance posture over time. Each scan can diff against the previous baseline to detect regressions.

## Next Steps

- [Verification Types](verification-types.md) — Deep dive on code, external, and hybrid checks
- [Checkpoint Authoring](checkpoint-authoring.md) — Writing custom checkpoint definitions
- [CI Integration](ci-integration.md) — Advanced pipeline configurations
- [Cross-Repo Aggregation](cross-repo-aggregation.md) — Organization-wide compliance heatmaps
