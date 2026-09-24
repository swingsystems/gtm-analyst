import pytest

from gaa.semantic.loader import ContractError, load_contracts

GOOD = """
name: bookings_amount
version: 1
description: Value of bookings signed in the period.
owner: sales-ops
table: V_BOOKINGS
grain: booking
measure:
  column: AMOUNT
  aggregation: sum
period_column: FISCAL_QUARTER
null_policy: preserve
dimensions:
  - {name: region, column: REGION, description: Account region}
default_filters:
  - {column: IS_INTERCOMPANY, op: eq, value: "false"}
"""


def _write(root, name, body):
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(body)


def test_loads_a_valid_directory(tmp_path):
    _write(tmp_path, "bookings.yaml", GOOD)
    contracts = load_contracts(tmp_path)
    assert "bookings_amount@1" in contracts.metrics
    assert contracts.metrics["bookings_amount@1"].owner == "sales-ops"


def test_same_name_different_versions_both_load(tmp_path):
    _write(tmp_path, "v1.yaml", GOOD)
    _write(tmp_path, "v2.yaml", GOOD.replace("version: 1", "version: 2"))
    contracts = load_contracts(tmp_path)
    assert {"bookings_amount@1", "bookings_amount@2"} <= set(contracts.metrics)


def test_duplicate_name_and_version_raises(tmp_path):
    _write(tmp_path, "a.yaml", GOOD)
    _write(tmp_path, "b.yaml", GOOD)
    with pytest.raises(ContractError, match="duplicate"):
        load_contracts(tmp_path)


def test_missing_directory_raises_contract_error_not_oserror(tmp_path):
    """Pointing it at the wrong path is the most likely first mistake. It must
    say so, not emit a traceback that reads as a broken tool."""
    with pytest.raises(ContractError):
        load_contracts(tmp_path / "nope")


def test_malformed_contract_names_the_file(tmp_path):
    _write(tmp_path, "broken.yaml", "name: x\n")
    with pytest.raises(ContractError, match="broken.yaml"):
        load_contracts(tmp_path)


def test_unsafe_yaml_tag_is_rejected(tmp_path):
    """The guard against code execution via a malicious contract file."""
    _write(tmp_path, "evil.yaml", GOOD + "\nevil: !!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(ContractError):
        load_contracts(tmp_path)


def test_a_contract_carrying_sql_is_rejected(tmp_path):
    """extra=forbid on the model means a 'sql' key fails here rather than being
    silently dropped — silence is how SQL would get into a schema that promises
    it holds none."""
    _write(tmp_path, "sneaky.yaml", GOOD + "\nsql: SELECT 1\n")
    with pytest.raises(ContractError):
        load_contracts(tmp_path)


def test_empty_directory_raises(tmp_path):
    """An empty contract set means every later metric lookup fails with a
    confusing 'unknown metric' rather than the real cause."""
    tmp_path.mkdir(exist_ok=True)
    with pytest.raises(ContractError, match="no contracts"):
        load_contracts(tmp_path)


def test_the_yaml_tag_is_rejected_AT_THE_PARSE_LAYER(tmp_path):
    """Pin the mechanism, not just the outcome.

    The test above asserts a ContractError is raised, which `extra="forbid"`
    would also produce by rejecting the unknown `evil:` key. So it stays green
    even if `safe_load` is swapped for `yaml.load` -- except by then os.system
    has already run. Verified: doing exactly that prints PWNED and the test
    still passes.

    The parse layer must be what refuses, so this asserts the ContractError was
    caused by a YAMLError rather than by model validation.
    """
    import yaml

    _write(tmp_path, "evil.yaml",
           GOOD + "\nevil: !!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(ContractError) as excinfo:
        load_contracts(tmp_path)
    assert isinstance(excinfo.value.__cause__, yaml.YAMLError), (
        "the tag must be refused while parsing, before any value reaches the "
        f"model; cause was {type(excinfo.value.__cause__).__name__}"
    )
