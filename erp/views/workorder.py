"""
erp/views/workorder.py
Work Order — creates and edits work order master records (billing configuration).
Shift schedule and billing summary are managed in worklog.py.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime

import streamlit as st

from ..supabase_client import SupabaseClient

# ── Constants ─────────────────────────────────────────────────────────────────

BILLING_TYPES  = ["Monthly Fixed Rental", "Daily Rental"]
BILLING_CYCLES = ["Calendar Month", "Custom"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(value) -> date | None:
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


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Work Orders</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed.")
        st.write(str(exc))
        return

    # ── Fetchers ───────────────────────────────────────────────────────────────
    def fetch_work_orders() -> list[dict]:
        try:
            return sb.list_work_orders()
        except Exception as exc:
            st.error(f"Failed to load work orders: {exc}")
            return []

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers: {exc}")
            return []

    def fetch_sites() -> list[dict]:
        try:
            return sb.list_sites()
        except Exception as exc:
            st.error(f"Failed to load sites: {exc}")
            return []

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception as exc:
            st.error(f"Failed to load machines: {exc}")
            return []

    work_orders = fetch_work_orders()
    customers   = fetch_customers()
    sites       = fetch_sites()
    machines    = fetch_machines()

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}
    machine_map  = {m.get("id"): m for m in machines  if m.get("id")}
    wo_map       = {w.get("id"): w for w in work_orders if w.get("id")}

    # ── Edit selector ──────────────────────────────────────────────────────────
    selected_wo_id = st.selectbox(
        "Edit existing work order",
        options=[""] + list(wo_map),
        format_func=lambda wid: "New work order" if not wid
            else f"{wo_map[wid].get('wo_number', 'Unknown')} — "
                 f"{customer_map.get(wo_map[wid].get('customer_id', ''), {}).get('customer_name', '')}",
        key="selected_wo_id",
    )
    selected_wo = wo_map.get(selected_wo_id)

    # ── Sync session state on WO selection change ──────────────────────────────
    if st.session_state.get("_editing_wo_id") != selected_wo_id:
        st.session_state["_editing_wo_id"]        = selected_wo_id
        wo = selected_wo or {}

        st.session_state["wo_customer_id"]        = wo.get("customer_id", "")
        st.session_state["wo_site_id"]            = wo.get("site_id", "")
        st.session_state["wo_machine_id"]         = wo.get("machine_id", "")
        st.session_state["wo_start_date"]         = _parse_date(wo.get("start_date"))
        st.session_state["wo_end_date"]           = _parse_date(wo.get("end_date"))
        st.session_state["wo_billing_type"]       = wo.get("billing_type", BILLING_TYPES[0])
        st.session_state["wo_billing_cycle_type"] = wo.get("billing_cycle_type", BILLING_CYCLES[0])
        st.session_state["wo_billing_start_date"] = _parse_date(wo.get("billing_start_date"))
        st.session_state["wo_billing_end_date"]   = _parse_date(wo.get("billing_end_date"))
        st.session_state["wo_rental_per_month"]   = float(wo.get("rental_per_month") or 0.0)

    # ── A. Basic Selection ─────────────────────────────────────────────────────
    st.markdown('<p class="filter-label">Basic Selection</p>', unsafe_allow_html=True)

    sel1, sel2 = st.columns(2)
    with sel1:
        selected_customer_id = st.selectbox(
            "Customer *",
            options=[""] + list(customer_map),
            format_func=lambda cid: "Select customer" if not cid
                else customer_map[cid].get("customer_name", "Unknown"),
            key="wo_customer_id",
        )
    with sel2:
        filtered_sites = {
            sid: s for sid, s in site_map.items()
            if str(s.get("customer_id", "")) == str(selected_customer_id)
        }
        if st.session_state.get("wo_site_id") not in filtered_sites:
            st.session_state["wo_site_id"] = ""
        selected_site_id = st.selectbox(
            "Site *",
            options=[""] + list(filtered_sites),
            format_func=lambda sid: "Select site" if not sid
                else filtered_sites[sid].get("site_name", "Unknown"),
            key="wo_site_id",
        )

    selected_machine_id = st.selectbox(
        "Machine *",
        options=[""] + list(machine_map),
        format_func=lambda mid: "Select machine" if not mid
            else f"{machine_map[mid].get('asset_code', '')} — {machine_map[mid].get('machine_type', '')}",
        key="wo_machine_id",
    )

    dt1, dt2 = st.columns(2)
    with dt1:
        start_date = st.date_input("Start Date", key="wo_start_date")
    with dt2:
        end_date = st.date_input("End Date (if applicable)", key="wo_end_date")

    # ── B. Billing & Cycle Configuration ───────────────────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    st.markdown('<p class="filter-label">Billing &amp; Cycle Configuration</p>', unsafe_allow_html=True)

    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        billing_type = st.selectbox(
            "Billing Type",
            options=BILLING_TYPES,
            key="wo_billing_type",
        )
    with bc2:
        billing_cycle_type = st.selectbox(
            "Billing Cycle",
            options=BILLING_CYCLES,
            key="wo_billing_cycle_type",
        )
    with bc3:
        rental_per_month = st.number_input(
            "Rental per Month",
            value=float(st.session_state.get("wo_rental_per_month", 0.0)),
            step=0.01,
            min_value=0.0,
            key="wo_rental_per_month",
        )

    if billing_cycle_type == "Calendar Month":
        today              = date.today()
        billing_start_date = today.replace(day=1)
        billing_end_date   = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        bcd1, bcd2 = st.columns(2)
        with bcd1:
            st.date_input("Billing Cycle Start Date", value=billing_start_date,
                          disabled=True, key="wo_billing_start_date_display")
        with bcd2:
            st.date_input("Billing Cycle End Date", value=billing_end_date,
                          disabled=True, key="wo_billing_end_date_display")
    else:
        bcd1, bcd2 = st.columns(2)
        with bcd1:
            billing_start_date = st.date_input("Billing Cycle Start Date",
                                               key="wo_billing_start_date")
        with bcd2:
            billing_end_date = st.date_input("Billing Cycle End Date",
                                             key="wo_billing_end_date")

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    # ── Form (submit) ──────────────────────────────────────────────────────────
    with st.form("wo_form"):
        if selected_wo:
            st.markdown(
                f"<span style='font-size:11px;color:#6b7280;'>WO Number: "
                f"<strong>{selected_wo.get('wo_number', '—')}</strong></span>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        submitted = st.form_submit_button(
            "Update Work Order" if selected_wo else "Create Work Order"
        )

        if submitted:
            if not selected_customer_id:
                st.error("Customer is required.")
            elif not selected_site_id:
                st.error("Site is required.")
            elif not selected_machine_id:
                st.error("Machine is required.")
            else:
                payload = dict(
                    customer_id=selected_customer_id,
                    site_id=selected_site_id,
                    machine_id=selected_machine_id,
                    start_date=start_date.isoformat() if start_date else None,
                    end_date=end_date.isoformat() if end_date else None,
                    billing_type=billing_type,
                    billing_cycle_type=billing_cycle_type,
                    billing_start_date=billing_start_date.isoformat() if billing_start_date else None,
                    billing_end_date=billing_end_date.isoformat() if billing_end_date else None,
                    rental_per_month=float(rental_per_month) if rental_per_month else None,
                )
                try:
                    if selected_wo:
                        sb.update_work_order(selected_wo_id, payload)
                        st.success("Work order updated.")
                    else:
                        created = sb.insert_work_order(payload)
                        wo_num = created.get("wo_number") or created.get("id", "")
                        st.success(f"Work order created: {wo_num}")
                    work_orders = fetch_work_orders()
                except Exception as exc:
                    st.error(f"Could not save work order: {exc}")

    # ── Work order list ────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    col_cap, col_btn = st.columns([5, 1])
    with col_cap:
        st.markdown('<p class="filter-label">All Work Orders</p>', unsafe_allow_html=True)
    with col_btn:
        if st.button("Refresh", key="refresh_wo"):
            work_orders = fetch_work_orders()

    if work_orders:
        st.dataframe(
            [
                {
                    "WO Number":     w.get("wo_number", ""),
                    "Customer":      customer_map.get(w.get("customer_id", ""), {}).get("customer_name", ""),
                    "Site":          site_map.get(w.get("site_id", ""), {}).get("site_name", ""),
                    "Machine":       machine_map.get(w.get("machine_id", ""), {}).get("asset_code", ""),
                    "Billing Type":  w.get("billing_type", ""),
                    "Billing Cycle": w.get("billing_cycle_type", ""),
                    "Cycle Start":   w.get("billing_start_date", ""),
                    "Cycle End":     w.get("billing_end_date", ""),
                    "Rental/Month":  w.get("rental_per_month", ""),
                }
                for w in work_orders
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No work orders found.")
