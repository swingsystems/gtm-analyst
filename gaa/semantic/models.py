import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A column or table name is interpolated into generated SQL as an identifier, never
# bound as a parameter. Anything that is not a bare identifier is therefore an
# injection vector and is rejected here, at the schema, rather than downstream.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(v: str) -> str:
    if not _IDENTIFIER.match(v):
        raise ValueError(f"{v!r} is not a plain SQL identifier")
    return v


class Aggregation(str, Enum):
    """The closed set of aggregations a measure may declare.

    Closed on purpose: a measure names a column and picks from this enum, so there
    is no field anywhere in a contract that can carry an aggregation expression.
    """

    SUM = "sum"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    MIN = "min"
    MAX = "max"
    AVG = "avg"


class FilterOp(str, Enum):
    """The closed set of comparison operators a filter may use.

    Filters are structured triples, never predicate strings, so this enum is the
    only vocabulary available for the operator position.
    """

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"


class Measure(BaseModel):
    """The quantity a metric computes: one column, one aggregation from the enum."""

    model_config = ConfigDict(extra="forbid")

    column: str
    aggregation: Aggregation

    @field_validator("column")
    @classmethod
    def column_must_be_identifier(cls, v: str) -> str:
        return _validate_identifier(v)


class Dimension(BaseModel):
    """A column a metric may be sliced by, with the business name callers use."""

    model_config = ConfigDict(extra="forbid")

    name: str
    column: str
    description: str

    @field_validator("column")
    @classmethod
    def column_must_be_identifier(cls, v: str) -> str:
        return _validate_identifier(v)


class Filter(BaseModel):
    """A structured predicate: {column, op, value}, never a SQL fragment.

    `value` is deliberately NOT validated as an identifier. Values bind as query
    parameters, so a value that looks like SQL is inert; validating it here would
    misplace the injection defence, which lives in the compiler's parameter binding.
    """

    model_config = ConfigDict(extra="forbid")

    column: str
    op: FilterOp
    value: str

    @field_validator("column")
    @classmethod
    def column_must_be_identifier(cls, v: str) -> str:
        return _validate_identifier(v)


class MetricContract(BaseModel):
    """The governed definition of one metric. Metadata only -- it can carry no SQL.

    Every field is either a bare identifier, a member of a closed enum, or free prose
    that never reaches the warehouse. The measure declares a column plus an
    aggregation; filters are {column, op, value} triples. There is no field a metric
    author could use to smuggle a predicate, a subquery, or an expression into
    generated SQL, and `extra="forbid"` means an attempt to add one (a stray `sql:`
    key) fails loudly instead of being silently ignored -- silence is exactly how SQL
    gets into a schema that promises it cannot.

    `table` must be unqualified: reference SQL and contracts both resolve through the
    session's default schema, which is what makes identical SQL return different rows
    per persona. A database- or schema-qualified name would defeat that outright.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    version: int = Field(gt=0)
    description: str
    owner: str
    table: str
    grain: str
    measure: Measure
    dimensions: list[Dimension] = Field(default_factory=list)
    default_filters: list[Filter] = Field(default_factory=list)
    null_policy: Literal["preserve", "exclude"]
    period_column: str

    @field_validator("table", "period_column")
    @classmethod
    def must_be_unqualified_identifier(cls, v: str) -> str:
        return _validate_identifier(v)
