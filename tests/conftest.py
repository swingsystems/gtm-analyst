"""A provider spending limit is not a test failure.

Someone forking this repository and running pytest with an unfunded or
exhausted Anthropic key would otherwise see five red tests and conclude the
project is broken. The thing being reported -- "your API budget is gone" -- is
true of their account and says nothing about this code, and a skip communicates
that where a failure does not.

Narrow on purpose. This converts ONLY the provider's usage-limit, rate-limit,
and credit-balance responses. Every other API error still fails, because
swallowing those is how a broken agent arm passes CI forever.
"""
import anthropic
import pytest

# Only the provider's own error types. A network error or a bug in this code
# raises something else and must still fail.
_PROVIDER_ERRORS = (anthropic.RateLimitError, anthropic.BadRequestError)

_LIMIT_MARKERS = ("usage limit", "rate limit", "credit balance")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    outcome = yield
    excinfo = outcome.excinfo
    if excinfo is None:
        return
    exc = excinfo[1]
    # isinstance, not the concrete type's module. Checking __module__ misses any
    # subclass defined outside the anthropic package -- including the ones in
    # this repository's own tests, which is how that bug was found.
    if not isinstance(exc, _PROVIDER_ERRORS):
        return
    if any(marker in str(exc).lower() for marker in _LIMIT_MARKERS):
        outcome.force_exception(
            pytest.skip.Exception(
                f"provider limit reached, not a code failure: {exc}", _use_item_location=True
            )
        )
