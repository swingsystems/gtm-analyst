"""Execute reference SQL as a persona and normalise the result.

Reference SQL is ground truth. It is read from disk and sent verbatim -- nothing
is interpolated into it, and exactly one statement is permitted -- so the only
thing that varies between personas is which session runs it.
"""
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from gaa.connection import session_for_persona
from gaa.spec.models import Persona, Question
from gaa.spec.sql import sql_statements


@dataclass(frozen=True)
class ReferenceResult:
    question_id: str
    persona: str
    rows: list[dict[str, str]]
    query_id: str


def normalise(value: object) -> str:
    """Render a cell as a string so decimal scale survives comparison.

    Numbers compared as floats would make a rounding artifact indistinguishable
    from a real discrepancy, which is the whole class of error the evaluation is
    trying to detect.
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    return str(value)


def run_reference(spec_root: Path, question: Question, persona: Persona) -> ReferenceResult:
    """Run one question's reference SQL as one persona."""
    sql = (spec_root / "reference_sql" / question.reference_sql).read_text()
    statements = sql_statements(sql)
    if len(statements) != 1:
        raise ValueError(
            f"{question.reference_sql}: expected a single statement, found {len(statements)}"
        )

    with session_for_persona(persona) as conn:
        cursor = conn.cursor()
        cursor.execute(statements[0])
        columns = [c[0] for c in cursor.description]
        rows = [
            dict(zip(columns, (normalise(v) for v in row), strict=True))
            for row in cursor.fetchall()
        ]
        query_id = cursor.sfqid

    return ReferenceResult(question.id, persona.name, rows, query_id)
