"""
erp/store.py
In-memory data layer backed by st.session_state (the App.tsx store + mockData.ts +
data/supabase.ts counterpart). Holds the canonical entities, derives the lookup
option lists and the vw_fleet_status read model, and applies the workflow side
effects on mutation (dispatch flips a machine to On Rent), so changes show up
across views immediately.

Swap these methods for real Supabase/Postgres calls to go live; the views only
touch the public methods below.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import streamlit as st

from .models import (
    Customer,
    Site,
    Machine,
    Operator,
    WorkOrder,
    WorkOrderLine,
    Deployment,
    FleetStatusRow,
    CustomerOption,
    SiteOption,
    MachineOption,
    WorkOrderOption,
    WorkOrderLineOption,
    OperatorOption,
    OperationalStatus,
    ConditionStatus,
    OperatorStatus,
    WorkOrderStatus,
    DeploymentStatus,
)
from .validation import WorkOrderForm, DeploymentForm


class Store:
    def __init__(self) -> None:
        self.customers: list[Customer] = _seed_customers()
        self.sites: list[Site] = _seed_sites()
        self.machines: list[Machine] = _seed_machines()
        self.operators: list[Operator] = _seed_operators()
        self.work_orders: list[WorkOrder] = _seed_work_orders()
        self.work_order_lines: list[WorkOrderLine] = _seed_work_order_lines()
        self.deployments: list[Deployment] = _seed_deployments()
        self._wo_seq = 5
        self._dep_seq = 4
        self._id_seq = 1000

    # -- helpers ----------------------------------------------------------- #
    def _next_id(self) -> str:
        self._id_seq += 1
        return f"gen-{self._id_seq}"

    def machine(self, machine_id: str) -> Optional[Machine]:
        return next((m for m in self.machines if m.id == machine_id), None)

    def _customer_name(self, cid: Optional[str]) -> Optional[str]:
        if not cid:
            return None
        return next((c.customer_name for c in self.customers if c.id == cid), None)

    def _site_name(self, sid: Optional[str]) -> Optional[str]:
        if not sid:
            return None
        return next((s.site_name for s in self.sites if s.id == sid), None)

    # -- lookup options ---------------------------------------------------- #
    def customer_options(self) -> list[CustomerOption]:
        return [
            CustomerOption(id=c.id, customer_code=c.customer_code, customer_name=c.customer_name)
            for c in self.customers
            if c.is_active
        ]

    def site_options(self, customer_id: Optional[str] = None) -> list[SiteOption]:
        return [
            SiteOption(id=s.id, site_code=s.site_code, site_name=s.site_name, customer_id=s.customer_id)
            for s in self.sites
            if s.is_active and (customer_id is None or s.customer_id == customer_id)
        ]

    def machine_options(self) -> list[MachineOption]:
        return [
            MachineOption(
                id=m.id,
                asset_code=m.asset_code,
                machine_type=m.machine_type,
                operational_status=m.operational_status,
                condition_status=m.condition_status,
                current_monthly_rental=m.current_monthly_rental,
            )
            for m in self.machines
            if m.is_active
        ]

    def active_work_order_options(self, customer_id: Optional[str] = None) -> list[WorkOrderOption]:
        return [
            WorkOrderOption(id=w.id, wo_number=w.wo_number, customer_id=w.customer_id, site_id=w.site_id, status=w.status)
            for w in self.work_orders
            if w.status == WorkOrderStatus.ACTIVE
            and (customer_id is None or w.customer_id == customer_id)
        ]

    def work_order_line_options(self, work_order_id: Optional[str] = None) -> list[WorkOrderLineOption]:
        return [
            WorkOrderLineOption(id=l.id, work_order_id=l.work_order_id, machine_id=l.machine_id, monthly_rental=l.monthly_rental)
            for l in self.work_order_lines
            if work_order_id is None or l.work_order_id == work_order_id
        ]

    def active_operator_options(self) -> list[OperatorOption]:
        return [
            OperatorOption(id=o.id, operator_code=o.operator_code, operator_name=o.operator_name, status=o.status)
            for o in self.operators
            if o.status == OperatorStatus.ACTIVE
        ]

    def work_order_option(self, work_order_id: str) -> Optional[WorkOrderOption]:
        w = next((x for x in self.work_orders if x.id == work_order_id), None)
        if not w:
            return None
        return WorkOrderOption(id=w.id, wo_number=w.wo_number, customer_id=w.customer_id, site_id=w.site_id, status=w.status)

    # -- read model: vw_fleet_status -------------------------------------- #
    def fleet_rows(self) -> list[FleetStatusRow]:
        active_dep = {
            d.machine_id: d for d in self.deployments if d.status == DeploymentStatus.ACTIVE
        }
        rows: list[FleetStatusRow] = []
        for m in self.machines:
            dep = active_dep.get(m.id)
            rows.append(
                FleetStatusRow(
                    machine_id=m.id,
                    asset_code=m.asset_code,
                    machine_type=m.machine_type,
                    make=m.make,
                    model=m.model,
                    operational_status=m.operational_status,
                    condition_status=m.condition_status,
                    current_location=m.current_location,
                    current_site_id=m.current_site_id,
                    current_site_name=self._site_name(m.current_site_id),
                    current_customer_id=m.current_customer_id,
                    current_customer_name=self._customer_name(m.current_customer_id),
                    current_monthly_rental=m.current_monthly_rental,
                    lifetime_revenue=m.lifetime_revenue,
                    active_deployment_code=dep.deployment_code if dep else None,
                    expected_return_date=dep.expected_return_date if dep else None,
                    is_active=m.is_active,
                )
            )
        return rows

    # -- mutations --------------------------------------------------------- #
    def create_work_order(self, form: WorkOrderForm) -> WorkOrder:
        wo_id = self._next_id()
        number = form.wo_number or f"WO-2026-{self._wo_seq:04d}"
        self._wo_seq += 1
        wo = WorkOrder(
            id=wo_id,
            wo_number=number,
            po_number=form.po_number,
            po_date=form.po_date,
            customer_id=form.customer_id,
            site_id=form.site_id,
            start_date=form.start_date,
            end_date=form.end_date,
            status=form.status,
        )
        self.work_orders.insert(0, wo)
        for line in form.lines:
            self.work_order_lines.append(
                WorkOrderLine(id=self._next_id(), work_order_id=wo_id, **line.model_dump())
            )
        return wo

    def create_deployment(self, form: DeploymentForm) -> str:
        code = f"DEP-2026-{self._dep_seq:04d}"
        self._dep_seq += 1
        self.deployments.append(
            Deployment(
                id=self._next_id(),
                deployment_code=code,
                work_order_id=form.work_order_id,
                work_order_line_id=form.work_order_line_id,
                machine_id=form.machine_id,
                operator_id=form.operator_id,
                customer_id=form.customer_id,
                site_id=form.site_id,
                deployment_date=form.deployment_date,
                expected_return_date=form.expected_return_date,
                status=DeploymentStatus.ACTIVE,
            )
        )
        # Side effects the DB trigger/RPC would perform.
        for m in self.machines:
            if m.id == form.machine_id:
                m.operational_status = OperationalStatus.ON_RENT
                m.condition_status = ConditionStatus.RUNNING
                m.current_customer_id = form.customer_id
                m.current_site_id = form.site_id
        if form.operator_id:
            for o in self.operators:
                if o.id == form.operator_id:
                    o.current_machine_id = form.machine_id
                    o.current_site_id = form.site_id
        return code

    def create_machine(self, payload: dict) -> Machine:
        """Create a new machine from a payload dict and return the Machine."""
        mid = self._next_id()
        m = Machine(
            id=mid,
            asset_code=payload.get("asset_code", ""),
            machine_type=payload.get("machine_type", ""),
            make=payload.get("make"),
            model=payload.get("model"),
            serial_number=payload.get("serial_number"),
            original_yom=payload.get("original_yom"),
            operational_yom=payload.get("operational_yom"),
            purchase_date=payload.get("purchase_date"),
            purchase_cost=payload.get("purchase_cost"),
            working_height=payload.get("working_height"),
            current_location=payload.get("current_location"),
            current_site_id=payload.get("current_site_id"),
            operational_status=payload.get("operational_status", OperationalStatus.AVAILABLE),
            condition_status=payload.get("condition_status", ConditionStatus.RUNNING),
            lifetime_revenue=payload.get("lifetime_revenue", 0.0),
            current_monthly_rental=payload.get("current_monthly_rental"),
            current_customer_id=payload.get("current_customer_id"),
            is_active=payload.get("is_active", True),
        )
        self.machines.insert(0, m)
        return m

    def update_machine(self, machine_id: str, payload: dict) -> Optional[Machine]:
        """Update an existing machine by id with values from payload."""
        for idx, m in enumerate(self.machines):
            if m.id == machine_id:
                updated = m.model_copy()
                for k, v in payload.items():
                    if hasattr(updated, k) and v is not None:
                        setattr(updated, k, v)
                self.machines[idx] = updated
                return updated
        return None


def get_store() -> Store:
    if "store" not in st.session_state:
        st.session_state["store"] = Store()
    return st.session_state["store"]


# --------------------------------------------------------------------------- #
# SEED DATA                                                                   #
# --------------------------------------------------------------------------- #

def _seed_customers() -> list[Customer]:
    return [
        Customer(id="c1", customer_code="CUST-001", customer_name="Larsen Infra Projects", contact_person="R. Nair", mobile="+91 98200 11122", email="projects@larseninfra.in", gst_number="27AABCL1234M1Z5", billing_address="Plot 14, MIDC", city="Pune", state="Maharashtra", pincode="411019", payment_terms=45, is_active=True),
        Customer(id="c2", customer_code="CUST-002", customer_name="Coastal Energy EPC", contact_person="S. Menon", mobile="+91 90000 33445", email="site@coastalenergy.in", gst_number="33AAGCC9876P1Z2", billing_address="SIPCOT Industrial Park", city="Chennai", state="Tamil Nadu", pincode="603002", payment_terms=30, is_active=True),
        Customer(id="c3", customer_code="CUST-003", customer_name="Northstar Realty", contact_person="A. Gupta", mobile="+91 99100 55667", email="ops@northstarrealty.in", gst_number="07AAACN4567Q1Z8", billing_address="Sector 62", city="Noida", state="Uttar Pradesh", pincode="201309", payment_terms=60, is_active=True),
    ]


def _seed_sites() -> list[Site]:
    return [
        Site(id="s1", site_code="SITE-001", site_name="Metro Line 3 – Pkg 4", customer_id="c1", city="Pune", state="Maharashtra", pincode="411005", is_active=True),
        Site(id="s2", site_code="SITE-002", site_name="Ring Road Flyover", customer_id="c1", city="Pune", state="Maharashtra", pincode="411046", is_active=True),
        Site(id="s3", site_code="SITE-003", site_name="LNG Terminal Phase 2", customer_id="c2", city="Chennai", state="Tamil Nadu", pincode="600057", is_active=True),
        Site(id="s4", site_code="SITE-004", site_name="Tower Cluster B", customer_id="c3", city="Noida", state="Uttar Pradesh", pincode="201310", is_active=True),
    ]


def _seed_machines() -> list[Machine]:
    return [
        Machine(id="m1", asset_code="BL-1450", machine_type="Boom Lift", make="JLG", model="1500AJ", serial_number="JLG-AA-1001", original_yom=2019, operational_yom=2019, purchase_date=date(2019, 6, 1), purchase_cost=4200000, working_height=45, current_location="Metro Line 3 – Pkg 4", current_site_id="s1", operational_status=OperationalStatus.ON_RENT, condition_status=ConditionStatus.RUNNING, lifetime_revenue=7350000, current_monthly_rental=185000, current_customer_id="c1", is_active=True),
        Machine(id="m2", asset_code="SL-260", machine_type="Scissor Lift", make="Genie", model="GS-2632", serial_number="GEN-SL-2210", original_yom=2021, operational_yom=2021, purchase_date=date(2021, 2, 15), purchase_cost=1100000, working_height=10, current_location="Yard – Pune", current_site_id=None, operational_status=OperationalStatus.AVAILABLE, condition_status=ConditionStatus.RUNNING, lifetime_revenue=1980000, current_monthly_rental=65000, current_customer_id=None, is_active=True),
        Machine(id="m3", asset_code="TC-080", machine_type="Telehandler", make="JCB", model="540-170", serial_number="JCB-TH-3320", original_yom=2020, operational_yom=2020, purchase_date=date(2020, 9, 10), purchase_cost=3600000, working_height=17, current_location="LNG Terminal Phase 2", current_site_id="s3", operational_status=OperationalStatus.ON_RENT, condition_status=ConditionStatus.RUNNING, lifetime_revenue=5120000, current_monthly_rental=142000, current_customer_id="c2", is_active=True),
        Machine(id="m4", asset_code="BL-1100", machine_type="Boom Lift", make="JLG", model="1100SJ", serial_number="JLG-BB-1102", original_yom=2018, operational_yom=2018, purchase_date=date(2018, 4, 20), purchase_cost=3900000, working_height=33, current_location="Workshop – Pune", current_site_id=None, operational_status=OperationalStatus.AVAILABLE, condition_status=ConditionStatus.UNDER_REPAIR, lifetime_revenue=6680000, current_monthly_rental=168000, current_customer_id=None, is_active=True),
        Machine(id="m5", asset_code="SL-190", machine_type="Scissor Lift", make="Genie", model="GS-1930", serial_number="GEN-SL-1905", original_yom=2022, operational_yom=2022, purchase_date=date(2022, 7, 1), purchase_cost=950000, working_height=8, current_location="Workshop – Chennai", current_site_id=None, operational_status=OperationalStatus.AVAILABLE, condition_status=ConditionStatus.BREAKDOWN, lifetime_revenue=760000, current_monthly_rental=52000, current_customer_id=None, is_active=True),
        Machine(id="m6", asset_code="CR-250", machine_type="Crawler Crane", make="Kobelco", model="CK2500", serial_number="KOB-CR-2501", original_yom=2017, operational_yom=2017, purchase_date=date(2017, 11, 5), purchase_cost=18500000, working_height=0, current_location="Tower Cluster B", current_site_id="s4", operational_status=OperationalStatus.ON_RENT, condition_status=ConditionStatus.RUNNING, lifetime_revenue=24200000, current_monthly_rental=620000, current_customer_id="c3", is_active=True),
        Machine(id="m7", asset_code="BL-0600", machine_type="Boom Lift", make="Haulotte", model="HA20", serial_number="HAU-BL-0606", original_yom=2020, operational_yom=2020, purchase_date=date(2020, 3, 12), purchase_cost=2800000, working_height=20, current_location="Yard – Pune", current_site_id=None, operational_status=OperationalStatus.RESERVED, condition_status=ConditionStatus.RUNNING, lifetime_revenue=3110000, current_monthly_rental=98000, current_customer_id=None, is_active=True),
        Machine(id="m8", asset_code="FL-030", machine_type="Forklift", make="Toyota", model="8FD30", serial_number="TOY-FL-3008", original_yom=2016, operational_yom=2016, purchase_date=date(2016, 8, 1), purchase_cost=850000, working_height=0, current_location="Decommissioned", current_site_id=None, operational_status=OperationalStatus.SOLD, condition_status=ConditionStatus.BER, lifetime_revenue=2240000, current_monthly_rental=None, current_customer_id=None, is_active=False),
    ]


def _seed_operators() -> list[Operator]:
    return [
        Operator(id="op1", operator_code="OP-001", operator_name="Vikram Singh", mobile_number="+91 98111 22233", joining_date=date(2019, 1, 10), license_number="MH-OPR-44521", license_type="Boom/Scissor", license_expiry=date(2027, 1, 9), status=OperatorStatus.ACTIVE, current_machine_id="m1", current_site_id="s1"),
        Operator(id="op2", operator_code="OP-002", operator_name="Suresh Iyer", mobile_number="+91 98111 33344", joining_date=date(2020, 5, 22), license_number="TN-OPR-77810", license_type="Telehandler", license_expiry=date(2026, 12, 31), status=OperatorStatus.ACTIVE, current_machine_id="m3", current_site_id="s3"),
        Operator(id="op3", operator_code="OP-003", operator_name="Manoj Kumar", mobile_number="+91 98111 44455", joining_date=date(2021, 9, 15), license_number="UP-OPR-30122", license_type="Crane", license_expiry=date(2026, 9, 14), status=OperatorStatus.ACTIVE, current_machine_id=None, current_site_id=None),
        Operator(id="op4", operator_code="OP-004", operator_name="Imran Shaikh", mobile_number="+91 98111 55566", joining_date=date(2018, 3, 1), license_number="MH-OPR-29083", license_type="Boom/Scissor", license_expiry=date(2025, 2, 28), status=OperatorStatus.ON_LEAVE, current_machine_id=None, current_site_id=None),
    ]


def _seed_work_orders() -> list[WorkOrder]:
    return [
        WorkOrder(id="wo1", wo_number="WO-2026-0001", po_number="PO-LIP-5521", po_date=date(2026, 1, 5), customer_id="c1", site_id="s1", start_date=date(2026, 1, 10), end_date=date(2026, 12, 31), status=WorkOrderStatus.ACTIVE),
        WorkOrder(id="wo2", wo_number="WO-2026-0002", po_number="PO-CEE-2210", po_date=date(2026, 2, 1), customer_id="c2", site_id="s3", start_date=date(2026, 2, 10), end_date=date(2026, 8, 31), status=WorkOrderStatus.ACTIVE),
        WorkOrder(id="wo3", wo_number="WO-2026-0003", po_number="PO-NSR-9001", po_date=date(2026, 3, 12), customer_id="c3", site_id="s4", start_date=date(2026, 3, 20), end_date=None, status=WorkOrderStatus.ACTIVE),
        WorkOrder(id="wo4", wo_number="WO-2026-0004", po_number=None, po_date=None, customer_id="c1", site_id="s2", start_date=date(2026, 5, 1), end_date=None, status=WorkOrderStatus.DRAFT),
    ]


def _seed_work_order_lines() -> list[WorkOrderLine]:
    return [
        WorkOrderLine(id="wl1", work_order_id="wo1", machine_id="m1", monthly_rental=185000, mobilization_charges=45000, demobilization_charges=40000, operator_charges=38000, fuel_charges=0, billing_start_date=date(2026, 1, 10)),
        WorkOrderLine(id="wl2", work_order_id="wo1", machine_id="m2", monthly_rental=65000, mobilization_charges=18000, demobilization_charges=16000, operator_charges=0, fuel_charges=0),
        WorkOrderLine(id="wl3", work_order_id="wo2", machine_id="m3", monthly_rental=142000, mobilization_charges=35000, demobilization_charges=30000, operator_charges=36000, fuel_charges=12000, billing_start_date=date(2026, 2, 10)),
        WorkOrderLine(id="wl4", work_order_id="wo3", machine_id="m6", monthly_rental=620000, mobilization_charges=250000, demobilization_charges=220000, operator_charges=90000, fuel_charges=0, billing_start_date=date(2026, 3, 20)),
        WorkOrderLine(id="wl5", work_order_id="wo3", machine_id="m7", monthly_rental=98000, mobilization_charges=22000, demobilization_charges=20000, operator_charges=30000, fuel_charges=0),
    ]


def _seed_deployments() -> list[Deployment]:
    return [
        Deployment(id="d1", deployment_code="DEP-2026-0001", work_order_id="wo1", work_order_line_id="wl1", machine_id="m1", operator_id="op1", customer_id="c1", site_id="s1", deployment_date=date(2026, 1, 12), expected_return_date=date(2026, 6, 15), status=DeploymentStatus.ACTIVE),
        Deployment(id="d2", deployment_code="DEP-2026-0002", work_order_id="wo2", work_order_line_id="wl3", machine_id="m3", operator_id="op2", customer_id="c2", site_id="s3", deployment_date=date(2026, 2, 12), expected_return_date=date(2026, 8, 30), status=DeploymentStatus.ACTIVE),
        Deployment(id="d3", deployment_code="DEP-2026-0003", work_order_id="wo3", work_order_line_id="wl4", machine_id="m6", operator_id="op3", customer_id="c3", site_id="s4", deployment_date=date(2026, 3, 22), expected_return_date=date(2026, 6, 10), status=DeploymentStatus.ACTIVE),
    ]
