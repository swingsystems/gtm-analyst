.PHONY: setup spec-validate lint test verify-integrity

setup:
	uv sync --all-extras

spec-validate:
	uv run gaa spec-validate --root evals/spec

lint:
	uv run ruff check gaa tests

test:
	uv run pytest -v

verify-integrity:
	uv run pytest tests/test_spec_predates_models.py -v

.PHONY: governance
governance:
	uv run python scripts/apply_governance.py
