from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from gaa.spec.models import Invariant, Persona, Question


class SpecError(Exception):
    """Raised when the evaluation spec is malformed or internally inconsistent."""


@dataclass(frozen=True)
class Spec:
    personas: dict[str, Persona]
    questions: list[Question]
    invariants: list[Invariant]
    root: Path


def _read_yaml(path: Path) -> dict:
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{path}: expected a mapping at the top level")
    return data


def load_spec(root: Path) -> Spec:
    """Load and validate the evaluation spec directory.

    Validates structure, referential integrity between questions and personas, and
    the existence of every referenced reference-SQL file.
    """
    personas_raw = _read_yaml(root / "personas.yaml").get("personas", [])
    try:
        personas = {p.name: p for p in (Persona(**item) for item in personas_raw)}
    except (ValidationError, TypeError) as exc:
        raise SpecError(f"personas.yaml: {exc}") from exc

    invariants_raw = _read_yaml(root / "invariants.yaml").get("invariants", [])
    try:
        invariants = [Invariant(**item) for item in invariants_raw]
    except (ValidationError, TypeError) as exc:
        raise SpecError(f"invariants.yaml: {exc}") from exc

    questions: list[Question] = []
    seen: set[str] = set()
    for path in sorted((root / "questions").glob("*.yaml")):
        data = _read_yaml(path)
        try:
            question = Question(**data)
        except (ValidationError, TypeError) as exc:
            raise SpecError(f"{path}: {exc}") from exc

        if question.id in seen:
            raise SpecError(f"{path}: duplicate question id {question.id!r}")
        seen.add(question.id)

        sql_path = root / "reference_sql" / question.reference_sql
        if not sql_path.is_file():
            raise SpecError(f"{path}: reference SQL file not found: {question.reference_sql}")

        for expected in question.expected:
            if expected.persona not in personas:
                raise SpecError(f"{path}: unknown persona {expected.persona!r}")

        questions.append(question)

    return Spec(personas=personas, questions=questions, invariants=invariants, root=root)
