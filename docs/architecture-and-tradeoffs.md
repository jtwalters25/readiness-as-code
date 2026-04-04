# Architecture & Tradeoffs

This document explains the key design decisions in readiness-as-code, what alternatives were considered, and why specific tradeoffs were made. It's written for engineers evaluating whether this system fits their organization, and for anyone interested in the thinking behind the design.

## Core Architectural Decision: Files, Not Infrastructure

The entire system is JSON definitions + a Python scanner + CI templates. No database, no server, no dashboard, no SaaS account.

**Why:** The adoption barrier for compliance tools is almost never technical — it's organizational. Every dependency you add (a server to maintain, an account to provision, a dashboard to configure) becomes a reason for a team to say "we'll set it up next quarter." By making the system a folder you drop into a repo, adoption becomes a PR.

**Tradeoff:** No centralized state. Cross-repo aggregation requires collecting baselines from multiple repos and running the aggregator manually or in a pipeline. A database-backed system could provide live dashboards. We chose adoption speed over centralized visibility, knowing that aggregation can be layered on later without changing the core model.

## Checkpoint Definitions: Data, Not Code

Review requirements are stored as structured JSON, not hardcoded in scanner logic. Each checkpoint specifies what to verify, how to verify it, what guideline it maps to, and what severity it carries.

**Why:** Guideline documents change. If checks are hardcoded in Python, every guideline update requires a code change, a review, a test cycle, and a deployment. With JSON definitions, a compliance team can update what gets checked without touching scanner code. The scanner is the engine; the definitions are the fuel.

**Tradeoff:** JSON is less expressive than code. Complex verification logic (e.g., "this config value should be present AND should reference a valid service principal") can't be expressed in a simple grep pattern. This is why we have the `confidence` field — checks that can't be fully determined by pattern matching are flagged as `likely` or `inconclusive` rather than producing false certainties.

**Alternative considered:** A DSL (domain-specific language) for checkpoint definitions, similar to Rego (OPA) or Sentinel (HashiCorp). Rejected because the learning curve would kill adoption. JSON is universally understood, and the LLM-assisted authoring skill compensates for the verbosity.

## Three Verification Types: Code, External, Hybrid

Not everything that matters lives in the repo. A monitoring dashboard, an incident management registration, or an executive sign-off are real requirements that can't be verified by scanning code.

**Why three types instead of just code scanning:**

- **Code checkpoints** handle what's deterministically verifiable in the repo. These are fast, automated, and high-confidence.
- **External checkpoints** handle artifacts that live outside the repo. These require a human to attest "I verified this" with their identity, a date, and evidence. The scanner checks that the attestation exists and hasn't expired.
- **Hybrid checkpoints** handle requirements where both sides must be in place. An observability SDK must be in the code AND the monitoring backend must be configured. Neither alone is sufficient.

**Tradeoff:** External attestations are trust-based. Someone can attest that a dashboard exists without it being useful. We mitigate this with expiry (attestations must be periodically renewed) and by explicitly labeling checks that require human judgment. But the system cannot verify the *quality* of an external artifact — only its *existence and recency*.

**Alternative considered:** Integrating directly with monitoring APIs, incident management APIs, etc. to verify external artifacts programmatically. Rejected because it would create coupling to specific vendors (Grafana, PagerDuty, Datadog, etc.), require credentials and network access, and violate the "no infrastructure" principle. The attestation model is vendor-agnostic and works offline.

## Confidence Levels: Verified, Likely, Inconclusive

Not all automated checks are equally certain. A `file_exists` check is deterministic. A grep for "health" in source files might match a comment, miss an implementation in a different language, or catch a false positive in test fixtures.

**Why:** Without confidence levels, every pattern-based check produces either a false certainty (hard fail when the implementation exists but doesn't match the regex) or gets tuned so loosely it catches nothing. Confidence levels let the scanner say "I'm not sure" instead of lying.

- `verified` — Deterministic. File exists or doesn't. Config value matches or doesn't.
- `likely` — Pattern-based. Probably right, but might miss valid implementations. Fails but with a "verify manually if unexpected" message.
- `inconclusive` — Can't determine from code alone. Produces "needs review" instead of a hard fail.

**Tradeoff:** Three states are more complex than pass/fail. Teams need to understand what "likely" means and how to respond. We decided this complexity is worth it because the alternative — binary pass/fail on heuristic checks — is the primary reason developers lose trust in compliance tools.

## Exceptions: Explicit, Justified, Expiring

Teams can acknowledge known gaps with a justification, a decision reference, and an expiry date. The scanner stops flagging the exception but re-flags it when the expiry passes.

**Why:** Every real system has intentional gaps. A service might not need a Dockerfile because it runs on a PaaS. A team might defer auth implementation to next sprint with an architecture decision on file. Without a mechanism to record these decisions, the scanner produces noise, and teams either ignore it or game it.

**Why expiry instead of permanent dismissal:** Permanent exceptions accumulate technical debt invisibly. A decision made in January might not be valid in July — the team changed, the architecture changed, the risk profile changed. Expiry forces periodic re-evaluation: "Is this still intentional, or did we just forget?"

**Tradeoff:** Exception management adds overhead. Teams need to write justifications, set expiry dates, and re-evaluate when they expire. We believe this overhead is the point — it makes risk acceptance a deliberate act rather than a passive one.

## Calibration Mode: Try Before You Enforce

New teams run in `--calibrate` mode before turning on PR gating. The scanner reports results but doesn't fail the build.

**Why:** If the first experience with a compliance tool is "your PR is blocked by 15 checks you've never seen," the tool gets removed before it proves its value. Calibration mode lets teams see their baseline, file exceptions for known gaps, tune definitions for false positives, and build trust in the results — before enforcement begins.

**This is the single most important adoption decision in the system.** The technical architecture doesn't matter if teams reject the tool on day one.

## Closed-Loop Work Item Tracking

Gaps link to work items. On subsequent scans, the scanner cross-references: if a work item is marked "Done" but the code still has the gap, it's flagged as a regression. If the code is fixed but the work item is still open, it's flagged as stale.

**Why:** The most common failure mode in compliance tracking is tickets getting closed without the underlying issue being resolved. Someone marks a PBI as "Done" because they believe the fix shipped, but the fix didn't actually address the check, or it was reverted, or it was merged to the wrong branch. Bidirectional verification catches this.

**Tradeoff:** Requires integration with a work item system (GitHub Issues, Azure DevOps, Jira). The adapter interface keeps this pluggable, but it's the one piece of the system that requires external credentials and API access.

## Cross-Repo Aggregation: Individual Audits → Organizational Intelligence

When multiple services use the same checkpoint definitions, their baselines can be aggregated into a heatmap showing systemic patterns.

**Why:** "This service is missing telemetry" is a team problem. "4 of 5 services are missing telemetry" is a platform problem that requires a different investment. Without aggregation, leadership makes team-by-team decisions when they should be making platform decisions.

**Tradeoff:** Aggregation assumes comparable definitions. Services with different review scopes or risk profiles should use different checkpoint packs, and the aggregator should group by `applicable_tags` to avoid misleading comparisons. We chose simplicity (compare all baselines) as the default, with tag-based grouping as an advanced feature.

## LLM-Assisted Authoring: Not Detection

The LLM skill helps *author* checkpoint definitions from guideline documents. It does not replace the deterministic scanner for detection.

**Why this separation matters:** Deterministic checks are reproducible, auditable, and fast. LLM evaluations are non-deterministic, expensive, and hard to audit. Using an LLM at authoring time (human reviews the output) gives you the productivity benefit without the reliability risk. The human remains in the loop for what matters: deciding what to check and whether the check is correct.

**Where LLM detection is appropriate:** The Copilot scan skill allows on-demand LLM evaluation for nuanced checks the scanner can't handle (documentation quality, architecture alignment, test coverage depth). These are explicitly labeled as "LLM assessments" with confidence levels, not mixed into the deterministic results.

## What This System Cannot Do

Transparency about limitations is a design feature, not a weakness.

- **Cannot verify quality of external artifacts.** A dashboard can exist and be useless. An attestation confirms existence, not adequacy.
- **Cannot prevent adversarial compliance.** A no-op health endpoint passes the grep check. Pattern matching confirms presence, not correctness. Depth-layered checks (multiple checks for the same requirement) and anomaly flagging (rapid gap closure) mitigate but don't eliminate this.
- **Cannot replace runtime validation.** The system verifies code-time and config-time properties. Whether the health endpoint actually returns 200 in production is a different system's job.
- **Cannot scale checkpoint authoring without investment.** Extracting verifiable checkpoints from a 40-page guideline document is skilled work. The LLM-assisted authoring reduces but doesn't eliminate this effort.

These are known boundaries, not bugs.
