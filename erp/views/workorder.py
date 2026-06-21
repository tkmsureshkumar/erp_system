"""
erp/views/workorder.py
Form to add work orders and line items, persisted to Supabase.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from ..models import WorkOrderStatus
from ..supabase_client import SupabaseClient


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _ensure_line_items_state() -> None:
    if "wo_line_items" not in st.session_state:
        st.session_state["wo_line_items"] = []


def _ensure_line_item_form_state() -> None:
    st.session_state.setdefault("line_machine_id", "")
    st.session_state.setdefault("line_monthly_rental", "")
    st.session_state.setdefault("line_mobilization_charges", "")
    st.session_state.setdefault("line_demobilization_charges", "")
    st.session_state.setdefault("line_operator_charges", "")
    st.session_state.setdefault("line_fuel_charges", "")
    st.session_state.setdefault("line_billing_start_date", date.today())
    st.session_state.setdefault("line_billing_end_date", date.today())
    if st.session_state.pop("reset_wo_line_item_form", False):
        st.session_state["line_machine_id"] = ""
        st.session_state["line_monthly_rental"] = ""
        st.session_state["line_mobilization_charges"] = ""
        st.session_state["line_demobilization_charges"] = ""
        st.session_state["line_operator_charges"] = ""
        st.session_state["line_fuel_charges"] = ""
        st.session_state["line_billing_start_date"] = date.today()
        st.session_state["line_billing_end_date"] = date.today()


def _reset_line_item_inputs() -> None:
    st.session_state["reset_wo_line_item_form"] = True


def render() -> None:
    st.subheader("Work Orders")

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_customers() -> list[dict[str, object]]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers from Supabase: {exc}")
            return []

    def fetch_sites() -> list[dict[str, object]]:
        try:
            return sb.list_sites()
        except Exception as exc:
            st.error(f"Failed to load sites from Supabase: {exc}")
            return []

    def fetch_machines() -> list[dict[str, object]]:
        try:
            return sb.list_machines()
        except Exception as exc:
            st.error(f"Failed to load machines from Supabase: {exc}")
            return []

    _ensure_line_items_state()
    _ensure_line_item_form_state()
    customers = fetch_customers()
    sites = fetch_sites()
    machines = fetch_machines()
    status_values = [e.value for e in WorkOrderStatus]

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map = {s.get("id"): s for s in sites if s.get("id")}
    machine_map = {m.get("id"): m for m in machines if m.get("id")}

    customer_ids = [cid for cid in customer_map]
    selected_customer_id = st.selectbox(
        "Customer",
        options=[""] + customer_ids,
        format_func=lambda cid: "Select a customer" if not cid else f"{customer_map[cid].get('customer_name', 'Unknown')} ({cid})",
        key="wo_customer_id",
    )

    filtered_sites = [
        s
        for s in sites
        if selected_customer_id and str(s.get("customer_id")) == str(selected_customer_id)
    ]
    filtered_site_map = {s.get("id"): s for s in filtered_sites if s.get("id")}
    if st.session_state.get("wo_site_id") and st.session_state["wo_site_id"] not in filtered_site_map:
        st.session_state["wo_site_id"] = ""

    selected_site_id = st.selectbox(
        "Site",
        options=[""] + list(filtered_site_map),
        format_func=lambda sid: "Select a site" if not sid else f"{filtered_site_map[sid].get('site_name', 'Unknown')} ({sid})",
        key="wo_site_id",
    )

    with st.form("work_order_header_form"):
        po_number = st.text_input("PO Number", key="wo_po_number")
        po_date = st.date_input("PO Date", key="wo_po_date")
        start_date = st.date_input("Start Date", key="wo_start_date")
        end_date = st.date_input("End Date", key="wo_end_date")
        status = st.selectbox("Status", options=status_values, key="wo_status")

        if st.form_submit_button("Save Work Order"):
            if not selected_customer_id:
                st.error("Customer is required.")
            elif not selected_site_id:
                st.error("Site is required.")
            elif not po_number:
                st.error("PO Number is required.")
            elif len(st.session_state.wo_line_items) == 0:
                st.error("Add at least one work order line item.")
            else:
                order_payload = dict(
                    po_number=po_number,
                    po_date=po_date.isoformat(),
                    customer_id=selected_customer_id,
                    site_id=selected_site_id,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat() if end_date else None,
                    status=status,
                )
                try:
                    created_wo = sb.insert_work_order(order_payload)
                    work_order_id = created_wo.get("id")
                    if not work_order_id:
                        raise RuntimeError("Could not retrieve new work order ID")

                    for line in st.session_state.wo_line_items:
                        line_payload = dict(
                            work_order_id=work_order_id,
                            machine_id=line["machine_id"],
                            monthly_rental=float(line["monthly_rental"] or 0),
                            mobilization_charges=float(line["mobilization_charges"] or 0),
                            demobilization_charges=float(line["demobilization_charges"] or 0),
                            operator_charges=float(line["operator_charges"] or 0),
                            fuel_charges=float(line["fuel_charges"] or 0),
                            billing_start_date=line["billing_start_date"].isoformat() if line["billing_start_date"] else None,
                            billing_end_date=line["billing_end_date"].isoformat() if line["billing_end_date"] else None,
                        )
                        sb.insert_work_order_line(line_payload)

                    st.success("Work order and line items saved to Supabase.")
                    st.session_state.wo_line_items = []
                except Exception as exc:
                    st.error(f"Could not save work order to Supabase: {exc}")

    st.markdown("---")
    st.subheader("Work Order Line Items")

    with st.form("work_order_line_form"):
        machine_id = st.selectbox(
            "Machine",
            options=[""] + list(machine_map),
            format_func=lambda mid: "Select a machine" if not mid else f"{machine_map[mid].get('asset_code', 'Unknown')} - {machine_map[mid].get('machine_type', '')}",
            key="line_machine_id",
        )
        monthly_rental = st.text_input("Monthly Rental", key="line_monthly_rental")
        mobilization_charges = st.text_input("Mobilization Charges", key="line_mobilization_charges")
        demobilization_charges = st.text_input("Demobilization Charges", key="line_demobilization_charges")
        operator_charges = st.text_input("Operator Charges", key="line_operator_charges")
        fuel_charges = st.text_input("Fuel Charges", key="line_fuel_charges")
        billing_start_date = st.date_input("Billing Start Date", key="line_billing_start_date")
        billing_end_date = st.date_input("Billing End Date", key="line_billing_end_date")

        if st.form_submit_button("Add Line Item"):
            if not machine_id:
                st.error("Machine is required for line item.")
            else:
                st.session_state.wo_line_items.append(
                    {
                        "machine_id": machine_id,
                        "monthly_rental": monthly_rental,
                        "mobilization_charges": mobilization_charges,
                        "demobilization_charges": demobilization_charges,
                        "operator_charges": operator_charges,
                        "fuel_charges": fuel_charges,
                        "billing_start_date": billing_start_date,
                        "billing_end_date": billing_end_date,
                    }
                )
                _reset_line_item_inputs()
    if st.session_state.wo_line_items:
        for idx, item in enumerate(st.session_state.wo_line_items):
            machine_name = machine_map.get(item["machine_id"], {}).get("asset_code", "Unknown")
            st.write(
                f"**Line {idx + 1}:** {machine_name} | Monthly: {item['monthly_rental']} | Mobilization: {item['mobilization_charges']} | Billing {item['billing_start_date']} to {item['billing_end_date']}"
            )
            if st.button(f"Remove line {idx + 1}", key=f"remove_line_{idx}"):
                st.session_state.wo_line_items.pop(idx)
                st.experimental_rerun()

    if not customers:
        st.info("No customers found. Add customers in the Customers page first.")
    if not sites:
        st.info("No sites found. Add sites in the Sites page first.")
    if not machines:
        st.info("No machines found. Add machines in the Machines page first.")
