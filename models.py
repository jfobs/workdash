from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class LeaseInput(BaseModel):
    lease_id: str
    lease_name: str
    classification: Literal["operating", "finance"]
    commencement_date: date
    payment_frequency: Literal["monthly"] = "monthly"
    payment_amount: Decimal = Field(gt=0)
    payment_timing: Literal["EOM", "BOM"]
    lease_term_months: Optional[int] = Field(default=None, gt=0)
    end_date: Optional[date] = None
    annual_discount_rate: Decimal = Field(ge=0)
    lease_incentives: Decimal = Decimal("0")
    initial_direct_costs: Decimal = Decimal("0")
    prepaid_rent: Decimal = Decimal("0")
    residual_value_guarantee: Decimal = Decimal("0")
    variable_payment_amount: Decimal = Decimal("0")
    nonlease_component_payment: Decimal = Decimal("0")
    carrying_value_override: Optional[Decimal] = None

    @model_validator(mode="after")
    def validate_term_or_end_date(self) -> "LeaseInput":
        if self.lease_term_months is None and self.end_date is None:
            raise ValueError("Either lease_term_months or end_date is required")
        if self.lease_term_months is None and self.end_date is not None:
            months = (self.end_date.year - self.commencement_date.year) * 12 + (
                self.end_date.month - self.commencement_date.month
            ) + 1
            if months <= 0:
                raise ValueError("end_date must be after commencement_date")
            self.lease_term_months = months
        return self


@dataclass
class EngineSettings:
    currency_rounding: int = 2
    sign_mode: Literal["tb", "absolute"] = "tb"
    true_up_tolerance: Decimal = Decimal("0.01")
