"""Reshape the synthetic warehouse into Salesforce's object model.

Salesforce is the schema most GTM data actually arrives in, so "can this
architecture sit on top of a real CRM" is the first question an adopter asks.
This answers it concretely: the same facts, re-expressed as Account,
Opportunity, User, Territory2 and UserTerritory2Association, with Salesforce's
own naming and conventions.

**No Salesforce connection is involved and none is required.** Nothing here
calls an API or reads an org. The data is the same synthetic data, reshaped.
What it demonstrates is that the governance boundary and the evaluation do not
depend on the source system -- swap it, and every recorded answer still
reconciles.

What is faithful to Salesforce, because the details are where a mapping breaks:

* **18-character Ids with object key prefixes.** 001 Account, 006 Opportunity,
  005 User, 0MI Territory2. Real Ids are case-sensitive 15-char with a 3-char
  case-safe suffix; these are 18 characters in the same shape.
* **Custom fields carry `__c`.** A field without it is standard, and inventing a
  standard field is the mistake that makes a mapping look right and behave wrong.
* **External Id fields.** Every real integration has them -- they are how a
  Salesforce record points back at the system that created it. Here they carry
  the warehouse's own keys, which is why results reconcile exactly.
* **Closed-won semantics.** A booking is an Opportunity with StageName
  'Closed Won', IsWon and IsClosed true. Pipeline that never closed is not a
  booking, and conflating them is the most common GTM reporting error there is.
* **Region is derived, not stored.** Accounts carry BillingCountry, as a real
  org does, and the staging layer maps country to region. A CRM rarely hands you
  the rollup you report on.

What is NOT here, deliberately: billings and revenue. Salesforce is the CRM, not
the revenue sub-ledger -- in a real deployment those come from an ERP, and
pretending Salesforce owns them would misrepresent both systems.
"""
import csv
from pathlib import Path

Row = dict[str, str]

# Salesforce key prefixes. The first three characters of an Id identify the
# object, which is why a mis-typed Id is usually obvious on sight.
_PREFIX = {
    "Account": "001",
    "Opportunity": "006",
    "User": "005",
    "Territory2": "0MI",
}

# A CRM stores where the account is, not which reporting region it rolls into.
# The rollup is a modelling decision, and putting it in staging is what makes it
# reviewable instead of buried in a report.
_REGION_COUNTRIES = {
    "AMER": ["US", "CA", "BR", "MX"],
    "EMEA": ["GB", "DE", "FR", "NL", "ES"],
    "APAC": ["JP", "AU", "SG", "IN"],
}


def salesforce_id(obj: str, key: str) -> str:
    """A stable 18-character Id for a warehouse key.

    Deterministic rather than random so regenerating the seeds does not churn
    every foreign key in the diff, and so a failure is reproducible.
    """
    prefix = _PREFIX[obj]
    digits = "".join(ch for ch in key if ch.isdigit()) or "0"
    body = f"{int(digits):012d}"[:12]
    return f"{prefix}{body}AAA"[:18].ljust(18, "A")


def country_for(region: str, key: str) -> str:
    """Pick a country inside the region, deterministically from the key.

    The reverse mapping in staging must be exact, so the country is chosen from
    the region rather than invented independently.
    """
    countries = _REGION_COUNTRIES[region]
    digits = "".join(ch for ch in key if ch.isdigit()) or "0"
    return countries[int(digits) % len(countries)]


def _read(path: Path) -> list[Row]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _write(path: Path, rows: list[Row], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _users(accounts: list[Row], territories: list[Row]) -> list[Row]:
    """One User per rep, from every rep referenced anywhere.

    Taking the union rather than one source matters: a rep who owns no account
    but does hold a territory still has to exist, and an Opportunity whose
    OwnerId points at nothing is the classic broken CRM extract.
    """
    rep_ids = sorted(
        {a["OWNER_REP_ID"] for a in accounts} | {t["REP_ID"] for t in territories}
    )
    return [
        {
            "Id": salesforce_id("User", rep),
            "External_Id__c": rep,
            "Name": f"Rep {rep[-3:]}",
            "Username": f"{rep.lower()}@example.invalid",
            "IsActive": "true",
        }
        for rep in rep_ids
    ]


def build(seeds_dir: Path, out_dir: Path) -> dict[str, int]:
    """Write Salesforce-shaped CSVs from the canonical seeds."""
    accounts = _read(seeds_dir / "raw_accounts.csv")
    bookings = _read(seeds_dir / "raw_bookings.csv")
    territories = _read(seeds_dir / "raw_territory_assignments.csv")

    sf_accounts = [
        {
            "Id": salesforce_id("Account", a["ACCOUNT_ID"]),
            "External_Id__c": a["ACCOUNT_ID"],
            "Name": a["ACCOUNT_NAME"],
            "BillingCountry": country_for(a["REGION"], a["ACCOUNT_ID"]),
            # Empty stays empty. Salesforce picklists are routinely blank, and
            # q010 exists to prove the resulting NULL group survives aggregation.
            "Segment__c": a["SEGMENT"],
            "OwnerId": salesforce_id("User", a["OWNER_REP_ID"]),
            "CreatedDate": a["CREATED_DATE"],
        }
        for a in accounts
    ]

    sf_opps = [
        {
            "Id": salesforce_id("Opportunity", b["BOOKING_ID"]),
            "External_Id__c": b["BOOKING_ID"],
            "AccountId": salesforce_id("Account", b["ACCOUNT_ID"]),
            "OwnerId": salesforce_id("User", b["OWNER_REP_ID"]),
            "Name": f"{b['ACCOUNT_NAME']} - {b['LICENSE_TYPE']}",
            "CloseDate": b["BOOKING_DATE"],
            "Amount": b["AMOUNT"],
            "CurrencyIsoCode": b["CURRENCY"],
            "StageName": "Closed Won",
            "IsWon": "true",
            "IsClosed": "true",
            "License_Type__c": b["LICENSE_TYPE"],
            "Term_Months__c": b["TERM_MONTHS"],
            "Is_Intercompany__c": b["IS_INTERCOMPANY"],
        }
        for b in bookings
    ]

    sf_territories = [
        {
            "Id": salesforce_id("Territory2", t["TERRITORY_ID"]),
            "External_Id__c": t["TERRITORY_ID"],
            "Name": f"Territory {t['TERRITORY_ID'][-3:]}",
            "Region__c": t["REGION"],
        }
        for t in {r["TERRITORY_ID"]: r for r in territories}.values()
    ]

    # Salesforce models the rep-to-territory link as its own object with
    # effective dates, which is exactly the effective-dated join q011 tests.
    sf_assignments = [
        {
            "Territory2Id": salesforce_id("Territory2", t["TERRITORY_ID"]),
            "UserId": salesforce_id("User", t["REP_ID"]),
            "EffectiveStartDate": t["VALID_FROM"],
            "EffectiveEndDate": t["VALID_TO"],
        }
        for t in territories
    ]

    sf_users = _users(accounts, territories)

    written = {}
    for name, rows in [
        ("sfdc_account", sf_accounts),
        ("sfdc_opportunity", sf_opps),
        ("sfdc_user", sf_users),
        ("sfdc_territory2", sf_territories),
        ("sfdc_user_territory2_association", sf_assignments),
    ]:
        _write(out_dir / f"{name}.csv", rows, list(rows[0]))
        written[name] = len(rows)
    return written


if __name__ == "__main__":  # pragma: no cover - a thin CLI over build()
    seeds = Path(__file__).parent.parent.parent / "warehouse" / "seeds"
    written = build(seeds, seeds / "salesforce")
    for name, count in written.items():
        print(f"{name}: {count} rows")
    print(f"-> {seeds / 'salesforce'}")
