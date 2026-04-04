# Web API Checkpoint Pack

Production readiness checks for REST/HTTP API services.

## What's Included

17 checkpoints covering:

**Code checks (12):** Health endpoint, authentication middleware, rate limiting, input validation, error handling, structured logging, request tracing, graceful shutdown, Dockerfile, API docs, timeouts, retry policies.

**External checks (4):** Monitoring dashboard, alerting, on-call rotation, runbook.

**Hybrid checks (1):** Observability SDK + backend configuration.

## Usage

Copy `checkpoint-definitions.json` into your `.readiness/` directory, or merge with your existing definitions:

```bash
cp examples/web-api/checkpoint-definitions.json .readiness/checkpoint-definitions.json
```

Set your service tags in `.readiness/config.json`:

```json
{
  "service_name": "my-api",
  "service_tags": ["web-api"]
}
```

Then scan:

```bash
ready scan --verbose
```

## Customization

These checks are opinionated starting points. You should:

- Adjust regex patterns if your framework uses different conventions
- Add exception entries for checks that don't apply to your specific service
- Add your own org-specific checks (SLO registration, deployment approval, etc.)
- Change severity levels based on your team's risk tolerance
