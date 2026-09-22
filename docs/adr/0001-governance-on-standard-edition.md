# ADR 0001 — Persona governance without row access policies

Date: 2026-09-22
Status: Accepted

## Context

The architecture's central claim is that the same analytics question, asked by three different
personas, returns three different *correct* answers — and that the agent cannot get around the
boundary. The original design implemented this with Snowflake row access policies and masking
policies applied to shared tables.

The development account (`YRB45360`) is **Standard Edition**. Both features are gated:

```
CREATE MASKING POLICY ...    -> Unsupported feature 'MASKING POLICY'.
CREATE ROW ACCESS POLICY ... -> Unsupported feature 'ROW ACCESS POLICY'.
```

Verified 2026-09-22 against a live account, not inferred from documentation.

Three options were considered: build on a 30-day Enterprise trial; upgrade the account, which is
not self-serve and raises per-credit pricing roughly 1.5×; or implement the boundary with features
Standard does provide. The third was chosen — no expiry clock, no second account to maintain, and
no dependency on a trial that would lapse before the repository stops being read.

A pluggable backend implementing *both* approaches was considered and rejected as speculative. The
project's own design principle is "Snowflake-native now, portable later if ever… the option stays
open and unpaid for." Building two governance implementations because the dev account is the wrong
tier is paying for portability nobody has asked for.

## Decision

Implement the persona boundary as **one schema per persona, containing identically-named secure
views**, with role grants scoped to a single schema each.

```
GAA.FINANCE.V_BOOKINGS   -- unfiltered            <- GAA_FINANCE_GLOBAL only
GAA.EMEA.V_BOOKINGS      -- WHERE REGION='EMEA'   <- GAA_SALES_DIR_EMEA only
GAA.REP.V_BOOKINGS       -- WHERE OWNER_REP_ID=…  <- GAA_REP_INDIVIDUAL only
GAA.MARTS.FCT_BOOKINGS   -- base table            <- GAA_LOADER only
```

Every persona session connects with its own role *and* its own default schema. Reference SQL uses
**unqualified** table names, so identical SQL text resolves to a different view per persona. The
property the evaluation depends on is preserved exactly.

Masking is emulated inside the restricted views: `ACCOUNT_NAME` is replaced with
`'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8)`. Row counts are unchanged, distinct values are not —
which is precisely what the `masking_preserves_row_count` invariant asserts, so that invariant
remains meaningful and unmodified.

`Persona` gains a `snowflake_schema` field alongside `snowflake_role`. This change lands before the
Task 5 freeze, which is why the freeze begins at Task 5 rather than at Task 2.

## Consequences

**Preserved.** Same question, same SQL, three different correct answers. Enforcement lives in the
warehouse, not in the agent or the prompt. The bypass tests remain meaningful and get one new case:
a persona must not be able to read another persona's schema, nor the base tables in `MARTS`.

**Lost.** The repository cannot demonstrate `CREATE ROW ACCESS POLICY` or `CREATE MASKING POLICY`
directly. Where the target audience names those features specifically, this is a real gap and is
stated plainly rather than papered over. The mechanism differs; the guarantee does not.

**Weaker in one specific way, and worth being honest about.** Row access policies attach to the
table, so they hold however the data is reached. Schema-scoped views rely on grants being correct —
a mis-grant exposes a whole schema rather than being caught by a policy predicate. The conformance
suite therefore tests grants adversarially, and the threat model lists mis-granted schema access as
a primary failure mode rather than a footnote.

**Portable.** Standard Edition is the floor, so any Snowflake account can deploy this, which widens
the set of people who can run `make deploy` and see it work. An Enterprise variant using native
policies remains a clean future addition behind the same conformance suite — and if it is ever
built, this ADR records why it was not built first.
