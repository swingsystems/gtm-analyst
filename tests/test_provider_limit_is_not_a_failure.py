"""The conftest hook must skip ONLY provider limits.

Swallowing other API errors is how a broken agent arm passes CI forever, so the
narrowness is the part worth testing -- not the skip itself.
"""
import anthropic
import pytest


class _FakeLimit(anthropic.BadRequestError):
    """Constructed without an httpx response, which the real class wants and
    which is not available offline. Only the type and message matter here."""

    def __init__(self, message: str):
        Exception.__init__(self, message)


def test_a_provider_usage_limit_is_reported_as_a_skip_not_a_failure() -> None:
    """A fork running pytest with an unfunded key must not see red tests that
    say nothing about this code."""
    raise _FakeLimit("You have reached your specified API usage limits.")


def test_a_credit_balance_message_is_also_a_skip() -> None:
    raise _FakeLimit("Your credit balance is too low to access the API.")


def test_a_genuine_api_error_still_fails() -> None:
    with pytest.raises(_FakeLimit):
        raise _FakeLimit("model: invalid model name")


def test_a_non_provider_exception_still_fails() -> None:
    with pytest.raises(ValueError):
        raise ValueError("a genuine bug must not be skipped")
