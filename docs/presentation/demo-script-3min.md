# Demo Script — 3 Minute Lightning Cut

**Audience:** Lightning talks, hackathon demos, investor pitch meetings where you get five slides and someone's already checking their phone.
**Runtime:** ~3 minutes. One villain. One demo. One close.
**Format:** Two-thirds of the time is the terminal. No "and one more thing" — earn the full version if you want it.

---

## Pre-Stage Checklist

- [ ] Terminal open, 48pt font, black background
- [ ] `demo-service/` repo prepped with hardcoded key in `src/config.py:14` and missing `/health`
- [ ] Commands in shell history
- [ ] Three slides total — villain, reveal, closing URL

---

## BEAT 1 — The Villain (30 seconds)

> *[Slide 1: **"AI writes code in seconds. Readiness reviews take weeks."**]*
>
> "Every team in this room just got 10x faster at writing code. Nobody got 10x faster at being safe.
>
> *[Pause.]*
>
> Production readiness — health checks, secrets hygiene, on-call, telemetry — is the last part of shipping software that still runs on a Google Doc.
>
> That gap is where every incident lives."

---

## BEAT 2 — The Reveal (20 seconds)

> *[Slide 2: the word **'ready'**]*
>
> "We built the discipline layer. No server, no SaaS, no account. Four JSON files and a scanner. Installs with pip. Runs on every PR.
>
> Let me show you."

---

## BEAT 3 — The Demo (90 seconds)

> "Service I've never seen before. Watch.

```bash
$ cd demo-service
$ ready scan
```

```
ready? — demo-service   62%   2 blocking · 3 warnings

  ✗ No secrets in code
    src/config.py:14
    → Remove hardcoded keys. Use environment variables or a secrets manager.

  ✗ Health check endpoint
    → Add a /health endpoint that returns 200 when the service is live.
```

> "**Fifteen seconds.** Auto-detected the stack. Found the secret. Gave me the line number and the fix.
>
> *[Switch to editor. Fix the secret. `os.environ['API_KEY']`. Save. Switch back.]*

```bash
$ ready scan
```

```
ready? — demo-service   71%   1 blocking · 3 warnings   ▲ +9%
```

> *[Point at the arrow.]*
>
> **I didn't ask for a diff. It just noticed.**
>
> Every scan, forever, tells you whether you're drifting. Without anyone asking. Without anyone remembering."

---

## BEAT 4 — The Close (25 seconds)

> *[Slide 3: **github.com/jtwalters25/readiness-as-code**]*
>
> "Every incident retro ends with the same sentence: *we should have caught this before launch.*
>
> This is the thing that would have caught it.
>
> Open source. Free. On GitHub today. **The discipline layer finally runs at the speed of the rest of your pipeline.**
>
> Thank you."

---

## What Got Cut (and why that's okay)

The 6-minute version has three demo beats — first scan, drift detection, closed-loop ticket reconciliation — plus a cross-repo aggregation "one more thing." The lightning cut keeps **first scan + drift** and drops the rest.

Why: the drift moment is the single most re-quotable beat. It's the thing people tell their colleagues about after the talk. Everything else is supporting evidence. When you have three minutes, you cut to the quote.

If you have four minutes, add back the `ready items --verify` beat. If you have five, add back the aggregate heatmap. If you have six, run the full script.

## The One Rule

**Do not pitch in a lightning talk.** The entire point of three minutes is that you get one demo and one line people repeat. Any sentence that isn't the villain, the demo, or the close is a sentence you need to cut.
