"""
erp/views/wldetailreport.py
Detailed Worklog Report — full shift-level entries for all machines.
Supports pre-filled filters when navigated from the Worklog Summary page.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient
from ._report_utils import render_print_export_buttons
from .worklogreport import (
    _flatten_worklogs,
    _kpi_card,
    _section_hdr,
    _PAGE_CSS,
)


def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Detailed Worklog</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase connection failed.")
        st.write(str(exc))
        return

    # ── Data fetch ─────────────────────────────────────────────────────────────
    @st.cache_data(ttl=60, show_spinner="Loading shift log data…")
    def _load():
        try:
            wls   = sb.list_all_worklogs()
        except Exception:
            wls   = []
        try:
            wos   = sb.list_work_orders()
        except Exception:
            wos   = []
        try:
            custs = sb.list_customers()
        except Exception:
            custs = []
        try:
            sites = sb.list_sites()
        except Exception:
            sites = []
        try:
            machs = sb.list_machines()
        except Exception:
            machs = []
        return wls, wos, custs, sites, machs

    work_logs, work_orders, customers, sites, machines = _load()

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}
    machine_map  = {m.get("id"): m for m in machines  if m.get("id")}

    df_all = _flatten_worklogs(work_logs, work_orders, customer_map, site_map, machine_map)

    if df_all.empty:
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='font-size:36px;color:#2563EB;'>assignment</span>"
            "</div>"
            "<h3>No worklog data found</h3>"
            "<p>Save a work log first to see the shift log here.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Refresh"):
            st.cache_data.clear()
            st.rerun()
        return

    # ── Banner: navigated from summary? ────────────────────────────────────────
    _prefill_machine = st.session_state.pop("wld_mach",  None)
    _prefill_month   = st.session_state.pop("wld_month", None)

    if _prefill_machine or _prefill_month:
        parts = [p for p in [_prefill_machine, _prefill_month] if p]
        st.markdown(
            f"<div style='padding:10px 16px;background:#EFF6FF;border:1px solid #BFDBFE;"
            f"border-radius:8px;font-size:13px;color:#1E40AF;margin-bottom:14px;'>"
            f"Pre-filtered from Worklog Summary: "
            f"<strong>{' · '.join(parts)}</strong></div>",
            unsafe_allow_html=True,
        )
        # Store into filter keys so selectboxes pick them up
        if _prefill_machine:
            st.session_state["wld_fmach"]  = _prefill_machine
        if _prefill_month:
            st.session_state["wld_fmonth"] = _prefill_month

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("tune", "Filters")
        fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2, 2, 2, 1])

        with fc1:
            month_opts = ["All"] + sorted(df_all["Billing Month"].dropna().unique().tolist())
            sel_month  = st.selectbox("Billing Month", month_opts, key="wld_fmonth")
        with fc2:
            cust_opts  = ["All"] + sorted(df_all["Customer"].dropna().unique().tolist())
            sel_cust   = st.selectbox("Customer", cust_opts, key="wld_fcust")
        with fc3:
            mach_opts  = ["All"] + sorted(df_all["Asset Code"].dropna().unique().tolist())
            sel_mach   = st.selectbox("Machine", mach_opts, key="wld_fmach")
        with fc4:
            sn_opts    = ["All"] + sorted(df_all["Serial Number"].dropna().unique().tolist())
            sel_sn     = st.selectbox("Serial No.", sn_opts, key="wld_fsn")
        with fc5:
            valid_dates = df_all["Date"].dropna()
            min_d = valid_dates.min() if not valid_dates.empty else date.today()
            max_d = valid_dates.max() if not valid_dates.empty else date.today()
            sel_from = st.date_input("Date From", value=min_d, key="wld_from")
        with fc6:
            sel_to   = st.date_input("Date To",   value=max_d, key="wld_to")
        with fc7:
            st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
            if st.button("Clear", key="wld_clear"):
                for k in ["wld_fmonth", "wld_fcust", "wld_fmach", "wld_fsn",
                          "wld_from", "wld_to"]:
                    st.session_state.pop(k, None)
                st.rerun()

    # Apply filters
    df = df_all.copy()
    if sel_month != "All":
        df = df[df["Billing Month"] == sel_month]
    if sel_cust != "All":
        df = df[df["Customer"] == sel_cust]
    if sel_mach != "All":
        df = df[df["Asset Code"] == sel_mach]
    if sel_sn != "All":
        df = df[df["Serial Number"] == sel_sn]
    if sel_from and sel_to:
        df = df[(df["Date"] >= sel_from) & (df["Date"] <= sel_to)]

    df = df.sort_values(["Billing Month", "Asset Code", "Date"]).reset_index(drop=True)
    working_df = df[df["Start Time"].notna() & (df["Start Time"] != "")]

    if df.empty:
        st.info("No shift entries match the selected filters.")
        return

    # ── KPI strip ──────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='kpi-grid-6'>"
        + _kpi_card("precision_manufacturing", "Machines",    str(df["Asset Code"].nunique()),
                    "deployed machines",         "#0EA5E9")
        + _kpi_card("groups",                  "Customers",   str(df["Customer"].nunique()),
                    "active customers",          "#E87722")
        + _kpi_card("calendar_today",          "Total Entries", str(len(df)),
                    "shift rows",                "#10B981")
        + _kpi_card("schedule",                "Net Hours",   f"{working_df['Net Time'].sum():,.1f}",
                    "total net hours",           "#8B5CF6")
        + _kpi_card("more_time",               "OT Hours",    f"{working_df['OT'].sum():,.1f}",
                    "overtime hours",            "#EF4444")
        + _kpi_card("build",                   "B/D Hours",   f"{working_df['Breakdown Hrs'].sum():,.1f}",
                    "breakdown hours",           "#6B7280")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Shift log table ────────────────────────────────────────────────────────
    display_cols = [
        "Billing Month", "Customer", "Site", "Asset Code", "Machine",
        "Serial Number", "Date", "Weekday", "Start Time", "End Time",
        "Net Time", "Start HMR", "End HMR", "Breakdown Hrs",
        "OT", "HSD in Ltr", "Operator", "Remarks",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    detail_df = df[display_cols].copy()

    st.markdown(
        f"<div style='font-size:12px;color:#6B7280;margin-bottom:6px;'>"
        f"<b>{len(detail_df):,}</b> entries &nbsp;·&nbsp; "
        f"<b>{len(working_df):,}</b> working days &nbsp;·&nbsp; "
        f"Sundays highlighted in yellow</div>",
        unsafe_allow_html=True,
    )

    def _highlight_sunday(row: pd.Series) -> list[str]:
        if str(row.get("Weekday", "")) == "Sunday":
            return ["background-color:#fef08a;color:#713f12"] * len(row)
        return [""] * len(row)

    st.dataframe(
        detail_df.style
        .apply(_highlight_sunday, axis=1)
        .format(
            {"Net Time": "{:.2f}", "OT": "{:.1f}",
             "Breakdown Hrs": "{:.2f}", "HSD in Ltr": "{:.1f}"},
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
        height=min(38 + len(detail_df) * 35 + 4, 600),
        column_config={
            "Billing Month":  st.column_config.TextColumn("Month",       width="small"),
            "Customer":       st.column_config.TextColumn("Customer",    width="medium"),
            "Site":           st.column_config.TextColumn("Site",        width="medium"),
            "Asset Code":     st.column_config.TextColumn("Asset",       width="small"),
            "Machine":        st.column_config.TextColumn("Machine",     width="medium"),
            "Serial Number":  st.column_config.TextColumn("Serial No.",  width="small"),
            "Date":           st.column_config.DateColumn("Date",        width="small", format="DD-MM-YYYY"),
            "Weekday":        st.column_config.TextColumn("Day",         width="small"),
            "Start Time":     st.column_config.TextColumn("Start",       width="small"),
            "End Time":       st.column_config.TextColumn("End",         width="small"),
            "Net Time":       st.column_config.NumberColumn("Net Hrs",   format="%.2f", width="small"),
            "Start HMR":      st.column_config.NumberColumn("HMR In",    format="%.1f", width="small"),
            "End HMR":        st.column_config.NumberColumn("HMR Out",   format="%.1f", width="small"),
            "Breakdown Hrs":  st.column_config.NumberColumn("B/D Hrs",   format="%.2f", width="small"),
            "OT":             st.column_config.NumberColumn("OT Hrs",    format="%.1f", width="small"),
            "HSD in Ltr":     st.column_config.NumberColumn("HSD (Ltr)", format="%.1f", width="small"),
            "Operator":       st.column_config.TextColumn("Operator",    width="medium"),
            "Remarks":        st.column_config.TextColumn("Remarks",     width="medium"),
        },
    )

    # ── Export / Print ─────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
    _subtitle = f"{sel_month if sel_month != 'All' else 'All months'}"
    if sel_mach != "All":
        _subtitle += f" · {sel_mach}"
    if sel_cust != "All":
        _subtitle += f" · {sel_cust}"

    render_print_export_buttons(
        detail_df,
        base_name="worklog_detail",
        key_prefix="wld_exp",
        title="Detailed Worklog",
        subtitle=_subtitle,
        sheet_name="Worklog Detail",
    )

    # ── Navigation: back to summary ────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    bc1, bc2 = st.columns([1, 7])
    with bc1:
        if st.button("← WL Summary", key="wld_back_btn"):
            st.query_params["page"] = "wlreport"
            st.rerun()
    with bc2:
        if st.button("Refresh Data", key="wld_refresh"):
            st.cache_data.clear()
            st.rerun()
