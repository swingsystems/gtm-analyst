from gtm_analyst.spec.sql import sql_statements, strip_line_comments


def test_semicolon_in_a_comment_does_not_split_the_statement():
    """The bug this module exists for: prose punctuation in a comment silently
    turned one query into two."""
    sql = """-- Revenue is not the same population as bookings; timing differs.
SELECT 1 AS VALUE
"""
    assert len(sql_statements(sql)) == 1


def test_two_real_statements_are_two():
    assert len(sql_statements("SELECT 1; SELECT 2;")) == 2


def test_trailing_semicolon_is_not_an_empty_statement():
    assert len(sql_statements("SELECT 1;")) == 1


def test_trailing_comment_on_a_code_line_is_removed():
    assert strip_line_comments("SELECT 1 -- pick one\n").strip() == "SELECT 1"


def test_comment_only_input_yields_no_statements():
    assert sql_statements("-- nothing here\n-- still nothing\n") == []
