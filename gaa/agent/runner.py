"""The agent loop, shared by every arm.

One implementation, parameterised by arm. The arms differ in which tools they
are offered and in one paragraph of their system prompt, and in nothing else:
separate loops would drift, and every difference between them would be measured
as if it were a property of the architecture.

Tools are called directly on the ToolSurface rather than over MCP. The MCP
server in gaa/mcp/server.py wraps this same surface and exists for external
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

from gaa.agent.card import AnswerCard
from gaa.agent.prompts import system_prompt
from gaa.mcp.tools import ToolError, ToolSurface
from gaa.spec.models import Persona

MODEL = "claude-sonnet-5"
MAX_TURNS = 8

# Which tools each arm may see. The strict arm is not merely told not to write
# SQL -- run_sql is absent from its tool list, so the separation is structural.
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
) -> AnswerCard:
    """Answer one question as one persona, using one arm's tools."""
    surface = ToolSurface(persona, contracts_root, audit_path=audit_path)
    client = client or anthropic.Anthropic()

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    executions: list[dict[str, Any]] = []

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system_prompt(arm),
            tools=_tool_schemas(arm),
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            break

        results = []
        for use in tool_uses:
            try:
                payload = getattr(surface, use.name)(**use.input)
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

    text = "\n".join(b.text for b in response.content if b.type == "text")

    confidence, basis = "none", "model did not state one"
    match = _CONFIDENCE.search(text)
    if match:
        confidence = match.group(1).lower()
        basis = match.group(2).strip() or "not elaborated"
    why_not_match = _WHY_NOT.search(text)
    why_not = why_not_match.group(1).strip() if why_not_match else None

    last = executions[-1] if executions else None
    if last is None:
        return AnswerCard(
            question=question, persona=persona.name, arm=arm, rows=[], sql=None,
            metrics_used=[], lineage=[], context={
                "persona": persona.name, "role": persona.snowflake_role,
                "schema": persona.snowflake_schema,
            },
            query_id=None, confidence=confidence, confidence_basis=basis,
            why_not=why_not or "the agent executed no query and gave no reason",
        )

    return AnswerCard(
        question=question, persona=persona.name, arm=arm,
        rows=last["rows"], sql=last["sql"], params=last.get("params", []),
        metrics_used=last["metrics_used"], lineage=last["lineage"],
        context=last["context"], query_id=last["query_id"],
        confidence=confidence, confidence_basis=basis, why_not=why_not,
    )
