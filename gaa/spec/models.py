from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", "with ", "drop ", "grant ")


class Persona(BaseModel):
    """A caller identity. Maps one-to-one onto a Snowflake role."""

    name: str
    snowflake_role: str
    description: str


class ExpectedResult(BaseModel):
    """The correct answer for one persona. Values are strings to preserve decimal scale."""

    persona: str
    rows: list[dict[str, str]]


class Question(BaseModel):
    """One evaluation question and its deterministic ground truth.

    `reference_sql` names a file under evals/spec/reference_sql/. It is never SQL
    text: spec YAML is metadata only, so no YAML field can carry a fragment that
    reaches Snowflake.
    """

    id: str
    text: str
    reference_sql: str
    grain: str
    expected: list[ExpectedResult]
    tags: list[str] = Field(default_factory=list)
    source: Literal["authored", "blind_spot", "spider2"]

    @field_validator("reference_sql")
    @classmethod
    def must_be_filename_not_sql(cls, v: str) -> str:
        if not v.endswith(".sql"):
            raise ValueError("reference_sql must be a .sql filename, not SQL text")
        lowered = v.lower()
        if any(kw in lowered for kw in _SQL_KEYWORDS) or "\n" in v or "/" in v:
            raise ValueError("reference_sql must be a bare filename containing no SQL")
        return v


class Invariant(BaseModel):
    """A metamorphic property that must hold regardless of the specific numbers."""

    id: str
    description: str
    kind: Literal["sum_of_parts", "monotonic_nesting", "masking_preserves_row_count", "determinism"]
    params: dict[str, Any] = Field(default_factory=dict)
