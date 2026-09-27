"""The agent loop, shared by every arm.

One implementation, parameterised by arm. The arms differ in which tools they
are offered and in one paragraph of their system prompt, and in nothing else:
separate loops would drift, and every difference between them would be measured
as if it were a property of the architecture.

Tools are called directly on the ToolSurface rather than over MCP. The MCP
server in gtm_analyst/mcp/server.py wraps this same surface and exists for external
agents; routing the experiment through a subprocess would add moving parts
without changing what is being measured.
"""
import inspect
import json
import re
from pathlib import Path
from typing import Any

import anthropic
from snowflake.connector.errors import Error as SnowflakeError

from gtm_analyst.agent.card import AnswerCard
from gtm_analyst.agent.prompts import system_prompt
from gtm_analyst.agent.providers import provider_for
from gtm_analyst.agent.spend import Spend
from gtm_analyst.mcp.tools import ToolError, ToolSurface
from gtm_analyst.spec.models import Persona

MODEL = "claude-sonnet-5"

# The default model per provider. Named explicitly so a run records which model
# produced it rather than inheriting whatever the SDK considers current.
DEFAULT_MODELS = {
    "anthropic": MODEL,
    "openai": "gpt-4.1",
    # Tool-calling capable and free to evaluate. Named explicitly rather than
    # inherited, so a card records which model produced it.
    # Verified invokable WITH TOOLS on the build tier. NVIDIA's /models listing
    # includes models that are not deployed: several return 410 Gone or 404
    # "Function not found" when actually called, so a default has to be probed
    # rather than read off the catalogue.
    "nvidia": "mistralai/mistral-nemotron",
    "openrouter": "nvidia/nemotron-3.5-lightning:free",
}

# Every arm gets the SAME budget. A turn limit that binds on one arm and not
# another measures patience rather than grounding. Raised from 8 after watching
# the free-SQL arm spend every turn investigating a real data bug and never
# reach an answer.
MAX_TURNS = 16

# Which tools each arm may see. The strict arm is not merely told not to write
# SQL -- run_sql is absent from its tool list, so the separation is structural.
# Whether an arm may see metrics that declare joins. This is the ONLY thing
# separating the two constrained arms, and it has to be enforced rather than
# assumed: both load the same contracts directory, so a join-bearing contract
# added for one arm is visible to the other unless filtered.
ARM_ALLOWS_JOINS: dict[str, bool] = {
    "strict-contract": False,
    "safe-join-contract": True,
    "free-sql": True,
}

ARM_TOOLS: dict[str, tuple[str, ...]] = {
    "strict-contract": ("list_metrics", "describe_metric", "query_metric", "explain_lineage"),
    "safe-join-contract": ("list_metrics", "describe_metric", "query_metric", "explain_lineage"),
    "free-sql": ("list_metrics", "describe_metric", "run_sql", "explain_lineage"),
}

_CONFIDENCE = re.compile(r"^CONFIDENCE:\s*(high|medium|low|none)\b[.:\-]?\s*(.*)$",
                         re.IGNORECASE | re.MULTILINE)
_WHY_NOT = re.compile(r"^WHY_NOT:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _tool_schemas(arm: str) -> list[dict[str, Any]]:
    """Advertise each permitted tool, described by its own docstring."""
    schemas = []
    for name in ARM_TOOLS[arm]:
        method = getattr(ToolSurface, name)
        properties, required = {}, []
        for param, spec in inspect.signature(method).parameters.items():
            if param == "self":
                continue
            annotation = str(spec.annotation)
            if "list[dict]" in annotation:
                kind: dict[str, Any] = {"type": "array", "items": {"type": "object"}}
            elif "list[str]" in annotation:
                kind = {"type": "array", "items": {"type": "string"}}
            else:
                kind = {"type": "string"}
            properties[param] = kind
            if spec.default is inspect.Parameter.empty:
                required.append(param)
        schemas.append({
            "name": name,
            "description": inspect.getdoc(method) or "",
            "input_schema": {"type": "object", "properties": properties, "required": required},
        })
    return schemas


def answer(
    question: str,
    persona: Persona,
    arm: str,
    contracts_root: Path,
    audit_path: Path | None = None,
    client: anthropic.Anthropic | None = None,
    provider: str = "anthropic",
    model: str | None = None,
) -> AnswerCard:
    """Answer one question as one persona, using one arm's tools.

    `provider` selects the model backend. The system prompt and the tool surface
    are identical whichever is chosen -- a cross-model comparison is worthless
    if the two models were asked different questions.

    Cells from different providers must never be merged into one grid. An arm
    difference would then be indistinguishable from a model difference.
    """
    surface = ToolSurface(
        persona, contracts_root, audit_path=audit_path,
        allow_joins=ARM_ALLOWS_JOINS[arm],
    )
    chosen_model = model or (MODEL if provider == "anthropic" else DEFAULT_MODELS[provider])
    backend = provider_for(
        provider, model=chosen_model,
        **({"client": client} if client is not None else {}),
    )

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    executions: list[dict[str, Any]] = []
    finished = False
    spend = Spend(model=chosen_model)
    text = ""

    for _ in range(MAX_TURNS):
        turn = backend.complete(system_prompt(arm), _tool_schemas(arm), messages)
        spend.add(**turn.usage)
        text = turn.text

        # Recorded in the provider's own shape so one canonical transcript
        # exists per cell regardless of backend.
        assistant: list[dict[str, Any]] = []
        if turn.text:
            assistant.append({"type": "text", "text": turn.text})
        assistant += [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
            for c in turn.tool_calls
        ]
        messages.append({"role": "assistant", "content": assistant})

        if turn.is_final:
            finished = True
            break

        results = []
        for use in turn.tool_calls:
            try:
                payload = getattr(surface, use.name)(**use.arguments)
                if use.name in ("query_metric", "run_sql"):
                    executions.append(payload)
                results.append({
                    "type": "tool_result", "tool_use_id": use.id,
                    "content": json.dumps(payload, default=str)[:20000],
                })
            except (ToolError, SnowflakeError, ValueError, TypeError) as exc:
                # Surfaced to the model verbatim rather than swallowed. A
                # refusal is information the agent should be able to act on --
                # and an arm that never learns why a call failed would look
                # worse than it is, for reasons the experiment does not mean
                # to measure.
                results.append({
                    "type": "tool_result", "tool_use_id": use.id, "is_error": True,
                    "content": f"{type(exc).__name__}: {exc}",
                })
        messages.append({"role": "user", "content": results})

    # An agent stopped mid-investigation has not answered, and its last query is
    # a probe rather than a result. Reporting that probe as the answer would put
    # an exploratory number in a cell the scorer treats as final -- so the card
    # says what happened instead.
    exhausted = not finished

    confidence, basis = "none", "model did not state one"
    match = _CONFIDENCE.search(text)
    if match:
        confidence = match.group(1).lower()
        basis = match.group(2).strip() or "not elaborated"
    why_not_match = _WHY_NOT.search(text)
    why_not = why_not_match.group(1).strip() if why_not_match else None

    last = executions[-1] if executions else None
    if exhausted:
        return AnswerCard(
            question=question, persona=persona.name, arm=arm, rows=[], sql=None,
            metrics_used=[], lineage=[],
            context={
                "persona": persona.name, "role": persona.snowflake_role,
                "schema": persona.snowflake_schema,
            },
            query_id=None, confidence="none",
            confidence_basis=f"stopped after {MAX_TURNS} turns without concluding",
            why_not=(
                f"Exhausted the {MAX_TURNS}-turn budget while still working. "
                f"{len(executions)} quer{'y' if len(executions) == 1 else 'ies'} ran, "
                "none reported as a final answer."
            ),
            # Recorded on this path too. A run that burned its whole turn budget
            # and produced nothing is the MOST expensive kind, and omitting its
            # cost would make the cheapest-looking arm the one that gave up.
            spend=spend.as_dict(),
        )
    if last is None:
        return AnswerCard(
            question=question, persona=persona.name, arm=arm, rows=[], sql=None,
            metrics_used=[], lineage=[], context={
                "persona": persona.name, "role": persona.snowflake_role,
                "schema": persona.snowflake_schema,
            },
            query_id=None, confidence=confidence, confidence_basis=basis,
            why_not=why_not or "the agent executed no query and gave no reason",
            spend=spend.as_dict(),
        )

    return AnswerCard(
        question=question, persona=persona.name, arm=arm,
        rows=last["rows"], sql=last["sql"], params=last.get("params", []),
        metrics_used=last["metrics_used"], lineage=last["lineage"],
        context=last["context"], query_id=last["query_id"],
        confidence=confidence, confidence_basis=basis, why_not=why_not,
        spend=spend.as_dict(),
    )
