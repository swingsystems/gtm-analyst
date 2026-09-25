from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from gtm_analyst.semantic.models import MetricContract


class ContractError(Exception):
    """Raised when a metric contract is malformed or the contract set is inconsistent."""


@dataclass(frozen=True)
class ContractSet:
    metrics: dict[str, MetricContract]
    root: Path


def _read_yaml(path: Path) -> dict:
    try:
        with path.open() as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise ContractError(f"{path}: required contract file is missing") from exc
    except yaml.YAMLError as exc:
        raise ContractError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"{path}: expected a mapping at the top level")
    return data


def load_contracts(root: Path) -> ContractSet:
    """Load and validate a directory of metric contracts.

    Every ``*.yaml`` under `root` is parsed with ``yaml.safe_load`` -- never
    ``yaml.load`` -- so a contract carrying a ``!!python/object/apply`` tag fails to
    parse instead of executing, and validated against `MetricContract`, whose
    ``extra="forbid"`` rejects any key the schema does not name.

    Metrics are keyed ``"{name}@{version}"`` so several versions of one metric can
    coexist; a repeated name *and* version is an authoring mistake and raises.
    """
    if not root.is_dir():
        raise ContractError(f"{root}: contract directory not found")

    metrics: dict[str, MetricContract] = {}
    for path in sorted(root.glob("*.yaml")):
        data = _read_yaml(path)
        try:
            contract = MetricContract(**data)
        except (ValidationError, TypeError) as exc:
            raise ContractError(f"{path}: {exc}") from exc

        key = f"{contract.name}@{contract.version}"
        if key in metrics:
            raise ContractError(f"{path}: duplicate metric contract {key!r}")
        metrics[key] = contract

    if not metrics:
        raise ContractError(f"{root}: no contracts found")

    return ContractSet(metrics=metrics, root=root)
