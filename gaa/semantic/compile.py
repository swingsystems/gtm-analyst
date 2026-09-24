"""Assemble parameterised SQL from a metric contract and a request.

Placeholders are qmark (``?``), bound SERVER-SIDE by the Snowflake driver. The
default pyformat style interpolates client-side -- it escapes correctly, but the
final statement is still assembled locally from caller values. Server-side
binding means the value never enters the statement text at all, which is the
stronger guarantee for a system whose central claim is that it cannot be made to
run SQL it was not asked to run.

This module is the security boundary for query construction. Identifiers come
ONLY from the contract, which validated them as bare identifiers at load time.
Every value supplied by the caller binds as a parameter and is never formatted
into the statement.

That asymmetry is deliberate and load-bearing: the schema does not sanitise
values, because sanitising would invite treating validation as the defence.
Binding is the defence, and it lives here.
"""
from dataclasses import dataclass, field

from gaa.semantic.loader import ContractSet
from gaa.semantic.models import Filter, FilterOp, MetricContract

_SQL_OPS = {
    FilterOp.EQ: "=",
    FilterOp.NE: "<>",
    FilterOp.GT: ">",
    FilterOp.GTE: ">=",
    FilterOp.LT: "<",
    FilterOp.LTE: "<=",
}

_NULL_PLACEHOLDER = "(none)"


class CompileError(Exception):
    """Raised when a request cannot be satisfied by the contract."""


@dataclass(frozen=True)
class QueryRequest:
    metric: str
    dimensions: list[str] = field(default_factory=list)
    filters: list[dict] = field(default_factory=list)
    period: str | None = None


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: list[str]
    metrics_used: list[str]
    lineage: list[str]


def _measure_sql(contract: MetricContract) -> str:
    agg = contract.measure.aggregation.value.upper()
    column = contract.measure.column
    if agg == "COUNT_DISTINCT":
        return f"COUNT(DISTINCT {column})"
    return f"{agg}({column})"


def _resolve_dimensions(contract: MetricContract, names: list[str]) -> list[tuple[str, str]]:
    """Map requested dimension names to (alias, column expression)."""
    declared = {d.name: d for d in contract.dimensions}
    resolved = []
    for name in names:
        dimension = declared.get(name)
        if dimension is None:
            raise CompileError(
                f"{contract.name}: dimension {name!r} is not declared; "
                f"available: {sorted(declared) or 'none'}"
            )
        expression = dimension.column
        if contract.null_policy == "preserve":
            # A NULL group must survive aggregation. Dropping it is the
            # null_segment_dropped failure, and it is invisible in the output.
            expression = f"COALESCE({dimension.column}, ?)"
        resolved.append((dimension.column, expression))
    return resolved


def _filter_clause(
    contract: MetricContract, filt: Filter, allowed: set[str]
) -> tuple[str, list[str]]:
    if filt.column not in allowed:
        raise CompileError(
            f"{contract.name}: filter column {filt.column!r} is not declared on this metric"
        )
    if filt.op is FilterOp.IN:
        values = [v.strip() for v in filt.value.split(",") if v.strip()]
        if not values:
            raise CompileError(f"{contract.name}: 'in' filter on {filt.column} has no values")
        placeholders = ", ".join(["?"] * len(values))
        return f"{filt.column} IN ({placeholders})", values
    return f"{filt.column} {_SQL_OPS[filt.op]} ?", [filt.value]


def compile_query(contracts: ContractSet, request: QueryRequest) -> CompiledQuery:
    """Build a single parameterised SELECT for one metric."""
    contract = contracts.metrics.get(request.metric)
    if contract is None:
        raise CompileError(
            f"unknown metric {request.metric!r}; available: {sorted(contracts.metrics)}"
        )

    params: list[str] = []

    dimensions = _resolve_dimensions(contract, request.dimensions)
    select_parts, group_parts = [], []
    for column, expression in dimensions:
        if "?" in expression:
            params.append(_NULL_PLACEHOLDER)
        select_parts.append(f"{expression} AS {column}")
        group_parts.append(expression)
    select_parts.append(f"{_measure_sql(contract)} AS VALUE")

    # A filter may name the metric's own dimensions, its declared default-filter
    # columns, or the period column. Nothing else: the contract exists so a
    # caller cannot reach an arbitrary column on the underlying view.
    allowed = (
        {d.column for d in contract.dimensions}
        | {f.column for f in contract.default_filters}
        | {contract.period_column}
    )

    where_parts: list[str] = []
    if request.period is not None:
        where_parts.append(f"{contract.period_column} = ?")
        params.append(request.period)
    for filt in contract.default_filters:
        clause, values = _filter_clause(contract, filt, allowed)
        where_parts.append(clause)
        params.extend(values)
    for raw in request.filters:
        clause, values = _filter_clause(contract, Filter(**raw), allowed)
        where_parts.append(clause)
        params.extend(values)

    sql = f"SELECT {', '.join(select_parts)}\nFROM {contract.table}"
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)
    if group_parts:
        # Group by ordinal, never by repeating the expression. A COALESCE
        # carrying a placeholder would otherwise appear twice while its value is
        # bound once, and the driver rejects the statement at execution time --
        # found by running it, not by testing it.
        ordinals = ", ".join(str(i + 1) for i in range(len(group_parts)))
        sql += f"\nGROUP BY {ordinals}\nORDER BY {ordinals}"

    return CompiledQuery(
        sql=sql,
        params=params,
        metrics_used=[request.metric],
        lineage=[contract.table],
    )
