# CI Integration

`ready` is built to run in your pipeline, not as a one-off local command. The
scanner exits non-zero when there are blocking (red) failures, so any CI system
that fails a job on a non-zero exit code gates merges automatically.

Templates for three platforms ship in [`templates/`](../templates/). Each runs
the same scan and uploads the baseline snapshot as an artifact for drift
tracking.

## Gating behavior

`ready scan` exits with a non-zero status when at least one checkpoint fails at
red (blocking) severity. Warnings (yellow) do not fail the build. To report
without failing — useful when first adopting `ready` — run in calibrate mode:

```bash
ready scan --calibrate        # report-only, always exits 0
```

Writing a baseline on each run enables the drift indicator (`▲ +12%` / `▼ -5%`)
on subsequent scans:

```bash
ready scan --verbose --baseline .readiness/review-baseline.json
```

Commit the baseline to keep an audit trail of score over time.

## GitHub Actions

Two options.

**1. The published Action** (simplest — posts a PR comment with score and
blocking count):

```yaml
# .github/workflows/readiness.yml
name: Readiness Check
on: [pull_request]

jobs:
  readiness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: jtwalters25/readiness-as-code@v0.7.1
```

See the [GitHub Action section of the README](../README.md#github-action) for the
full list of inputs (`pack`, `fail-on-red`, `baseline`, `markdown`,
`fix-context`, `dashboard`, `args`) and outputs (`readiness-pct`, `failing-red`,
`failing-yellow`, `passing`, `is-ready`).

**2. The raw workflow template**
([`templates/github-actions.yml`](../templates/github-actions.yml)) — copy it to
`.github/workflows/readiness.yml` when you want direct control over the steps. It
runs on pull requests (ignoring `*.md` and `docs/**`), on a weekly Monday 08:00
UTC cron, and on manual dispatch. It uploads the baseline as an artifact
(90-day retention) and includes optional, opt-in Slack and Microsoft Teams
failure notifications gated on `SLACK_WEBHOOK_URL` / `TEAMS_WEBHOOK_URL` repo
secrets.

> This repository dogfoods that template: see
> [`.github/workflows/readiness.yml`](../.github/workflows/readiness.yml), which
> scans `ready` with `ready` on every PR.

## GitLab CI

Include [`templates/gitlab-ci.yml`](../templates/gitlab-ci.yml):

```yaml
include:
  - local: 'templates/gitlab-ci.yml'
```

The `readiness-scan` job runs in the `test` stage on merge-request pipelines,
scheduled pipelines, and manual (web) runs, and publishes the baseline as an
artifact with 90-day expiry.

## Azure Pipelines

Reference [`templates/azure-pipelines.yml`](../templates/azure-pipelines.yml) as
a stage. It exposes three parameters:

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `mode` | `full` \| `pr` \| `calibrate` | `full` | `calibrate` runs report-only (no build failure) |
| `failOnRed` | boolean | `true` | Whether blocking gaps fail the build |
| `pythonVersion` | string | `3.11` | Python version for the agent |

The `ReadinessCheck` stage installs `ready`, runs the scan (calibrate mode when
selected), and publishes the baseline via `PublishBuildArtifacts`.

For the Azure DevOps pipeline **extension** — which publishes each checkpoint as
a test case plus a dashboard widget — see
[`ado-extension/README.md`](../ado-extension/README.md).

## Related

- [Getting Started](getting-started.md)
- [Architecture & Tradeoffs](architecture-and-tradeoffs.md)
- [Verification Types](verification-types.md)
