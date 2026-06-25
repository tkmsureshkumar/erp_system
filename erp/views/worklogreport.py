"""
erp/views/worklogreport.py
Worklog Report — flattens all saved worklogs from work_orders.machine_config
into a filterable report dashboard with KPI cards, billing summary, and
a full detailed schedule table.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_time_str(value) -> time | None:
    if not value:
        return None
    if isinstance(value, time):
        return value
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), fmt).time()
        except ValueError:
            continue
    return None


def _net_hours(start: time | None, end: time | None) -> float:
    if not start or not end:
        return 0.0
    diff = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return round(max(diff, 0) / 60, 2)


def _fmt_time(value) -> str:
    """Return 12-hour AM/PM string from HH:MM or time object."""
    t = _parse_time_str(value)
    if not t:
        return ""
    h12  = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{h12}:{t.minute:02d} {ampm}"


def _flatten_worklogs(
    work_orders: list[dict],
    customer_map: dict,
    site_map: dict,
) -> pd.DataFrame:
    """Explode all machine schedules into a flat per-day DataFrame."""
    rows: list[dict] = []
    for wo in work_orders:
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        except Exception:
            continue
        if not isinstance(mc_list, list):
            continue

        cust  = customer_map.get(wo.get("customer_id", ""), {})
        site_ = site_map.get(wo.get("site_id", ""), {})

        for mc in mc_list:
            sched_raw = mc.get("shift_schedule")
            if not sched_raw:
                continue
            try:
                sched = json.loads(sched_raw) if isinstance(sched_raw, str) else sched_raw
            except Exception:
                continue
            if not isinstance(sched, list):
                continue

            rental     = float(mc.get("rental_per_month") or 0)
            shift_st   = _parse_time_str(mc.get("shift_start_time"))
            shift_et   = _parse_time_str(mc.get("shift_end_time"))
            std_hrs    = _net_hours(shift_st, shift_et)

            for entry in sched:
                rows.append({
                    "WO Number":     wo.get("wo_number", ""),
                    "Customer":      cust.get("customer_name", ""),
                    "Site":          site_.get("site_name", ""),
                    "Machine":       mc.get("machine_label", ""),
                    "Billing Type":  mc.get("billing_type", ""),
                    "Billing Cycle": mc.get("billing_cycle", ""),
                    "Rental/Month":  rental,
                    "Cycle Start":   mc.get("billing_cycle_start_date", ""),
                    "Cycle End":     mc.get("billing_cycle_end_date", ""),
                    "Std Hrs/Day":   std_hrs,
                    "Date":          entry.get("date"),
                    "Weekday":       entry.get("weekday", ""),
                    "Start Time":    _fmt_time(entry.get("start_time")),
                    "End Time":      _fmt_time(entry.get("end_time")),
                    "Net Time":      float(entry.get("net_time") or 0),
                    "Start HMR":     entry.get("start_hmr"),
                    "End HMR":       entry.get("end_hmr"),
                    "Breakdown Hrs": float(entry.get("breakdown_hours") or 0),
                    "OT":            float(entry.get("ot") or 0),
                    "Operator":      entry.get("operator", ""),
                    "Remarks":       entry.get("remarks", ""),
                })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    return df


def _billing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Group by WO + Machine and compute billing metrics per machine."""
    if df.empty:
        return pd.DataFrame()

    working = df[df["Start Time"].notna() & (df["Start Time"] != "")]
    grp = (
        working
        .groupby(["WO Number", "Customer", "Site", "Machine",
                  "Billing Type", "Rental/Month", "Std Hrs/Day",
                  "Cycle Start", "Cycle End"], dropna=False)
        .agg(
            Working_Days=("Net Time", "count"),
            Actual_Hours=("Net Time", "sum"),
            OT_Hours=("OT", "sum"),
            Breakdown_Hours=("Breakdown Hrs", "sum"),
        )
        .reset_index()
    )

    grp["Working Hrs"]  = grp["Working_Days"] * grp["Std Hrs/Day"]
    grp["Qty"]          = grp.apply(
        lambda r: round(r["Actual_Hours"] / r["Working Hrs"], 4) if r["Working Hrs"] else 0, axis=1
    )
    grp["Billing"]      = (grp["Rental/Month"] * grp["Qty"]).round(0)
    grp["OT Rate"]      = grp.apply(
        lambda r: round(r["Rental/Month"] / r["Working Hrs"], 2) if r["Working Hrs"] else 0, axis=1
    )

    return grp.rename(columns={
        "Working_Days":   "Working Days",
        "Actual_Hours":   "Actual Hrs",
        "OT_Hours":       "OT Hrs",
        "Breakdown_Hours":"Breakdown Hrs",
    })[[
        "WO Number", "Customer", "Site", "Machine",
        "Billing Type", "Cycle Start", "Cycle End",
        "Rental/Month", "Working Days", "Working Hrs",
        "Actual Hrs", "Qty", "Billing",
        "OT Hrs", "OT Rate", "Breakdown Hrs",
    ]]


def _kpi_card(label: str, value: str, colour: str = "#111827", bg: str = "#ffffff") -> str:
    return (
        f"<div style='background:{bg};border:1px solid #e5e7eb;border-radius:8px;"
        f"padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        f"text-transform:uppercase;color:#9ca3af;margin-bottom:8px;'>{label}</div>"
        f"<div style='font-size:32px;font-weight:800;color:{colour};line-height:1;'>{value}</div>"
        f"</div>"
    )


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Reports</div>
        <div class="page-title">Worklog Report</div>
        """,
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
    @st.cache_data(ttl=60, show_spinner="Loading worklog data…")
    def _load() -> tuple[list, list, list]:
        try:
            wos  = sb.list_work_orders()
        except Exception:
            wos  = []
        try:
            custs = sb.list_customers()
        except Exception:
            custs = []
        try:
            sites = sb.list_sites()
        except Exception:
            sites = []
        return wos, custs, sites

    work_orders, customers, sites = _load()

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}

    df_all = _flatten_worklogs(work_orders, customer_map, site_map)

    if df_all.empty:
        st.info("No worklog data found. Save a work log first.")
        if st.button("Refresh"):
            st.cache_data.clear()
            st.rerun()
        return

    # ── Filters ────────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='border-top:2px solid #E87722;padding-top:10px;margin-bottom:8px;"
        "font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        "text-transform:uppercase;'>Filters</div>",
        unsafe_allow_html=True,
    )

    fc1, fc2, fc3, fc4, fc5, fc6 = st.columns([2, 2, 2, 2, 2, 1])

    with fc1:
        cust_opts = ["All"] + sorted(df_all["Customer"].dropna().unique().tolist())
        sel_cust  = st.selectbox("Customer", cust_opts, key="rpt_cust")
    with fc2:
        wo_opts   = ["All"] + sorted(df_all["WO Number"].dropna().unique().tolist())
        sel_wo    = st.selectbox("Work Order", wo_opts, key="rpt_wo")
    with fc3:
        mach_opts = ["All"] + sorted(df_all["Machine"].dropna().unique().tolist())
        sel_mach  = st.selectbox("Machine", mach_opts, key="rpt_mach")
    with fc4:
        valid_dates = df_all["Date"].dropna()
        min_d = valid_dates.min() if not valid_dates.empty else date.today()
        max_d = valid_dates.max() if not valid_dates.empty else date.today()
        sel_from = st.date_input("Date From", value=min_d, key="rpt_from")
    with fc5:
        sel_to   = st.date_input("Date To",   value=max_d, key="rpt_to")
    with fc6:
        st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
        if st.button("Clear", key="rpt_clear"):
            for k in ["rpt_cust", "rpt_wo", "rpt_mach", "rpt_from", "rpt_to"]:
                st.session_state.pop(k, None)
            st.rerun()

    # Apply filters
    df = df_all.copy()
    if sel_cust != "All":
        df = df[df["Customer"] == sel_cust]
    if sel_wo != "All":
        df = df[df["WO Number"] == sel_wo]
    if sel_mach != "All":
        df = df[df["Machine"] == sel_mach]
    if sel_from and sel_to:
        df = df[(df["Date"] >= sel_from) & (df["Date"] <= sel_to)]

    working_df = df[df["Start Time"].notna() & (df["Start Time"] != "")]

    # ── KPI Cards ──────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    total_wos   = df["WO Number"].nunique()
    total_mach  = df["Machine"].nunique()
    work_days   = len(working_df)
    net_hrs     = working_df["Net Time"].sum()
    ot_hrs      = working_df["OT"].sum()
    breakdown   = working_df["Breakdown Hrs"].sum()

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    cards = [
        (k1, "Work Orders",    str(total_wos),          "#E87722"),
        (k2, "Machines",       str(total_mach),          "#0ea5e9"),
        (k3, "Working Days",   str(work_days),           "#10b981"),
        (k4, "Net Hours",      f"{net_hrs:,.1f}",        "#8b5cf6"),
        (k5, "OT Hours",       f"{ot_hrs:,.1f}",         "#ef4444"),
        (k6, "Breakdown Hrs",  f"{breakdown:,.1f}",      "#f59e0b"),
    ]
    for col, label, val, colour in cards:
        with col:
            st.markdown(_kpi_card(label, val, colour), unsafe_allow_html=True)

    # ── Billing Summary ────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='border-top:2px solid #E87722;padding-top:10px;margin-bottom:8px;"
        "font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        "text-transform:uppercase;'>Billing Summary — per Machine</div>",
        unsafe_allow_html=True,
    )

    billing_df = _billing_summary(df)
    if billing_df.empty:
        st.info("No completed shift data in the selected filters.")
    else:
        total_billing = billing_df["Billing"].sum()
        st.markdown(
            f"<div style='display:flex;gap:32px;padding:8px 12px;"
            f"background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;"
            f"margin-bottom:8px;font-size:12px;'>"
            f"<span style='color:#6b7280;'>Total Estimated Billing: "
            f"<strong style='color:#E87722;font-size:16px;'>{total_billing:,.0f}</strong></span>"
            f"<span style='color:#6b7280;'>Machines: "
            f"<strong style='color:#111827;'>{len(billing_df)}</strong></span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.dataframe(
            billing_df.style.format({
                "Rental/Month":  "{:,.0f}",
                "Working Hrs":   "{:.1f}",
                "Actual Hrs":    "{:.2f}",
                "Qty":           "{:.4f}",
                "Billing":       "{:,.0f}",
                "OT Hrs":        "{:.2f}",
                "OT Rate":       "{:.2f}",
                "Breakdown Hrs": "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # ── Detailed Schedule Log ──────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    hdr1, hdr2 = st.columns([5, 1])
    with hdr1:
        st.markdown(
            "<div style='border-top:2px solid #E87722;padding-top:10px;"
            "font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
            "text-transform:uppercase;'>Detailed Shift Log</div>",
            unsafe_allow_html=True,
        )
    with hdr2:
        csv = (
            df[[
                "WO Number", "Customer", "Site", "Machine",
                "Date", "Weekday", "Start Time", "End Time",
                "Net Time", "Start HMR", "End HMR",
                "Breakdown Hrs", "OT", "Operator", "Remarks",
                "Billing Type", "Rental/Month",
            ]]
            .to_csv(index=False)
            .encode("utf-8")
        )
        st.download_button(
            label="Export CSV",
            data=csv,
            file_name=f"worklog_report_{date.today()}.csv",
            mime="text/csv",
            key="export_csv",
        )

    display_cols = [
        "WO Number", "Customer", "Site", "Machine",
        "Date", "Weekday", "Start Time", "End Time",
        "Net Time", "Start HMR", "End HMR",
        "Breakdown Hrs", "OT", "Operator", "Remarks",
    ]
    detail_df = df[display_cols].copy()

    # Highlight Sunday rows
    def _highlight_sunday(row):
        if str(row.get("Weekday", "")) == "Sunday":
            return ["background-color:#fef08a; color:#713f12"] * len(row)
        return [""] * len(row)

    st.dataframe(
        detail_df.style.apply(_highlight_sunday, axis=1).format(
            {"Net Time": "{:.2f}", "OT": "{:.1f}", "Breakdown Hrs": "{:.2f}"},
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date":          st.column_config.DateColumn("Date",      width="small"),
            "Weekday":       st.column_config.TextColumn("Weekday",   width="small"),
            "Start Time":    st.column_config.TextColumn("Start",     width="small"),
            "End Time":      st.column_config.TextColumn("End",       width="small"),
            "Net Time":      st.column_config.NumberColumn("Net Hrs", format="%.2f", width="small"),
            "Start HMR":     st.column_config.NumberColumn("HMR In",  format="%.1f", width="small"),
            "End HMR":       st.column_config.NumberColumn("HMR Out", format="%.1f", width="small"),
            "Breakdown Hrs": st.column_config.NumberColumn("Brkdn",   format="%.1f", width="small"),
            "OT":            st.column_config.NumberColumn("OT",      format="%.1f", width="small"),
            "Operator":      st.column_config.TextColumn("Operator",  width="medium"),
            "Remarks":       st.column_config.TextColumn("Remarks",   width="medium"),
        },
    )

    st.markdown(
        f"<div style='margin-top:8px;font-size:11px;color:#9ca3af;'>"
        f"Showing {len(detail_df):,} rows · {work_days} working days</div>",
        unsafe_allow_html=True,
    )

    # Refresh control
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    if st.button("Refresh Data", key="rpt_refresh"):
        st.cache_data.clear()
        st.rerun()
