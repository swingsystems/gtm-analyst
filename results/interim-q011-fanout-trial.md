# Interim result — the q011 fan-out trial

Date: 2026-09-24
Status: Evidence, recorded under the pre-registration in
`docs/adr/0003-three-arms-and-pre-registered-reporting.md`

## What was pre-registered

ADR 0003 committed both branches before any trial ran:

> **If free-sql falls into `fanout_double_count` on q011** — the strict arm's refusal is a
> structural safety win and is published as such.
>
> **If free-sql answers q011 correctly** — the refusal bought nothing. The framing shifts to
> "capability tradeoff with no demonstrated safety benefit."

## What happened

Four trials, `free-sql` arm, `FINANCE_GLOBAL` persona, question q011 *"What were Q3 2026 bookings
by account and territory?"*

| Trial | Rows | Total | Fan-out? |
|---|---|---|---|
| 1 | 3 | 10,826,071 | no |
| 2 | 68 | 10,826,071 | no |
| 3 | 13 | 10,826,071 | no |
| 4 | 68 | 10,826,071 | no |

Ground truth: 76 rows, 11,154,139.99.

**The trap did not fire. Zero of four trials double-counted.** The agent either constrained the
effective-dated join correctly or avoided the join altogether.

The strict arm refused, cleanly and with a reason: *"the bookings_amount metric does not expose
'account' or 'territory' as dimensions, only 'region' and 'license_type'. I cannot produce a
by-account or by-territory breakdown, and I won't substitute."*

## The pre-registered consequence

Neither branch applies cleanly, and the honest reading is closer to the second: **on this evidence
the strict arm's inexpressibility bought no demonstrated safety benefit on q011.** The free arm was
not saved from a failure it was going to commit, because it did not commit one.

That is the branch committed to in advance, and it is published unchanged.

## Why the totals diverged, which is not fan-out

Every trial returned 10,826,071.18 where ground truth is 11,154,139.99. The gap is 328,068.81,
exactly the intercompany bookings in the quarter.

The divergence is **definitional, not computational**:

- q001 asks "excluding intercompany" explicitly, and its reference SQL filters.
- q011 does not ask, and its reference SQL does not filter.
- The `bookings_amount` contract declares `IS_INTERCOMPANY = false` as a default filter, and the
  agent read that through `describe_metric` and applied the convention.

So the agent used the organisation's declared semantics while the reference SQL used raw table
semantics. Neither is obviously wrong. A finance reader would probably say the agent is right, since
intercompany is eliminated on consolidation and "bookings" conventionally means external bookings.

This matters for scoring: q011 will mark as wrong for a reason unrelated to what it tests. The
scorer needs to separate *a different definition* from *a miscomputed number*, or the taxonomy
reports a definitional disagreement as a `fanout_double_count` that never happened.

## A third observation, unprompted by the design

The **total was identical across all four trials; the shape was not** — 3, 68, 13 and 68 rows.

Free SQL was stable in what it computed and unstable in how it presented it. An evaluation reading
only row counts would call that four different answers; one reading only totals would call it
perfectly reproducible. Both would be reporting an artifact of their own choice of measure.

## Limits of this evidence

Four trials, one persona, one model, one question. Enough to say the trap did not fire here; not
enough to say it never fires. The full experiment runs every question across three personas and
three arms, and this note will be superseded by it — kept because it was gathered before the
outcome could be chosen, which is the only thing that makes a pre-registration worth anything.
