# Verification Types

Every checkpoint has one of three types, depending on where the evidence lives.

## Code Checkpoints

**What they check:** Files, patterns, and configurations inside the repository.

**How they work:** The scanner runs deterministic checks — grep, glob, file existence, JSON path queries — against the codebase. Results are pass/fail with file-path evidence.

**Verification methods:**

| Method | Use When | Example |
|--------|----------|---------|
| `file_exists` | A specific file should be present | README.md, Dockerfile |
| `glob` | Files matching a pattern should exist | `tests/**/*.py` with min_matches |
| `grep` | Source code should contain a pattern | Auth middleware, health endpoints |
| `grep` (min_matches: 0) | Source code should NOT contain a pattern | Hardcoded secrets, banned imports |
| `json_path` | A config value should be set | `$.logging.level` = `"info"` |

**Example:**

```json
{
  "id": "ops-007",
  "title": "Health check endpoint exists",
  "type": "code",
  "verification": {
    "method": "grep",
    "pattern": "(health|healthz|healthcheck|readyz|livez)",
    "target": "**/*.{py,ts,js,go,cs}",
    "min_matches": 1,
    "confidence": "likely"
  }
}
```

**Confidence levels:**

Not all code checks are equally deterministic. A `file_exists` check is certain. A grep for "health" might match a comment. Use the `confidence` field:

- `verified` (default) — Deterministic. File exists or doesn't. Hard fail on miss.
- `likely` — Pattern-based. Might miss valid implementations. Fails but flags as "verify manually if unexpected."
- `inconclusive` — Can't determine from code alone. Produces "needs review" instead of a hard fail.

## External Checkpoints

**What they check:** Artifacts that live outside the repository — monitoring dashboards, incident management registrations, SLO configurations, executive sign-offs.

**How they work:** A human records an attestation in `.readiness/external-evidence.json` with their identity, date, evidence link, and expiry. The scanner checks that the attestation exists and hasn't expired.

**Example definition:**

```json
{
  "id": "ext-001",
  "title": "Monitoring dashboard configured",
  "type": "external",
  "verification": {
    "method": "external_attestation",
    "attestation_key": "monitoring_dashboard"
  }
}
```

**Example attestation:**

```json
{
  "checkpoint_id": "monitoring_dashboard",
  "attested_by": "jwalters",
  "attested_date": "2026-03-15",
  "evidence_link": "https://grafana.internal/d/my-service-dashboard",
  "notes": "Includes request rate, error rate, latency P50/P99, and saturation panels",
  "expires": "2026-06-15"
}
```

**Important:** Attestation confirms existence, not adequacy. A dashboard can exist but be useless. For quality-sensitive external artifacts, pair with a judgment checkpoint or periodic human review.

**Expiry:** All external attestations should have an expiry date. When it passes, the scanner re-flags the checkpoint. This forces periodic re-verification instead of "attest once, forget forever."

## Hybrid Checkpoints

**What they check:** Requirements where both code AND an external artifact must be in place.

**How they work:** The scanner runs the code verification AND checks for an external attestation. Both must pass.

**Common use case:** Observability. The SDK must be wired in code (code check), AND the monitoring backend must be configured to receive the data (external attestation).

**Example:**

```json
{
  "id": "hyb-001",
  "title": "Observability SDK wired and backend configured",
  "type": "hybrid",
  "verification": {
    "method": "hybrid",
    "code_verification": {
      "method": "grep",
      "pattern": "(opentelemetry|applicationinsights|datadog)",
      "target": "**/*.{py,js,ts,go,cs}",
      "min_matches": 1,
      "confidence": "likely"
    },
    "attestation_key": "observability_backend"
  }
}
```

The scanner reports evidence from both sides:

```
[code] src/telemetry.py:3 — matched "opentelemetry"
[external] Attested by jwalters on 2026-03-15: https://otel-collector.internal/config
```

If code passes but external fails (or vice versa), the checkpoint fails with clear evidence of which side is missing.

## Choosing the Right Type

| If the evidence lives in... | Use | Example |
|----------------------------|-----|---------|
| The repo (files, code, configs) | `code` | Tests exist, health endpoint, no secrets |
| An external system | `external` | Dashboard, ICM registration, SLO config |
| Both the repo AND an external system | `hybrid` | SDK in code + backend configured |
| Human judgment only | `external` (with notes) | Architecture review, doc quality |
