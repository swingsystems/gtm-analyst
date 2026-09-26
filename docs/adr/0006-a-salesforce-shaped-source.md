# ADR 0006 — A Salesforce-shaped source, with synthetic data and no Salesforce connection

Date: 2026-09-25
Status: Accepted

## Context

`docs/bring-your-own-models.md` claims the architecture is source-agnostic: swap
the warehouse and everything above it — marts, secure views, metric contracts,
tool surface, frozen evaluation — is unaffected. That was an assertion. Nothing
demonstrated it, and an unverified claim about portability is exactly the kind
this project exists to be suspicious of.

Salesforce is the schema most go-to-market data actually arrives in, so it is
the honest test case. There is no Salesforce relationship, licence, or org
available here, and inventing one would be worse than not doing it.

## Decision

Reshape the same synthetic data into Salesforce's object model — Account,
Opportunity, User, Territory2, UserTerritory2Association — and let the staging
layer switch between sources on a dbt var.

**No Salesforce connection is involved and none is required.** Nothing calls an
API or reads an org. This is not an integration and is not described as one.

The result is arithmetic rather than rhetorical: building the warehouse with
`--vars 'source_system: salesforce'` produces **10,826,071.18**, the same total
the README quotes, reached through a different source system. All invariants
hold, all ten governance boundary tests pass, and the frozen spec — which may
not be edited — reconciles unchanged.

## Why the details are faithful

A source adapter that is approximately right is worse than none, because it
moves totals without anybody noticing. So the Salesforce conventions that carry
meaning are reproduced rather than approximated: 18-character Ids with object
key prefixes, `__c` on custom fields, `External_Id__c` pointing back at the
originating system, closed-won semantics for what counts as a booking, region
derived from `BillingCountry` rather than stored, and effective-dated territory
assignment as its own object.

Blank `Segment__c` stays blank. Salesforce picklists are routinely empty, q010
exists to prove the NULL group survives aggregation, and an adapter that
helpfully filled it in would have deleted the question.

## What is excluded, and why that is not laziness

**Billings and revenue keep their native source under either setting.**
Salesforce is the CRM, not the revenue sub-ledger. In a real deployment those
come from an ERP, and modelling them as Salesforce objects would misrepresent
both systems to anyone who knows either one.

## Consequences

- Eleven offline tests assert the two sources are the same facts, including
  penny-identical totals using `Decimal`, exact country-to-region round-tripping
  (a wrong region puts an account in front of the wrong director), and
  byte-identical regeneration so the committed seeds and the generator cannot
  quietly diverge.
- Adding the seeds changed the account's privilege set — five new tables owned
  by the loader — and `make check-drift` caught it. That is the detector working
  on a real change rather than an injected one. Verified no persona can read the
  new tables, then re-baselined deliberately: 69 grants to 74.
- The live equivalence is not asserted in CI, because it needs a full rebuild
  against a warehouse. `docs/salesforce-shaped-source.md` gives the commands.
- Two real-org limitations are documented rather than hidden: `IsWon` is current
  state, not what was true at quarter end, so as-of reporting needs
  `OpportunityFieldHistory`; and `CurrencyIsoCode` is carried through
  unconverted, so a multi-currency org summing mixed currencies gets a wrong
  number that no test here will catch.
