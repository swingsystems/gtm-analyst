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

**1. ~~`REP001` is hardcoded in the persona views.~~ CLOSED.** The rep is now
resolved from `CURRENT_USER()` through `GAA.IDENTITY.MAP_USER_TO_REP`, a table
in a schema no persona role has any grant on. The secure view reads it with its
owner's rights; the caller cannot, so a rep cannot enumerate other reps.

It fails **closed**: an unmapped session makes the scalar subquery return NULL,
`OWNER_REP_ID = NULL` is UNKNOWN, and UNKNOWN does not pass a WHERE clause. That
is the opposite of the usual direction, where a mapping miss drops the filter
and returns the unfiltered table. Asserted by deleting the mapping row and
confirming the rep sees zero rows
(`test_an_unmapped_user_sees_nothing_rather_than_everything`).

**Residual.** The map is populated by the deploy script for the reference
deployment. A real one feeds it from the HR or CRM system of record, and a stale
row there still grants the wrong book.

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
to JSONL. This previously claimed the log carries "the SQL executed and the
policies in effect"; it does not, and the overstatement is corrected rather than
left flattering. `AuditEntry` records persona, role, schema, tool, outcome,
metrics used, Snowflake query id, duration, and error text.

That is still enough to learn the schema shape, the persona topology, and which
questions were refused. The error text is the sharpest part, since a refusal
message can quote what was asked for. Not encrypted, not rotated, not
permission-scoped.

**5. ~~The MCP server is unauthenticated.~~ CLOSED for the reachable case.**
Over stdio the server still trusts its transport, and that is sound: the pipe
comes from a process the user started and the operating system is the boundary.

The risk was that the SDK also speaks `sse` and `streamable-http`, so network
exposure was one argument away, and on those transports "trusts its transport"
means anyone who can reach the port is the persona. A network transport now
refuses to start without `GAA_MCP_TOKEN`, checked **before** the server is built
and before anything binds -- refusing after the port is open is not refusing. A
token under 32 characters is rejected too: a guessable one is the same exposure
plus the belief that it is closed. An unknown transport raises rather than
falling through to the stdio path, because new transports arrive in SDK releases
without asking.

Requests are checked by an ASGI wrapper around the whole app rather than a
route, so nothing reaches the tool surface unauthenticated, and the comparison
uses `compare_digest` so the token cannot be recovered a character at a time.

**Residual.** One shared secret, no rotation, no per-caller identity, and no
TLS termination of its own. It is a gate, not an identity system. Anything
facing a real network wants a reverse proxy doing mTLS or OIDC in front.

**6. The evaluation path is not gated at all.** This was previously written as
if CI ran the chaos suite and the evaluation on every PR. It does not: CI holds
no Snowflake credentials, so every live test skips and 7 of the 8 chaos tests
never execute there. The catch rate in `chaos/README.md` is a local measurement,
not a gate.

A credentialed `warehouse` job now exists that runs the boundary tests, the
invariants, and the chaos suite. Without secrets configured it emits a warning
saying those are not being verified, rather than passing green.

**Residual, and it is the real one.** The secrets are not configured on any
account, so today the gate is written but not armed. Branch protection is also
not configured, and without it a contributor who can push to the default branch
can weaken a chaos variant and have it merge unrun. `docs/ci-setup.md` covers
both, including the uncomfortable part: every service user shares one public
key, so whatever private key CI holds can act as all three personas.

**7. ~~Cost is uncontrolled.~~ CLOSED on the warehouse side.** Three caps, in
increasing bluntness: a 120-second statement timeout on every persona session
(Snowflake's account default is often two days); a row cap with the overflow
disclosed as `truncated` rather than silently shortening the answer; and a
monthly resource monitor on the warehouse, NOTIFY at 80% and SUSPEND at 100%.
Verified live — the session reports a 120s timeout and `GAA_MONITOR` is attached
at warehouse level with a 50-credit monthly quota.

SUSPEND rather than SUSPEND_IMMEDIATE deliberately: killing statements mid-flight
turns a budget event into a data-quality incident, because a half-finished dbt
build looks exactly like a broken model.

**Residual.** Nothing caps *model* spend, which is what actually halted the
experiment here. That limit lives with the model provider, not in this code.

---

## What this model does not cover

Data exfiltration by a legitimately authorised user, insider misuse of the
operator account, Snowflake's own security posture, and anything about the model
provider's handling of prompts and results. All out of scope, none addressed.
