# Demo Script — 6 Minutes

**Audience:** Engineering leaders, DevTools conferences, founder demos, investor meetings with technical operators in the room.
**Runtime:** ~6 minutes. Four acts. One "and one more thing."
**Format:** Live terminal demo. Backup video running on a second machine.

---

## Pre-Stage Checklist

- [ ] Terminal open, 48pt font, black background, white text
- [ ] Two repos prepped:
  - `demo-service/` — a web API deliberately missing a `/health` endpoint, with a hardcoded API key in `src/config.py:14`, and no on-call registration
  - `services/` — five sibling repos with committed baselines, four of which have telemetry gaps
- [ ] Commands pre-loaded in shell history (hit `↑` on stage, never type from scratch)
- [ ] A second monitor cued to a backup video of the demo in case of live failure
- [ ] Slides on clicker, black between beats

---

## ACT I — The Villain (90 seconds, no demo)

> *[Walk out. Clicker in hand. Black slide.]*
>
> "I want to show you something that's been bothering me for two years.
>
> *[Slide: a single line — **"AI writes code in seconds. Readiness reviews take weeks."**]*
>
> Every engineering team I talk to has the same problem. They adopted Copilot. They adopted Cursor. They adopted Claude. Their velocity went through the roof.
>
> And then... the incidents started.
>
> *[Slide: three generic incident headlines, no company names]*
>
> Not because their engineers got worse. Their engineers got **faster**. The scaffolding didn't keep up.
>
> *[Pause. Walk across stage.]*
>
> Here's the thing nobody wants to say out loud: **production readiness is the last part of software that still runs on a Google Doc.**
>
> A checklist. A review meeting. A human trying to remember if you registered the on-call rotation.
>
> *[Slide: **'Velocity: AI-speed. Discipline: person-speed.'**]*
>
> That gap — right there — is where every incident lives."

---

## ACT II — The Reveal (60 seconds, no demo yet)

> "So we built something. It's called **ready**.
>
> *[Slide: the word 'ready' in the project font. Nothing else.]*
>
> Three things to know.
>
> *[Slide: **'1. No infrastructure.'**]*
>
> No server. No SaaS. No account. Four JSON files and a scanner. You install it with pip. You run it. That's it.
>
> *[Slide: **'2. Runs on every PR.'**]*
>
> Same pipeline as your tests. Same pace. No human in the loop. No ceremony.
>
> *[Slide: **'3. It already knows your stack.'**]*
>
> You don't write checkpoints. You point it at your repo. It figures out what you are and what you're missing.
>
> *[Pause.]*
>
> Let me show you."

---

## ACT III — The Live Demo (3 minutes)

### Beat 1 — The fifteen-second first score

> "This is a service a team shipped last week. I've never seen this repo before. Watch."

```bash
$ cd demo-service
$ ready scan
```

> *[Let the progress bar scroll. Wait for the result.]*

```
ready? — demo-service   62%   2 blocking · 3 warnings

  ✗ No secrets in code
    src/config.py:14
    → Remove hardcoded keys. Use environment variables or a secrets manager.

  ✗ Health check endpoint
    → Add a /health endpoint that returns 200 when the service is live.
```

> "**Fifteen seconds.** No config. No setup. No init. It auto-detected this was a web API, picked the right pack, and told us exactly what's broken and where.
>
> Sixty-two percent. Two blocking issues. The file path. The line number. The fix.
>
> *[Look up at audience.]*
>
> This is what your next review meeting should have started with — instead of two hours of people clicking around trying to figure it out by hand."

### Beat 2 — The drift moment (this is the WOW)

> "Now watch this.
>
> *[Type slowly, let them see it.]*

```bash
$ ready scan --baseline .readiness/review-baseline.json
```

> "Okay, now I've committed a baseline. I'm going to go fix the secret.
>
> *[Switch to editor. Delete the hardcoded key. Paste `os.environ['API_KEY']`. Save. Switch back.]*

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
> Every scan, forever, shows you whether you're getting better or worse. Without anyone asking. Without anyone remembering.
>
> *[Beat.]*
>
> That's the thing that's been missing. Not 'are we compliant today' — **'are we drifting.'**"

### Beat 3 — The closed loop

> "One more thing I want to show you. Because this is the part that actually changes how teams behave.

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
> **ready is the first thing that cross-checks the ticket system against the actual code.**
>
> That's not a scanner. That's a lie detector for your backlog."

---

## ACT IV — And One More Thing (45 seconds)

> *[Walk to center stage. Lower voice.]*
>
> "I wanted to keep this one for the end.
>
> *[Slide: **'ready aggregate'**]*
>
> Everything you just saw is one repo. One team. But every engineering leader in this room has the same question every Monday morning:
>
> *[Slide: **'Which of my services is the next incident?'**]*

```bash
$ ready aggregate services/*/.readiness/review-baseline.json --html
```

> *[Open the generated HTML. A heatmap fills the screen. Red squares cluster in one row.]*
>
> *[Point at it.]*
>
> Telemetry gaps. In four of your five services.
>
> That is not a team problem. That is a **platform** problem. And you have never been able to see it until right now.
>
> *[Pause. Look up.]*
>
> This is `ready`. It's open source. It's free. **It's on GitHub today.**
>
> The discipline layer finally runs at the speed of the rest of your pipeline.
>
> Thank you."

---

## Staging Notes

- **Rehearse the demo three times minimum.** The worst thing that can happen is a typo on stage. Pre-stage the commands in shell history so you just hit `↑`.
- **Have a backup video of the demo** running on a second machine, cued up. Steve Jobs had this for the original iPhone keynote. If live fails, cut to video without missing a beat.
- **The pauses are the product.** The script is written with `[Pause.]` for a reason. Resist the urge to fill them.
- **Numbers are your friend.** "Fifteen seconds." "Sixty-two percent." "Four of five services." Specifics > adjectives.
- **Name the villains generically.** "A wave of breaches," "production breakdowns" — never name a specific company. It ages the talk and picks a fight.
- **Don't pitch. Demonstrate.** If the demo works, you don't need to explain why it matters. The room will do that for you.

## Failure Recovery

- **Network dies:** `ready scan` is local-only. You're fine. The `items --verify` beat touches ticket systems — if offline, skip Beat 3 and jump to Act IV.
- **Demo repo breaks:** Cut to backup video on second monitor. Narrate over it. The audience will never know.
- **Clicker fails:** Keep going without slides. The words matter more than the slides. The slides are scaffolding.
- **You forget a line:** Pause. Drink water. The pause reads as confidence. Picking up from the next beat is always fine.
