"""The agent's entire access surface.

A persona is bound when a ToolSurface is CONSTRUCTED, and no tool takes a role,
schema, or user argument. That is the structural difference between a boundary
enforced by the warehouse and one enforced by a prompt: an agent cannot ask for
privileges it was not given, because there is no parameter through which to ask.
"""
import json
from pathlib import Path
from typing import Any

from gaa.connection import session_for_persona
from gaa.mcp.audit import AuditEntry, AuditLog
from gaa.runner.reference import normalise
from gaa.semantic.compile import CompileError, QueryRequest, compile_query
from gaa.semantic.loader import ContractSet, load_contracts
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

    TOOLS = ("list_metrics", "describe_metric", "query_metric", "run_sql", "explain_lineage")

    LINEAGE_PATH = (
        Path(__file__).parent.parent.parent / "warehouse" / "governance" / "lineage.json"
    )

    def __init__(
        self,
        persona: Persona,
        contracts_root: Path,
        audit_path: Path | None = None,
        allow_joins: bool = True,
    ):
        """Bind a persona, and decide whether joined metrics are visible at all.

        allow_joins=False hides every contract declaring a join, which is what
        makes the strict arm strict. Filtering here rather than in a separate
        directory keeps one source of truth for a metric definition: the two
        constrained arms then differ in what they are shown, not in what the
        organisation believes a metric means.

        Without this the arms silently converge, because adding one join-bearing
        contract to the shared directory hands the strict arm a join surface and
        the experiment quietly compares an arm against itself.
        """
        self._persona = persona
        contracts = load_contracts(contracts_root)
        if not allow_joins:
            contracts = ContractSet(
                metrics={k: c for k, c in contracts.metrics.items() if not c.joins},
                root=contracts.root,
            )
        self._contracts = contracts
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
        """List every metric available, with its grain and its dimensions.

        Start here. Each entry names a metric, says what one row of the
        underlying data represents, and lists the dimensions it can be sliced
        by. Use describe_metric for the full definition of one of them,
        including its default filters and how it treats nulls.
        """
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
        """Return one metric's full contract.

        Reports the measure and its aggregation, the grain, every dimension it
        may be sliced by, the filters applied by default whether or not you ask
        for them, the period column, and whether null dimension values are kept
        as their own group or excluded. Read this before calling query_metric:
        the default filters in particular change what the number means.
        """
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
        """Run one metric and return its rows.

        Slice by any dimension the contract declares, filter on any column it
        declares, and scope to a period such as "2026-Q3". The metric's default
        filters always apply in addition to yours.

        Anything the contract does not declare is refused, and refused before a
        connection is opened rather than as a database error. The refusal names
        what was available, so a rejected call tells you what to ask for instead.

        Returns the rows, the exact SQL executed, the metric versions used, the
        objects read, and the Snowflake query id for that execution.
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

    def explain_lineage(self, name: str) -> dict[str, Any]:
        """Report which objects a metric reads from, for THIS persona.

        Lineage is build-time metadata recorded by scripts/apply_governance.py,
        not runtime introspection. A SECURE view hides its own definition from
        anyone who is not its owner, so the agent cannot discover what it reads
        from -- which is precisely the property that stops it introspecting its
        way around the boundary. It is told because we recorded it.

        Each persona is told about its OWN view. The controller and the rep read
        different objects for the same metric, and lineage that reported a
        canonical view would be lying by omission.
        """
        with self._audit.around(self._entry("explain_lineage")) as entry:
            contract = self._contracts.metrics.get(name)
            if contract is None:
                raise ToolError(
                    f"unknown metric {name!r}; available: {sorted(self._contracts.metrics)}"
                )
            entry.metrics_used = [name]

            qualified = f"GAA.{self._persona.snowflake_schema}.{contract.table}".upper()
            manifest = (
                json.loads(self.LINEAGE_PATH.read_text())
                if self.LINEAGE_PATH.exists()
                else {}
            )
            return {
                "metric": name,
                "version": contract.version,
                "view": qualified,
                "sources": manifest.get(qualified, []),
                "context": self._context(),
            }
