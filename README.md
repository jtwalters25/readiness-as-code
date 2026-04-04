<p align="center">
  <img src="docs/assets/banner.svg" alt="Readiness as Code" width="600" />
</p>

<h3 align="center">
  Continuous review compliance — as a folder in your repo.
</h3>

<p align="center">
  No infrastructure. No SaaS. No subscription.<br/>
  JSON definitions + Python scanner + CI template.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> •
  <a href="docs/getting-started.md">Docs</a> •
  <a href="docs/architecture-and-tradeoffs.md">Architecture</a> •
  <a href="docs/checkpoint-authoring.md">Authoring</a> •
  <a href="docs/verification-types.md">Verification Types</a> •
  <a href="docs/ci-integration.md">CI Integration</a>
</p>

---

## Why This Exists

Most teams perform engineering, security, and operational reviews at a point in time. The moment the review ends, readiness begins to drift. Changes ship, telemetry gets removed, configs shift, exception handling gets altered — and nobody notices until an incident.

This project treats readiness as a **continuously evaluated property**: review criteria are expressed as code, exceptions are explicit and time-bound, drift is detected automatically, and human judgment is preserved but made visible.

It replaces **prep work**, not judgment.

## Before / After

| Before | After |
|--------|-------|
| Manual readiness checklists (hours) | Automated scan (seconds) |
| Point-in-time review ceremonies | Continuous compliance on every PR |
| Drift detected by incidents | Drift detected before merge |
| Tribal knowledge of what's missing | Structured gap list with file-path evidence |
| "Are we ready?" is a subjective question | "Are we ready?" has a deterministic answer |
| Accepted risks forgotten over time | Accepted risks expire and re-surface automatically |

## Quickstart

```bash
pip install readiness-as-code

cd your-repo
ready init          # scaffolds .readiness/ with starter checks
ready scan          # see your score instantly
```

```
ready? — your-service
Readiness: 80%  (8/10 passing)

🔴 RED — cannot ship (1)
   ✗ [gen-006] No secrets in code
     evidence: src/config.py:14

🟡 YELLOW — fix before launch (1)
   ○ [sec-001] Security policy exists

🟢 8 checks passing
```

Three commands. No config files. No accounts. No dashboards to deploy.

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
             (Red/Yellow/Green)   (closed-loop:         (aggregate baselines
              + exit code for      regression &          across services →
              CI gating)           staleness detection)   systemic patterns)
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

## Key Capabilities

**Three verification types.** Code checks scan your repo automatically. External checks track human attestations for artifacts outside the repo (dashboards, registrations, sign-offs). Hybrid checks require both. → [Details](docs/verification-types.md)

**Closed-loop work item tracking.** Gaps become tracked work items (GitHub Issues, Azure DevOps, Jira). If a ticket is closed but the code still fails → flagged as **regression**. If code is fixed but the ticket is still open → flagged as **stale**.

**Cross-repo aggregation.** Run `ready aggregate` across multiple baselines. *"Telemetry gaps in 4 of 5 services"* — that's a platform problem, not a team problem. Individual audits become organizational intelligence.

**Expiring accepted risks.** Teams can acknowledge known gaps with justification and an expiry date. The scanner respects them — then re-flags when the expiry passes. No more permanent dismissals.

**AI-assisted checkpoint authoring.** Don't write JSON by hand. Feed your guideline doc to any AI using the included skills. It proposes checkpoint definitions; you review and approve. Works with Claude, ChatGPT, Copilot, Cursor, or any model. → [Details](docs/checkpoint-authoring.md)

**CI gating on every PR.** The scanner exits non-zero on red failures. Drop the included template into GitHub Actions, Azure Pipelines, or GitLab CI. Teams can't accidentally drift from what was reviewed. → [Details](docs/ci-integration.md)

## Who This Is For

**Engineering teams** — Stop spending hours on review prep. Know your compliance posture at any time.

**Reviewers** — Arrive at reviews with a pre-populated, evidence-backed assessment. Spend the meeting on judgment calls, not discovery.

**Engineering leadership** — Compliance posture across all services in one view. Auditable trail of every decision.

## What This Is Not

- **Not a static analysis tool.** SonarQube checks code quality. This checks whether your service meets its review requirements.
- **Not a policy engine.** OPA/Sentinel enforce infra policies at deploy time. This tracks operational and engineering readiness across code and non-code artifacts.
- **Not a compliance SaaS.** Drata/RegScale automate regulatory frameworks. This enforces your team's own internal review standards.
- **Not a replacement for review meetings.** This replaces the prep work so the meeting can focus on judgment calls the scanner can't make.

## Commands

```bash
ready init                     # Scaffold .readiness/ directory
ready scan                     # Red/Yellow/Green scan
ready scan --verbose           # Full detail with fix hints
ready scan --calibrate         # Report-only (no exit code failure)
ready scan --json              # Machine-readable output
ready scan --baseline FILE     # Write baseline snapshot
ready items --create           # Propose + create work items (human approves each)
ready items --verify           # Cross-check work items vs code
ready aggregate PATHS...       # Cross-repo heatmap from multiple baselines
```

## AI Integration

### MCP Server (Claude, Cursor, Copilot, any MCP client)

readiness-as-code ships a [Model Context Protocol](https://modelcontextprotocol.io) server so any AI assistant can run scans, inspect checkpoints, and aggregate results — no CLI required.

```bash
pip install "readiness-as-code[mcp]"
ready-mcp    # starts the MCP server on stdio
```

Configure your AI tool to launch `ready-mcp` and it gains four tools:

| Tool | Description |
|------|-------------|
| `scan_repo` | Full readiness scan with Red/Yellow/Green results |
| `list_checkpoints` | View all checkpoint definitions |
| `explain_checkpoint` | Deep-dive on a specific check (great after a failure) |
| `aggregate_baselines` | Cross-repo heatmap for systemic gap detection |

**→ [Setup instructions for Claude Desktop, Cursor, VS Code, and more](mcp/README.md)**

### AI Skills (prompt-based, any model)

For AI tools without MCP support, use the prompt skills in `ai-skills/`:

```
# Claude / Claude Code
Read ai-skills/author-checkpoints.instructions.md and generate checkpoints from docs/ops-review.md

# Cursor
@ai-skills/scan.instructions.md  →  Scan this repo for readiness

# GitHub Copilot
#file:ai-skills/author-checkpoints.instructions.md
```

Works with Claude, ChatGPT, Copilot, Cursor, Gemini — any model that can read a file.

## Design Principles

1. **Detection, not decisions.** The scanner finds gaps. Humans decide what to do.
2. **Continuous, not ceremonial.** Checked on every PR, not once a quarter.
3. **Portable, not hosted.** Files in your repo. No infrastructure.
4. **Evidence-backed, not trust-based.** Every assertion has a file path, attestation, or work item.
5. **Expiring, not permanent.** Accepted risks have expiry dates. Nothing is forever.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
