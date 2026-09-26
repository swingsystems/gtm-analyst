"""Apply a known defect, confirm the harness notices, put it back.

**These mutate a shared warehouse.** Each variant rebuilds real tables, so two
runs against the same database race: one restores what the other just broke, and
the failures look like flaky detection rather than a collision. The CI workflow
serialises the warehouse job for this reason, and a chaos run should never share
a database with anything a person is using.

A guard nobody has watched fail is not a guard. These variants exist so the
catch rate is measured rather than assumed, and because this project has
already shipped one of them for real: `calendar_too_short` is the bug committed
in e517ed4, which discarded a quarter of all revenue while dbt reported success.
"""
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
CHAOS_DIR = REPO / "chaos"
WAREHOUSE = REPO / "warehouse"


@dataclass(frozen=True)
class Variant:
    name: str
    target: Path
    rebuild: str
    caught_by: str


VARIANTS: dict[str, Variant] = {
    "calendar_too_short": Variant(
        name="calendar_too_short",
        target=WAREHOUSE / "models" / "marts" / "dim_fiscal_calendar.sql",
        rebuild="dim_fiscal_calendar+",
        caught_by="assert_no_rows_lost_revenue, and every revenue question",
    ),
    "coalesce_swallows_null": Variant(
        name="coalesce_swallows_null",
        target=WAREHOUSE / "models" / "staging" / "stg_accounts.sql",
        rebuild="stg_accounts+",
        caught_by="q010, where the null segment group disappears",
    ),
    "fanout_join": Variant(
        name="fanout_join",
        target=WAREHOUSE / "models" / "marts" / "fct_bookings.sql",
        rebuild="fct_bookings+",
        caught_by="the unique test on BOOKING_ID, and every bookings total",
    ),
    "wrong_effective_date": Variant(
        name="wrong_effective_date",
        target=WAREHOUSE / "models" / "marts" / "dim_territory_scd.sql",
        rebuild="dim_territory_scd+",
        caught_by="q011, where a handover date lands in two territories at once",
    ),
    "off_by_one_quarter": Variant(
        name="off_by_one_quarter",
        # NOT q008, which the plan predicted. q008 filters on BOOKING_DATE and
        # never reads FISCAL_QUARTER, so a shifted label leaves it untouched.
        # The prediction was made before the variant existed and was wrong.
        target=WAREHOUSE / "models" / "marts" / "dim_fiscal_calendar.sql",
        rebuild="dim_fiscal_calendar+",
        caught_by="q001 and every question filtering on FISCAL_QUARTER",
    ),
}


def _dbt(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "dbt", *args], cwd=WAREHOUSE,
        capture_output=True, text=True, check=False,
    )


@contextmanager
def chaos(name: str, rebuild: bool = True):
    """Swap in a broken model for the duration of the block, then restore it.

    Restoration runs in a finally block and rebuilds, because leaving a
    deliberately broken model in a live warehouse would poison every later run
    in a way that looks like a real defect.
    """
    variant = VARIANTS[name]
    backup = variant.target.with_suffix(".sql.original")
    shutil.copy2(variant.target, backup)
    try:
        shutil.copy2(CHAOS_DIR / f"{name}.sql", variant.target)
        if rebuild:
            _dbt("run", "--select", variant.rebuild)
        yield variant
    finally:
        shutil.copy2(backup, variant.target)
        backup.unlink()
        if rebuild:
            restored = _dbt("run", "--select", variant.rebuild)
            # Checked, not fired and forgotten. An unchecked restore leaves a
            # deliberately broken model live in a shared warehouse, where the
            # next thing to read it sees a real-looking defect with no
            # explanation -- which is worse than the failure being tested.
            if restored.returncode != 0:
                raise RestoreFailed(
                    f"{name} was applied but could NOT be reverted; "
                    f"{variant.target.name} is live and broken in the warehouse. "
                    f"Rebuild with: dbt run --select {variant.rebuild}\n"
                    f"{(restored.stdout + restored.stderr).strip()[-600:]}"
                )


class RestoreFailed(RuntimeError):
    """A planted defect could not be reverted. The warehouse is left broken."""


class DbtUnavailable(RuntimeError):
    """dbt could not run at all, which is not the same as a failing test."""


def dbt_tests_pass() -> bool:
    """True when dbt's tests pass.

    Raises when dbt could not run, rather than returning False. The distinction
    is the whole point: a missing profile and a failing data test both produce a
    non-zero exit, and collapsing them means a chaos variant "caught" a defect
    that was never planted because nothing ever executed. CI found this by
    having no profile -- every variant reported caught, and the restore
    assertion is the only reason it surfaced.
    """
    result = _dbt("test")
    if result.returncode == 0:
        return True
    blob = f"{result.stdout}\n{result.stderr}"
    # Every way dbt can decline to run. A Compilation Error means the project
    # never reached the warehouse, and missing packages is the commonest cause
    # -- CI hit exactly that and it read as a failing data test.
    for marker in ("Could not find profile", "Credentials in profile",
                   "runtime error", "Runtime Error", "profiles.yml",
                   "Compilation Error", "dbt deps", "not found in dbt_packages",
                   "Encountered an error"):
        if marker in blob:
            raise DbtUnavailable(
                f"dbt could not run, so nothing was tested: {blob.strip()[-600:]}"
            )
    return False
