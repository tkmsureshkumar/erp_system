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

# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    gap: 14px;
    margin: 0 0 28px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 16px 20px 12px;
    position: relative;
    overflow: hidden;
    transition: box-shadow .18s, transform .18s;
    animation: cs-fadeup .35s ease;
}
.kpi-card:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,.08);
    transform: translateY(-2px);
}
.kpi-accent-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 8px;
    display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 26px; font-weight: 800;
    color: #111827; line-height: 1;
    margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub {
    font-size: 11px; color: #6B7280;
}
.kpi-icon {
    position: absolute; top: 14px; right: 16px;
    font-size: 20px; opacity: .12;
}

/* ── Section header ─────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 60px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px;
    text-align: center;
    animation: cs-fadeup .35s ease;
}
.empty-icon-ring {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px;
    margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 {
    font-size: 17px; font-weight: 700; color: #111827;
    margin: 0 0 8px;
}
.empty-state-v2 p {
    font-size: 13px; color: #9CA3AF;
    max-width: 270px; line-height: 1.6; margin: 0;
}

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── Data helpers ──────────────────────────────────────────────────────────────

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


# ── HTML builders ─────────────────────────────────────────────────────────────

def _kpi_card(icon: str, label: str, value: int | str,
              sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Operator Report</div>",
        unsafe_allow_html=True,
    )

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
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='font-size:36px;color:#2563EB;'>engineering</span>"
            "</div>"
            "<h3>No operator data found</h3>"
            "<p>Assign operators in the Work Log page first to see shift summaries here.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Refresh", key="opr_empty_refresh"):
            st.cache_data.clear()
            st.rerun()
        return

    # ── KPI strip (full dataset) ───────────────────────────────────────────────
    all_working = df_all[df_all["Start Time"].notna() & (df_all["Start Time"] != "")]
    n_operators = df_all["Operator"].nunique()
    n_days      = len(all_working)
    net_hrs     = all_working["Net Time"].sum()
    ot_hrs      = all_working["OT"].sum()
    hsd_ltr     = all_working["HSD in Ltr"].sum()
    bd_hrs      = all_working["Breakdown Hrs"].sum()

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='kpi-grid' style='grid-template-columns:repeat(6,1fr);'>"
        + _kpi_card("engineering",       "Operators",     n_operators,
                    "unique operators",                   "#E87722")
        + _kpi_card("calendar_month",    "Working Days",  f"{n_days:,}",
                    "total shift days logged",            "#10B981")
        + _kpi_card("schedule",          "Net Hours",     f"{net_hrs:,.1f}",
                    "total net work hours",               "#8B5CF6")
        + _kpi_card("more_time",         "OT Hours",      f"{ot_hrs:,.1f}",
                    "overtime accumulated",               "#EF4444")
        + _kpi_card("local_gas_station", "HSD (Ltr)",     f"{hsd_ltr:,.1f}",
                    "diesel consumed",                    "#F59E0B")
        + _kpi_card("build",             "Breakdown Hrs", f"{bd_hrs:,.1f}",
                    "total downtime recorded",            "#6B7280")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("tune", "Filters")
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
            if st.button("Clear", key="opr_clear", use_container_width=True):
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

    # ── Operator Summary ───────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        _section_hdr("summarize", "Operator Summary")

        summary_df = _operator_summary(df)
        if summary_df.empty:
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#9CA3AF;'>person_off</span>"
                "</div>"
                "<h3>No completed shift rows</h3>"
                "<p>No rows match the selected filters. Try broadening your date range or removing filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
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
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        hdr1, hdr2 = st.columns([5, 1])
        with hdr1:
            _section_hdr("table_rows", "Detailed Shift Log")
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
