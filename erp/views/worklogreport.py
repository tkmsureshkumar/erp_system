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
from ._report_utils import (
    render_print_export_buttons,
    render_drilldown_table,
    WL_STATUS,
)


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
.kpi-grid-6 {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 14px;
    margin: 0 0 28px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 16px 18px 12px;
    position: relative;
    overflow: hidden;
    transition: box-shadow .18s, transform .18s;
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
    font-size: 9px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 8px;
    display: flex; align-items: center; gap: 5px;
}
.kpi-value {
    font-size: 26px; font-weight: 800;
    color: #111827; line-height: 1;
    margin-bottom: 5px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub {
    font-size: 10px; color: #6B7280;
}
.kpi-icon {
    position: absolute; top: 14px; right: 14px;
    font-size: 20px; opacity: .12;
}

/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 72px 40px;
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

/* ── Section header ──────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Billing section title ───────────────────────────────────────────── */
.billing-title {
    font-size: 22px; font-weight: 800;
    color: #1E2938; margin: 0 0 2px;
    letter-spacing: -.3px;
}
.billing-subtitle {
    font-size: 12px; color: #6B7280; margin-bottom: 18px;
}

/* ── Billing totals bar ──────────────────────────────────────────────── */
.billing-totals {
    display: flex; gap: 32px;
    padding: 12px 18px;
    background: #F8FAFC;
    border: 1px solid #E2EBF0;
    border-radius: 10px;
    margin-bottom: 14px;
    font-size: 12px;
    align-items: center;
    animation: cs-fadeup .3s ease;
}

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


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
    machine_map: dict | None = None,
) -> pd.DataFrame:
    wo_map = {wo["id"]: wo for wo in work_orders if wo.get("id")}
    rows: list[dict] = []
    _mmap = machine_map or {}

    for wl in work_logs:
        wo = wo_map.get(wl.get("work_order_id"), {})
        if not wo:
            continue
        cust  = customer_map.get(wo.get("customer_id", ""), {})
        site_ = site_map.get(wo.get("site_id", ""), {})

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

        # Enrich from machines table
        mobj       = _mmap.get(machine_id, {})
        asset_code = mobj.get("asset_code") or wl.get("machine_label") or mc.get("machine_label", "")
        serial_no  = mobj.get("serial_number", "")
        make       = mobj.get("make", "")
        model      = mobj.get("model", "")
        suffix     = " ".join(p for p in [make, model] if p)
        machine_display = f"{asset_code} — {suffix}" if suffix else asset_code

        rental  = float(mc.get("rental_per_month") or 0)
        ot_rate = float(wl.get("ot_rate") or 0)
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
        if isinstance(sched, dict):
            shift_type = sched.get("shift_type")
            if shift_type == "double":
                sched = list(sched.get("shift1") or []) + list(sched.get("shift2") or [])
            elif shift_type == "single":
                sched = sched.get("rows") or []
            else:
                continue
        if not isinstance(sched, list):
            continue

        for entry in sched:
            rows.append({
                "Billing Month": wl.get("year", ""),
                "Customer":      cust.get("customer_name", ""),
                "Site":          site_.get("site_name", ""),
                "Asset Code":    asset_code,
                "Machine":       machine_display,
                "Serial Number": serial_no,
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

    working = df[df["Start Time"].notna() & (df["Start Time"] != "")].copy()
    if working.empty:
        return pd.DataFrame()

    # Compute OT Billing per row before aggregating (avoids needing OT Rate in groupby)
    working["_ot_bill_row"] = working["OT"] * working["OT Rate"]

    grp = (
        working
        .groupby(
            ["Billing Month", "Customer", "Site", "Asset Code", "Machine",
             "Serial Number", "Rental/Month", "Std Hrs/Day"],
            dropna=False,
        )
        .agg(
            Working_Days  = ("Net Time",      "count"),
            Actual_Hours  = ("Net Time",      "sum"),
            OT_Hours      = ("OT",            "sum"),
            Breakdown_Hrs = ("Breakdown Hrs", "sum"),
            OT_Billing    = ("_ot_bill_row",  "sum"),
        )
        .reset_index()
    )

    grp["Working Hrs"] = grp["Working_Days"] * grp["Std Hrs/Day"]
    grp["Qty"]         = grp.apply(
        lambda r: round(r["Actual_Hours"] / r["Working Hrs"], 4) if r["Working Hrs"] else 0, axis=1
    )
    grp["Billing"]     = (grp["Rental/Month"] * grp["Qty"]).round(0)

    return grp.rename(columns={
        "Working_Days":   "Working Days",
        "Actual_Hours":   "Actual Hrs",
        "OT_Hours":       "OT Hrs",
        "Breakdown_Hrs":  "Breakdown Hrs",
        "OT_Billing":     "OT Billing",
    })[[
        "Billing Month", "Customer", "Site", "Machine", "Serial Number",
        "Rental/Month", "Working Days", "Working Hrs",
        "Actual Hrs", "Qty", "Billing",
        "OT Hrs", "OT Billing",
        "Breakdown Hrs",
    ]]


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


def _style_billing(col: pd.Series) -> list[str]:
    if col.name == "Qty":
        return ["background-color:#FEFCE8; color:#854D0E; font-weight:700"] * len(col)
    if col.name == "Breakdown Hrs":
        return [
            "background-color:#FEE2E2; color:#991B1B; font-weight:600"
            if float(v or 0) > 0
            else "background-color:#F0FDF4; color:#166534"
            for v in col
        ]
    return [""] * len(col)


def _wl_status_styler(styler):
    """Apply WL_STATUS palette to the Status column in the billing table."""
    def _row_status(col):
        if col.name != "Status":
            return [""] * len(col)
        out = []
        for v in col:
            bg, fg = WL_STATUS.get(str(v), ("#F1F5F9", "#374151"))
            out.append(f"background-color:{bg};color:{fg};font-weight:700;")
        return out
    return styler.apply(_row_status, axis=0)


# ── Detail popup dialog ───────────────────────────────────────────────────────

@st.dialog("Worklog Detail Report", width="large")
def _show_detail_popup(summary_row, detail_df: pd.DataFrame) -> None:
    machine_val = str(summary_row.get("Machine", "")       or "—")
    month_val   = str(summary_row.get("Billing Month", "") or "—")
    customer    = str(summary_row.get("Customer", "")      or "—")
    site        = str(summary_row.get("Site", "")          or "—")
    status_val  = str(summary_row.get("Status", "")        or "—")
    billing_val = float(summary_row.get("Billing",    0)   or 0)
    ot_bill     = float(summary_row.get("OT Billing", 0)   or 0)

    _SC = {
        "Submitted":       ("#DCFCE7", "#166534"),
        "Draft":           ("#FEF3C7", "#92400E"),
        "Invoiced":        ("#EDE9FE", "#5B21B6"),
        "Pending Billing": ("#FEF3C7", "#92400E"),
    }
    s_bg, s_fg = _SC.get(status_val, ("#F1F5F9", "#374151"))

    # ── Machine / period banner ───────────────────────────────────────────────
    st.markdown(
        f"<div style='background:linear-gradient(135deg,#1E3A5F,#2563EB);"
        f"border-radius:10px;padding:14px 20px;margin-bottom:14px;"
        f"display:flex;justify-content:space-between;align-items:center;'>"
        f"<div>"
        f"<div style='font-size:17px;font-weight:800;color:#fff;'>{machine_val}</div>"
        f"<div style='font-size:12px;color:rgba(255,255,255,.75);margin-top:2px;'>{month_val}</div>"
        f"</div>"
        f"<span style='background:{s_bg};color:{s_fg};padding:4px 14px;"
        f"border-radius:20px;font-size:12px;font-weight:700;'>{status_val}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Deployment + billing summary ──────────────────────────────────────────
    d1, d2, d3, d4 = st.columns(4)
    for col, lbl, val, color in [
        (d1, "Customer",       customer,              "#111827"),
        (d2, "Site",           site,                  "#111827"),
        (d3, "Rental Billing", f"₹{billing_val:,.0f}", "#E87722"),
        (d4, "OT Billing",     f"₹{ot_bill:,.0f}",    "#EF4444"),
    ]:
        with col:
            st.markdown(
                f"<div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
                f"text-transform:uppercase;color:#9CA3AF;margin-bottom:4px;'>{lbl}</div>"
                f"<div style='font-size:13px;font-weight:700;color:{color};'>{val}</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    if detail_df.empty:
        st.info("No shift entries found for this machine and month.", icon="ℹ️")
        return

    working_df = detail_df[detail_df["Start Time"].notna() & (detail_df["Start Time"] != "")]

    # ── KPI strip ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Working Days", len(working_df))
    k2.metric("Net Hours",    f"{working_df['Net Time'].sum():.1f} h")
    k3.metric("OT Hours",     f"{working_df['OT'].sum():.1f} h")
    k4.metric("Breakdown",    f"{working_df['Breakdown Hrs'].sum():.1f} h")

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Shift log table ───────────────────────────────────────────────────────
    _display = [
        "Date", "Weekday", "Start Time", "End Time",
        "Net Time", "Start HMR", "End HMR",
        "Breakdown Hrs", "OT", "HSD in Ltr", "Operator", "Remarks",
    ]
    _display = [c for c in _display if c in detail_df.columns]
    show_df  = detail_df[_display].copy()

    def _sun(row):
        if str(row.get("Weekday", "")) == "Sunday":
            return ["background-color:#fef08a;color:#713f12"] * len(row)
        return [""] * len(row)

    st.markdown(
        f"<div style='font-size:12px;color:#6B7280;margin-bottom:6px;'>"
        f"<b>{len(show_df)}</b> entries &nbsp;·&nbsp; "
        f"<b>{len(working_df)}</b> working days &nbsp;·&nbsp; "
        f"Sundays highlighted in yellow</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        show_df.style
        .apply(_sun, axis=1)
        .format(
            {"Net Time": "{:.2f}", "OT": "{:.1f}",
             "Breakdown Hrs": "{:.2f}", "HSD in Ltr": "{:.1f}"},
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
        height=min(38 + len(show_df) * 35 + 4, 500),
        column_config={
            "Date":          st.column_config.DateColumn("Date",      width="small", format="DD-MM-YYYY"),
            "Weekday":       st.column_config.TextColumn("Day",       width="small"),
            "Start Time":    st.column_config.TextColumn("Start",     width="small"),
            "End Time":      st.column_config.TextColumn("End",       width="small"),
            "Net Time":      st.column_config.NumberColumn("Net Hrs", format="%.2f", width="small"),
            "Start HMR":     st.column_config.NumberColumn("HMR In",  format="%.1f", width="small"),
            "End HMR":       st.column_config.NumberColumn("HMR Out", format="%.1f", width="small"),
            "Breakdown Hrs": st.column_config.NumberColumn("B/D Hrs", format="%.2f", width="small"),
            "OT":            st.column_config.NumberColumn("OT Hrs",  format="%.1f", width="small"),
            "HSD in Ltr":    st.column_config.NumberColumn("HSD (L)", format="%.1f", width="small"),
            "Operator":      st.column_config.TextColumn("Operator",  width="medium"),
            "Remarks":       st.column_config.TextColumn("Remarks",   width="medium"),
        },
    )


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Worklog Summary</div>",
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
        try:
            machs = sb.list_machines()
        except Exception:
            machs = []
        return wls, wos, custs, sites, machs

    work_logs, work_orders, customers, sites, machines = _load()

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}
    machine_map  = {m.get("id"): m for m in machines  if m.get("id")}
    wo_map_nav   = {wo["id"]: wo for wo in work_orders if wo.get("id")}

    # ── Status lookup: (serial_number, billing_month) → status label ───────────
    _wl_status_map: dict[tuple[str, str], str] = {}
    # ── Navigation map: (Machine display, billing_month, customer) → nav params ─
    _nav_map: dict[tuple[str, str, str], dict] = {}
    for _wl in work_logs:
        _mid   = _wl.get("machine_id", "")
        _mobj  = machine_map.get(_mid, {})
        _sn    = _mobj.get("serial_number", "") or ""
        _bm    = _wl.get("year", "")
        _s = ("Invoiced"  if _wl.get("invoiced")
              else "Submitted" if not _wl.get("is_draft", True)
              else "Draft")
        if _sn and _bm:
            _wl_status_map[(_sn, _bm)] = _s
        _wo    = wo_map_nav.get(_wl.get("work_order_id", ""), {})
        if _wo:
            _cid   = _wo.get("customer_id", "")
            _cname = customer_map.get(_cid, {}).get("customer_name", "")
            _ac    = _mobj.get("asset_code") or _wl.get("machine_label", "") or ""
            _make  = _mobj.get("make",  "") or ""
            _model = _mobj.get("model", "") or ""
            _sfx   = " ".join(p for p in [_make, _model] if p)
            _mdisp = f"{_ac} — {_sfx}" if _sfx else _ac
            _bm_p  = _bm.split(" ")
            _nav_map[(_mdisp, _bm, _cname)] = {
                "customer_id": _cid,
                "wo_id":       _wl.get("work_order_id", ""),
                "month_name":  _bm_p[0] if _bm_p else "",
                "year":        int(_bm_p[1]) if len(_bm_p) > 1 else date.today().year,
            }

    df_all = _flatten_worklogs(work_logs, work_orders, customer_map, site_map, machine_map)

    if df_all.empty:
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='font-size:36px;color:#2563EB;'>assignment</span>"
            "</div>"
            "<h3>No worklog data found</h3>"
            "<p>Save a work log first to see reports here.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Refresh"):
            st.cache_data.clear()
            st.rerun()
        return

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("tune", "Filters")
        fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2, 2, 2, 1])

        with fc1:
            month_opts = sorted(df_all["Billing Month"].dropna().unique().tolist())
            sel_month  = st.multiselect("Billing Month", month_opts, key="rpt_month", placeholder="All")
        with fc2:
            cust_opts  = sorted(df_all["Customer"].dropna().unique().tolist())
            sel_cust   = st.multiselect("Customer", cust_opts, key="rpt_cust", placeholder="All")
        with fc3:
            mach_opts  = sorted(df_all["Asset Code"].dropna().unique().tolist())
            sel_mach   = st.multiselect("Machine", mach_opts, key="rpt_mach", placeholder="All")
        with fc4:
            sn_opts    = sorted(df_all["Serial Number"].dropna().unique().tolist())
            sel_sn     = st.multiselect("Serial Number", sn_opts, key="rpt_sn", placeholder="All")
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
                for k in ["rpt_month", "rpt_cust", "rpt_mach", "rpt_sn", "rpt_from", "rpt_to"]:
                    st.session_state.pop(k, None)
                st.rerun()

    # Apply filters
    df = df_all.copy()
    if sel_month:
        df = df[df["Billing Month"].isin(sel_month)]
    if sel_cust:
        df = df[df["Customer"].isin(sel_cust)]
    if sel_mach:
        df = df[df["Asset Code"].isin(sel_mach)]
    if sel_sn:
        df = df[df["Serial Number"].isin(sel_sn)]
    if sel_from and sel_to:
        df = df[(df["Date"] >= sel_from) & (df["Date"] <= sel_to)]

    working_df = df[df["Start Time"].notna() & (df["Start Time"] != "")]

    # ── KPI strip ──────────────────────────────────────────────────────────────
    billing_df = _billing_summary(df)
    total_billing    = billing_df["Billing"].sum()    if not billing_df.empty else 0
    total_ot_billing = billing_df["OT Billing"].sum() if not billing_df.empty else 0

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='kpi-grid-6'>"
        + _kpi_card("precision_manufacturing", "Machines",      str(df["Asset Code"].nunique()),
                    "deployed machines",         "#0EA5E9")
        + _kpi_card("groups",                  "Customers",     str(df["Customer"].nunique()),
                    "active customers",          "#E87722")
        + _kpi_card("calendar_today",          "Working Days",  str(len(working_df)),
                    "shift entries",             "#10B981")
        + _kpi_card("schedule",                "Net Hours",     f"{working_df['Net Time'].sum():,.1f}",
                    "total net hours",           "#8B5CF6")
        + _kpi_card("payments",                "Rental Billing",f"₹{total_billing:,.0f}",
                    "rental charges",            "#E87722")
        + _kpi_card("more_time",               "OT Billing",    f"₹{total_ot_billing:,.0f}",
                    "overtime charges",          "#EF4444")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Inject Status into billing_df ─────────────────────────────────────────
    if not billing_df.empty:
        def _get_wl_status(r):
            return _wl_status_map.get((r["Serial Number"], r["Billing Month"]), "—")
        _ins_pos = billing_df.columns.tolist().index("Machine") + 1
        billing_df.insert(_ins_pos, "Status", billing_df.apply(_get_wl_status, axis=1))

    # ── Billing Summary ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div class='billing-title'>Billing Summary</div>"
            "<div class='billing-subtitle'>per Machine · per Month — rental charges computed from shift log"
            " · click any row to open its detailed shift log</div>",
            unsafe_allow_html=True,
        )

        if billing_df.empty:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:36px;color:#2563EB;'>payments</span>"
                "</div>"
                "<h3>No billing data</h3>"
                "<p>No completed shift data in the selected filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='billing-totals'>"
                f"<span style='color:#6B7280;'>Rental Billing: "
                f"<strong style='color:#E87722;font-size:18px;'>{total_billing:,.0f}</strong></span>"
                f"<span style='color:#6B7280;'>OT Billing: "
                f"<strong style='color:#E87722;font-size:18px;'>{total_ot_billing:,.0f}</strong></span>"
                f"<span style='color:#6B7280;'>Total: "
                f"<strong style='color:#111827;font-size:18px;'>"
                f"{total_billing + total_ot_billing:,.0f}</strong></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            billing_col_cfg = {
                "Billing Month":  st.column_config.TextColumn("Month",        width="small"),
                "Customer":       st.column_config.TextColumn("Customer",     width="medium"),
                "Site":           st.column_config.TextColumn("Site",         width="medium"),
                "Machine":        st.column_config.TextColumn("Machine",      width="medium"),
                "Status":         st.column_config.TextColumn("Status",       width="small"),
                "Serial Number":  st.column_config.TextColumn("Serial No.",   width="small"),
                "Rental/Month":   st.column_config.NumberColumn("Rate/Month", format="₹%,.0f"),
                "Working Days":   st.column_config.NumberColumn("Work Days",  format="%d",   width="small"),
                "Working Hrs":    st.column_config.NumberColumn("Std Hrs",    format="%.1f", width="small"),
                "Actual Hrs":     st.column_config.NumberColumn("Act Hrs",    format="%.2f", width="small"),
                "Qty":            st.column_config.NumberColumn("Qty",        format="%.4f", width="small"),
                "Billing":        st.column_config.NumberColumn("Billing (₹)",format="₹%,.0f"),
                "OT Hrs":         st.column_config.NumberColumn("OT Hrs",     format="%.2f", width="small"),
                "OT Billing":     st.column_config.NumberColumn("OT Bill (₹)",format="₹%,.0f"),
                "Breakdown Hrs":  st.column_config.NumberColumn("B/D Hrs",    format="%.2f", width="small"),
            }
            selected_idx = render_drilldown_table(
                billing_df,
                "wlr_billing_tbl",
                column_config=billing_col_cfg,
                style_fn=lambda s: _wl_status_styler(
                    s.apply(_style_billing, axis=0).format({
                        "Rental/Month":  "{:,.0f}",
                        "Working Hrs":   "{:.1f}",
                        "Actual Hrs":    "{:.2f}",
                        "Qty":           "{:.4f}",
                        "Billing":       "{:,.0f}",
                        "OT Hrs":        "{:.2f}",
                        "OT Billing":    "{:,.0f}",
                        "Breakdown Hrs": "{:.2f}",
                    })
                ),
            )
            render_print_export_buttons(
                billing_df,
                base_name="worklog_summary",
                key_prefix="wlr_sum",
                title="Worklog Summary",
                subtitle="per Machine · per Month",
                sheet_name="Worklog Summary",
            )

            # ── Selected row → popup detail report ────────────────────────────
            _prev_billing_idx = st.session_state.get("_wlr_prev_billing_idx")
            if selected_idx is not None and selected_idx < len(billing_df):
                row         = billing_df.iloc[selected_idx]
                machine_val = row.get("Machine", "")
                month_val   = row.get("Billing Month", "")
                _ac = machine_val.split(" — ")[0].strip() if " — " in machine_val else machine_val
                _detail_df  = df[
                    (df["Asset Code"] == _ac) & (df["Billing Month"] == month_val)
                ].sort_values("Date").reset_index(drop=True)

                if selected_idx != _prev_billing_idx:
                    st.session_state["_wlr_prev_billing_idx"] = selected_idx
                    _show_detail_popup(row, _detail_df)
                else:
                    if st.button(
                        "📋 View Detail Report",
                        key="wlr_goto_detail",
                        help="Re-open the shift log for the selected row",
                    ):
                        _show_detail_popup(row, _detail_df)
            elif selected_idx is None:
                st.session_state["_wlr_prev_billing_idx"] = None

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    if st.button("Refresh Data", key="rpt_refresh"):
        st.cache_data.clear()
        st.rerun()
