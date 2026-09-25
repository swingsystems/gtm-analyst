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

from gtm_analyst.spec.sql import strip_line_comments
from gtm_analyst.spec.template import UnknownPlaceholder, placeholders, render

GOVERNANCE = Path(__file__).parent.parent / "warehouse" / "governance"

# Everything the renderer is allowed to supply. A new placeholder must be added
# here AND wired into scripts/apply_governance.py, which is the point: a value
# that cannot be derived from configuration has no business in the DDL.
SUPPLIED = {"operator", "warehouse", "database", "service_user_prefix",
            "public_key", "credit_quota"}


def _sql_files() -> list[Path]:
    return sorted(GOVERNANCE.glob("*.sql"))


def test_the_governance_directory_is_not_empty() -> None:
    """A glob that matches nothing would make every test below vacuously pass."""
    assert len(_sql_files()) >= 4


@pytest.mark.parametrize("path", _sql_files(), ids=lambda p: p.name)
def test_no_principal_is_named_literally(path: Path) -> None:
    """Match the shape of a hardcoded principal, not one known bad name.

    The first version of this test forbade the literal string of the developer's
    own username. That catches exactly one mistake -- the one already made --
    and passes happily for the next person who writes their own username in.
    A USER or WAREHOUSE that is not a placeholder is the actual defect.
    """
    # Comments first: these files explain themselves at length, and prose like
    # "one service user per persona" is not a grant.
    text = strip_line_comments(path.read_text())
    # Collapse placeholder bodies too: "{{ warehouse }}" contains the very word
    # being searched for, so the scan would flag the fix as the defect.
    text = re.sub(r"\{\{\s*\w+\s*\}\}", "{{}}", text)
    for keyword in ("USER", "WAREHOUSE"):
        for match in re.finditer(rf"\b{keyword}\s+(?!IF\b)(\S+)", text, re.IGNORECASE):
            named = match.group(1)
            assert named.startswith("{{"), (
                f"{path.name} names {keyword} {named} literally; it must come from "
                f"configuration, since it does not exist on anybody else's account"
            )
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


def test_a_numeric_value_is_checked_as_digits_not_waved_through() -> None:
    """credit_quota is a number, so the identifier rule rejects it. The fix must
    be a numeric class, not a wider identifier rule -- widening _IDENTIFIER to
    admit leading digits would have let '50; DROP DATABASE GAA' through."""
    assert render("CREDIT_QUOTA = {{ credit_quota }}", {"credit_quota": "50"}) \
        == "CREDIT_QUOTA = 50"
    with pytest.raises(ValueError, match="whole number"):
        render("CREDIT_QUOTA = {{ credit_quota }}", {"credit_quota": "50; DROP DATABASE GAA"})
