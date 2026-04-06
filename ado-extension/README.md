# ready — Azure DevOps Extension

Brings **readiness as code** scores directly into Azure DevOps: a pipeline task that runs `ready scan` and publishes checkpoint results as test cases, and a dashboard widget that shows your score and trend.

---

## Components

### Pipeline Task — `ReadinessScan`

Runs `ready scan` in your pipeline. Each checkpoint becomes a test case in the Tests tab. Red failures block the build.

**Inputs**

| Input | Default | Description |
|---|---|---|
| `workingDirectory` | `$(Build.SourcesDirectory)` | Directory to scan |
| `pack` | (auto) | Force a checkpoint pack: `starter`, `web-api`, `security-baseline`, `telemetry` |
| `calibrate` | `false` | Report-only — results are published but build never fails |
| `failOnYellow` | `false` | Treat warning checkpoints as build failures |
| `publishResults` | `true` | Publish checkpoint results as JUnit test cases |
| `publishBaseline` | `true` | Publish scan result as `readiness-scan` build artifact |

**Output Variables**

| Variable | Description |
|---|---|
| `ready.score` | Readiness percentage (0–100) |
| `ready.blocking` | Red (blocking) failure count |
| `ready.warnings` | Yellow (warning) failure count |

**Pipeline example:**

```yaml
steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'

  - task: ReadinessScan@1
    inputs:
      workingDirectory: $(Build.SourcesDirectory)
      publishResults: true
      publishBaseline: true
```

---

### Dashboard Widget — Readiness Score

Reads the `readiness-scan` artifact published by the task and renders:

- Readiness score (large number)
- Status dot (green ≥90% / yellow ≥70% / red <70%)
- Drift vs previous build (▲ +5% / ▼ -3%)
- Blocking failure count
- Sparkline trend (last 10 builds)
- Service name + last scan time

Widget size: **2×1** tiles.

**Configuration:** Select the pipeline and branch in the widget config panel. No PAT required — uses your ADO session token.

---

## Build & Package

### Prerequisites

```bash
npm install -g tfx-cli
```

### Install dependencies

```bash
cd ado-extension
npm run install:all
```

### Build TypeScript

```bash
npm run build
```

### Package as .vsix

```bash
npm run package
# Produces: jtwalters25.ready-readiness-as-code-1.0.0.vsix
```

### Publish privately to your ADO org

```bash
# Set your org name in the script first
npm run publish-private
```

Or install the `.vsix` directly via Marketplace > Manage Extensions > Upload.

---

## Publisher Setup

1. Create a publisher at [marketplace.visualstudio.com/manage](https://marketplace.visualstudio.com/manage)
2. Use publisher ID `jtwalters25` (or update `vss-extension.json` with yours)
3. Generate a PAT with **Marketplace (Publish)** scope for `tfx extension publish`

---

## Verification Checklist

- [ ] `npm run build` compiles task and widget without errors
- [ ] Pipeline task runs against a repo with `.readiness/` — test results appear in Tests tab
- [ ] `readiness-scan` artifact is published with valid JSON
- [ ] `ready.score` pipeline variable is set after the task runs
- [ ] Widget renders score, dot color, and trend from the artifact
- [ ] Widget config panel populates pipeline dropdown from your project
- [ ] End-to-end: open PR → pipeline runs → red failure blocks → fix it → pipeline passes → widget updates
