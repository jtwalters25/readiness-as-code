<p align="center">
  <img src="docs/assets/banner.svg" alt="ready" width="600" />
</p>

<h3 align="center">
  AI tools made your team faster. They didn't make your team safer.
</h3>

<p align="center">
  <strong>ready</strong> is the discipline layer that keeps pace with AI velocity —<br/>
  review criteria as committed definitions, evaluated on every change,<br/>
  with drift detected automatically before it becomes an incident.
</p>

<p align="center">
  No infrastructure. No SaaS. No subscription.<br/>
  JSON definitions + Python scanner + CI template.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> •
  <a href="docs/getting-started.md">Docs</a> •
  <a href="docs/architecture-and-tradeoffs.md">Architecture</a> •
  <a href="docs/verification-types.md">Verification Types</a> •
  <a href="docs/ci-integration.md">CI Integration</a>
</p>

<p align="center">
  <a href=".readiness/review-baseline.json">
    <img src="https://img.shields.io/badge/ready-100%25-brightgreen" alt="ready: 100%" />
  </a>
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License" />
</p>

---

## The Problem: Velocity Outran Discipline

AI coding tools removed the friction from writing and shipping code. They did not remove the friction from the discipline work — health checks, secrets hygiene, on-call registration, telemetry coverage, auth on every endpoint. That work is still human, still manual, still slow.

The result: **velocity is now AI-speed. Discipline is still person-speed.** The gap between the two is where incidents live.

This isn't a competence problem. The Claude Code source exposure, the wave of data breaches at otherwise-strong engineering orgs, the production breakdowns on services that passed code review — these are discipline failures caused by velocity. Smart teams moved fast, skipped the prep work, and found out later that the scaffolding wasn't there.

**Readiness as code** closes that gap. Review criteria are expressed as committed definitions. Every change is scanned against them. Exceptions are explicit and time-bound. The discipline layer runs at the same speed as the rest of the pipeline.

`ready` is the tool that implements this practice.

It replaces **prep work**, not judgment.

## Before / After

| Before | After |
|--------|-------|
| AI writes code in seconds; readiness checks take hours | Readiness checks run in the same pipeline, same pace |
| Manual checklists that can't keep up with AI velocity | Automated scan on every PR — no human bottleneck |
| Point-in-time review ceremonies | Continuous compliance, not a quarterly ritual |
| Drift detected by incidents | Drift detected before merge |
| Tribal knowledge of what's missing | Structured gap list with file-path evidence |
| "Are we ready?" is a subjective question | "Are we ready?" has a deterministic answer |
| Accepted risks forgotten over time | Accepted risks expire and re-surface automatically |

## Quickstart

```bash
pip install readiness-as-code

cd your-repo
ready scan
```

> **Windows / PATH issues?** Use `python -m ready scan` — works anywhere Python is installed.

```
ready? — your-service   80%   1 blocking · 2 warnings

  ✗ No secrets in code
    src/config.py:14
    → Remove hardcoded keys. Use environment variables or a secrets manager.

  + 2 warnings   (ready scan --verbose)
```

**No config. No accounts. No init required.** `ready scan` auto-detects your project type and runs immediately. When you're ready to customize, run `ready init`.

When everything is passing:

```
ready? — your-service   100%   ✓   ▲ +12%
```

One line. The drift indicator appears automatically whenever a committed baseline exists.

## How It Works

```
   Review Guidelines          checkpoint-definitions.json
  ┌─────────────────┐        ┌─────────────────────────┐
  │ "Health endpoint │  ───►  │ { "id": "ops-007",      │
  │  required"       │        │   "method": "grep",     │
  │ "Auth on all     │        │   "pattern": "health",  │
  │  endpoints"      │        │   "severity": "red" }   │
  └─────────────────┘        └───────────┬─────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │    ready scan        │
                              │                      │
                              │  Code checks ──────► grep, glob, file_exists
                              │  External checks ──► human attestations
                              │  Hybrid checks ────► both must pass
                              │                      │
                              │  Exceptions ────────► skip (if not expired)
                              │  Confidence ────────► verified / likely / inconclusive
                              └──────────┬──────────┘
                                         │
                    ┌────────────────────┬┴──────────────────┐
                    ▼                    ▼                    ▼
             Terminal Output      Work Item Tracking    Cross-Repo Heatmap
             (single line +       (closed-loop:         (aggregate baselines
              blocking items       regression &           across services →
              + CI exit code)      staleness detection)   systemic patterns)
```

## The Entire System

```
your-repo/
└── .readiness/
    ├── checkpoint-definitions.json   # What to check
    ├── exceptions.json               # Accepted risks + expiry
    ├── external-evidence.json        # Human attestations for non-code artifacts
    └── review-baseline.json          # Last scan snapshot (committed = audit trail)
```

Four JSON files and a scanner. That's it.

## Checkpoint Packs

Start with a curated pack, then customize:

```bash
ready init                                   # Universal starter (default)
ready init --pack web-api                    # REST/HTTP API checks
ready init --pack security-baseline          # Secrets, dependency hygiene, security policy
ready init --pack telemetry                  # Logging, tracing, metrics, dashboards
ready init --pack engineering-review         # Full engineering review (arch, security, testing, AI/RAI)
ready init --pack operational-review         # Operational readiness (SLOs, on-call, data, capacity)
ready init --pack governance                 # SDLC gates + external review attestations
ready init --list-packs                      # Show all available packs
```

| Pack | Checks | Best for |
|------|--------|----------|
| `starter` | 11 | Any repo |
| `web-api` | 17 | REST/HTTP services |
| `security-baseline` | 8 | Any repo with sensitive data |
| `telemetry` | 8 | Production services |
| `engineering-review` | 26 | Pre-launch engineering review |
| `operational-review` | 14 | Pre-launch operational review |
| `governance` | 15 | SDLC compliance + sign-off tracking |

## Key Capabilities

**Zero-config first run.** `ready scan` works immediately — no init, no config files. It auto-detects your project type and runs the most appropriate pack. Get your first score in under 15 seconds.

**Score-first output.** Default output is a single line. Blocking items appear below it with fix hints. Everything else is collapsed — run `--verbose` when you want the full picture.

**Auto-drift detection.** If a committed baseline exists, every scan shows a delta automatically: `▲ +12%` or `▼ -5%`. No flags, no extra commands.

**Three verification types.** Code checks scan your repo automatically. External checks track human attestations for artifacts outside the repo (dashboards, registrations, sign-offs). Hybrid checks require both. → [Details](docs/verification-types.md)

**Closed-loop work item tracking.** Gaps become tracked work items (GitHub Issues, Azure DevOps, Jira). If a ticket is closed but the code still fails → flagged as **regression**. If code is fixed but the ticket is still open → flagged as **stale**.

**Cross-repo aggregation.** Run `ready aggregate` across multiple baselines. *"Telemetry gaps in 4 of 5 services"* — that's a platform problem, not a team problem. Generate an HTML heatmap report leadership can actually read.

**Expiring accepted risks.** Teams can acknowledge known gaps with justification and an expiry date. The scanner respects them — then re-flags when the expiry passes. Nothing stays accepted forever by accident.

**Readiness audit.** `ready audit` reports the health of your readiness system itself — exception age distribution, definition staleness, review_by coverage, and score trend. Know when your discipline layer is drifting, not just your code.

**Codebase-aware checkpoint inference.** `ready infer` analyzes your repo — stack, frameworks, dependencies, ADRs, auth patterns, Docker config — and proposes tailored checkpoints with rationale. You approve each one before anything is written.

**AI-assisted checkpoint authoring.** `ready author --from guidelines.md` generates a ready-to-paste prompt combining your guideline document with authoring instructions. Paste it into any AI to generate checkpoint definitions. Works with Claude, ChatGPT, Copilot, Cursor, or any model.

**README badge.** `ready badge` generates a shields.io badge reflecting your committed readiness score. Paste it into your README.

**CI gating on every PR.** The scanner exits non-zero on red failures. Drop the included template into GitHub Actions, Azure Pipelines, or GitLab CI. → [Details](docs/ci-integration.md)

**Azure DevOps Marketplace extension.** First-class ADO integration: a pipeline task that runs `ready scan` and publishes every checkpoint as a test case in the Tests tab, plus a dashboard widget showing your score, trend sparkline, and blocking failure count across builds. → [Details](ado-extension/README.md)

## Who This Is For

**Teams using AI coding tools** — Copilot, Cursor, Claude Code, and their successors are accelerating how fast code gets written and shipped. `ready` is the enforcement layer that makes sure discipline scales at the same rate. The faster your team moves, the more you need it.

**Engineering teams** — Stop spending hours on review prep. Know your compliance posture at any time, on any branch, before anyone asks.

**Reviewers** — Arrive at reviews with a pre-populated, evidence-backed assessment. Spend the meeting on judgment calls, not discovery work the scanner already did.

**Engineering leadership** — Compliance posture across all services in one view. Auditable trail of every decision. An HTML heatmap showing systemic gaps — not anecdotes, not vibes.

## What This Is Not

- **Not a static analysis tool.** SonarQube checks code quality. This checks whether your service meets its review requirements.
- **Not a policy engine.** OPA/Sentinel enforce infra policies at deploy time. This tracks operational and engineering readiness across code and non-code artifacts.
- **Not a compliance SaaS.** Drata/RegScale automate regulatory frameworks. This enforces your team's own internal review standards.
- **Not a replacement for AI coding tools.** It's the complement to them — the discipline layer that keeps pace with the velocity they enable.
- **Not a replacement for review meetings.** This replaces the prep work so the meeting can focus on judgment calls the scanner can't make.

## Commands

```bash
# Scanning
ready scan                             # Score + blocking items
ready scan --verbose                   # Full detail — all checks, evidence, fix hints
ready scan --calibrate                 # Report-only (no exit code failure)
ready scan --json                      # Machine-readable output
ready scan --baseline FILE             # Write baseline snapshot (enables drift tracking)
ready scan --suggest-tuning            # Show pattern tuning suggestions after scan

# Setup
ready init                             # Scaffold .readiness/ with starter pack
ready init --pack web-api              # Scaffold with a specific pack
ready init --list-packs                # List available packs

# Authoring & inference
ready infer                            # Analyze codebase → propose tailored checkpoints (human approves each)
ready author --from FILE               # Generate AI prompt from a guideline document

# Audit trail
ready badge                            # Generate README badge from current score
ready decisions                        # Show all active, expiring, and expired exceptions
ready history [BASELINES...]           # Show readiness trend from baseline snapshots
ready audit                            # Audit exception health, definition staleness, and score health

# Work items
ready items --create                   # Propose + create work items (human approves each)
ready items --verify                   # Cross-check work items vs code

# Cross-repo
ready aggregate PATHS...               # Cross-repo heatmap from multiple baselines
ready aggregate PATHS... --html        # Generate self-contained HTML heatmap report
```

## AI Integration

### MCP Server (Claude, Cursor, Copilot, any MCP client)

ready ships a [Model Context Protocol](https://modelcontextprotocol.io) server so any AI assistant can run scans, inspect checkpoints, and aggregate results — no CLI required.

```bash
pip install "readiness-as-code[mcp]"
ready-mcp    # starts the MCP server on stdio
```

Configure your AI tool to launch `ready-mcp` and it gains four tools:

| Tool | Description |
|------|-------------|
| `scan_repo` | Full readiness scan with results |
| `list_checkpoints` | View all checkpoint definitions |
| `explain_checkpoint` | Deep-dive on a specific check |
| `aggregate_baselines` | Cross-repo heatmap for systemic gap detection |

**→ [Setup instructions for Claude Desktop, Cursor, VS Code, and more](mcp/README.md)**

### AI Skills (prompt-based, any model)

For deeper AI-assisted authoring, use `ready author` or the prompt skills in `ai-skills/`:

```bash
# Generate a checkpoint prompt from a guideline document
ready author --from docs/ops-review.md

# Then paste author-prompt.md into any AI:
# Claude:   "Read author-prompt.md and generate checkpoint definitions"
# Cursor:   @author-prompt.md
# Copilot:  #file:author-prompt.md
```

Works with Claude, ChatGPT, Copilot, Cursor, Gemini — any model that can read a file.

## Design Principles

These principles define what *readiness as code* means in practice. They are not implementation choices — they are the practice itself.

1. **Detection, not decisions.** The scanner finds gaps. Humans decide what to do.
2. **Continuous, not ceremonial.** Checked on every PR, not once a quarter.
3. **Velocity-aware, not velocity-hostile.** Designed to run at the speed of AI-assisted development — no human bottleneck in the loop.
4. **Portable, not hosted.** Files in your repo. No infrastructure.
5. **Evidence-backed, not trust-based.** Every assertion has a file path, attestation, or work item.
6. **Expiring, not permanent.** Accepted risks have expiry dates. Nothing is forever.
7. **Score-first, not report-first.** The answer to "are we ready?" is one line. Detail is on demand.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
