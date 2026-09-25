"""Apply a known defect, confirm the harness notices, put it back.

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
            _dbt("run", "--select", variant.rebuild)


def dbt_tests_pass() -> bool:
    return _dbt("test").returncode == 0
