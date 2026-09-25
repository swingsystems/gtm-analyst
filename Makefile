.PHONY: setup spec-validate lint test verify-integrity demo

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

demo:  ## No account, no key, no network. Start here.
	uv run gaa demo
	@echo ""
	@echo "  open results/demo/summary.md"
