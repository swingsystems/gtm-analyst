"""The Salesforce-shaped source must be the same facts, not similar ones.

Salesforce is the schema most GTM data actually arrives in, so the first
question an adopter asks is whether this architecture sits on top of a real CRM.
The answer is only worth anything if the numbers come out identical -- a source
adapter that is approximately right is worse than none, because it moves totals
without anybody noticing.

These run offline against the generated seeds. The live proof is stronger and
slower: building the whole warehouse with `--vars 'source_system: salesforce'`
yields the same 10,826,071.18 the README quotes, from Account and Opportunity
rather than from raw_accounts and raw_bookings.
"""
import csv
from decimal import Decimal
from pathlib import Path

import pytest

from gtm_analyst.adapters.salesforce import build, country_for, salesforce_id

SEEDS = Path(__file__).parent.parent / "warehouse" / "seeds"
SF = SEEDS / "salesforce"

_COUNTRY_TO_REGION = {
    **{c: "AMER" for c in ("US", "CA", "BR", "MX")},
    **{c: "EMEA" for c in ("GB", "DE", "FR", "NL", "ES")},
    **{c: "APAC" for c in ("JP", "AU", "SG", "IN")},
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def native() -> dict[str, list[dict]]:
    return {n: _rows(SEEDS / f"raw_{n}.csv")
            for n in ("accounts", "bookings", "territory_assignments")}


@pytest.fixture(scope="module")
def sfdc() -> dict[str, list[dict]]:
    return {p.stem: _rows(p) for p in sorted(SF.glob("sfdc_*.csv"))}


def test_the_salesforce_seeds_exist_and_are_not_empty(sfdc) -> None:
    """A glob matching nothing would make every test below vacuously pass."""
    assert set(sfdc) == {
        "sfdc_account", "sfdc_opportunity", "sfdc_user",
        "sfdc_territory2", "sfdc_user_territory2_association",
    }
    assert all(rows for rows in sfdc.values())


def test_every_booking_survives_as_a_closed_won_opportunity(native, sfdc) -> None:
    """Row loss here shows up downstream as a smaller total that still looks
    plausible -- the failure mode the fiscal-calendar bug already demonstrated."""
    assert len(sfdc["sfdc_opportunity"]) == len(native["bookings"])
    assert all(o["StageName"] == "Closed Won" for o in sfdc["sfdc_opportunity"])
    assert all(o["IsWon"] == "true" and o["IsClosed"] == "true"
               for o in sfdc["sfdc_opportunity"])


def test_the_total_is_penny_identical(native, sfdc) -> None:
    """Decimal, not float. A cent of drift between two representations of the
    same facts is indistinguishable from a real metric error."""
    native_total = sum(Decimal(b["AMOUNT"]) for b in native["bookings"])
    sf_total = sum(Decimal(o["Amount"]) for o in sfdc["sfdc_opportunity"])
    assert sf_total == native_total


def test_billing_country_maps_back_to_exactly_the_original_region(native, sfdc) -> None:
    """Region is derived from BillingCountry in staging, as it is in a real org.
    If that mapping is not exact the persona boundary silently moves -- an
    account landing in the wrong region is visible to the wrong director."""
    by_ext = {a["External_Id__c"]: a for a in sfdc["sfdc_account"]}
    for account in native["accounts"]:
        country = by_ext[account["ACCOUNT_ID"]]["BillingCountry"]
        assert _COUNTRY_TO_REGION[country] == account["REGION"], account["ACCOUNT_ID"]


def test_an_empty_segment_stays_empty_rather_than_becoming_a_literal(native, sfdc) -> None:
    """Salesforce picklists are routinely blank. q010 exists to prove the NULL
    group survives aggregation, and a source adapter that helpfully fills it in
    would delete the question."""
    blank_native = {a["ACCOUNT_ID"] for a in native["accounts"] if not a["SEGMENT"].strip()}
    blank_sf = {a["External_Id__c"] for a in sfdc["sfdc_account"]
                if not a["Segment__c"].strip()}
    assert blank_native, "the fixture no longer contains a blank segment"
    assert blank_sf == blank_native


def test_every_owner_and_account_reference_resolves(sfdc) -> None:
    """An Opportunity whose OwnerId points at nothing is the classic broken CRM
    extract, and an inner join downstream turns it into missing revenue."""
    user_ids = {u["Id"] for u in sfdc["sfdc_user"]}
    account_ids = {a["Id"] for a in sfdc["sfdc_account"]}
    for opp in sfdc["sfdc_opportunity"]:
        assert opp["OwnerId"] in user_ids, opp["Id"]
        assert opp["AccountId"] in account_ids, opp["Id"]
    for assoc in sfdc["sfdc_user_territory2_association"]:
        assert assoc["UserId"] in user_ids


def test_a_rep_holding_only_a_territory_still_exists_as_a_user(native, sfdc) -> None:
    """Users are the union of account owners and territory holders. Taking only
    one source drops reps who hold a territory but own no account."""
    expected = ({a["OWNER_REP_ID"] for a in native["accounts"]}
                | {t["REP_ID"] for t in native["territory_assignments"]})
    assert {u["External_Id__c"] for u in sfdc["sfdc_user"]} == expected


def test_territory_effective_dates_are_carried_across_unchanged(native, sfdc) -> None:
    """q011's fan-out trap depends on these windows. Shifting one by a day is a
    defect this project has already shipped once, in both directions."""
    native_windows = {(t["TERRITORY_ID"], t["REP_ID"], t["VALID_FROM"], t["VALID_TO"])
                      for t in native["territory_assignments"]}
    terr = {t["Id"]: t["External_Id__c"] for t in sfdc["sfdc_territory2"]}
    user = {u["Id"]: u["External_Id__c"] for u in sfdc["sfdc_user"]}
    sf_windows = {(terr[a["Territory2Id"]], user[a["UserId"]],
                   a["EffectiveStartDate"], a["EffectiveEndDate"])
                  for a in sfdc["sfdc_user_territory2_association"]}
    assert sf_windows == native_windows


def test_ids_carry_the_salesforce_object_key_prefix() -> None:
    """The first three characters of a Salesforce Id identify the object. A
    mapping that gets this wrong looks right and joins nothing."""
    assert salesforce_id("Account", "ACC00001").startswith("001")
    assert salesforce_id("Opportunity", "BK000001").startswith("006")
    assert salesforce_id("User", "REP001").startswith("005")
    assert len(salesforce_id("Account", "ACC00001")) == 18


def test_ids_are_stable_across_regeneration() -> None:
    """Random Ids would churn every foreign key in the diff on each run and make
    a failure impossible to reproduce."""
    assert salesforce_id("Account", "ACC00042") == salesforce_id("Account", "ACC00042")
    assert country_for("EMEA", "ACC00042") == country_for("EMEA", "ACC00042")


def test_regenerating_the_seeds_reproduces_them_byte_for_byte(tmp_path, native) -> None:
    """Otherwise the committed seeds and the generator have quietly diverged and
    nobody can tell which one the recorded results came from."""
    build(SEEDS, tmp_path)
    for path in sorted(SF.glob("sfdc_*.csv")):
        assert (tmp_path / path.name).read_text() == path.read_text(), path.name
