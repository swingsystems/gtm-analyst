"""Substituting account-specific identifiers into governance DDL.

DDL cannot bind parameters. `GRANT ROLE r TO USER ?` is not a thing, so the
operator's username, the warehouse, and the service-user prefix have to be
interpolated as text. That is the one place in this repository where string
interpolation into SQL is unavoidable, and it is therefore the one place where
*validation* is the control rather than a supplement to it.

Everywhere else -- the whole query path in gtm_analyst.semantic.compile -- caller values
bind server-side and are deliberately not sanitised, because sanitising invites
treating validation as the defence. The distinction is worth keeping straight:
here there is no binding to fall back on, so values must be bare identifiers and
anything else is refused before a connection is opened.
"""
import re

# {{ name }}, with optional surrounding whitespace. Deliberately not a general
# template language: no expressions, no filters, no conditionals. A governance
# file that needs logic needs a code review, not a bigger templating engine.
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

# An RSA public key in PEM body form is base64 and cannot pass the identifier
# check. It is exempt by NAME, not by shape, so the exemption cannot be borrowed
# by some later value that reaches a GRANT.
_NOT_AN_IDENTIFIER = frozenset({"public_key"})

# Values that are numbers, not names. Exempt from the identifier rule but NOT
# unchecked: they still go into DDL as text, so they are validated as digits.
# Widening _IDENTIFIER to admit leading digits would have been the lazy fix and
# would have let "50; DROP" through in a value that was never meant to be one.
_NUMERIC = frozenset({"credit_quota"})
_DIGITS = re.compile(r"^[0-9]+$")


class UnknownPlaceholder(KeyError):
    """The DDL asked for a value the caller did not supply.

    Raised rather than substituting an empty string: a blank operator name turns
    `GRANT ROLE x TO USER {{ operator }}` into a syntax error if you are lucky
    and a grant to the wrong principal if you are not.
    """


def placeholders(sql: str) -> set[str]:
    """Every name the SQL asks for. Used to check a file is satisfiable."""
    return {m.group(1) for m in _PLACEHOLDER.finditer(sql)}


def render(sql: str, values: dict[str, str]) -> str:
    """Substitute `{{ name }}` from `values`, refusing anything unsafe."""
    missing = placeholders(sql) - set(values)
    if missing:
        raise UnknownPlaceholder(
            f"governance DDL needs values that were not supplied: {sorted(missing)}"
        )

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        value = values[name]
        if name in _NUMERIC:
            if not _DIGITS.match(value):
                raise ValueError(f"{name}={value!r} must be a whole number")
            return value
        if name not in _NOT_AN_IDENTIFIER and not _IDENTIFIER.match(value):
            raise ValueError(
                f"{name}={value!r} is not a bare identifier; it would be "
                f"interpolated into DDL, where nothing can bind it"
            )
        return value

    return _PLACEHOLDER.sub(_sub, sql)
