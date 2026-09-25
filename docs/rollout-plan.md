# Rolling this out in 90 days

How an organisation adopts governed analytics agents without betting anything
important on them in the first month. Written for whoever has to answer for the
numbers, not for whoever writes the SQL.

The shape is deliberate: nothing reaches a decision-maker until the boundary has
been attacked on purpose and the error rate is a measured number rather than an
expectation.

---

## Before day 1 — the two things that stop this dead

**Confirm the edition.** Row access policies and masking policies are Enterprise
and above. This reference deployment runs on Standard because the development
account was Standard, and the boundary is built from schema-scoped grants and
secure views instead (`docs/adr/0001`). Both work. Knowing which you have
changes what you build, and finding out at week six is expensive.

**Confirm key-pair auth.** Service connections need it. Five minutes if it
exists, half a day of ticket-raising if it does not.

Neither is interesting. Both have blocked this project before.

---

## Phase 1 — days 1 to 30: attack it before trusting it

**Goal: a baseline error rate, and a boundary that has been attacked on purpose.**

Deploy to a sandbox with synthetic or masked data. Nothing from production yet.

1. Stand up the warehouse, personas, and views. Run `make deploy`, then run it
   **again** and confirm the privilege set is identical — grants are additive,
   and a deployment that accumulates instead of converging is a different system
   on its second run than its first.
2. Red-team the boundary. Try to escalate roles, read another persona's schema,
   reach the base marts, and infer restricted values from aggregates. Write down
   what worked. On this project, role escalation worked on the first attempt and
   the fix was architectural, not a patch.
3. Author 10–15 questions your finance and sales teams actually ask, each with
   reference SQL you are confident in. **Commit these before building anything
   they will be evaluated against**, and let the commit order prove it.
4. Run the evaluation. Record per-category failure rates. This is the baseline
   every later number is compared against.

**Exit criteria.** Every bypass path tested and closed or accepted in writing.
Baseline error rates recorded. Zero governance leaks.

**Stop if:** you cannot close a bypass path and cannot accept it in writing. A
boundary with an unexplained hole is not a boundary.

**People:** one analytics engineer, roughly half time. Someone with security
instincts for the red-team week, even a few hours.

---

## Phase 2 — days 31 to 60: narrow and supervised

**Goal: answers a human checks, against questions that matter.**

1. Pick the ten highest-value questions. Not the ten easiest.
2. Enable two or three personas, chosen so their permitted populations genuinely
   differ. If every persona sees the same data, nothing is being tested.
3. **Every answer is verified by a human before it informs anything.** The agent
   is a fast first draft, not a source.
4. Run the evaluation on every model change. A regression in any category fails
   the build.
5. Track disagreements between the agent and the verifier, and read them
   individually. On this project the most common divergence was **definitional,
   not computational** — the agent applied a declared default the reference SQL
   did not. Those are conversations about what a metric means, and they are
   worth more than the error rate.

**Exit criteria.** Thirty consecutive days of verified answers. Disagreements
triaged into "agent wrong", "reference wrong", and "the definition was never
agreed" — expect the third pile to be larger than anyone predicts.

**Stop if:** verifiers stop reading carefully. Supervision that has become a
rubber stamp is worse than none, because it manufactures confidence.

**People:** the analytics engineer, plus a named verifier per domain with the
time actually allocated.

---

## Phase 3 — days 61 to 90: widen, and plan for being wrong

**Goal: more domains, and a process for the answer that was wrong and reached a
decision.**

1. Add domains one at a time, each repeating Phase 2's supervision for two weeks.
2. Monitoring: governance leak rate, over-block rate, eval pass rate by category,
   time-to-answer, credit cost per answer. Alert on leak rate above zero.
3. **Write the incident process before you need it.** A wrong number reached a
   decision. Who finds out, how quickly, how is the blast radius scoped, who
   tells the people who acted on it? Every answer carries a Snowflake query id,
   so the trail exists — the question is whether anyone knows to follow it.
4. Review the accepted risks in `docs/threat-model.md` and decide which are still
   acceptable at this scale. Hardcoded persona filters and unrestricted audit
   logs age badly.

**Exit criteria.** Monitoring live. Incident process written and walked through
once against a fabricated incident. Accepted risks re-reviewed by someone who
did not write them.

---

## What to measure, and what not to

| Metric | Why | Watch for |
|---|---|---|
| Governance leak rate | The only one that must be zero | Any non-zero value is an incident, not a trend |
| Over-block rate | Refusing too much is a real failure, just a safe one | Rising quietly while accuracy looks great |
| Eval pass rate **by category** | Different causes, different fixes | A single accuracy number hiding a category getting worse |
| Coverage | How many questions could be attempted at all | An arm declining more and scoring better |
| Credit cost per answer | The thing that ends pilots | Unbounded scans on pathological questions |

**Do not report a single accuracy figure.** An agent that declines half the
questions and is right about the rest looks excellent and is less useful than
one that attempts everything and is right about most. On this project, coverage
and accuracy pointed in opposite directions and the single number would have
told the flattering half.

---

## Staffing, honestly

Phase 1 is one competent analytics engineer half time, plus a few security
hours. Phase 2 adds verifier time that must be genuinely allocated — unfunded
verification is the most common way pilots like this quietly fail. Phase 3 needs
whoever owns the incident process to actually own it.

No data scientist. No platform team. The work is modelling and governance, and
both live with the analytics engineering function.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Wrong number reaches a decision | Medium | High | Phase 2 verification; query id on every answer; incident process before Phase 3 |
| Metric definitions were never agreed | **High** | Medium | Surfaced by disagreement triage; this is a feature of the rollout, not a defect |
| Privilege drift re-opens escalation | Medium | High | Periodic `SHOW GRANTS TO USER` check — **not built**, see threat model |
| Verification becomes rubber-stamping | High | High | Track verifier disagreement rate; if it hits zero, supervision has stopped |
| Cost runs away | Medium | Medium | Credit-per-answer monitoring; warehouse-level resource monitor |
| Adoption stalls after the pilot | High | Low | Expected. Phase 3 widens deliberately rather than assuming pull |

---

## What this plan does not promise

It does not promise the agent will be right. It promises you will know how often
it is wrong, in which category, and who was permitted to see what — before you
depend on it.

The evaluation in this repository found that its own scorer was biased in its
author's favour, twice. Assume yours is too until you have tried to prove
otherwise.
