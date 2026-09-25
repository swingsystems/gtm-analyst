# Phase 6–8: Deployment, Written Deliverables, and the Viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a working system into one a stranger can deploy, verify, and judge — including judging where it fails.

**Architecture:** Nothing new is built. This phase makes what exists reachable: a demo path needing no account, deployment that converges, the two written deliverables that speak to operating capability rather than craft, and one page that renders an answer card.

**Tech Stack:** Make, Docker, DuckDB (tier-0 mirror), FastAPI + static HTML (reusing the atlas-dashboard pattern), GitHub Actions.

## Global Constraints

- **No API budget.** Anthropic access is exhausted until 2026-10-01. Every task here must complete without it; the mock agent covers what would otherwise need a model.
- `evals/spec/` stays frozen. `reference_sql/` must not be touched.
- All credentials stay in `.env`. The pre-commit hook must keep passing.
- Every task ends with `uv run pytest -q` and `uv run ruff check gaa tests scripts` clean, **gated before commit, not chained after it.**
- Claims in written deliverables must be traceable to a commit, a test, or a recorded result. Anything else is marked as an assumption.

## Execution Mode

Inline throughout. These are judgment-heavy documents and integration work, and the earlier hybrid split delegated only mechanical implementation.

---

### Task 1: Threat model and control mapping

**Files:** Create `docs/threat-model.md`. Test: none (a document).

**This has real material.** Five findings surfaced during the build, and the document's value is that they are observed rather than imagined:

| Finding | Where | Status |
|---|---|---|
| Role escalation succeeded — operator held every persona role | Task 10, Plan 1 | Fixed by per-persona service users |
| `GRANT ALL` gave the loader ~70 privileges including `CREATE SECRET` | Task 9, Plan 1 | Fixed by revoke-then-grant |
| `REP001` hardcoded in persona views | Task 10, Plan 1 | **Accepted risk** |
| Secret scanner printed 40 chars of a live key | Plan 2 | Fixed; key should be rotated |
| Free-SQL and contract arms share one tool surface | Task 6, Plan 2 | **Accepted risk** — experiment validity, not data |

- [ ] **Step 1: Enumerate failure modes**, each mapped to the control that exists and the test that proves it: prompt injection reaching the tool surface; tool parameter tampering; role escalation; exfiltration via aggregates; metric-contract tampering as a data-definition path; audit-log leakage of SQL and schema shape; supply-chain compromise of the CI evaluation path.
- [ ] **Step 2: List every uncontrolled mode as accepted risk with its reason.** A threat model claiming complete coverage is not credible.
- [ ] **Step 3: Record what secure views do and do not hide** — the definition is concealed from non-owners, which is why lineage is build-time metadata.
- [ ] **Step 4: Commit** `docs: threat model, with the findings this build actually produced`

---

### Task 2: 90-day rollout plan

**Files:** Create `docs/rollout-plan.md`.

The management artifact. A solo repo cannot prove second-line leadership; a rollout plan with staffing, metrics and rollback criteria is the closest honest substitute, and it is what a director-level reader is actually equipped to judge.

- [ ] **Step 1: Phase 1, days 1–30** — sandbox deploy, red-team the boundary, establish baseline leak and over-block rates before anyone trusts an answer.
- [ ] **Step 2: Phase 2, days 31–60** — limited personas against the ten highest-value questions, humans verify every answer, eval runs on every model change.
- [ ] **Step 3: Phase 3, days 61–90** — expand domains, add monitoring and an incident process for a wrong answer that reached a decision.
- [ ] **Step 4: Staffing shape, success metrics** (governance leak rate, over-block rate, eval pass rate, time-to-answer, credit cost per answer), **risk register, and explicit stop/rollback criteria.**
- [ ] **Step 5: Commit** `docs: 90-day rollout plan`

---

### Task 3: Tier-0 demo path

**Files:** Create `Makefile` targets, `gaa/demo/`, `tests/test_demo.py`.

**The adoption gate.** Ranked the #1 driver by every panel that reviewed this. A reader must see real answer cards, a real governance refusal and a real eval report **with no Snowflake account and no API key, in about five minutes.**

- [ ] **Step 1: Write the failing test** — `make demo` runs with every credential stripped from the environment and produces an answer card, a refusal, and a summary.
- [ ] **Step 2: Build it** on the 25 recorded cards plus the mock agent. No network calls.
- [ ] **Step 3: Run it in CI**, so the no-account path cannot silently break.
- [ ] **Step 4: Time it.** If it exceeds five minutes, that is a defect.
- [ ] **Step 5: Commit** `feat: tier-0 demo requiring no account and no key`

---

### Task 4: README

**Files:** Create `README.md`.

- [ ] **Step 1: Lead with the problem**, not the category. Three questions a reader recognises as their own.
- [ ] **Step 2: Answer-card example above the fold**, then the three-command quickstart.
- [ ] **Step 3: State the measured result with its limits inline** — 25 of 36 cells, n=2 questions head-to-head.
- [ ] **Step 4: Write "Why these evals might be lying to you"** — residual circularity, author-chosen questions, synthetic data, and the two scorer biases caught here. **This section is the point, not an appendix.**
- [ ] **Step 5: Cite Spider 2.0 as prior art in the opening**, with the distinction stated once.
- [ ] **Step 6: Commit** `docs: README`

---

### Task 5: Deployment convergence and CONTRIBUTING

**Files:** `Makefile`, `CONTRIBUTING.md`, `docs/bring-your-own-models.md`.

- [ ] **Step 1: `make deploy` and `make teardown`** against any Snowflake account, documented credit cost.
- [ ] **Step 2: Verify convergence** — deploy twice, assert the privilege set is identical. Grants are additive; this project has been bitten once.
- [ ] **Step 3: CONTRIBUTING with an explicit co-maintainer invitation.** Single-maintainer risk is real and adopters price it correctly.
- [ ] **Step 4: Bring-your-own-models guide** — swap the warehouse, author contracts, run the conformance suite.
- [ ] **Step 5: Commit** `feat: converging deploy, teardown, and contributor guide`

---

### Task 6: Spider2-snow adapter — **verification first**

**Files:** `docs/adr/0004-spider2-adapter.md`, then possibly `adapters/spider2/`.

**Do not build before checking.** Spider 2.0's tasks run against *their* Snowflake databases. This architecture's personas and views live on *ours*. Whether their tasks can run under our governance is unverified, and the plan has carried that caveat since it was written.

- [ ] **Step 1: Read their repo** — license, task format, whether databases are provided or referenced.
- [ ] **Step 2: Decide and record in an ADR**: run their tasks under our governance, borrow only their question structure, or drop it.
- [ ] **Step 3: Build only if step 2 says it is feasible.** Recording "not feasible, here is why" is a complete outcome.
- [ ] **Step 4: Commit** `docs(adr): whether the Spider2 adapter is feasible`

---

### Task 7: Three-persona viewer

**Files:** `viewer/` (FastAPI + static HTML), `docker/`.

One page: one question, three answer cards side by side. Same question, three different correct answers, each showing its SQL, metric versions, policy context and what was withheld.

- [ ] **Step 1: Render from the recorded cards.** No live calls, so it works in the demo tier.
- [ ] **Step 2: Show `why_not` prominently** — the withholding is the argument, not a footnote.
- [ ] **Step 3: Screenshot for the README.**
- [ ] **Step 4: Commit** `feat: three-persona answer card viewer`

**Explicitly out of scope:** pipeline charts, funnel views, drill-downs, an executive GTM dashboard. Per ADR 0002 — that is BI tool territory and unrelated to the thesis.

---

## Self-Review Notes

**Ordering rationale.** Tasks 1–2 first: they need no code, carry the most weight with a director-level reader, and the threat model's material is freshest now. Task 3 next because adoption dies at the demo gate. Tasks 6–7 last because one may not be feasible and the other is optional polish.

**Known risk.** Task 6 may end in "not feasible." That is a real outcome and the plan says so rather than assuming a build.

**Carried forward from Plan 2:** the remaining 11 experiment cells and any full 108-cell run are blocked until 2026-10-01. Nothing in this plan depends on them.
