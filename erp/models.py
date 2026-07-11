"""
erp/models.py
Canonical domain model — the Python counterpart of types.ts.

- DB ENUMs are `str, Enum` classes, so their `.value` is the exact DB string and
  they serialize cleanly while still giving you autocomplete + exhaustiveness.
- Tables are Pydantic v2 models. Nullable columns are `Optional[...] = None`.
- Money/decimals are `float`; dates are `datetime.date`; ids are `str` (UUID).
- Lightweight `*Option` models feed the lookup selects in the forms.
- `FleetStatusRow` is the read model behind the dashboard (vw_fleet_status).
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# ENUMS — single source of truth (value == exact DB string)                   #
# --------------------------------------------------------------------------- #
class OperationalStatus(str, Enum):
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    MOBILIZING = "Mobilizing"
    ON_RENT = "On Rent"
    DEMOBILIZING = "Demobilizing"
    SOLD = "Sold"


class ConditionStatus(str, Enum):
    RUNNING = "Running"
    BREAKDOWN = "Breakdown"
    UNDER_REPAIR = "Under Repair"
    BER = "BER (Beyond Economic Repair)"


class OperatorStatus(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    ON_LEAVE = "On Leave"


class WorkOrderStatus(str, Enum):
    DRAFT = "Draft"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    CLOSED = "Closed"


class DeploymentStatus(str, Enum):
    ACTIVE = "Active"
    CLOSED = "Closed"


class LogSheetStatus(str, Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class PiStatus(str, Enum):
    DRAFT = "Draft"
    SENT = "Sent"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"


class InvoiceStatus(str, Enum):
    DRAFT = "Draft"
    SENT = "Sent"
    PARTIALLY_PAID = "Partially Paid"
    PAID = "Paid"
    OVERDUE = "Overdue"
    CANCELLED = "Cancelled"


class PaymentMode(str, Enum):
    BANK_TRANSFER = "Bank Transfer"
    CHEQUE = "Cheque"
    CASH = "Cash"
    UPI = "UPI"
    NEFT = "NEFT"
    RTGS = "RTGS"


class AttendanceType(str, Enum):
    PRESENT = "Present"
    ABSENT = "Absent"
    HALF_DAY = "Half Day"
    OT = "OT"


# --------------------------------------------------------------------------- #
# CORE TABLES                                                                 #
# --------------------------------------------------------------------------- #
class Customer(BaseModel):
    id: str
    customer_code: str
    customer_name: str
    contact_person: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    gst_number: Optional[str] = None
    billing_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    payment_terms: Optional[int] = None
    is_active: bool = True


class Site(BaseModel):
    id: str
    site_code: str
    site_name: str
    customer_id: str  # FK -> customers.id (a site cannot exist without a customer)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    site_contact: Optional[str] = None
    site_contact_number: Optional[str] = None
    is_active: bool = True


class Machine(BaseModel):
    id: str
    asset_code: str
    machine_type: str
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
    operational_status: OperationalStatus
    condition_status: ConditionStatus
    lifetime_revenue: float = 0.0
    current_monthly_rental: Optional[float] = None
    current_customer_id: Optional[str] = None
    is_active: bool = True


class Operator(BaseModel):
    id: str
    operator_code: str
    operator_name: str
    mobile_number: Optional[str] = None
    joining_date: Optional[date] = None
    license_number: Optional[str] = None
    license_type: Optional[str] = None
    license_expiry: Optional[date] = None
    status: OperatorStatus
    current_machine_id: Optional[str] = None
    current_site_id: Optional[str] = None


class WorkOrder(BaseModel):
    id: str
    wo_number: str
    po_number: Optional[str] = None
    po_date: Optional[date] = None
    customer_id: str
    site_id: str  # trg_validate_wo_site_customer: site must belong to customer_id
    start_date: date
    end_date: Optional[date] = None
    status: WorkOrderStatus = WorkOrderStatus.DRAFT


class WorkOrderLine(BaseModel):
    id: str
    work_order_id: str
    machine_id: str
    monthly_rental: float = 0.0
    mobilization_charges: float = 0.0
    demobilization_charges: float = 0.0
    operator_charges: float = 0.0
    fuel_charges: float = 0.0
    billing_start_date: Optional[date] = None
    billing_end_date: Optional[date] = None


class Deployment(BaseModel):
    id: str
    deployment_code: str
    work_order_id: str  # trg_validate_deployment_wo: WO must be Active
    work_order_line_id: str
    machine_id: str  # deployments_one_active_per_machine: one Active per machine
    operator_id: Optional[str] = None
    customer_id: str
    site_id: str
    deployment_date: date
    expected_return_date: Optional[date] = None
    actual_return_date: Optional[date] = None
    status: DeploymentStatus = DeploymentStatus.ACTIVE


# --- Downstream tables kept for schema parity (not used by the v1 UI) ------- #
class LogSheet(BaseModel):
    id: str
    log_sheet_number: str
    deployment_id: str
    machine_id: str
    operator_id: Optional[str] = None
    customer_id: str
    site_id: str
    log_month: int
    log_year: int
    total_working_days: float = 0.0
    total_hours_worked: float = 0.0
    total_ot_hours: float = 0.0
    operator_days: float = 0.0
    fuel_consumed: float = 0.0
    remarks: Optional[str] = None
    status: LogSheetStatus = LogSheetStatus.DRAFT


class ProformaInvoice(BaseModel):
    id: str
    pi_number: str
    log_sheet_id: str
    deployment_id: str
    customer_id: str
    site_id: str
    work_order_id: str
    pi_date: date
    billing_period_from: date
    billing_period_to: date
    rental_amount: float = 0.0
    operator_amount: float = 0.0
    fuel_amount: float = 0.0
    mobilization_amount: float = 0.0
    other_charges: float = 0.0
    subtotal: float = 0.0
    gst_percentage: float = 0.0
    gst_amount: float = 0.0
    total_amount: float = 0.0
    status: PiStatus = PiStatus.DRAFT


class Invoice(BaseModel):
    id: str
    invoice_number: str
    pi_id: str
    customer_id: str
    site_id: str
    work_order_id: str
    invoice_date: date
    due_date: date
    billing_period_from: date
    billing_period_to: date
    rental_amount: float = 0.0
    operator_amount: float = 0.0
    fuel_amount: float = 0.0
    mobilization_amount: float = 0.0
    other_charges: float = 0.0
    subtotal: float = 0.0
    gst_percentage: float = 0.0
    gst_amount: float = 0.0
    total_amount: float = 0.0
    amount_paid: float = 0.0
    amount_outstanding: float = 0.0
    status: InvoiceStatus = InvoiceStatus.DRAFT


class Payment(BaseModel):
    id: str
    payment_number: str
    invoice_id: str
    customer_id: str
    payment_date: date
    amount: float
    payment_mode: PaymentMode
    reference_number: Optional[str] = None
    bank_name: Optional[str] = None
    remarks: Optional[str] = None


# --------------------------------------------------------------------------- #
# READ MODEL — vw_fleet_status                                                #
# --------------------------------------------------------------------------- #
class FleetStatusRow(BaseModel):
    machine_id: str
    asset_code: str
    machine_type: str
    make: Optional[str] = None
    model: Optional[str] = None
    operational_status: OperationalStatus
    condition_status: ConditionStatus
    current_location: Optional[str] = None
    current_site_id: Optional[str] = None
    current_site_name: Optional[str] = None
    current_customer_id: Optional[str] = None
    current_customer_name: Optional[str] = None
    current_monthly_rental: Optional[float] = None
    lifetime_revenue: float = 0.0
    active_deployment_code: Optional[str] = None
    expected_return_date: Optional[date] = None
    is_active: bool = True


# --------------------------------------------------------------------------- #
# LOOKUP OPTION MODELS                                                         #
# --------------------------------------------------------------------------- #
class CustomerOption(BaseModel):
    id: str
    customer_code: str
    customer_name: str

    @property
    def label(self) -> str:
        return f"{self.customer_code} · {self.customer_name}"


class SiteOption(BaseModel):
    id: str
    site_code: str
    site_name: str
    customer_id: str

    @property
    def label(self) -> str:
        return f"{self.site_code} · {self.site_name}"


class MachineOption(BaseModel):
    id: str
    asset_code: str
    machine_type: str
    operational_status: OperationalStatus
    condition_status: ConditionStatus
    current_monthly_rental: Optional[float] = None

    @property
    def label(self) -> str:
        return f"{self.asset_code} · {self.machine_type}"


class WorkOrderOption(BaseModel):
    id: str
    wo_number: str
    customer_id: str
    site_id: str
    status: WorkOrderStatus


class WorkOrderLineOption(BaseModel):
    id: str
    work_order_id: str
    machine_id: str
    monthly_rental: float = 0.0


class OperatorOption(BaseModel):
    id: str
    operator_code: str
    operator_name: str
    status: OperatorStatus

    @property
    def label(self) -> str:
        return f"{self.operator_code} · {self.operator_name}"


# Convenience: list[str] of enum values for selectboxes.
def enum_values(enum_cls: type[Enum]) -> list[str]:
    return [e.value for e in enum_cls]
