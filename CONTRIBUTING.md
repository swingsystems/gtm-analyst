# Contributing

## Co-maintainers wanted, explicitly

This has one maintainer. That is a real risk and adopters price it correctly: a
reference architecture without a maintainer stops being a reference. If you are
weighing whether to build on this, the honest answer is that its bus factor is
one and I would like that to change.

Taking over a layer means owning its tests and its decisions, not just merging
patches. The layers are separable on purpose:

| Layer | What owning it involves |
|---|---|
| `warehouse/` | dbt models, the fiscal calendar, seed generation |
| `warehouse/governance/` | roles, grants, persona views — **the security boundary** |
| `gtm_analyst/semantic/` | metric contracts and the compiler |
| `gtm_analyst/mcp/` | the tool surface, the other half of the boundary |
| `gtm_analyst/agent/` | the three arms and the answer card |
| `gtm_analyst/harness/` | scorer, chaos suite, experiment |

Governance and the tool surface are where a mistake becomes a breach rather than
a bug. Everything else is recoverable.

## The rules that are not negotiable

**1. `evals/spec/` is frozen.** Questions and reference SQL were committed before
the models they evaluate, and `tests/test_spec_predates_models.py` asserts it
from git history. A commit touching `reference_sql/` breaks that permanently and
cannot be repaired by rewriting history — rewriting is the thing the history
exists to disprove.

If ground truth turns out wrong, **fix the data, not the spec.** That has
happened three times here: intercompany recognition, anomaly placement, and
half-open territory windows. It is the discipline working, not a workaround.

**2. Contracts carry no SQL.** Measures declare a column and an aggregation from
a closed enum. `extra="forbid"` means a `sql:` key fails to load rather than
being ignored. Do not add a field that accepts a fragment.

**3. Values bind, identifiers validate.** Column names are checked as bare
identifiers; caller values are deliberately *not* sanitised, because binding is
the defence and sanitising invites treating validation as the defence. There is
a test asserting a `DROP TABLE` payload passes through the schema and lands in
`params`. Do not "harden" it.

**4. The tool surface takes no role, schema, or user argument.** A reflection
test asserts it over every published schema. Adding one moves the boundary from
the warehouse into the prompt.

**5. Gate checks before committing, not after.** Run `make lint && make test` and
read the result. I committed a red test once by chaining them to `git commit`
in one line.

## Scoring changes get extra scrutiny

Three scorer bugs have been found here, and **two of them flattered the thesis**.
The measurement is the deliverable, so a change that makes the results look
better is the change most likely to be wrong.

If you touch `gtm_analyst/harness/score.py`:

- Add the failing case as a test first, using **real recorded output** from
  `results/*/cards.json`, not only synthetic rows. All three bugs survived
  synthetic tests and died against real cards.
- Run `gtm rescore --cards results/pilot2/cards.json --out /tmp/check` and say
  in your PR which cells moved and why. Rescoring needs no credentials.
- If a change improves an arm's numbers, explain why that is a fix rather than a
  new bias in a new direction.

## Getting set up

```bash
make setup
make demo          # no credentials needed
make test
```

Snowflake work needs `.env` (copy `.env.example`) and key-pair auth. `make
deploy` provisions everything; `make teardown` removes it. Requires Standard
Edition or above — see [ADR 0001](docs/adr/0001-governance-on-standard-edition.md).

A pre-commit hook refuses staged credentials. It is not optional; `.gitignore`
is one `git add -f` away from failing and this repository is public.

## Things worth doing

- **Three chaos variants are unbuilt** — `fanout_join`, `wrong_effective_date`,
  `off_by_one_quarter`. `chaos/README.md` says which exist.
- **The Spider 2.0 adapter is unverified.** Whether their Snowflake tasks can run
  under this governance model is an open question, not a planned build.
- **No privilege-drift detection.** If someone grants a persona role to a human
  user, escalation becomes possible again and nothing notices.
- **The experiment is 25 of 36 cells.** It stopped at an API spending limit.

## Licensing of contributions

This project is [Apache-2.0](LICENSE). Contributions are accepted under the
same terms — Section 5 of the license already says so, so there is no separate
CLA to sign and there will not be one.

Do not paste code from a source whose license you have not checked. The NOTICE
file asserts that nothing third-party is vendored here, and that assertion is
only worth something if it stays true.
