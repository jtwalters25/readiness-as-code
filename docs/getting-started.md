# Getting Started

This guide walks you from zero to continuous readiness scanning in under 15 minutes.

## Prerequisites

- Python 3.10+
- A git repository you want to scan

## Step 1: Install and scan (30 seconds)

```bash
pip install readiness-as-code

cd your-repo
ready scan
```

> **Windows / PATH issues?** Use `python -m ready scan` — works anywhere Python is installed.

No init. No config files. `ready scan` auto-detects your project type and runs immediately:

```
ready? — your-service   73%   1 blocking · 2 warnings

  ✗ No secrets in code
    src/config.py:14
    → Remove hardcoded keys. Use environment variables or a secrets manager.

  + 2 warnings   (ready scan --verbose)
```

Run `ready scan --verbose` to see everything — warnings, passing checks, exceptions, and fix hints for all failures.

## Step 2: Initialize to customize (1 minute)

When you're ready to commit your configuration, initialize a `.readiness/` directory:

```bash
ready init                                   # Universal starter (default)
ready init --pack web-api                    # REST/HTTP API checks
ready init --pack security-baseline          # Secrets, dependency hygiene, security policy
ready init --pack telemetry                  # Logging, tracing, metrics, dashboards
ready init --pack engineering-review         # Full engineering review (26 checks)
ready init --pack operational-review         # Operational readiness (14 checks)
ready init --pack governance                 # SDLC gates + attestations (15 checks)
ready init --list-packs                      # Show all available packs
```

This creates:

| File | Purpose |
|------|---------|
| `checkpoint-definitions.json` | The checks to run |
| `exceptions.json` | Accepted risks with expiry dates |
| `external-evidence.json` | Human attestations for non-code artifacts |
| `config.json` | Service name and tags |

Set your `service_tags` in `config.json` to enable service-specific checks:

```json
{
  "service_name": "my-api",
  "service_tags": ["web-api"]
}
```

## Step 3: Calibrate (1–2 weeks)

Run in report-only mode while your team reviews results:

```bash
ready scan --calibrate
```

This runs the full scan but never fails the exit code — useful while you tune definitions and file exceptions before turning on enforcement.

**Red items that are intentional?** Add an exception:

```json
// .readiness/exceptions.json
{
  "version": "1.0",
  "exceptions": [
    {
      "checkpoint_id": "ops-002",
      "justification": "CLI tool — containerization not applicable",
      "accepted_by": "jwalters",
      "accepted_date": "2026-04-01",
      "expires": "2027-04-01"
    }
  ]
}
```

**External items already done?** Add an attestation:

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

Run `ready decisions` at any time to see all active, expiring, and expired exceptions in one view.

## Step 4: Add custom checkpoints

Two ways to add checkpoints tailored to your codebase:

**Option A — Let ready analyze your stack:**

```bash
ready infer
```

`ready infer` reads your repo — frameworks, dependencies, auth patterns, ADRs, Docker config — and proposes checkpoints with rationale. You approve each one with `[y/n/e]` before anything is written.

**Option B — Generate from a guideline document:**

```bash
ready author --from docs/ops-review.md
```

This writes an `author-prompt.md` combining your guideline with authoring instructions. Paste it into any AI:

```
Claude:   "Read author-prompt.md and generate checkpoint definitions"
Cursor:   @author-prompt.md
Copilot:  #file:author-prompt.md
```

The AI proposes checkpoints; you review and approve each one before writing to `.readiness/checkpoint-definitions.json`.

See [Checkpoint Authoring](checkpoint-authoring.md) for the full schema if you prefer to write definitions by hand.

## Step 5: Enable PR gating

When your team is calibrated and noise is gone:

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

**GitLab CI:**

```yaml
readiness:
  script:
    - pip install readiness-as-code
    - ready scan
```

Red failures block the PR. Yellow items are informational. Teams can't accidentally drift from what was reviewed.

## Step 6: Track history and add a badge

Commit a baseline snapshot to enable drift tracking on every subsequent scan:

```bash
ready scan --baseline .readiness/review-baseline.json
git add .readiness/review-baseline.json
git commit -m "chore: add readiness baseline"
```

From now on, every `ready scan` shows the delta automatically:

```
ready? — your-service   85%   ✓   ▲ +12%
```

Generate a README badge:

```bash
ready badge
```

```
[![ready](https://img.shields.io/badge/ready-85%25-brightgreen)](.readiness/review-baseline.json)
```

Paste it at the top of your README. Teams and reviewers see your readiness score at a glance.

View trend over time:

```bash
ready history
```

## Next Steps

- [Verification Types](verification-types.md) — Code, external, and hybrid checks explained
- [Checkpoint Authoring](checkpoint-authoring.md) — Writing custom checkpoint definitions
- [CI Integration](ci-integration.md) — Advanced pipeline configurations
- [Cross-Repo Aggregation](cross-repo-aggregation.md) — Organization-wide compliance heatmaps
- [Architecture & Tradeoffs](architecture-and-tradeoffs.md) — Design decisions and why they were made
