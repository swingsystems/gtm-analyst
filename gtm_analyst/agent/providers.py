"""One agent loop, more than one model provider.

Not portability for its own sake. The recorded cells were produced by one model,
and the only honest way to use a second provider is a COMPLETE separate
replication -- never to fill in missing cells of an existing grid. Mixing models
inside one grid means an observed arm difference could be a model difference,
which is the same class of error as comparing an arm against itself.

What this module therefore protects is comparability. Every provider receives
the identical system prompt and the identical tool surface, because a
cross-model result is worthless if the two models were asked different
questions. The conversions below are where that guarantee actually lives, and
where a silent bug would confound every number downstream -- so they are tested
directly rather than only through a live run.
"""
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

# A rate limit is a pacing problem, not a failure. The first live run died at
# cell 11 of 108 on a tokens-per-minute 429 -- losing the rest of a grid to a
# limit that clears in well under a second.
MAX_RETRIES = 6
MAX_BACKOFF_SECONDS = 30.0

# Retryable: the call can succeed later. NOT retryable: the account is out of
# money or the request is malformed. Retrying those burns wall-clock on a call
# that cannot succeed and buries the message explaining why it stopped.
_PERMANENT = ("insufficient_quota", "billing", "hard limit", "usage limit")


def backoff_seconds(attempt: int) -> float:
    """Exponential, capped. Uncapped growth on a long grid sleeps for hours."""
    return min(0.5 * (2 ** attempt), MAX_BACKOFF_SECONDS)


def _is_rate_limit(exc: BaseException) -> bool:
    if getattr(exc, "status_code", None) != 429:
        return False
    message = str(exc).lower()
    return not any(marker in message for marker in _PERMANENT)


def call_with_retry(
    func: Callable[[], Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Call `func`, retrying only a transient rate limit.

    Bounded rather than infinite: retrying forever turns a stuck run into a
    silent money leak. A 400 is a bug in our payload and is raised immediately,
    because retrying it hides the bug and charges for the privilege.
    """
    last: BaseException | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return func()
        except Exception as exc:  # re-raised below unless it is a transient 429
            if not _is_rate_limit(exc):
                raise
            last = exc
            if attempt < MAX_RETRIES:
                sleep(backoff_seconds(attempt))
    raise last  # type: ignore[misc]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Turn:
    """One model response, normalised across providers."""

    text: str
    tool_calls: list[ToolCall]
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def is_final(self) -> bool:
        """No tool calls means the model is answering rather than working."""
        return not self.tool_calls


class Provider(Protocol):
    model: str

    def complete(self, system: str, tools: list[dict[str, Any]],
                 history: list[dict[str, Any]]) -> Turn: ...


# --------------------------------------------------------------- tool schemas

def anthropic_tools(canonical: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic's shape is flat, with `input_schema`."""
    return [dict(t) for t in canonical]


def openai_tools(canonical: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenAI nests under {"type": "function", "function": {...}} and calls the
    schema `parameters`.

    Getting this wrong does not error -- the model is simply offered no tools
    and answers from memory, which reads as a weak model rather than a bug.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in canonical
    ]


# ------------------------------------------------------------- message history
#
# The loop keeps history in Anthropic's shape because that is what the recorded
# runs used, and converts on the way out. Converting in one direction only means
# there is a single canonical transcript per cell regardless of provider.

def _reader(block: Any):
    """A uniform getter for a content block, dict or SDK object."""
    if isinstance(block, dict):
        return lambda key, default=None: block.get(key, default)
    return lambda key, default=None: getattr(block, key, default)


def openai_messages(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate an Anthropic-shaped transcript into OpenAI's shape.

    Anthropic returns tool results as a user message containing tool_result
    blocks. OpenAI expects ONE message per result, role "tool", carrying the
    call id. Collapsing several results into one message loses the pairing, and
    the model then answers against the wrong tool's output without complaining.
    """
    out: list[dict[str, Any]] = []
    for message in history:
        role, content = message["role"], message["content"]

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        tool_calls = []
        texts = []
        for block in content:
            # Blocks arrive either as dicts (our own history) or as SDK objects
            # (an assistant turn appended verbatim), so both are read the same
            # way rather than converted at every call site.
            get = _reader(block)
            kind = get("type")

            if kind == "text":
                texts.append(get("text") or "")
            elif kind == "tool_use":
                tool_calls.append({
                    "id": get("id"),
                    "type": "function",
                    "function": {
                        "name": get("name"),
                        # A JSON STRING, not a dict. Some clients accept a dict
                        # and others reject the call, and a rejected call reads
                        # as the model refusing.
                        "arguments": json.dumps(get("input") or {}, default=str),
                    },
                })
            elif kind == "tool_result":
                out.append({
                    "role": "tool",
                    "tool_call_id": get("tool_use_id"),
                    "content": str(get("content") or ""),
                })

        if tool_calls or texts:
            entry: dict[str, Any] = {"role": role, "content": "\n".join(texts)}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
    return out


# ------------------------------------------------------------------- providers

class AnthropicProvider:
    """The original path, unchanged in behaviour.

    Kept byte-identical so introducing this abstraction cannot move the recorded
    baseline. If refactoring for a second provider changed the first one's
    results, the comparison would be measuring the refactor.
    """

    def __init__(self, model: str, client: Any | None = None):
        import anthropic

        self.model = model
        self._client = client or anthropic.Anthropic()

    def complete(self, system: str, tools: list[dict[str, Any]],
                 history: list[dict[str, Any]]) -> Turn:
        response = call_with_retry(lambda: self._client.messages.create(
            model=self.model, max_tokens=2048, system=system,
            tools=anthropic_tools(tools), messages=history,
        ))
        calls = [
            ToolCall(id=b.id, name=b.name, arguments=dict(b.input))
            for b in response.content if b.type == "tool_use"
        ]
        text = "\n".join(b.text for b in response.content if b.type == "text")
        usage = getattr(response, "usage", None)
        return Turn(text=text, tool_calls=calls, usage={
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        })


# NVIDIA NIM and OpenRouter both serve the OpenAI chat-completions API, so
# they are the same client pointed at a different host rather than new adapters.
# There is deliberately NO automatic switching between them: a grid is
# single-model, and swapping provider partway would make an arm difference
# indistinguishable from a model difference. Choosing another backend is a
# decision to run a separate complete grid.
ENDPOINTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env": "OPENAI_API_KEY",
        "keychain": "openai-api-key",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "env": "NVIDIA_API_KEY",
        "keychain": "nvidia-api-key",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
        "keychain": "openrouter-api-key",
    },
}


def keychain_secret(service: str) -> str | None:
    """Read a secret from the macOS keychain.

    Returned for use, never logged or written to disk. Any failure -- wrong
    platform, missing entry, locked keychain -- is None rather than an
    exception, so the caller can report one clear message naming both places a
    key may live.
    """
    import os
    import subprocess
    import sys

    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
             "-s", service, "-w"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def resolve_key(provider: str, env=None, keychain=keychain_secret) -> str:
    """Find a credential: environment first, then the macOS keychain.

    Environment wins so a run can be pointed at a different account without
    touching the login keychain. A bare "unauthorized" partway through a grid is
    the least useful error there is, so the failure names the provider and both
    places the key could live.
    """
    import os

    env = os.environ if env is None else env
    config = ENDPOINTS[provider]
    found = env.get(config["env"]) or keychain(config["keychain"])
    if not found:
        raise RuntimeError(
            f"no credential for {provider}: set ${config['env']}, or add it to "
            f"the macOS keychain as service {config['keychain']!r}"
        )
    return found


class OpenAIProvider:
    """OpenAI chat completions with tool calling.

    The system prompt is passed as a `system` message rather than reworded for
    the platform. Any edit there, however sensible, would make the cross-model
    comparison a comparison of prompts.
    """

    def __init__(self, model: str, client: Any | None = None,
                 api_key: str | None = None, provider: str = "openai"):
        from openai import OpenAI

        self.model = model
        self.provider = provider
        if client is not None:
            self._client = client
        else:
            config = ENDPOINTS[provider]
            self._client = OpenAI(
                api_key=api_key or resolve_key(provider),
                base_url=config["base_url"],
            )

    def complete(self, system: str, tools: list[dict[str, Any]],
                 history: list[dict[str, Any]]) -> Turn:
        messages = [{"role": "system", "content": system}] + openai_messages(history)
        response = call_with_retry(lambda: self._client.chat.completions.create(
            model=self.model, max_tokens=2048,
            tools=openai_tools(tools), messages=messages,
        ))
        choice = response.choices[0].message
        calls = []
        for call in (choice.tool_calls or []):
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                # Malformed arguments are the model's error, not ours. Passing
                # an empty dict lets the tool surface refuse it and tell the
                # model why, which is the same treatment every other bad call
                # gets.
                arguments = {}
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        usage = getattr(response, "usage", None)
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        return Turn(text=choice.content or "", tool_calls=calls, usage={
            # Cached prompt tokens are billed differently and are reported
            # INSIDE prompt_tokens, so they are subtracted out rather than
            # double counted.
            "input_tokens": max(prompt - cached, 0),
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "cache_read_tokens": cached,
            "cache_write_tokens": 0,
        })


def _openai_compatible(name: str):
    """Bind one OpenAI-compatible backend to its endpoint."""
    def build(model: str, **kwargs: Any) -> OpenAIProvider:
        return OpenAIProvider(model=model, provider=name, **kwargs)
    return build


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": _openai_compatible("openai"),
    "nvidia": _openai_compatible("nvidia"),
    "openrouter": _openai_compatible("openrouter"),
}


def provider_for(name: str, model: str, **kwargs: Any) -> Provider:
    """Build a provider by name, refusing an unknown one.

    Falling back to a default would mean a run labelled openai was actually
    anthropic -- an experiment that misreports its own conditions.
    """
    try:
        factory = PROVIDERS[name]
    except KeyError:
        raise KeyError(
            f"unknown provider {name!r}; have {sorted(PROVIDERS)}. Refusing to "
            f"default, because a run must not misreport which model produced it"
        ) from None
    return factory(model=model, **kwargs)
