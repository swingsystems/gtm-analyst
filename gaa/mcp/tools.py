"""The agent's entire access surface.

A persona is bound when a ToolSurface is CONSTRUCTED, and no tool takes a role,
schema, or user argument. That is the structural difference between a boundary
enforced by the warehouse and one enforced by a prompt: an agent cannot ask for
privileges it was not given, because there is no parameter through which to ask.
"""
from pathlib import Path
from typing import Any

from gaa.connection import session_for_persona
from gaa.mcp.audit import AuditEntry, AuditLog
from gaa.runner.reference import normalise
from gaa.semantic.compile import CompileError, QueryRequest, compile_query
from gaa.semantic.loader import load_contracts
from gaa.spec.models import Persona
from gaa.spec.sql import sql_statements, strip_line_comments

# An ALLOW-list, not a deny-list. A list of forbidden keywords is defeated by
# the first keyword nobody thought to forbid; a list of permitted leaders fails
# closed instead. Snowflake statements that read begin with SELECT or WITH.
_READ_ONLY_LEADERS = frozenset({"SELECT", "WITH"})


class ToolError(Exception):
    """Raised when a tool call cannot be satisfied."""


class ToolSurface:
    """Read-only tools, scoped to one persona for the life of the object."""

    TOOLS = ("list_metrics", "describe_metric", "query_metric", "run_sql")

    def __init__(self, persona: Persona, contracts_root: Path, audit_path: Path | None = None):
        self._persona = persona
        self._contracts = load_contracts(contracts_root)
        self._audit = AuditLog(audit_path)

    # -------------------------------------------------------------- helpers

    def _entry(self, tool: str) -> AuditEntry:
        return AuditEntry(
            persona=self._persona.name,
            role=self._persona.snowflake_role,
            schema=self._persona.snowflake_schema,
            tool=tool,
        )

    def _context(self) -> dict[str, str]:
        return {
            "persona": self._persona.name,
            "role": self._persona.snowflake_role,
            "schema": self._persona.snowflake_schema,
        }

    # ---------------------------------------------------------------- tools

    def list_metrics(self) -> list[dict[str, Any]]:
        """Every metric this deployment declares."""
        with self._audit.around(self._entry("list_metrics")):
            return [
                {
                    "name": key,
                    "description": contract.description,
                    "grain": contract.grain,
                    "dimensions": [d.name for d in contract.dimensions],
                }
                for key, contract in sorted(self._contracts.metrics.items())
            ]

    def describe_metric(self, name: str) -> dict[str, Any]:
        """One metric's full contract: grain, dimensions, defaults, null policy."""
        with self._audit.around(self._entry("describe_metric")) as entry:
            contract = self._contracts.metrics.get(name)
            if contract is None:
                raise ToolError(
                    f"unknown metric {name!r}; available: {sorted(self._contracts.metrics)}"
                )
            entry.metrics_used = [name]
            return {
                "name": name,
                "description": contract.description,
                "owner": contract.owner,
                "grain": contract.grain,
                "table": contract.table,
                "period_column": contract.period_column,
                "null_policy": contract.null_policy,
                "measure": {
                    "column": contract.measure.column,
                    "aggregation": contract.measure.aggregation.value,
                },
                "dimensions": [
                    {"name": d.name, "column": d.column, "description": d.description}
                    for d in contract.dimensions
                ],
                "default_filters": [
                    {"column": f.column, "op": f.op.value, "value": f.value}
                    for f in contract.default_filters
                ],
            }

    def query_metric(
        self,
        name: str,
        dimensions: list[str] | None = None,
        filters: list[dict] | None = None,
        period: str | None = None,
    ) -> dict[str, Any]:
        """Execute one metric as this persona.

        Compilation happens before any connection is opened, so an undeclared
        dimension is refused without ever reaching Snowflake.
        """
        with self._audit.around(self._entry("query_metric")) as entry:
            request = QueryRequest(
                metric=name,
                dimensions=dimensions or [],
                filters=filters or [],
                period=period,
            )
            try:
                compiled = compile_query(self._contracts, request)
            except CompileError as exc:
                raise ToolError(str(exc)) from exc
            entry.metrics_used = compiled.metrics_used

            with session_for_persona(self._persona) as conn:
                cursor = conn.cursor()
                cursor.execute(compiled.sql, compiled.params)
                columns = [c[0] for c in cursor.description]
                rows = [
                    dict(zip(columns, (normalise(v) for v in row), strict=True))
                    for row in cursor.fetchall()
                ]
                entry.query_id = cursor.sfqid

            return {
                "rows": rows,
                "sql": compiled.sql,
                "params": compiled.params,
                "metrics_used": compiled.metrics_used,
                "lineage": compiled.lineage,
                "query_id": entry.query_id,
                "context": self._context(),
            }

    def run_sql(self, statement: str) -> dict[str, Any]:
        """Execute arbitrary read-only SQL as this persona.

        This is the unconstrained comparison arm, so its permissiveness is a
        requirement: CTEs, joins, window functions and subqueries must all work,
        or the experiment handicaps the alternative it is measuring against and
        the contracts look good for the wrong reason.

        What it may not do is leave read-only territory. The warehouse boundary
        still applies because this runs as the persona -- this guard is a second
        layer, not the only one.
        """
        with self._audit.around(self._entry("run_sql")) as entry:
            statements = sql_statements(statement)
            if len(statements) != 1:
                raise ToolError(
                    f"run_sql takes a single statement, found {len(statements)}"
                )

            # Strip comments BEFORE reading the leading keyword, or commenting
            # out a SELECT silently promotes whatever follows it.
            body = strip_line_comments(statements[0]).strip()
            leader = body.split(None, 1)[0].upper() if body else ""
            if leader not in _READ_ONLY_LEADERS:
                raise ToolError(
                    f"run_sql is read-only: statements must begin with "
                    f"{' or '.join(sorted(_READ_ONLY_LEADERS))}, got {leader or 'nothing'!r}"
                )

            with session_for_persona(self._persona) as conn:
                cursor = conn.cursor()
                cursor.execute(body)
                columns = [c[0] for c in cursor.description]
                rows = [
                    dict(zip(columns, (normalise(v) for v in row), strict=True))
                    for row in cursor.fetchall()
                ]
                entry.query_id = cursor.sfqid

            return {
                "rows": rows,
                "sql": body,
                "params": [],
                "metrics_used": [],
                "lineage": [],
                "query_id": entry.query_id,
                "context": self._context(),
            }
