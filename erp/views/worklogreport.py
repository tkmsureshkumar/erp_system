"""
erp/views/worklogreport.py
Worklog Report — reads per-month records from the work_logs table.
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
    t = _parse_time_str(value)
    if not t:
        return ""
    h12  = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{h12}:{t.minute:02d} {ampm}"


def _flatten_worklogs(
    work_logs: list[dict],
    work_orders: list[dict],
    customer_map: dict,
    site_map: dict,
) -> pd.DataFrame:
    wo_map = {wo["id"]: wo for wo in work_orders if wo.get("id")}
    rows: list[dict] = []

    for wl in work_logs:
        wo = wo_map.get(wl.get("work_order_id"), {})
        if not wo:
            continue
        cust  = customer_map.get(wo.get("customer_id", ""), {})
        site_ = site_map.get(wo.get("site_id", ""), {})

        # Find matching machine config entry by machine_id or label
        machine_id = wl.get("machine_id", "")
        mc: dict = {}
        mc_raw = wo.get("machine_config")
        if mc_raw:
            try:
                mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
                if isinstance(mc_list, list):
                    for m in mc_list:
                        if m.get("machine_id") == machine_id:
                            mc = m
                            break
                    if not mc:
                        for m in mc_list:
                            if m.get("machine_label") == wl.get("machine_label"):
                                mc = m
                                break
            except Exception:
                pass

        rental   = float(mc.get("rental_per_month") or 0)
        ot_rate  = float(wl.get("ot_rate") or 0)
        shift_st = _parse_time_str(mc.get("shift_start_time"))
        shift_et = _parse_time_str(mc.get("shift_end_time"))
        std_hrs  = _net_hours(shift_st, shift_et)

        sched_raw = wl.get("schedule_data")
        if not sched_raw:
            continue
        try:
            sched = json.loads(sched_raw) if isinstance(sched_raw, str) else sched_raw
        except Exception:
            continue
        if not isinstance(sched, list):
            continue

        for entry in sched:
            rows.append({
                "Billing Month": wl.get("year", ""),
                "WO Number":     wo.get("wo_number", ""),
                "Customer":      cust.get("customer_name", ""),
                "Site":          site_.get("site_name", ""),
                "Machine":       wl.get("machine_label") or mc.get("machine_label", ""),
                "Billing Type":  mc.get("billing_type", ""),
                "Rental/Month":  rental,
                "OT Rate":       ot_rate,
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
                "HSD in Ltr":    float(entry.get("hsd_in_ltr") or 0),
                "Operator":      entry.get("operator", ""),
                "Remarks":       entry.get("remarks", ""),
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    return df


def _billing_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    working = df[df["Start Time"].notna() & (df["Start Time"] != "")]
    if working.empty:
        return pd.DataFrame()

    grp = (
        working
        .groupby(
            ["Billing Month", "WO Number", "Customer", "Site", "Machine",
             "Billing Type", "Rental/Month", "OT Rate", "Std Hrs/Day"],
            dropna=False,
        )
        .agg(
            Working_Days  = ("Net Time", "count"),
            Actual_Hours  = ("Net Time", "sum"),
            OT_Hours      = ("OT",       "sum"),
            Breakdown_Hrs = ("Breakdown Hrs", "sum"),
            HSD_Ltr       = ("HSD in Ltr",    "sum"),
        )
        .reset_index()
    )

    grp["Working Hrs"] = grp["Working_Days"] * grp["Std Hrs/Day"]
    grp["Qty"]         = grp.apply(
        lambda r: round(r["Actual_Hours"] / r["Working Hrs"], 4) if r["Working Hrs"] else 0, axis=1
    )
    grp["Billing"]     = (grp["Rental/Month"] * grp["Qty"]).round(0)
    grp["OT Billing"]  = (grp["OT_Hours"] * grp["OT Rate"]).round(0)

    return grp.rename(columns={
        "Working_Days":   "Working Days",
        "Actual_Hours":   "Actual Hrs",
        "OT_Hours":       "OT Hrs",
        "Breakdown_Hrs":  "Breakdown Hrs",
        "HSD_Ltr":        "HSD in Ltr",
    })[[
        "Billing Month", "WO Number", "Customer", "Site", "Machine",
        "Billing Type", "Rental/Month", "Working Days", "Working Hrs",
        "Actual Hrs", "Qty", "Billing",
        "OT Hrs", "OT Rate", "OT Billing",
        "Breakdown Hrs", "HSD in Ltr",
    ]]


def _kpi_card(label: str, value: str, colour: str = "#111827") -> str:
    return (
        f"<div style='background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;"
        f"padding:18px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        f"text-transform:uppercase;color:#9ca3af;margin-bottom:8px;'>{label}</div>"
        f"<div style='font-size:28px;font-weight:800;color:{colour};line-height:1;'>{value}</div>"
        f"</div>"
    )


def _section(title: str) -> None:
    st.markdown(
        f"<div style='border-top:2px solid #E87722;padding-top:10px;margin-bottom:8px;"
        f"font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        f"text-transform:uppercase;'>{title}</div>",
        unsafe_allow_html=True,
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
        return wls, wos, custs, sites

    work_logs, work_orders, customers, sites = _load()

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}

    df_all = _flatten_worklogs(work_logs, work_orders, customer_map, site_map)

    if df_all.empty:
        st.info("No worklog data found. Save a work log first.")
        if st.button("Refresh"):
            st.cache_data.clear()
            st.rerun()
        return

    # ── Filters ────────────────────────────────────────────────────────────────
    _section("Filters")
    fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2, 2, 2, 1])

    with fc1:
        month_opts = ["All"] + sorted(df_all["Billing Month"].dropna().unique().tolist())
        sel_month  = st.selectbox("Billing Month", month_opts, key="rpt_month")
    with fc2:
        cust_opts  = ["All"] + sorted(df_all["Customer"].dropna().unique().tolist())
        sel_cust   = st.selectbox("Customer", cust_opts, key="rpt_cust")
    with fc3:
        wo_opts    = ["All"] + sorted(df_all["WO Number"].dropna().unique().tolist())
        sel_wo     = st.selectbox("Work Order", wo_opts, key="rpt_wo")
    with fc4:
        mach_opts  = ["All"] + sorted(df_all["Machine"].dropna().unique().tolist())
        sel_mach   = st.selectbox("Machine", mach_opts, key="rpt_mach")
    with fc5:
        valid_dates = df_all["Date"].dropna()
        min_d = valid_dates.min() if not valid_dates.empty else date.today()
        max_d = valid_dates.max() if not valid_dates.empty else date.today()
        sel_from = st.date_input("Date From", value=min_d, key="rpt_from")
    with fc6:
        sel_to   = st.date_input("Date To",   value=max_d, key="rpt_to")
    with fc7:
        st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
        if st.button("Clear", key="rpt_clear"):
            for k in ["rpt_month", "rpt_cust", "rpt_wo", "rpt_mach", "rpt_from", "rpt_to"]:
                st.session_state.pop(k, None)
            st.rerun()

    # Apply filters
    df = df_all.copy()
    if sel_month != "All":
        df = df[df["Billing Month"] == sel_month]
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
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    for col, label, val, colour in [
        (k1, "Work Orders",   str(df["WO Number"].nunique()),          "#E87722"),
        (k2, "Machines",      str(df["Machine"].nunique()),             "#0ea5e9"),
        (k3, "Working Days",  str(len(working_df)),                    "#10b981"),
        (k4, "Net Hours",     f"{working_df['Net Time'].sum():,.1f}",  "#8b5cf6"),
        (k5, "OT Hours",      f"{working_df['OT'].sum():,.1f}",        "#ef4444"),
        (k6, "HSD (Ltr)",     f"{working_df['HSD in Ltr'].sum():,.1f}","#f59e0b"),
        (k7, "Breakdown Hrs", f"{working_df['Breakdown Hrs'].sum():,.1f}", "#6b7280"),
    ]:
        with col:
            st.markdown(_kpi_card(label, val, colour), unsafe_allow_html=True)

    # ── Billing Summary ────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    _section("Billing Summary — per Machine per Month")

    billing_df = _billing_summary(df)
    if billing_df.empty:
        st.info("No completed shift data in the selected filters.")
    else:
        total_billing    = billing_df["Billing"].sum()
        total_ot_billing = billing_df["OT Billing"].sum()
        st.markdown(
            f"<div style='display:flex;gap:32px;padding:8px 16px;"
            f"background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;"
            f"margin-bottom:8px;font-size:12px;align-items:center;'>"
            f"<span style='color:#6b7280;'>Rental Billing: "
            f"<strong style='color:#E87722;font-size:18px;'>{total_billing:,.0f}</strong></span>"
            f"<span style='color:#6b7280;'>OT Billing: "
            f"<strong style='color:#E87722;font-size:18px;'>{total_ot_billing:,.0f}</strong></span>"
            f"<span style='color:#6b7280;'>Total: "
            f"<strong style='color:#111827;font-size:18px;'>{total_billing + total_ot_billing:,.0f}</strong></span>"
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
                "OT Billing":    "{:,.0f}",
                "Breakdown Hrs": "{:.2f}",
                "HSD in Ltr":    "{:.1f}",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # ── Detailed Shift Log ─────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    hdr1, hdr2 = st.columns([5, 1])
    with hdr1:
        _section("Detailed Shift Log")
    with hdr2:
        export_cols = [
            "Billing Month", "WO Number", "Customer", "Site", "Machine",
            "Date", "Weekday", "Start Time", "End Time", "Net Time",
            "Start HMR", "End HMR", "Breakdown Hrs", "OT", "HSD in Ltr",
            "Operator", "Remarks", "Billing Type", "Rental/Month", "OT Rate",
        ]
        export_cols = [c for c in export_cols if c in df.columns]
        st.download_button(
            label="Export CSV",
            data=df[export_cols].to_csv(index=False).encode("utf-8"),
            file_name=f"worklog_report_{date.today()}.csv",
            mime="text/csv",
            key="export_csv",
        )

    display_cols = [
        "Billing Month", "WO Number", "Customer", "Site", "Machine",
        "Date", "Weekday", "Start Time", "End Time", "Net Time",
        "Start HMR", "End HMR", "Breakdown Hrs", "OT", "HSD in Ltr",
        "Operator", "Remarks",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    detail_df = df[display_cols].copy()

    def _highlight_sunday(row):
        if str(row.get("Weekday", "")) == "Sunday":
            return ["background-color:#fef08a; color:#713f12"] * len(row)
        return [""] * len(row)

    st.dataframe(
        detail_df.style.apply(_highlight_sunday, axis=1).format(
            {"Net Time": "{:.2f}", "OT": "{:.1f}",
             "Breakdown Hrs": "{:.2f}", "HSD in Ltr": "{:.1f}"},
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Billing Month": st.column_config.TextColumn("Billing Month", width="small"),
            "Date":          st.column_config.DateColumn("Date",          width="small"),
            "Weekday":       st.column_config.TextColumn("Weekday",       width="small"),
            "Start Time":    st.column_config.TextColumn("Start",         width="small"),
            "End Time":      st.column_config.TextColumn("End",           width="small"),
            "Net Time":      st.column_config.NumberColumn("Net Hrs",     format="%.2f", width="small"),
            "Start HMR":     st.column_config.NumberColumn("HMR In",      format="%.1f", width="small"),
            "End HMR":       st.column_config.NumberColumn("HMR Out",     format="%.1f", width="small"),
            "Breakdown Hrs": st.column_config.NumberColumn("B/D Hrs",     format="%.1f", width="small"),
            "OT":            st.column_config.NumberColumn("OT Hrs",      format="%.1f", width="small"),
            "HSD in Ltr":    st.column_config.NumberColumn("HSD (Ltr)",   format="%.1f", width="small"),
            "Operator":      st.column_config.TextColumn("Operator",      width="medium"),
            "Remarks":       st.column_config.TextColumn("Remarks",       width="medium"),
        },
    )

    st.markdown(
        f"<div style='margin-top:8px;font-size:11px;color:#9ca3af;'>"
        f"Showing {len(detail_df):,} rows · {len(working_df)} working days</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    if st.button("Refresh Data", key="rpt_refresh"):
        st.cache_data.clear()
        st.rerun()
