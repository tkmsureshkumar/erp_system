"""
erp/views/operatorreport.py
Operator Report — summarises shift hours, OT, and HSD logged per operator
from the Work Log page (work_logs table).
Handles both single-shift (`[...]`) and double-shift
(`{"shift_type":"double","shift1":[...],"shift2":[...]}`) schedule formats.
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


def _fmt_time(value) -> str:
    t = _parse_time_str(value)
    if not t:
        return ""
    h12  = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{h12}:{t.minute:02d} {ampm}"


def _iter_schedule_rows(schedule_data) -> list[dict]:
    """Return a flat list of schedule-entry dicts regardless of shift format."""
    if not schedule_data:
        return []
    try:
        data = json.loads(schedule_data) if isinstance(schedule_data, str) else schedule_data
    except Exception:
        return []

    if isinstance(data, dict) and data.get("shift_type") == "double":
        rows = list(data.get("shift1") or []) + list(data.get("shift2") or [])
    elif isinstance(data, list):
        rows = data
    else:
        return []
    return [r for r in rows if isinstance(r, dict)]


def _flatten_for_operators(
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

        machine_label = wl.get("machine_label", "")
        billing_month = wl.get("year", "")

        for entry in _iter_schedule_rows(wl.get("schedule_data")):
            operator = str(entry.get("operator") or "").strip()
            if not operator:
                continue
            start_raw = entry.get("start_time")
            end_raw   = entry.get("end_time")
            net       = float(entry.get("net_time") or 0)
            ot        = float(entry.get("ot")       or 0)
            hsd       = float(entry.get("hsd_in_ltr") or 0)
            bd        = float(entry.get("breakdown_hours") or 0)
            rows.append({
                "Operator":      operator,
                "Billing Month": billing_month,
                "WO Number":     wo.get("wo_number", ""),
                "Customer":      cust.get("customer_name", ""),
                "Site":          site_.get("site_name", ""),
                "Machine":       machine_label,
                "Date":          entry.get("date"),
                "Weekday":       entry.get("weekday", ""),
                "Start Time":    _fmt_time(start_raw),
                "End Time":      _fmt_time(end_raw),
                "Net Time":      net,
                "OT":            ot,
                "HSD in Ltr":    hsd,
                "Breakdown Hrs": bd,
                "Start HMR":     entry.get("start_hmr"),
                "End HMR":       entry.get("end_hmr"),
                "Remarks":       str(entry.get("remarks") or ""),
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    return df


def _operator_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-operator totals."""
    if df.empty:
        return pd.DataFrame()

    working = df[df["Start Time"].notna() & (df["Start Time"] != "")]
    if working.empty:
        return pd.DataFrame()

    grp = (
        working
        .groupby("Operator", dropna=False)
        .agg(
            Working_Days  = ("Net Time",      "count"),
            Net_Hrs       = ("Net Time",       "sum"),
            OT_Hrs        = ("OT",             "sum"),
            HSD_Ltr       = ("HSD in Ltr",     "sum"),
            Breakdown_Hrs = ("Breakdown Hrs",  "sum"),
            Machines      = ("Machine",        lambda x: ", ".join(sorted(x.dropna().unique()))),
            WO_Count      = ("WO Number",      "nunique"),
        )
        .reset_index()
        .rename(columns={
            "Working_Days":  "Working Days",
            "Net_Hrs":       "Net Hrs",
            "OT_Hrs":        "OT Hrs",
            "HSD_Ltr":       "HSD in Ltr",
            "Breakdown_Hrs": "Breakdown Hrs",
            "WO_Count":      "WOs",
        })
        .sort_values("Net Hrs", ascending=False)
    )
    return grp


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
        <div class="page-title">Operator Report</div>
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
    @st.cache_data(ttl=60, show_spinner="Loading operator data…")
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

    df_all = _flatten_for_operators(work_logs, work_orders, customer_map, site_map)

    if df_all.empty:
        st.info("No operator data found. Assign operators in the Work Log page first.")
        if st.button("Refresh"):
            st.cache_data.clear()
            st.rerun()
        return

    # ── Filters ────────────────────────────────────────────────────────────────
    _section("Filters")
    fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2, 2, 2, 1])

    with fc1:
        op_opts   = ["All"] + sorted(df_all["Operator"].dropna().unique().tolist())
        sel_op    = st.selectbox("Operator", op_opts, key="opr_op")
    with fc2:
        mo_opts   = ["All"] + sorted(df_all["Billing Month"].dropna().unique().tolist())
        sel_month = st.selectbox("Billing Month", mo_opts, key="opr_month")
    with fc3:
        wo_opts   = ["All"] + sorted(df_all["WO Number"].dropna().unique().tolist())
        sel_wo    = st.selectbox("Work Order", wo_opts, key="opr_wo")
    with fc4:
        mc_opts   = ["All"] + sorted(df_all["Machine"].dropna().unique().tolist())
        sel_mach  = st.selectbox("Machine", mc_opts, key="opr_mach")
    with fc5:
        valid_dates = df_all["Date"].dropna()
        min_d = valid_dates.min() if not valid_dates.empty else date.today()
        max_d = valid_dates.max() if not valid_dates.empty else date.today()
        sel_from = st.date_input("Date From", value=min_d, key="opr_from")
    with fc6:
        sel_to   = st.date_input("Date To",   value=max_d, key="opr_to")
    with fc7:
        st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
        if st.button("Clear", key="opr_clear"):
            for k in ["opr_op", "opr_month", "opr_wo", "opr_mach", "opr_from", "opr_to"]:
                st.session_state.pop(k, None)
            st.rerun()

    # Apply filters
    df = df_all.copy()
    if sel_op != "All":
        df = df[df["Operator"] == sel_op]
    if sel_month != "All":
        df = df[df["Billing Month"] == sel_month]
    if sel_wo != "All":
        df = df[df["WO Number"] == sel_wo]
    if sel_mach != "All":
        df = df[df["Machine"] == sel_mach]
    if sel_from and sel_to:
        df = df[(df["Date"] >= sel_from) & (df["Date"] <= sel_to)]

    working_df = df[df["Start Time"].notna() & (df["Start Time"] != "")]

    # ── KPI Cards ──────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    for col, label, val, colour in [
        (k1, "Operators",     str(df["Operator"].nunique()),                "#E87722"),
        (k2, "Working Days",  str(len(working_df)),                         "#10b981"),
        (k3, "Net Hours",     f"{working_df['Net Time'].sum():,.1f}",       "#8b5cf6"),
        (k4, "OT Hours",      f"{working_df['OT'].sum():,.1f}",             "#ef4444"),
        (k5, "HSD (Ltr)",     f"{working_df['HSD in Ltr'].sum():,.1f}",    "#f59e0b"),
        (k6, "Breakdown Hrs", f"{working_df['Breakdown Hrs'].sum():,.1f}", "#6b7280"),
    ]:
        with col:
            st.markdown(_kpi_card(label, val, colour), unsafe_allow_html=True)

    # ── Operator Summary ───────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    _section("Operator Summary")

    summary_df = _operator_summary(df)
    if summary_df.empty:
        st.info("No completed shift rows in the selected filters.")
    else:
        st.dataframe(
            summary_df.style.format({
                "Net Hrs":       "{:.2f}",
                "OT Hrs":        "{:.2f}",
                "HSD in Ltr":    "{:.1f}",
                "Breakdown Hrs": "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Operator":      st.column_config.TextColumn("Operator",      width="medium"),
                "Working Days":  st.column_config.NumberColumn("Days",        width="small"),
                "Net Hrs":       st.column_config.NumberColumn("Net Hrs",     format="%.2f", width="small"),
                "OT Hrs":        st.column_config.NumberColumn("OT Hrs",      format="%.2f", width="small"),
                "HSD in Ltr":    st.column_config.NumberColumn("HSD (Ltr)",   format="%.1f", width="small"),
                "Breakdown Hrs": st.column_config.NumberColumn("B/D Hrs",     format="%.2f", width="small"),
                "Machines":      st.column_config.TextColumn("Machines",      width="large"),
                "WOs":           st.column_config.NumberColumn("WOs",         width="small"),
            },
        )

    # ── Detailed Shift Log ─────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    hdr1, hdr2 = st.columns([5, 1])
    with hdr1:
        _section("Detailed Shift Log")
    with hdr2:
        export_cols = [
            "Operator", "Billing Month", "WO Number", "Customer", "Site", "Machine",
            "Date", "Weekday", "Start Time", "End Time", "Net Time",
            "Start HMR", "End HMR", "OT", "HSD in Ltr", "Breakdown Hrs", "Remarks",
        ]
        export_cols = [c for c in export_cols if c in df.columns]
        st.download_button(
            label="Export CSV",
            data=df[export_cols].to_csv(index=False).encode("utf-8"),
            file_name=f"operator_report_{date.today()}.csv",
            mime="text/csv",
            key="opr_export_csv",
        )

    display_cols = [
        "Operator", "Billing Month", "WO Number", "Customer", "Site", "Machine",
        "Date", "Weekday", "Start Time", "End Time", "Net Time",
        "OT", "HSD in Ltr", "Breakdown Hrs", "Start HMR", "End HMR", "Remarks",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    detail_df = df[display_cols].copy().sort_values(
        ["Operator", "Date"], na_position="last"
    )

    def _highlight_sunday(row):
        if str(row.get("Weekday", "")) == "Sunday":
            return ["background-color:#fef08a; color:#713f12"] * len(row)
        return [""] * len(row)

    st.dataframe(
        detail_df.style.apply(_highlight_sunday, axis=1).format(
            {
                "Net Time":      "{:.2f}",
                "OT":            "{:.1f}",
                "Breakdown Hrs": "{:.2f}",
                "HSD in Ltr":    "{:.1f}",
            },
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Operator":      st.column_config.TextColumn("Operator",    width="medium"),
            "Billing Month": st.column_config.TextColumn("Month",       width="small"),
            "WO Number":     st.column_config.TextColumn("WO",          width="small"),
            "Customer":      st.column_config.TextColumn("Customer",    width="medium"),
            "Site":          st.column_config.TextColumn("Site",        width="medium"),
            "Machine":       st.column_config.TextColumn("Machine",     width="medium"),
            "Date":          st.column_config.DateColumn("Date",        width="small"),
            "Weekday":       st.column_config.TextColumn("Weekday",     width="small"),
            "Start Time":    st.column_config.TextColumn("Start",       width="small"),
            "End Time":      st.column_config.TextColumn("End",         width="small"),
            "Net Time":      st.column_config.NumberColumn("Net Hrs",   format="%.2f", width="small"),
            "OT":            st.column_config.NumberColumn("OT Hrs",    format="%.1f", width="small"),
            "HSD in Ltr":    st.column_config.NumberColumn("HSD (Ltr)", format="%.1f", width="small"),
            "Breakdown Hrs": st.column_config.NumberColumn("B/D Hrs",   format="%.1f", width="small"),
            "Start HMR":     st.column_config.NumberColumn("HMR In",    format="%.1f", width="small"),
            "End HMR":       st.column_config.NumberColumn("HMR Out",   format="%.1f", width="small"),
            "Remarks":       st.column_config.TextColumn("Remarks",     width="medium"),
        },
    )

    st.markdown(
        f"<div style='margin-top:8px;font-size:11px;color:#9ca3af;'>"
        f"Showing {len(detail_df):,} rows · "
        f"{df['Operator'].nunique()} operator(s) · "
        f"{len(working_df)} working days</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    if st.button("Refresh Data", key="opr_refresh"):
        st.cache_data.clear()
        st.rerun()
