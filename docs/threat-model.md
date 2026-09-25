# Threat model

What can go wrong, which control stops it, and which test proves the control
works. Failure modes with no control are listed as accepted risk with a reason —
a threat model claiming complete coverage is not credible, and the gaps are the
part worth reading.

Every finding below was observed during this build, not imagined for this
document. Where a control exists because something broke, the commit is cited.

## Trust boundary

The agent runs as a persona service user holding exactly one Snowflake role. Its
entire reach is the tool surface in `gaa/mcp/tools.py`. Enforcement lives in the
warehouse: grants, schema scoping, and secure views. The prompt is not a control
and is never relied on as one.

```
agent ──► ToolSurface ──► persona service user ──► GAA.<PERSONA>.V_*
          (5 tools)        (one role, one schema)   (secure views)
                                                     │
                            GAA.MARTS.* ◄────────────┘  loader-only
```

---

## Findings from this build

### 1. Role escalation succeeded — FIXED

A session opened as `GAA_REP_INDIVIDUAL` ran `USE ROLE GAA_FINANCE_GLOBAL` and
read all 306 bookings. Snowflake scopes privilege to the session role but lets a
session switch to any role its **user** holds, and the operator held all four.
The schema grants were never the weak point; the user's role portfolio was.

**Control.** One service user per persona, each granted exactly one role, with
the persona roles revoked from the operator (`e6f5e51`). Escalation now fails
with `003013 SQL access control error`.

**Test.** `tests/test_governance_boundary.py::test_no_persona_can_escalate_role`,
covering rep→finance, EMEA→finance and rep→ACCOUNTADMIN.

**Residual.** The control depends on nobody granting a persona role to a human
user later. Nothing detects that today — see accepted risk 3.

### 2. Loader held ~70 privileges including `CREATE SECRET` — FIXED

`GRANT ALL ON SCHEMA` conferred roughly seventy privileges on the loader,
including `CREATE AGENT`, `CREATE MCP SERVER` and `CREATE SECRET`. Narrowing the
grants in the file did not remove them: **grants are additive**, so the role kept
everything while the SQL appeared to say otherwise.

**Control.** Revoke-then-grant, so the privilege set converges on what is written
regardless of history (`62e3d84`). 100 grants down to 10, and dbt still builds
and passes all 38 tests on the narrower set — least privilege demonstrated
rather than asserted.

**Test.** dbt build and test suite pass under the reduced grants.

### 3. Secret scanner printed part of a live key — FIXED

The first version of the pre-commit hook printed a truncated match to be helpful
and put roughly forty characters of a live Anthropic key into a terminal log.
Truncation is not redaction.

**Control.** The hook names the offending file and never echoes matched text
(`d634aa3`).

**Residual.** That key should be rotated. It is valid, partially exposed in a
local log, and shared with another project.

---

## Failure modes and controls

| Failure mode | Control | Proven by |
|---|---|---|
| Prompt injection reaching the tool surface | The agent cannot name a role, schema or user: no tool accepts one. A compromised prompt still executes as the same persona. | `test_no_tool_accepts_a_persona_role_or_schema_argument`, asserted by reflection over every tool and over the published MCP schemas |
| SQL injection via filter values | Identifiers come only from the contract and are validated as bare identifiers; every caller value binds **server-side** via qmark. A `DROP TABLE` payload appears in `params`, never in the statement. | `test_a_malicious_filter_value_never_reaches_the_sql`; verified live against the warehouse |
| SQL injection via metric contracts | Contracts carry no SQL. Measures declare a column plus an aggregation from a closed enum; filters are structured triples. A contract with a `sql:` key fails to load. | `test_a_contract_carrying_sql_is_rejected` |
| Code execution via a malicious spec or contract file | `yaml.safe_load` only. Tests assert the error was **caused by** a YAMLError, pinning refusal to the parse layer rather than to model validation. | `test_the_yaml_tag_is_rejected_AT_THE_PARSE_LAYER` in both loader suites |
| Writes through the free-SQL arm | Allow-list on the leading keyword (`SELECT`, `WITH`), not a deny-list. Comments are stripped first, so commenting out a SELECT cannot promote a DELETE. | 14 write and privilege statements tested as refused |
| Cross-persona reads | Schema-scoped grants; no persona has any grant on `MARTS`. | `test_no_persona_can_read_the_base_marts`, `test_rep_cannot_read_another_personas_schema` |
| Agent introspecting its way around the boundary | Secure views hide their definitions from non-owners. Probing as a persona, `VIEW_DEFINITION` is NULL and `GET_DDL` is refused. Lineage is therefore build-time metadata recorded by `apply_governance`. | Verified by probe; recorded in `f413915` |
| Silent partial answers | A restricted persona that can see only part of what was asked must populate `why_not`. Audited across 18 recorded runs: zero silent partials. | `AnswerCard` validation; fixture audit |
| Unauditable answers | An answered card without its SQL and Snowflake query id fails construction. | `test_an_answered_card_without_a_query_id_is_refused` |
| Deliberately broken models reaching production numbers | Chaos suite plants known defects and requires the harness to catch them. | `tests/test_chaos.py`, 5 of 5 caught |

---

## Accepted risks

Listed because omitting them would make the table above a claim of completeness.

**1. `REP001` is hardcoded in the persona views.** A real deployment maps
`CURRENT_USER()` to a rep. Acceptable for a single-operator reference deployment;
unacceptable in production, where every rep would see one rep's book.

**2. The free-SQL and contract arms share one tool surface.** Nothing prevents a
contract-constrained agent from calling `run_sql`; the arms are separated by
which tools their prompts describe and which contracts they are shown, not by
capability. This is a risk to the **experiment's validity**, not to the data —
the warehouse boundary holds either way.

**3. Privilege drift is detectable but not detected.** If someone grants a
persona role to a human user, escalation becomes possible again. The mechanism
now exists — `scripts/privilege_snapshot.py` dumps the account's full grant set
as deterministic JSON, and `make verify-convergence` fails on any change across
two governance runs. Verified to work by granting `MONITOR ON DATABASE GAA` to
the rep role and confirming the diff caught it. **Nothing runs it on a
schedule**, so it catches a deployment that fails to converge, not a grant
someone makes on a Tuesday. That gap is unclosed.

**4. Audit log contents are not access-controlled.** Every tool call is written
to JSONL carrying the SQL executed, the persona, and the policies in effect.
Anyone who can read the file learns the schema shape and the governance model.
Not encrypted, not rotated, not permission-scoped.

**5. The MCP server is unauthenticated.** It binds a persona at startup and
trusts its transport. Fine for stdio and a local client; it would need real
authentication before being exposed over a network.

**6. The evaluation path is not gated at all.** This was previously written as
if CI ran the chaos suite and the evaluation on every PR. It does not: CI holds
no Snowflake credentials, so every live test skips and 7 of the 8 chaos tests
never execute there. The catch rate in `chaos/README.md` is a local measurement,
not a gate.

So the supply-chain concern is worse than first stated. A contributor able to
modify a chaos variant or a reference query would weaken the harness and CI
would stay green -- not because it was fooled, but because it never looked.
Closing this needs a CI service account and branch protection. Neither exists.

**7. Cost is uncontrolled.** Nothing caps the credits an agent may spend. A
pathological question could scan large tables repeatedly. The real experiment run
was in fact halted by an Anthropic spending limit, which is the same class of
problem from the other side.

---

## What this model does not cover

Data exfiltration by a legitimately authorised user, insider misuse of the
operator account, Snowflake's own security posture, and anything about the model
provider's handling of prompts and results. All out of scope, none addressed.
