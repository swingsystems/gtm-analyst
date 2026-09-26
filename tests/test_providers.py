"""One agent loop, more than one model provider.

The point is not portability for its own sake. The recorded 25 cells were
produced by claude-sonnet-5, and the honest way to use a second provider is a
COMPLETE separate replication -- never to fill in missing cells of the first
grid. Mixing models inside one grid means an arm difference could be a model
difference, which is the same class of error as comparing an arm against itself.

So what these tests protect is comparability. Every provider must receive the
identical system prompt and the identical tool surface, because a cross-model
result is worthless if the two models were asked different questions.
"""
import json

import pytest

from gtm_analyst.agent.providers import (
    PROVIDERS,
    ToolCall,
    Turn,
    anthropic_tools,
    openai_messages,
    openai_tools,
    provider_for,
)
from gtm_analyst.agent.runner import ARM_TOOLS, _tool_schemas


def test_both_providers_are_registered() -> None:
    assert {"anthropic", "openai"} <= set(PROVIDERS)


def test_an_unknown_provider_refuses_rather_than_defaulting() -> None:
    """Silently falling back to the default would mean a run labelled openai
    was actually claude -- an experiment that lies about its own arm."""
    with pytest.raises(KeyError, match="unknown provider"):
        provider_for("mistral", model="whatever")


def test_the_tool_surface_is_identical_across_providers() -> None:
    """Same tools, same names, same required arguments. If one provider is
    shown a smaller surface it is a different experiment."""
    canonical = _tool_schemas("strict-contract")
    a = anthropic_tools(canonical)
    o = openai_tools(canonical)
    assert [t["name"] for t in a] == [f["function"]["name"] for f in o]
    for src, fn in zip(canonical, o, strict=True):
        assert fn["function"]["parameters"] == src["input_schema"]
        assert fn["function"]["description"] == src["description"]


def test_openai_tools_use_the_function_wrapper_shape() -> None:
    """OpenAI nests under {"type": "function", "function": {...}} while
    Anthropic is flat. Getting this wrong means the model is offered no tools
    and answers from memory, which looks like a bad model rather than a bug."""
    o = openai_tools(_tool_schemas("free-sql"))
    assert all(f["type"] == "function" for f in o)
    assert all({"name", "description", "parameters"} <= set(f["function"]) for f in o)


def test_anthropic_tools_keep_input_schema_not_parameters() -> None:
    a = anthropic_tools(_tool_schemas("free-sql"))
    assert all("input_schema" in t and "parameters" not in t for t in a)


def test_every_arm_advertises_a_nonempty_surface_to_both() -> None:
    for arm in ARM_TOOLS:
        canonical = _tool_schemas(arm)
        assert canonical, arm
        assert len(openai_tools(canonical)) == len(anthropic_tools(canonical)) == len(canonical)


# ---------------------------------------------------------------- message shape

def test_a_tool_result_becomes_a_tool_role_message_for_openai() -> None:
    """Anthropic returns results as a user message containing tool_result
    blocks; OpenAI expects one message per result with role "tool" and the
    call id. Collapsing several results into one message loses the pairing and
    the model silently answers against the wrong tool output."""
    history = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "a1", "name": "list_metrics", "input": {}},
            {"type": "tool_use", "id": "a2", "name": "describe_metric",
             "input": {"metric": "bookings_amount"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "a1", "content": "[]"},
            {"type": "tool_result", "tool_use_id": "a2", "content": "{}"},
        ]},
    ]
    out = openai_messages(history)
    tool_msgs = [m for m in out if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert {m["tool_call_id"] for m in tool_msgs} == {"a1", "a2"}


def test_assistant_tool_calls_carry_json_encoded_arguments() -> None:
    """OpenAI wants arguments as a JSON STRING. Passing a dict is accepted by
    some clients and rejected by others, and a rejected call reads as a refusal."""
    history = [
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "x", "name": "query_metric",
             "input": {"metric": "bookings_amount", "dimensions": ["region"]}},
        ]},
    ]
    call = openai_messages(history)[0]["tool_calls"][0]
    assert isinstance(call["function"]["arguments"], str)
    assert json.loads(call["function"]["arguments"])["dimensions"] == ["region"]


def test_plain_text_assistant_turns_survive_the_conversion() -> None:
    """The final answer is text. Dropping it would make every run look like a
    refusal."""
    history = [{"role": "assistant", "content": [
        {"type": "text", "text": "Total bookings were 10826071.18"}]}]
    assert "10826071.18" in openai_messages(history)[0]["content"]


def test_an_error_result_is_still_delivered_to_the_model() -> None:
    """A refusal is information the agent should act on. Dropping errors would
    make constrained arms look worse for a reason the experiment is not
    measuring."""
    history = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "e", "is_error": True,
         "content": "ToolError: no such dimension"}]}]
    out = openai_messages(history)
    assert "no such dimension" in out[0]["content"]


# ---------------------------------------------------------------- turn parsing

def test_a_turn_with_no_tool_calls_is_final() -> None:
    assert Turn(text="done", tool_calls=[]).is_final
    assert not Turn(text="", tool_calls=[ToolCall("1", "list_metrics", {})]).is_final
