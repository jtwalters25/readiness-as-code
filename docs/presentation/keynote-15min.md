# Keynote — 15 Minutes

**Audience:** DevTools keynote, QCon / re:Invent-style track, investor day with a technical audience, enterprise leadership summit.
**Runtime:** ~15 minutes. Five acts. Two demos. One category claim.
**Format:** Part keynote, part product demo. Build the case, prove it, then widen the lens.

The 6-minute script is a product demo. This is a **category talk** — you are not just showing a tool, you are naming a new category and claiming it.

---

## Structure at a Glance

| Act | Runtime | What happens |
|-----|---------|--------------|
| I. The Villain | 2:00 | Name the gap. Velocity vs. discipline. |
| II. The Category That Doesn't Exist | 2:30 | What every existing tool checks, and what none of them check. |
| III. The Reveal | 1:00 | Name the product. Name the practice. |
| IV. The Demo | 5:30 | Four live beats. Single repo → cross-repo. |
| V. The Claim | 2:30 | Category claim + call to action. |
| Buffer | 1:30 | Laughs, pauses, the unexpected. |

---

## ACT I — The Villain (2 minutes)

> *[Walk out. Black slide. Clicker in hand.]*
>
> "I want to start with a question I've been asking engineering leaders for two years.
>
> *[Slide: **'When was the last time a production incident at your company was caused by bad code?'**]*
>
> Think about it for a second. Your last big incident. Your last pager storm. Your last retro.
>
> *[Pause.]*
>
> It wasn't bad code. Was it.
>
> *[Click.]*
>
> *[Slide: list — **'No health endpoint. Missing alerts. Secrets in config. On-call not registered. Dashboard linked to the wrong service. Auth middleware disabled for testing and never re-enabled.'**]*
>
> It was **prep work that nobody did**. Or prep work that someone did six months ago and nobody checked again.
>
> That's the pattern. Every incident retro in every company I've ever worked with ends with the same sentence.
>
> *[Slide: **'We should have caught this before launch.'**]*
>
> And nobody — nobody — builds the thing that would have caught it.
>
> *[Walk across stage. Change tone.]*
>
> Here's what changed in the last two years that makes this urgent.
>
> *[Slide: a velocity curve going vertical]*
>
> Your team got 10x faster at writing code. Copilot, Cursor, Claude Code — pick your tool. The code side of the pipeline is now running at AI speed.
>
> *[Slide: a flat line labeled 'review meetings']*
>
> But the review side of the pipeline? The side where a human checks whether the service is actually **ready**? That's still a meeting on Thursday.
>
> *[Slide: the two curves overlaid. A shaded gap between them.]*
>
> **That gap is where every modern incident lives.** Velocity is AI-speed. Discipline is person-speed. And the faster the top curve goes, the wider the gap gets.
>
> *[Pause. Let it sit.]*"

---

## ACT II — The Category That Doesn't Exist (2:30)

> *[Slide: a 2x2 grid. Quality / Policy / Compliance / ??? ]*
>
> "I want to walk you through the tools every engineering org in this room already has.
>
> *[Click. Logo fills the first quadrant: SonarQube, CodeQL, Semgrep]*
>
> **Code quality.** These check whether your code is well-written. They run on every PR. They're great. They don't check whether your service has a health endpoint.
>
> *[Click. OPA, Sentinel, Checkov.]*
>
> **Policy as code.** These check whether your infra is configured correctly. They run at deploy time. They're great. They don't check whether you registered on-call.
>
> *[Click. Drata, Vanta, RegScale.]*
>
> **Compliance automation.** These check whether you meet SOC 2 or ISO 27001. They run continuously. They're great. They don't check whether your telemetry dashboard is linked to the right service.
>
> *[Click. The fourth quadrant is empty.]*
>
> *[Pause. Point at the empty quadrant.]*
>
> Nobody has built the tool for the fourth quadrant. **The thing that checks whether your service is actually ready to go to production** — not whether it compiles, not whether the infra is policy-compliant, not whether the regulators are happy. Whether **you**, as an engineering team, are prepared for what happens when this thing breaks at 3 AM.
>
> *[Slide: the fourth quadrant labeled **'Readiness as Code'**]*
>
> This is the category. And it has been missing for the entire history of software engineering. Not because it wasn't needed — every retro proves it was — but because nobody could make the economics work when the scaffolding required a server, a database, a dashboard, an account.
>
> *[Beat.]*
>
> Until now."

---

## ACT III — The Reveal (1 minute)

> *[Slide: the word **'ready'** alone on the screen.]*
>
> "This is `ready`. It is the reference implementation of readiness as code.
>
> Three things to know before I show you how it works.
>
> *[Slide: **'1. No infrastructure.'**]*
>
> Four JSON files and a Python scanner. That's the whole system. No server, no SaaS, no account, no dashboard to provision. **Adoption is a pull request.**
>
> *[Slide: **'2. Runs on every PR. Same pipeline as your tests.'**]*
>
> No ceremony. No quarterly review. No human bottleneck. The discipline layer runs at the same pace as the rest of your pipeline — because the rest of your pipeline is now running at AI speed.
>
> *[Slide: **'3. It already knows your stack.'**]*
>
> You don't write checkpoints from scratch. You run `ready infer`, it analyzes your repo, and it proposes a tailored set of checks you approve one at a time.
>
> *[Pause.]*
>
> Let me show you what that looks like."

---

## ACT IV — The Live Demo (5:30)

Four beats. Same as the 6-minute script but with space to breathe between them.

### Beat 1 — The 15-second first score (60 seconds)

> "This is a service a team shipped last week. I have never seen this repo before."

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

> "Fifteen seconds. No config. No init. No setup. It auto-detected this was a web API, picked the right pack, ran 12 checkpoints, and told us where we stand.
>
> Sixty-two percent ready. Two blocking issues. The file path. The line number. The fix.
>
> *[Look up.]*
>
> That's a pre-populated review meeting. That's two hours of prep work that nobody had to do."

### Beat 2 — The drift moment (75 seconds)

> "Now I'm going to commit a baseline."

```bash
$ ready scan --baseline .readiness/review-baseline.json
$ git add .readiness && git commit -m "Initial readiness baseline"
```

> "That's a snapshot of where this service is today. From now on, every scan compares against it.
>
> Watch what happens when I fix something.
>
> *[Switch to editor. Fix the hardcoded key.]*

```bash
$ ready scan
```

```
ready? — demo-service   71%   1 blocking · 3 warnings   ▲ +9%
```

> *[Point at the arrow. Pause.]*
>
> **I didn't pass a flag. I didn't run a diff command. It just noticed.**
>
> Every scan, forever, shows the delta. If you're getting better — up arrow. If you're getting worse — down arrow. Without anyone asking. Without anyone remembering.
>
> This is the thing that's been missing. Not 'are we compliant today' — 'are we **drifting**.'
>
> Because every team in this room has services that were at 95% a year ago and are at 70% today, and nobody noticed until the incident."

### Beat 3 — The closed loop (75 seconds)

> "One more. This is the part that actually changes how teams behave."

```bash
$ ready items --verify
```

```
⚠ REGRESSION  ISSUE-142 was closed, but health-check still fails
⚠ STALE       ISSUE-156 is still open, but the fix already landed
```

> *[Let it sit.]*
>
> Every team on Earth has tickets that got closed because someone wanted to clear a sprint. Every team on Earth has tickets that are still open months after the problem was fixed.
>
> **`ready` is the first thing I've ever seen that cross-checks your ticket system against your actual code.**
>
> When a ticket closes, it verifies the code still fails — if so, **regression**. When code gets fixed, it verifies the ticket is still open — if so, **stale**.
>
> That's not a scanner. That's a lie detector for your backlog. And backlogs have been lying to engineering leaders for thirty years."

### Beat 4 — The cross-repo heatmap (60 seconds)

> "And one more thing. Because everything I've shown you so far is one repo, one team.
>
> Every engineering leader in this room has a question they ask themselves every Monday morning:
>
> *[Slide: **'Which of my services is the next incident?'**]*

```bash
$ ready aggregate services/*/.readiness/review-baseline.json --html
```

> *[Open the generated HTML. A heatmap fills the screen. Red squares cluster in one row.]*
>
> *[Point at the row.]*
>
> Telemetry gaps. In four of five services.
>
> That is not a team problem. That is a **platform** problem. You have been hiring more SREs to fix it and it has been getting worse. Because until right now, you couldn't see that the pattern existed.
>
> One command. Five baselines. Systemic gap, identified.
>
> *[Pause.]*
>
> This is what 'readiness as code' unlocks that no existing category can touch."

---

## ACT V — The Claim (2:30)

> *[Walk to center stage. Close laptop lid.]*
>
> "I want to close on something harder than a demo.
>
> *[Slide: **'Readiness as Code'**]*
>
> Every category in modern software started the same way. Someone looked at work that was being done manually — slowly, expensively, inconsistently — and said *this should be code*.
>
> Infrastructure as code. Policy as code. Compliance as code.
>
> And every one of those categories was resisted at first, because the people doing the manual work thought the manual work was the valuable part. It wasn't. **The judgment was the valuable part.** The paperwork was just the paperwork.
>
> *[Beat.]*
>
> Production readiness is still where infrastructure was in 2012. Still manual. Still in Google Docs. Still a meeting on Thursday. Still the thing that gets skipped when velocity goes up.
>
> And every incident retro at every company I've ever talked to ends with the same sentence. *We should have caught this before launch.*
>
> *[Slide: **'The discipline layer finally runs at the speed of the rest of your pipeline.'**]*
>
> `ready` is the tool that implements the practice. It's open source. It's free. It's on GitHub today. It installs in one command, runs in fifteen seconds, and tells you the truth about your services in a single line.
>
> *[Slide: **github.com/jtwalters25/readiness-as-code**]*
>
> But the tool isn't the point. The tool is the proof that the category is possible.
>
> **Readiness as code is now a real thing.** It is going to get built, either by us or by someone else, because the gap between AI-speed velocity and person-speed discipline is getting wider every day and every engineering leader in this room knows it.
>
> We just happen to have a head start.
>
> *[Pause. Walk off.]*
>
> Thank you."

---

## Staging Notes

- **Two acts are stationary, two acts move.** Stand still for the villain. Pace for the category argument. Stand still at the laptop for the demo. Walk for the close. Movement signals act breaks.
- **The second demo is the hardest one.** The aggregate heatmap is the "one more thing" — rehearse the click-and-point flow more than any other beat. If the audience doesn't *see* the red cluster in the heatmap, the punch line is lost.
- **Do not read the slides.** Slides are punctuation. Say the words; let the slides confirm them two beats later.
- **Plant the category claim early.** Act II names "readiness as code" as the empty quadrant. Act V cashes the check. Don't improvise away from that structure — the payoff depends on the setup.
- **Buffer is non-negotiable.** A 15-minute talk needs 13:30 of material. If you run long, you will stop making eye contact, start reading slides, and lose the room. Cut one supporting beat per rehearsal until you hit 13:30 clean.

## What This Version Has That 6-min Doesn't

1. **The category map** (Act II). This is the strategic frame. Without it, the product looks like a linter. With it, the product looks like the Terraform of production readiness.
2. **The fourth demo beat** (cross-repo aggregation). In the 6-min version this is "one more thing"; here it's a full-weight demo with setup.
3. **The claim** (Act V). Categories are named, not discovered. A keynote is the right place to do the naming.
4. **Slower pacing.** The 6-min script hits every beat at run speed. The 15-min script has room for the pauses to land.

## What This Version Does NOT Have

- A product roadmap. Roadmaps belong in investor meetings, not keynotes.
- A competitive matrix. The category argument in Act II does that work implicitly — stating it explicitly makes you look defensive.
- A Q&A slide. End on the claim. If there's Q&A, let the conference organizer introduce it.
