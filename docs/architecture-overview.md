# Architecture overview

Most agent demos answer a question. The hard part is answering it **differently
for different people, and proving afterwards which query ran.**

## The problem

An agent that can query your warehouse can also leak it.

When a rep and a CFO ask the same question, does the agent return different
answers — or quietly hand the CFO's number to the rep? When an agent-produced
figure lands in a board deck, can you reconstruct which SQL ran, under which
role? When an auditor asks how you test AI agents for data-access violations,
what do you show them?

## The shape

```
agent ──► tool surface ──► persona service user ──► GAA.<PERSONA>.V_*
          (5 tools)         (exactly ONE role)        (secure views)
                                                        │
                             GAA.MARTS.* ◄──────────────┘  loader only
```

Four decisions carry the whole thing.

### 1. Identically-named views in per-persona schemas

`V_BOOKINGS` exists three times — in `FINANCE`, `EMEA` and `REP`. Reference SQL
is unqualified, so the session's default schema decides what it means. One SQL
string, three different correct answers, and the difference is enforced by the
warehouse rather than by the prompt.

### 2. One role per service user

A session can switch to any role its *user* holds. Snowflake scopes privilege to
the session role, but the user's role portfolio is the real boundary — a lesson
this project learned by watching a rep session run `USE ROLE
GAA_FINANCE_GLOBAL` successfully. Each persona now gets its own service user
holding exactly one role.

### 3. The tool surface accepts no role, schema, or user argument

An agent has no parameter through which to request different privileges, so a
compromised prompt still executes as the same identity. Asserted by reflection
over every published tool schema, not by convention.

### 4. Metric contracts contain no SQL

Measures declare a column and an aggregation from a closed enum. The compiler
assembles the statement and binds every caller value server-side. A contract
carrying a `sql:` key fails to load rather than being ignored.

## What is in it

| | |
|---|---|
| Warehouse | 12 dbt models, 38 data tests, 3 personas |
| Semantic layer | 6 metric contracts, no SQL in any of them |
| Tool surface | 5 MCP tools — `list_metrics`, `describe_metric`, `query_metric`, `run_sql`, `explain_lineage` |
| Agent | 3 arms — free SQL, strict contracts, contracts with compiler-mandatory join predicates — sharing a byte-identical system prompt, so the comparison measures the constraint rather than the wording |
| Evaluation | 12 questions with reference SQL, committed **before** the models they evaluate, asserted from git history by a test |
| Chaos suite | 5 deliberately broken models the harness must catch; 5/5 on every credentialed CI run |
| Invariants | global equals the sum of regions; rep ≤ region ≤ global; masking changes values but never row counts |
| Edition | Snowflake **Standard** — no row access policies required |
| Sources | native tables or the **Salesforce object model**, same numbers from `Account` and `Opportunity` |
| Providers | Anthropic, OpenAI, NVIDIA, OpenRouter behind one interface |
| Cost | recorded per answer card — roughly a cent an answer |

## What it demonstrates about itself

Across a complete 108-cell evaluation:

- **Zero governance leaks.** No persona returned a row outside its permitted
  scope.
- **67 of 67 answered cells carry provenance** — the SQL, the role, and a
  Snowflake query id that resolves in `ACCOUNT_USAGE`. A card without one fails
  construction; it cannot be built.
- **Partial answers must declare what was withheld.** Silence is a validation
  error, because a partial answer that looks complete is the dangerous case.

`make demo` replays 25 recorded answer cards in about a second — no Snowflake
account, no API key, no network.

## What it admits

Four bugs in its own scoring code, three of which made the constrained arms look
better than they were. 65 completed evaluation cells thrown away, with the
reason kept in `results/discarded/`. And a governance conclusion that reversed
when the model changed — both readings published, because
[ADR 0003](adr/0003-three-arms-and-pre-registered-reporting.md) fixed the
reporting schema before any number existed.

A reference architecture whose evaluation has never been caught lying is one
nobody has looked at hard enough.

Further reading: [threat model](threat-model.md) with residual risk on every
item marked closed, [90-day rollout plan](rollout-plan.md) with explicit stop
criteria, and 7 [ADRs](adr/).
