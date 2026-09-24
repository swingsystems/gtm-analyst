"""Pydantic models for the dataset profile that drives synthetic generation.

A profile describes the *shape* of a warehouse: how many accounts, which regions,
what a booking amount looks like, which anomalies to plant. The generator itself
knows nothing about GTM; swap the profile and you get a different domain.
"""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ProfileError(Exception):
    """Raised when the dataset profile is malformed or internally inconsistent."""


class AccountsProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(gt=0)
    regions: list[str] = Field(min_length=1)
    segments: list[str] = Field(min_length=1)
    reps: int = Field(gt=0)


class BookingsProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    per_account: tuple[int, int]
    amount_range: tuple[int, int]
    window: tuple[date, date]
    license_split: dict[str, float]
    subscription_terms: list[int] = Field(min_length=1)
    intercompany_every: int = Field(gt=0)

    @model_validator(mode="after")
    def _check(self) -> "BookingsProfile":
        low, high = self.per_account
        if low < 1 or high < low:
            raise ValueError(
                f"per_account must be an ascending pair of positives, got {[low, high]}"
            )
        lo_amount, hi_amount = self.amount_range
        if lo_amount < 0 or hi_amount < lo_amount:
            raise ValueError(
                "amount_range must be ascending and non-negative, got "
                f"{[lo_amount, hi_amount]}"
            )
        if self.window[1] < self.window[0]:
            raise ValueError("window end must not precede window start")
        if not self.license_split:
            raise ValueError("license_split must name at least one license type")
        total = sum(self.license_split.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"license_split must sum to 1.0, got {total}")
        if any(term < 1 for term in self.subscription_terms):
            raise ValueError("subscription_terms must all be at least 1 month")
        return self


class BillingsProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lag_days: tuple[int, int]

    @model_validator(mode="after")
    def _check(self) -> "BillingsProfile":
        low, high = self.lag_days
        if low < 0 or high < low:
            raise ValueError(f"lag_days must be ascending and non-negative, got {[low, high]}")
        return self


class AnomaliesProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bookings_without_billing: int = Field(ge=0)
    bookings_without_revenue: int = Field(ge=0)
    quarter_boundary_dates: list[date] = Field(default_factory=list)
    territory_reassignment_date: date
    # Anomalies spread evenly across the whole booking window mostly land
    # outside the quarter the questions ask about, leaving the reconciliation
    # questions with almost no signal. Confining them to the window under test
    # is what makes q003 and q004 measure anything.
    concentrate_window: list[date] = Field(default_factory=list)


class DatasetProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    accounts: AccountsProfile
    bookings: BookingsProfile
    billings: BillingsProfile
    anomalies: AnomaliesProfile

    @property
    def minimum_bookings(self) -> int:
        """Fewest bookings the profile can possibly produce."""
        return self.accounts.count * self.bookings.per_account[0]

    @model_validator(mode="after")
    def _check(self) -> "DatasetProfile":
        floor = self.minimum_bookings
        for field in ("bookings_without_billing", "bookings_without_revenue"):
            count = getattr(self.anomalies, field)
            if count >= floor:
                raise ValueError(
                    f"anomalies.{field}={count} must be smaller than the "
                    f"{floor} bookings the profile guarantees"
                )
        forced = len(self.anomalies.quarter_boundary_dates)
        if forced > floor:
            raise ValueError(
                f"anomalies.quarter_boundary_dates has {forced} dates but only "
                f"{floor} bookings are guaranteed"
            )
        for boundary in self.anomalies.quarter_boundary_dates:
            if not self.bookings.window[0] <= boundary <= self.bookings.window[1]:
                raise ValueError(f"quarter boundary {boundary} falls outside the booking window")
        return self


def load_profile(path: Path) -> DatasetProfile:
    """Load and validate a dataset profile from YAML."""
    try:
        with Path(path).open() as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise ProfileError(f"{path}: profile file is missing") from exc
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError(f"{path}: expected a mapping at the top level")

    try:
        return DatasetProfile(**data)
    except (ValidationError, TypeError) as exc:
        raise ProfileError(f"{path}: {exc}") from exc
