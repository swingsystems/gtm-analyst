"""The answer card: an answer together with everything needed to check it.

A number on its own is unauditable, so this model refuses to hold one. An
answered card must carry the statement that produced it and the Snowflake query
id that ties it to a row in ACCOUNT_USAGE; a refusal must carry a reason. Both
rules are enforced at construction rather than by convention, because a card
that could be emitted without provenance eventually would be.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

Arm = Literal["free-sql", "strict-contract", "safe-join-contract", "mock"]
Confidence = Literal["high", "medium", "low", "none"]


class AnswerCard(BaseModel):
    """One answer, with its provenance."""

    model_config = ConfigDict(extra="forbid")

    question: str
    persona: str
    arm: Arm

    rows: list[dict[str, str]]
    sql: str | None
    params: list[str] = []

    metrics_used: list[str]
    lineage: list[str]
    context: dict[str, Any]
    query_id: str | None

    confidence: Confidence
    confidence_basis: str
    # Populated whenever something was withheld or could not be answered. A
    # partial answer that does not say what was withheld is the dangerous case:
    # it looks complete and is quietly smaller.
    why_not: str | None = None
    # What this answer cost to produce. OPTIONAL on purpose: the 25 cards
    # recorded before spend was measured must still load, and the model sets
    # extra="forbid", so a required field would make the published evidence
    # unreadable. None means "not measured", which is different from zero.
    spend: dict[str, Any] | None = None

    @property
    def is_refusal(self) -> bool:
        """True when nothing was executed at all, as distinct from an empty result."""
        return self.sql is None

    @model_validator(mode="after")
    def _provenance_is_mandatory(self) -> "AnswerCard":
        if self.sql is None:
            if not self.why_not:
                raise ValueError(
                    "a refusal must set why_not; refusing silently tells the caller "
                    "nothing and looks identical to a failure"
                )
            return self
        if not self.sql.strip():
            raise ValueError("an answered card must carry the statement it ran")
        if not self.query_id:
            raise ValueError(
                "an answered card must carry its Snowflake query_id; without it the "
                "audit trail stops at our own logs"
            )
        return self

    def to_markdown(self) -> str:
        """Render for a human reviewer. Every provenance field appears."""
        lines = [
            f"**Q.** {self.question}",
            (f"**Asked as** `{self.persona}` (role `{self.context.get('role', '?')}`, "
             f"schema `{self.context.get('schema', '?')}`) · arm `{self.arm}`"),
            "",
        ]
        if self.rows:
            headers = list(self.rows[0])
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join(["---"] * len(headers)) + "|")
            for row in self.rows:
                lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
        else:
            lines.append("_no rows_")
        lines.append("")
        if self.why_not:
            lines.append(f"**Withheld / not answered.** {self.why_not}")
            lines.append("")
        lines.append(f"**Confidence.** {self.confidence} — {self.confidence_basis}")
        lines.append(f"**Metrics.** {', '.join(self.metrics_used) or 'none (free SQL)'}")
        lines.append(f"**Lineage.** {', '.join(self.lineage) or 'n/a'}")
        lines.append(f"**Query id.** `{self.query_id or 'not executed'}`")
        if self.sql:
            lines += ["", "```sql", self.sql.strip(), "```"]
        return "\n".join(lines)


def strip_sidecars(record: dict[str, Any]) -> dict[str, Any]:
    """Drop the harness's own keys from a recorded card.

    The harness writes sidecars alongside each card -- `_question_id` to join
    back to the spec, `_recorded_at` to scope a contamination window. AnswerCard
    sets extra="forbid" deliberately, since an unrecognised field is schema
    drift worth failing on, so they are stripped by their underscore prefix
    rather than by relaxing the model.

    One helper because three call sites each had their own popping logic, and
    adding a second sidecar silently broke two of them.
    """
    return {k: v for k, v in record.items() if not k.startswith("_")}
