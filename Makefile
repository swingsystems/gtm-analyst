.PHONY: setup spec-validate lint test verify-integrity demo \
        deploy teardown verify-convergence governance seed build viewer \
        check-drift baseline

setup:
	uv sync --all-extras

spec-validate:
	uv run gaa spec-validate --root evals/spec

lint:
	uv run ruff check gaa tests scripts

test:
	uv run pytest -v

verify-integrity:
	uv run pytest tests/test_spec_predates_models.py -v

.PHONY: governance
governance:
	uv run python scripts/apply_governance.py

viewer:  ## One question, three identities, one self-contained HTML file.
	uv run gaa viewer
	@echo "  open results/viewer.html"

demo:  ## No account, no key, no network. Start here.
	uv run gaa demo
	@echo ""
	@echo "  open results/demo/summary.md"

# --- Snowflake ---------------------------------------------------------------
# Needs .env and key-pair auth. `make demo` above needs neither; start there.

seed:  ## Generate synthetic CRM seeds. Deterministic, no account needed.
	uv run gaa synth

build:  ## dbt build: models plus every data test. Fails the deploy on a red test.
	cd warehouse && uv run dbt build

deploy: seed build governance  ## Full deployment against the account in .env.
	@echo ""
	@echo "  deployed. now: make verify-convergence"

teardown:  ## Drop the database, the service users, and the four roles.
	uv run python -m scripts.teardown

# Grants are additive: narrowing them in the SQL does not narrow them on the
# account. A second run that changes the privilege set means the deployment
# accumulates rather than converges, and is a different system every time.
# Drift is different from convergence. Convergence asks "does re-running the
# deploy change anything". Drift asks "has anyone changed the account since" --
# which is the case that re-opens role escalation, and the one no deploy sees.
check-drift:
	uv run python -m scripts.privilege_snapshot --baseline governance-baseline/grants.json

baseline:  ## Re-baseline DELIBERATELY, after reviewing what check-drift reported.
	uv run python -m scripts.privilege_snapshot --out governance-baseline/grants.json

verify-convergence:
	@mkdir -p .convergence
	uv run python -m scripts.privilege_snapshot --out .convergence/before.json
	$(MAKE) governance
	uv run python -m scripts.privilege_snapshot --out .convergence/after.json
	@diff -u .convergence/before.json .convergence/after.json \
	  && echo "converged: the second run changed nothing" \
	  || (echo ""; echo "NOT CONVERGED -- the privilege set above differs between runs"; exit 1)
