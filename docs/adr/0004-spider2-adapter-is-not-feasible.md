# ADR 0004 — The Spider 2.0 adapter is not feasible as scoped

Date: 2026-09-25
Status: Accepted — **dropped, with one narrower variant kept open**

The plan carried this task with a standing caveat: *verify before building*, and
"not feasible, here is why" is a complete outcome. It is the outcome.

## Context

[Spider 2.0](https://github.com/xlang-ai/Spider2) (ICLR 2025 Oral) is the
credible prior art in enterprise text-to-SQL, and Spider2-Snow runs on Snowflake
specifically. Adapting it looked attractive for one reason that still holds:
**the questions in this repository are mine**, which is limitation 4 in the
README and the hardest of the six to argue away. Borrowing somebody else's
questions would remove it outright.

So the question was never "is Spider 2.0 good" — it is — but "can its tasks run
under this architecture's governance model."

## What was checked, 2026-09-25

Read directly from the repository rather than inferred:

| | Finding |
|---|---|
| License | MIT. **Not a blocker** — reuse and redistribution are permitted with attribution. |
| Scale | 547 tasks in `spider2-snow.jsonl`, spread across **152 distinct databases**. |
| Task shape | `{instance_id, instruction, db_id, external_knowledge}`. Nothing else. |
| Evaluation | One predicted `.sql` per instance, compared against recorded gold execution results. |
| Access | A Google form granting access to **their** shared Snowflake account. Their README has carried a suspension notice for that account since 2026-08-12. |
| Self-hosting | Possible. Email request, a Snowflake secure share, and an account **in AWS us-west-2**. 18 non-`sf_` examples cannot be shared at all. |

## Decision

**Do not build the adapter.** Cite Spider 2.0 as prior art, state the distinction
once, and leave it there.

Four reasons, in order of how hard they are to work around.

**1. The tasks have no identity dimension, and that is the whole subject here.**
A task is a question and a database name. There is no persona, no role, no
notion of who is asking. "Governance leak" and "governance over-block" — the two
failure categories this architecture exists to measure — are not merely unscored
by Spider 2.0; they are *unexpressible* in its task format. I would have to
invent personas for their databases, which reintroduces exactly the
author-chosen bias the adapter was supposed to remove. The adapter would import
their questions and my assumptions, and the assumptions are the part under
suspicion.

**2. Only one of three arms could run them.** Spider 2.0 hands the model a
schema and expects arbitrary SQL. `strict-contract` and `safe-join-contract`
answer only through declared metrics, so on an unmodelled database they return
"inexpressible" for all 547 tasks — correctly, and uselessly. The experiment *is*
the comparison between arms. An adapter that exercises only `free-sql` measures
text-to-SQL ability, which Spider 2.0 already measures better than I would.

**3. Governance here is authored, not inferred.** Persona schemas, secure views,
and metric contracts are written per warehouse by someone who understands the
data. Covering 152 databases is 152 modelling projects, not one adapter. This is
not a shortcut I failed to find; it is what the architecture is.

**4. Access is the least of it, but it is not nothing.** The shared account has
been suspended for weeks, and self-hosting requires a us-west-2 account this
project does not have, plus their approval, plus absorbing the compute.

Reason 4 will resolve on its own. Reasons 1 through 3 will not.

## What stays open, and it is worth doing

One narrower version survives every objection above: **import a single database
and author governance over it properly.**

`THELOOK_ECOMMERCE` is the candidate — 19 tasks, retail commerce, with orders,
users, and product categories, so customer- and category-scoped personas are
natural rather than invented. The work is: accept the secure share, write
persona views and metric contracts for that one schema, and run all three arms
against **their** 19 questions and **their** gold results.

That is a real removal of limitation 4 on one database, and it is falsifiable in
the uncomfortable direction: the contract arms might find most of those 19
questions inexpressible, which would be a genuine finding about how narrow
contract-constrained querying is when the questions were not written with it in
mind. I would rather learn that than not.

Not now. It needs a us-west-2 Snowflake account, their approval, and one honest
modelling pass — and the current experiment is still 11 cells short of complete.
Recording it here so the reason it was not done is the real one.

## Consequences

- The README's claim about Spider 2.0 stays exactly as written: complementary
  prior art, distinction stated once, no adapter implied.
- README limitation 4 — "the questions are mine" — **remains uncorrected**, and
  now has a documented path to being fixed rather than an implied one.
- No `adapters/` directory. Nothing was built.
