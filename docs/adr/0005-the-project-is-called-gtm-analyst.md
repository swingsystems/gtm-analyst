# ADR 0005 — The project is called GTM Analyst, and the warehouse objects are not renamed with it

Date: 2026-09-25
Status: Accepted

## Context

The project shipped under a working title and an internal package named `gaa`,
for "governed analytics agents". That abbreviation meant something to its author
and nothing to anyone else, which is a poor property for something meant to be
found and forked.

## Decision

**GTM Analyst.** Repository `gtm-analyst`, package `gtm_analyst`, CLI `gtm`.

It names the *role* rather than a metaphor. Every go-to-market org already has an
analyst — the person who answers "what were Q3 bookings for EMEA?" and whose
answer other people act on. This project is that analyst, with a boundary the
analyst cannot cross and a receipt attached to every number. Both audiences the
project needs reach it from one name: GTM people recognise the job, and the
AI-agent framing follows without explanation.

It also survives the architecture. The code is domain-agnostic — see
`docs/bring-your-own-models.md` — and "analyst" stays true when somebody points
it at a warehouse that has nothing to do with go-to-market. A name like
`gtm-agents` describes the mechanism; this one describes what it does for you.

Names rejected, with the reason, because the reasons are reusable:

| Rejected | Why |
|---|---|
| Clearbook | [Clear Books](https://www.clearbooks.co.uk) is UK accounting software. Too close for a project with a finance persona. |
| Purview | Microsoft Purview is a data governance product — the same category. |
| Quotascope | Promises quota; the project computes bookings and revenue and has no quota metric. |
| Sightline, Vantage, Warrant, Provenance, Territory | Already taken on PyPI. |
| Anything containing "book" | Drowns in bookkeeping search results. |

## The warehouse objects keep their `GAA_` prefix

`GAA`, `GAA_LOADER`, `GAA_FINANCE_GLOBAL`, `GAA_SALES_DIR_EMEA`,
`GAA_REP_INDIVIDUAL`, and `GAA_MONITOR` are **not** renamed.

Renaming them would be cosmetic and would cost real evidence. The 25 recorded
answer cards in `results/pilot2/` each carry a Snowflake query id that resolves
in `ACCOUNT_USAGE` against those exact role names, and the README quotes one of
them verbatim. Those cards cannot be regenerated — the run they came from was
halted by a provider spending limit, and rerunning the agent to produce
prettier role names would spend money to weaken the audit trail.

The committed privilege baseline in `governance-baseline/grants.json` names them
too, so a rename means re-baselining and losing the drift history that baseline
exists to provide.

So the position is: the database name is already configuration
(`SNOWFLAKE_DATABASE`), and the role names are a deployment detail an adopter
may set to whatever their conventions require. `GAA_` is what this particular
deployment happens to use, and the recorded evidence points at it.

An adopter starting fresh should rename them. This deployment has history, and
history is the point.

## Consequences

- `pip install gtm-analyst`, `gtm demo`, `gtm serve --persona …`.
- The project's own environment variables move from `GAA_*` to `GTM_*`.
  Snowflake's own variables (`SNOWFLAKE_*`) are unchanged.
- Completed plan documents under `docs/superpowers/plans/` still say `gaa`.
  They are dated records of decisions taken under the old name, and editing
  them would be rewriting history for cosmetics.
