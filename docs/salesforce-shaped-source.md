# Running on the Salesforce object model

Salesforce is the schema most go-to-market data actually arrives in, so the
first question an adopter asks is whether this architecture sits on top of a
real CRM rather than on a shape invented to make it work.

It does, and the proof is arithmetic: build the warehouse from Account and
Opportunity instead of from the native seeds, and every number comes out
identical.

```bash
gtm synth                                          # canonical seeds
python -m gtm_analyst.adapters.salesforce          # reshape into SFDC objects
cd warehouse && dbt build --vars 'source_system: salesforce'
gtm check-invariants
```

`sum_of_parts_bookings` reports **10,826,071.18** either way — the same total
the README quotes, reached through a different source system.

## No Salesforce connection is involved

Nothing here calls a Salesforce API, reads an org, or requires a licence. The
data is the same synthetic data, reshaped into Salesforce's object model. What
it demonstrates is that the governance boundary and the frozen evaluation do not
depend on the source system.

## Where the switch lives

Three staging models, and nothing above them:

```
sfdc_account, sfdc_opportunity, sfdc_user,      ─┐
sfdc_territory2, sfdc_user_territory2_association│
                                                 ├─► stg_accounts
raw_accounts, raw_bookings,                      │   stg_bookings          ─► marts ─► persona views
raw_territory_assignments                       ─┘   stg_territory_assignments
```

The marts, the secure views, the metric contracts, the tool surface, and the
twelve frozen questions are all above that line and cannot tell which source
ran. That is the whole claim of `docs/bring-your-own-models.md`, demonstrated
rather than asserted.

## What is faithful, and why each detail matters

| Detail | Why it is not cosmetic |
|---|---|
| 18-character Ids with object key prefixes (001 Account, 006 Opportunity, 005 User, 0MI Territory2) | The first three characters identify the object. A mapping that gets this wrong looks right and joins nothing. |
| Custom fields carry `__c` | Inventing a standard field is the mistake that makes a mapping look correct and behave wrong against a real org. |
| `External_Id__c` on every object | How a real Salesforce record points back at the system that created it. It is also why results reconcile exactly rather than approximately. |
| `StageName = 'Closed Won'`, `IsWon`, `IsClosed` | A booking is a closed-won opportunity. Open pipeline is not revenue, and conflating them is the most common reporting error in GTM. |
| Region derived from `BillingCountry` | A CRM stores where an account *is*, not which region it rolls into. Putting that mapping in staging makes it reviewable instead of buried in a report. |
| `Territory2` + `UserTerritory2Association` with effective dates | Salesforce models rep-to-territory as its own effective-dated object — precisely the join q011 exists to trap. |
| Blank `Segment__c` stays blank | Salesforce picklists are routinely empty. q010 proves the resulting NULL group survives aggregation; an adapter that helpfully filled it in would delete the question. |

## What is deliberately NOT here

**Billings and revenue.** Salesforce is the CRM, not the revenue sub-ledger. In
a real deployment those come from an ERP, and pretending Salesforce owns them
would misrepresent both systems. Those models keep their native source under
either setting.

## Pointing it at a real org

Replace the generated seeds with an extract — Fivetran, Airbyte, Salesforce
Connect, or a Bulk API dump. The staging models expect the field names above; if
your org renamed a custom field, change it in one place.

Two things will bite you, and neither is this project's fault:

- **Opportunity history.** Real orgs reopen and re-close opportunities. `IsWon`
  is the current state, not what was true at quarter end. If you report on
  bookings as-of a date, you need `OpportunityFieldHistory` and this adapter
  does not model it.
- **Currency.** `CurrencyIsoCode` is carried through unconverted. A
  multi-currency org needs `DatedConversionRate`, and summing mixed currencies
  produces a number that is wrong in a way no test here will catch.
