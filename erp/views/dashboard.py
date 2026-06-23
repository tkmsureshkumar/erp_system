"""
erp/views/dashboard.py
Fleet Dashboard — landing page showing fleet status metric cards and filters.
"""
from __future__ import annotations

import streamlit as st

from ..supabase_client import SupabaseClient


def _metric_card(label: str, value: int, color: str, icon: str, extra_style: str = "") -> str:
    return f"""
    <div class="metric-card" style="{extra_style}">
      <div class="metric-label">{label}</div>
      <div class="metric-value" style="color:{color};">{value}</div>
      <div class="metric-icon" style="color:{color};">{icon}</div>
    </div>
    """


def render() -> None:
    # ---- Page header ----
    col_head, col_btn = st.columns([6, 1])
    with col_head:
        st.markdown(
            """
            <div class="page-eyebrow">// Access Fleet Operations</div>
            <div class="page-title">Fleet Dashboard</div>
            """,
            unsafe_allow_html=True,
        )
    with col_btn:
        st.markdown(
            '<a href="?page=machines" target="_self" class="btn-orange">+ ADD MACHINE</a>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # ---- Load data ----
    machines: list[dict] = []
    customers_list: list[dict] = []
    sb = None
    try:
        sb = SupabaseClient()
        machines = sb.list_machines()
        customers_list = sb.list_customers()
    except Exception as exc:
        st.error(f"Could not connect to Supabase: {exc}")

    # ---- Compute counts ----
    total = len(machines)
    available = sum(1 for m in machines if m.get("operational_status") == "Available")
    on_rent = sum(1 for m in machines if m.get("operational_status") == "On Rent")
    mobilizing = sum(1 for m in machines if m.get("operational_status") == "Mobilizing")
    demobilizing = sum(1 for m in machines if m.get("operational_status") == "Demobilizing")
    breakdown = sum(1 for m in machines if m.get("condition_status") == "Breakdown")

    # ---- Metric cards — 3 rows × 2 columns ----
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            _metric_card("Total Fleet", total, "#111827", "&#9782;"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _metric_card("Available", available, "#16a34a", "&#9711;"),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown(
            _metric_card("On Rent", on_rent, "#2563eb", "&#9146;"),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            _metric_card("Breakdown", breakdown, "#ef4444", "&#9651;",
                         "border-bottom: 3px solid #ef4444;"),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    c5, c6 = st.columns(2)
    with c5:
        st.markdown(
            _metric_card("Mobilizing", mobilizing, "#E87722", "&#128666;"),
            unsafe_allow_html=True,
        )
    with c6:
        st.markdown(
            _metric_card("Demobilizing", demobilizing, "#E87722", "&#128666;"),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # ---- Filters ----
    cf1, cf2 = st.columns(2)
    with cf1:
        st.markdown('<p class="filter-label">CUSTOMER</p>', unsafe_allow_html=True)
        cust_options = ["All"] + [c.get("customer_name", "") for c in customers_list if c.get("customer_name")]
        selected_cust = st.selectbox("Customer", cust_options, label_visibility="collapsed", key="dash_customer")
    with cf2:
        st.markdown('<p class="filter-label">LOCATION</p>', unsafe_allow_html=True)
        locs = sorted({m.get("current_location", "") for m in machines if m.get("current_location")})
        loc_options = ["All"] + locs
        selected_loc = st.selectbox("Location", loc_options, label_visibility="collapsed", key="dash_location")

    # ---- Filtered machine table ----
    filtered = machines
    if selected_cust != "All":
        cust_id = next((c.get("id") for c in customers_list if c.get("customer_name") == selected_cust), None)
        if cust_id:
            filtered = [m for m in filtered if m.get("current_customer_id") == cust_id]
    if selected_loc != "All":
        filtered = [m for m in filtered if m.get("current_location") == selected_loc]

    if filtered:
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
        st.dataframe(
            [
                {
                    "Asset Code": m.get("asset_code", ""),
                    "Type": m.get("machine_type", ""),
                    "Operational": m.get("operational_status", ""),
                    "Condition": m.get("condition_status", ""),
                    "Location": m.get("current_location", "—"),
                    "Customer": m.get("current_customer_id", "—"),
                }
                for m in filtered
            ],
            use_container_width=True,
            hide_index=True,
        )
