# GTM Analyst

**A GTM analyst you can audit.** Governed analytics agents on Snowflake, where
every number carries its SQL, the role that ran it, and a query id you can
resolve yourself.

Deploy it in a day. Prove it against your own warehouse.

An analytics agent that can query your warehouse can also leak it.

When a sales rep and a CFO ask the same question, does the agent return
different answers — or does it quietly hand the CFO's number to the rep? When an
agent-produced figure reaches a board deck, can you reconstruct which SQL ran,
under which role, against which policies? When a SOC 2 auditor asks how you test
your AI agents for data access violations, what do you show them?

This is a reference architecture that answers all three, with running code and a
published measurement — including the measurements that went against it.

---

## See it in five minutes, with no account and no API key

```bash
git clone <this repo> && cd gtm-analyst
make setup
make demo
```

`make demo` replays 25 answer cards recorded against a live Snowflake account.
It runs in about a second, makes no network calls — a test patches
`socket.connect` to raise, so this cannot quietly stop being true — and needs no
credentials of any kind.

### One question, three identities, three correct answers

> *What were total bookings for Q3 2026 by region, excluding intercompany?*

| asked as | rows | total | withheld |
|---|---|---|---|
| `FINANCE_GLOBAL` | 3 | 10,826,071.18 | — |
| `SALES_DIR_EMEA` | 1 | 4,137,843.49 | yes |
| `REP_INDIVIDUAL` | 1 | 1,313,784.51 | yes |

Same question. Same SQL. Different answers, because the **warehouse** decides
what each identity may see — not the prompt.

`make viewer` renders that as one self-contained page, with the withholding
where it belongs — next to the numbers, not in a footnote:

![Three personas answering one question, each showing its role, schema, metric version, query id, and what it withheld](docs/images/three-personas.png)

### Every answer carries what you need to check it

```
**Q.** What were total bookings for Q3 2026 by region, excluding intercompany?
**Asked as** FINANCE_GLOBAL (role GAA_FINANCE_GLOBAL, schema FINANCE) · arm strict-contract

| AMER | 2005507.42 |
| APAC | 4682720.27 |
| EMEA | 4137843.49 |

**Metrics.** bookings_amount@1     **Lineage.** V_BOOKINGS
**Query id.** 01c74b56-010b-a606-000a-95d700bc8ffa
```

That query id resolves in your own `ACCOUNT_USAGE`. An answered card **cannot be
constructed** without its SQL and query id — validation refuses it — and a
partial answer must say what was withheld.

---

## What it is not

**This is not a text-to-SQL benchmark.** [Spider 2.0](https://github.com/xlang-ai/Spider2)
(ICLR 2025 Oral) already evaluates language models on enterprise text-to-SQL,
including Snowflake and dbt subsets, and does it well.

The distinction, stated once: **Spider 2.0 tells you whether the SQL is right.
This tells you whether the agent was allowed to run it, as whom, and whether you
can prove it afterward.** "Governance leak" and "governance over-block" are
failure categories a correctness benchmark structurally cannot express.

---

## The measurement

Three arms answer the same questions as the same personas:

| arm | what it may do |
|---|---|
| `free-sql` | writes arbitrary read-only SQL |
| `strict-contract` | restricted to declared metrics, no joins |
| `safe-join-contract` | declared metrics, joins carrying compiler-mandatory predicates |

Two grids, reported separately and never merged — an arm difference would
otherwise be indistinguishable from a model difference
([ADR 0007](docs/adr/0007-two-providers-never-one-grid.md)).

**`gpt-4.1` — complete: 108 of 108 cells**, all twelve questions, $1.15.
Head to head on the four questions every arm could express:

| arm | head-to-head | attempted | conditional accuracy |
|---|---|---|---|
| safe-join-contract | 12/12 · 100% | 19/36 | 74% |
| strict-contract | 12/12 · 100% | 23/36 | 52% |
| free-sql | 11/12 · 92% | 36/36 | 39% |

**`claude-sonnet-5` — partial: 25 of 36 cells**, stopped by an API spending
limit mid-grid. Two questions head to head, six cells per arm, where one flipped
cell moves an arm seventeen points. It is not retroactively completed.

**Coverage is not accuracy.** The strict arm was right about everything it
attempted and declined a quarter of the questions. A single accuracy figure would
report "strict-contract: 100%", which is true and would badly mislead — which is
why the [pre-registered reporting schema](docs/adr/0003-three-arms-and-pre-registered-reporting.md)
forbids one.

### Not tied to one model

The agent runs against Anthropic or OpenAI behind one interface, with a
**byte-identical system prompt and tool surface** for both — a cross-model
result is worthless if the two models were asked different questions.

```bash
gtm experiment --provider openai            # a separate, complete grid
```

**Grids are never merged.** If some cells come from one model and some from
another, an arm difference becomes indistinguishable from a model difference —
the same failure as comparing an arm against itself. Resume replays only cells
whose recorded model matches the run, and an unknown provider raises rather than
defaulting, so a run cannot misreport which model produced it.
[ADR 0007](docs/adr/0007-two-providers-never-one-grid.md).

Full results and their limits: [`results/`](results/).

The run resumes rather than restarting — `gtm experiment --resume-from
results/pilot2/cards.json` replays the 25 recorded cells and calls the model
only for the missing ones. Recorded cells are **rescored**, never trusted: a
score is cheap and deterministic, the card is the expensive artifact, and
carrying old scores forward would mix scorer versions inside one report.

---

## Why these evals might be lying to you

The most important section here. Seven concrete reasons, not hedging.

**1. The scorer was biased in my favour. Twice.** It compared column *names*.
Contract arms always emit `VALUE` because the compiler names the measure; free
SQL names its own. A numerically identical free-SQL answer scored wrong. That
version read **contracts 6/6, free-SQL 0/3** — clean, quotable, false. Fixing it
gave a dead tie. Fixing only the row comparison and leaving the same assumption
in the total calculation then produced **67% vs 33%**, which was also wrong.

**2. A third scorer bug reported a fan-out that never happened.** After removing
alias-dependence, the total summed *every* numeric cell — so a count column
beside the measure inflated the total past the fan-out threshold. In the one
category the whole design exists to detect.

**3. My own ground truth was wrong, and an agent found it.** The territory
validity window was written inclusively and read half-open, losing 180,848.13 at
handovers. The free-SQL agent kept probing instead of answering because the data
genuinely didn't reconcile. One author wrote the models, the questions, and the
reference SQL — and the reference SQL encoded his own mistake as truth.

**4. The questions are mine.** Selection bias is real: I chose questions this
architecture can express. The intercompany filter in particular was my
invention — I flagged it as possibly imported from manufacturing, never
confirmed it, and built it in anyway. Borrowing Spider 2.0's questions would fix
this; [ADR 0004](docs/adr/0004-spider2-adapter-is-not-feasible.md) explains why
their tasks cannot run under this governance model, and what narrower version
could.

**5. The data is synthetic.** It cannot reproduce real CRM entropy — duplicate
accounts, mid-quarter reassignments, half-filled custom fields.

**6. The headline conclusion turned out to be model-dependent.** On the Claude
grid the fan-out trap never fired: across four dedicated q011 trials the
free-SQL arm never committed one, and
[ADR 0003](docs/adr/0003-three-arms-and-pre-registered-reporting.md) had
pre-committed both branches, so the published reading was the unflattering one —
*the strict arm's inexpressibility bought no demonstrated safety benefit.*

The complete `gpt-4.1` grid says the opposite. On the five questions the strict
arm could not express, free SQL was **wrong on 13 of 15 cells**; safe-join was
wrong on 3, strict on 2. The refusal bought a great deal.

Both readings are published. Neither is "the" answer: a governance result that
flips between two models is a result about that pair of models, and anyone
quoting either number without the other is quoting half of it.

**7. The scorer was biased in my favour a fourth time.** The reference SQL
renders a NULL group as `(none)`; free SQL returns `''`. Same absent segment,
identical measure, scored wrong — and only the free arm pays, because the
contract arms emit the compiler's canonical shape. The first run of the complete
grid read **free-sql 33% against safe-join 74%**: clean, quotable, and wrong.
Corrected, free-SQL's head-to-head goes from 75% to 92%.

Caught because two categories looked impossible: `strict-contract` was credited
with four `fanout_double_count` failures despite having no join surface at all.

Ten further cells return the right numbers under a different projection —
`ACCOUNT_ID` where ground truth has `ACCOUNT_NAME`. Those are **left scored
wrong**. Converting them would repeat scorer bug #3, which was an
over-correction in exactly this direction.

Four of those seven flattered the thesis, and **four separate scorer bugs have
now been found, three of which made the constrained arms look better**. Every
one was caught by checking a number that looked too clean against real recorded
output. None was caught by a synthetic test.

That is the actual claim of this repository: not that these numbers are right,
but that the machinery keeps catching itself, and that the corrections are
published rather than quietly absorbed. Assume more remain.

---

## How it works

Short version below; the [architecture overview](docs/architecture-overview.md)
covers the four decisions that carry it, the full inventory, and what the
evaluation demonstrates — and admits.

```
agent ──► tool surface ──► persona service user ──► GAA.<PERSONA>.V_*
          (5 tools)         (exactly one role)        (secure views)
                                                       │
                             GAA.MARTS.* ◄─────────────┘  loader only
```

- **Metric contracts** are structured YAML with **no SQL**. Measures declare a
  column and an aggregation from a closed enum; the compiler assembles SQL and
  binds every caller value server-side.
- **The tool surface accepts no role, schema, or user argument.** An agent has no
  parameter through which to request different privileges, and a reflection test
  asserts it over every published schema.
- **Governance is Standard Edition compatible** — schema-scoped grants and secure
  views rather than row access policies, so any Snowflake account can deploy it.
  See [ADR 0001](docs/adr/0001-governance-on-standard-edition.md).

## Adopting it

1. **`make demo`** — five minutes, no account.
2. **`make deploy`** — your Snowflake, under an hour. Then `make
   verify-convergence`, which applies governance a second time and fails if the
   account's privilege set changed. Grants are additive, so a deployment that
   accumulates instead of converging is a different system on its second run;
   this project lost ~70 stray privileges to exactly that. `make teardown`
   removes everything it created.
3. **Point it at your models** — [bring-your-own-models guide](docs/bring-your-own-models.md).
   Already on Salesforce? The
   [Salesforce-shaped source](docs/salesforce-shaped-source.md) builds the same
   warehouse from Account and Opportunity and reaches the **same
   10,826,071.18** — the governance boundary and the frozen evaluation do not
   depend on the source system. No Salesforce connection required; the data is
   synthetic, reshaped.
4. **Write your questions first.** Commit the questions and reference SQL
   *before* the models they evaluate, and let the commit order prove it. A test
   asserts that ordering in this repo.

Also worth reading: the [threat model](docs/threat-model.md), which lists the
accepted risks, what has since been closed, and the residual on each; the
[90-day rollout plan](docs/rollout-plan.md); and [SECURITY.md](SECURITY.md) for
how to report something.

## Status

Working and incomplete. The warehouse, governance, tool surface, three agent
arms, scorer, and chaos suite are built and tested (394 tests). A fresh
clone with no credentials runs the offline suite green in under two seconds; the
rest skip with a stated reason rather than failing. The experiment
has run completely on `gpt-4.1` and partially on `claude-sonnet-5`. The Spider
2.0 adapter was checked and dropped
([ADR 0004](docs/adr/0004-spider2-adapter-is-not-feasible.md)). All five chaos
variants are built and the catch rate is 5 of 5 — and one of them caught a wrong
prediction in [`chaos/README.md`](chaos/README.md) itself.

Single maintainer. [Co-maintainers wanted](CONTRIBUTING.md).

## License

[Apache-2.0](LICENSE). Fork it, deploy it, sell services around it — the patent
grant is there so your legal team does not have to think about it. See
[NOTICE](NOTICE) for the dependency license audit and what this project does
*not* include.

**Provenance:** built on a personal Snowflake account against synthetic data.
The architecture, governance objects, agent, and evaluation are real and
independently reproducible. The data is not a real company's.
