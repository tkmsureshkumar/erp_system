"""
erp/validation.py
Form-submission payloads with the same guarantees as the Zod schemas.

Field types mirror the DB; cross-field rules are enforced with Pydantic
`model_validator`s:
  - WorkOrder: >=1 line, no duplicate machine per WO, end >= start, billing window.
  - Deployment: expected_return >= deployment_date.

Relational guards that need sibling data (site-belongs-to-customer, WO-is-Active,
machine-is-Available) are enforced in the view by filtering the offered options
and a final `guard_*` check before commit — the same split as the React layer.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import (
    WorkOrderStatus,
    DeploymentStatus,
    Machine,
    OperationalStatus,
    ConditionStatus,
)


class MachineForm(BaseModel):
    asset_code: str = Field(min_length=1)
    machine_type: str = Field(min_length=1)
    make: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    original_yom: Optional[int] = None
    operational_yom: Optional[int] = None
    purchase_date: Optional[date] = None
    purchase_cost: Optional[float] = None
    working_height: Optional[float] = None
    current_location: Optional[str] = None
    current_site_id: Optional[str] = None
    operational_status: OperationalStatus = OperationalStatus.AVAILABLE
    condition_status: ConditionStatus = ConditionStatus.RUNNING
    lifetime_revenue: float = 0.0
    current_monthly_rental: Optional[float] = None
    current_customer_id: Optional[str] = None
    is_active: bool = True


class WorkOrderLineForm(BaseModel):
    machine_id: str = Field(min_length=1)
    monthly_rental: float = Field(ge=0)
    mobilization_charges: float = Field(ge=0, default=0.0)
    demobilization_charges: float = Field(ge=0, default=0.0)
    operator_charges: float = Field(ge=0, default=0.0)
    fuel_charges: float = Field(ge=0, default=0.0)
    billing_start_date: Optional[date] = None
    billing_end_date: Optional[date] = None

    @model_validator(mode="after")
    def _billing_window(self) -> "WorkOrderLineForm":
        if (
            self.billing_start_date
            and self.billing_end_date
            and self.billing_end_date < self.billing_start_date
        ):
            raise ValueError("Billing end is before billing start")
        return self


class WorkOrderForm(BaseModel):
    wo_number: str = Field(min_length=1)
    po_number: Optional[str] = None
    po_date: Optional[date] = None
    customer_id: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    start_date: date
    end_date: Optional[date] = None
    status: WorkOrderStatus = WorkOrderStatus.DRAFT
    lines: list[WorkOrderLineForm]

    @field_validator("lines")
    @classmethod
    def _at_least_one_line(cls, v: list[WorkOrderLineForm]) -> list[WorkOrderLineForm]:
        if len(v) < 1:
            raise ValueError("A work order needs at least one machine line")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "WorkOrderForm":
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        seen: set[str] = set()
        for line in self.lines:
            if line.machine_id in seen:
                raise ValueError(
                    f"Machine appears more than once on the work order"
                )
            seen.add(line.machine_id)
        return self


class DeploymentForm(BaseModel):
    customer_id: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    work_order_id: str = Field(min_length=1)
    work_order_line_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    operator_id: Optional[str] = None
    deployment_date: date
    expected_return_date: Optional[date] = None
    status: DeploymentStatus = DeploymentStatus.ACTIVE

    @model_validator(mode="after")
    def _return_after_deploy(self) -> "DeploymentForm":
        if (
            self.expected_return_date
            and self.expected_return_date < self.deployment_date
        ):
            raise ValueError("Expected return cannot be before deployment date")
        return self


# --- Relational guards (need store data) ----------------------------------- #
def machine_dispatchable(machine: Optional[Machine]) -> tuple[bool, Optional[str]]:
    """Mirror of deployments_one_active_per_machine: only an Available, healthy
    machine can be dispatched."""
    if machine is None:
        return False, "No machine resolved for this line"
    if machine.operational_status != OperationalStatus.AVAILABLE:
        return (
            False,
            f'Machine is "{machine.operational_status.value}", not Available '
            "— it may already have an active deployment",
        )
    if machine.condition_status in (ConditionStatus.BREAKDOWN, ConditionStatus.BER):
        return False, f'Machine condition is "{machine.condition_status.value}"'
    return True, None
