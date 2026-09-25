"""Governance DDL must not name this developer's account.

The README claims `make deploy` runs against any Snowflake account. It did not:
the operator username, the warehouse, and a public key were written literally
into the DDL, so a stranger's first deploy would have granted roles to a user
that does not exist on their account. These tests are what makes the claim true
rather than aspirational.
"""
import re
from pathlib import Path

import pytest

from gaa.spec.template import UnknownPlaceholder, placeholders, render

GOVERNANCE = Path(__file__).parent.parent / "warehouse" / "governance"

# Everything the renderer is allowed to supply. A new placeholder must be added
# here AND wired into scripts/apply_governance.py, which is the point: a value
# that cannot be derived from configuration has no business in the DDL.
SUPPLIED = {"operator", "warehouse", "database", "service_user_prefix", "public_key"}


def _sql_files() -> list[Path]:
    return sorted(GOVERNANCE.glob("*.sql"))


def test_the_governance_directory_is_not_empty() -> None:
    """A glob that matches nothing would make every test below vacuously pass."""
    assert len(_sql_files()) >= 4


@pytest.mark.parametrize("path", _sql_files(), ids=lambda p: p.name)
def test_no_account_specific_identifier_is_hardcoded(path: Path) -> None:
    text = path.read_text()
    # The developer's username, the default warehouse on a trial account, and a
    # literal RSA key -- each one silently wrong on somebody else's account.
    for literal in ("GAA_OPERATOR", "COMPUTE_WH"):
        assert literal not in text.upper(), f"{path.name} hardcodes {literal}"
    assert not re.search(r"RSA_PUBLIC_KEY\s*=\s*'(?!\{\{)", text), (
        f"{path.name} embeds a literal public key"
    )


@pytest.mark.parametrize("path", _sql_files(), ids=lambda p: p.name)
def test_every_placeholder_can_be_supplied(path: Path) -> None:
    unknown = placeholders(path.read_text()) - SUPPLIED
    assert not unknown, f"{path.name} needs values nothing supplies: {sorted(unknown)}"


def test_rendering_refuses_a_placeholder_it_was_not_given() -> None:
    """Silently leaving `{{ operator }}` in the SQL would be a syntax error at
    best and a grant to the wrong principal at worst. Fail before connecting."""
    with pytest.raises(UnknownPlaceholder, match="operator"):
        render("GRANT ROLE R TO USER {{ operator }};", {"warehouse": "WH"})


def test_rendering_substitutes_and_leaves_the_rest_verbatim() -> None:
    out = render("GRANT USAGE ON WAREHOUSE {{ warehouse }} TO ROLE GAA_LOADER;",
                 {"warehouse": "MY_WH"})
    assert out == "GRANT USAGE ON WAREHOUSE MY_WH TO ROLE GAA_LOADER;"


def test_a_value_that_is_not_an_identifier_is_refused() -> None:
    """These land in DDL, which cannot bind parameters. Validation IS the
    control here, unlike in the query path where binding is."""
    with pytest.raises(ValueError, match="identifier"):
        render("USER {{ operator }};", {"operator": "BOB; DROP DATABASE GAA"})


def test_a_public_key_is_allowed_to_contain_base64_padding() -> None:
    """Keys are not identifiers and are exempt -- but only that one name, so the
    exemption cannot be borrowed by a value that reaches a GRANT."""
    out = render("SET RSA_PUBLIC_KEY='{{ public_key }}';", {"public_key": "MIIBIjAN+/=="})
    assert "MIIBIjAN+/==" in out


def test_teardown_is_never_applied_by_the_apply_script() -> None:
    """teardown.sql sits in the directory apply_governance.py globs, and sorts
    after the four numbered files. Applying it would drop what was just built."""
    from scripts.apply_governance import EXCLUDED

    assert (GOVERNANCE / "teardown.sql").exists()
    assert "teardown.sql" in EXCLUDED


def test_teardown_does_not_drop_the_warehouse() -> None:
    """The warehouse is named by configuration. It may predate this deployment
    or be shared with unrelated work, so tearing it down is not ours to do."""
    text = (GOVERNANCE / "teardown.sql").read_text().upper()
    assert "DROP WAREHOUSE" not in text
