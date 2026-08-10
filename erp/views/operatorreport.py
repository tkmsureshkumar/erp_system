"""
erp/views/operatorreport.py
Operator Reports — Master list and Salary Report.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient
from ._report_utils import render_export_buttons, render_drilldown_table


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
.kpi-grid-5 {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
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
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 8px; display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 26px; font-weight: 800; color: #111827;
    line-height: 1; margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 11px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 14px; right: 16px;
    font-size: 20px; opacity: .12;
}

.form-sec-hdr {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* report section title */
.rpt-section-title {
    font-size: 17px; font-weight: 800; color: #1E2938;
    margin: 20px 0 10px; letter-spacing: -.2px;
}
.rpt-section-sub {
    font-size: 12px; color: #6B7280; margin: -6px 0 14px;
}

.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 60px 40px;
    background: #FAFBFC; border: 2px dashed #E2EBF0;
    border-radius: 16px; text-align: center;
}
.empty-icon-ring {
    width: 72px; height: 72px; border-radius: 50%;
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 34px; margin-bottom: 18px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 { font-size:16px; font-weight:700; color:#111827; margin:0 0 6px; }
.empty-state-v2 p  { font-size:13px; color:#9CA3AF; max-width:270px; line-height:1.6; margin:0; }

@keyframes cs-fadeup {
    from { opacity:0; transform:translateY(10px); }
    to   { opacity:1; transform:translateY(0); }
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
    if not schedule_data:
        return []
    try:
        data = json.loads(schedule_data) if isinstance(schedule_data, str) else schedule_data
    except Exception:
        return []
    if isinstance(data, dict):
        shift_type = data.get("shift_type")
        if shift_type == "double":
            rows = list(data.get("shift1") or []) + list(data.get("shift2") or [])
        elif shift_type == "single":
            rows = data.get("rows") or []
        else:
            return []
    elif isinstance(data, list):
        rows = data
    else:
        return []
    return [r for r in rows if isinstance(r, dict)]


def _resolve_operator(stored: str, op_by_code: dict, op_by_name: dict) -> dict:
    """Match a stored operator string (plain name OR 'CODE — Name') to an operator record."""
    stored = stored.strip()
    if " — " in stored:
        code, name = stored.split(" — ", 1)
        op = op_by_code.get(code.strip().upper())
        if op:
            return op
        op = op_by_name.get(name.strip().lower())
        if op:
            return op
    return op_by_name.get(stored.lower(), {})


def _available_days(joining_date_str, period_start: date, period_end: date) -> int:
    """Days in [period_start, period_end] on or after joining_date."""
    if not joining_date_str:
        return (period_end - period_start).days + 1
    try:
        jd = date.fromisoformat(str(joining_date_str)[:10])
    except Exception:
        return (period_end - period_start).days + 1
    effective_start = max(period_start, jd)
    if effective_start > period_end:
        return 0
    return (period_end - effective_start).days + 1


def _flatten_for_salary(
    work_logs: list[dict],
    work_orders: list[dict],
    customer_map: dict,
    site_map: dict,
    machine_map: dict,
    op_by_code: dict,
    op_by_name: dict,
) -> pd.DataFrame:
    wo_map = {wo["id"]: wo for wo in work_orders if wo.get("id")}
    rows: list[dict] = []

    for wl in work_logs:
        wo = wo_map.get(wl.get("work_order_id"), {})
        if not wo:
            continue
        cust  = customer_map.get(wo.get("customer_id", ""), {})
        site_ = site_map.get(wo.get("site_id", ""), {})

        machine_id    = wl.get("machine_id", "")
        mobj          = machine_map.get(machine_id, {})
        asset_code    = mobj.get("asset_code") or wl.get("machine_label") or ""
        make          = mobj.get("make", "") or ""
        model         = mobj.get("model", "") or ""
        suffix        = " ".join(p for p in [make, model] if p)
        machine_label = f"{asset_code} — {suffix}" if suffix else asset_code

        billing_month = wl.get("year", "")

        for entry in _iter_schedule_rows(wl.get("schedule_data")):
            op_raw = str(entry.get("operator") or "").strip()
            if not op_raw:
                continue

            op_rec = _resolve_operator(op_raw, op_by_code, op_by_name)

            net = float(entry.get("net_time") or 0)
            ot  = float(entry.get("ot")       or 0)
            bd  = float(entry.get("breakdown_hours") or 0)

            rows.append({
                "Emp Code":          op_rec.get("emp_code", ""),
                "Operator":          op_rec.get("operator_name") or op_raw,
                "Op Status":         op_rec.get("status", ""),
                "Fixed Salary":      float(op_rec.get("fixed_salary") or 0),
                "Joining Date":      op_rec.get("joining_date"),
                "Name in Passbook":  op_rec.get("name_in_passbook", ""),
                "Account No.":       op_rec.get("bank_account_number", ""),
                "IFSC":              op_rec.get("ifsc_code", ""),
                "Billing Month":     billing_month,
                "Customer":          cust.get("customer_name", ""),
                "Site":              site_.get("site_name", ""),
                "Machine":           machine_label,
                "Date":              entry.get("date"),
                "Weekday":           entry.get("weekday", ""),
                "Start Time":        _fmt_time(entry.get("start_time")),
                "End Time":          _fmt_time(entry.get("end_time")),
                "Net Time":          net,
                "OT":                ot,
                "Breakdown Hrs":     bd,
                "Start HMR":         entry.get("start_hmr"),
                "End HMR":           entry.get("end_hmr"),
                "Remarks":           str(entry.get("remarks") or ""),
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    return df


# ── UI helpers ────────────────────────────────────────────────────────────────

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


def _rpt_title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"<div class='rpt-section-title'>{title}</div>"
        + (f"<div class='rpt-section-sub'>{subtitle}</div>" if subtitle else ""),
        unsafe_allow_html=True,
    )


# ── Tab: Operator Master ──────────────────────────────────────────────────────

def _render_operator_master(operators: list[dict]) -> None:
    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    if not operators:
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='font-size:34px;color:#2563EB;'>engineering</span>"
            "</div>"
            "<h3>No operators found</h3>"
            "<p>Add operators from the Operators module first.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    active_only = st.checkbox("Show active employees only", value=True, key="om_active_only")
    data = operators if not active_only else [o for o in operators if o.get("status") == "Active"]

    if not data:
        st.info("No active operators found.")
        return

    STATUS_COLORS = {
        "Active":   ("#DCFCE7", "#166534"),
        "Inactive": ("#FEE2E2", "#991B1B"),
        "On Leave": ("#FEF3C7", "#92400E"),
    }

    def _fmt_date(v) -> str:
        if not v:
            return "—"
        try:
            return date.fromisoformat(str(v)[:10]).strftime("%d %b %Y")
        except Exception:
            return str(v)

    hs = ("padding:9px 12px;background:#F8FAFC;font-size:10px;font-weight:700;"
          "letter-spacing:.11em;text-transform:uppercase;color:#6B7280;"
          "border-bottom:2px solid #E2EBF0;white-space:nowrap;")

    headers = [
        "Emp Code", "Status", "Joining Date", "Name", "Fixed Salary",
        "Mobile", "Father Name", "Aadhar", "Licence No.",
        "Heavy Licence Start", "Light Licence Start",
        "Name in Passbook", "Account Number", "IFSC Code",
    ]

    # ── Sort controls ─────────────────────────────────────────────────────────
    _OM_SORT_COLS = ["Emp Code", "Name", "Status", "Joining Date", "Fixed Salary", "Mobile"]
    _OM_SORT_MAP  = {
        "Emp Code":     lambda o: (o.get("emp_code") or "").lower(),
        "Name":         lambda o: (o.get("operator_name") or "").lower(),
        "Status":       lambda o: (o.get("status") or "").lower(),
        "Joining Date": lambda o: str(o.get("joining_date") or ""),
        "Fixed Salary": lambda o: float(o.get("fixed_salary") or 0),
        "Mobile":       lambda o: (o.get("mobile_number") or "").lower(),
    }
    _om1, _om2, _ = st.columns([2, 1, 5])
    with _om1:
        _om_col = st.selectbox("Sort by", _OM_SORT_COLS, key="om_sort_col")
    with _om2:
        _om_dir = st.selectbox("Order", ["↑ Asc", "↓ Desc"], key="om_sort_dir",
                               label_visibility="collapsed")
    data = sorted(data, key=_OM_SORT_MAP[_om_col], reverse=(_om_dir == "↓ Desc"))

    rows_html = ""
    for i, op in enumerate(data):
        bg    = "#FFFFFF" if i % 2 == 0 else "#FAFBFC"
        st_v  = op.get("status") or "—"
        sbg, sfg = STATUS_COLORS.get(st_v, ("#F1F5F9", "#374151"))
        salary = op.get("fixed_salary")
        sal_disp = f"₹{float(salary):,.0f}" if salary else "—"

        rows_html += (
            f"<tr style='background:{bg};border-bottom:1px solid #F1F5F9;'>"
            f"<td style='padding:8px 12px;font-weight:700;color:#1E3A5F;font-size:12px;'>"
            f"{op.get('emp_code') or '—'}</td>"
            f"<td style='padding:8px 12px;'>"
            f"<span style='background:{sbg};color:{sfg};padding:2px 9px;"
            f"border-radius:12px;font-size:11px;font-weight:700;'>{st_v}</span></td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{_fmt_date(op.get('joining_date'))}</td>"
            f"<td style='padding:8px 12px;font-size:12px;font-weight:600;color:#111827;'>"
            f"{op.get('operator_name') or '—'}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>{sal_disp}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{op.get('mobile_number') or '—'}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{op.get('father_name') or '—'}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;font-family:monospace;'>"
            f"{op.get('aadhar_number') or '—'}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{op.get('license_number') or '—'}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{_fmt_date(op.get('heavy_license_startdate'))}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{_fmt_date(op.get('light_license_startdate'))}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{op.get('name_in_passbook') or '—'}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;font-family:monospace;'>"
            f"{op.get('bank_account_number') or '—'}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;font-family:monospace;'>"
            f"{op.get('ifsc_code') or '—'}</td>"
            f"</tr>"
        )

    table_html = (
        "<div style='overflow-x:auto;border:1px solid #E2EBF0;border-radius:10px;"
        "box-shadow:0 1px 3px rgba(0,0,0,.05);'>"
        "<table style='width:100%;border-collapse:collapse;font-family:inherit;'>"
        "<thead><tr>"
        + "".join(f"<th style='{hs}'>{h}</th>" for h in headers)
        + f"</tr></thead><tbody>{rows_html}</tbody></table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)
    st.markdown(
        f"<div style='margin-top:10px;font-size:11px;color:#9CA3AF;'>"
        f"Showing {len(data)} operator{'s' if len(data) != 1 else ''}"
        f"{'  ·  Active only' if active_only else ''}</div>",
        unsafe_allow_html=True,
    )

    # Export
    def _s(op, k): return str(op.get(k) or "")
    export_df = pd.DataFrame([{
        "Emp Code":           _s(op, "emp_code"),
        "Status":             _s(op, "status"),
        "Joining Date":       _s(op, "joining_date"),
        "Name":               _s(op, "operator_name"),
        "Fixed Salary":       op.get("fixed_salary") or "",
        "Mobile":             _s(op, "mobile_number"),
        "Father Name":        _s(op, "father_name"),
        "Aadhar":             _s(op, "aadhar_number"),
        "Licence No.":        _s(op, "license_number"),
        "Heavy Licence Start":_s(op, "heavy_license_startdate"),
        "Light Licence Start":_s(op, "light_license_startdate"),
        "Name in Passbook":   _s(op, "name_in_passbook"),
        "Account Number":     _s(op, "bank_account_number"),
        "IFSC Code":          _s(op, "ifsc_code"),
    } for op in data])
    render_export_buttons(
        export_df,
        base_name="operator_master",
        excel_key="om_xlsx",
        pdf_key="om_pdf",
        title="Operator Master",
        subtitle="Active operators" if active_only else "All operators",
        sheet_name="Operators",
    )


# ── Tab: Salary Report ────────────────────────────────────────────────────────

def _render_salary_report(
    df_all: pd.DataFrame,
    sel_from: date,
    sel_to: date,
) -> None:
    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    if df_all.empty:
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='font-size:34px;color:#2563EB;'>engineering</span>"
            "</div>"
            "<h3>No operator data found</h3>"
            "<p>Assign operators in the Work Log page to see salary summaries here.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # Only active employees
    df_active = df_all[df_all["Op Status"] == "Active"].copy()

    if df_active.empty:
        st.info("No active operator data in the current filter selection.")
        return

    # ── Salary filters ─────────────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("tune", "Filters")
        fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2, 2, 2, 1])

        with fc1:
            mo_opts = sorted(df_active["Billing Month"].dropna().unique().tolist())
            sel_mo  = st.multiselect("Billing Month", mo_opts, key="sal_month", placeholder="All")
        with fc2:
            cu_opts = sorted(df_active["Customer"].dropna().unique().tolist())
            sel_cu  = st.multiselect("Customer", cu_opts, key="sal_cust", placeholder="All")
        with fc3:
            si_opts = sorted(df_active["Site"].dropna().unique().tolist())
            sel_si  = st.multiselect("Site", si_opts, key="sal_site", placeholder="All")
        with fc4:
            op_opts = sorted(df_active["Operator"].dropna().unique().tolist())
            sel_op  = st.multiselect("Operator", op_opts, key="sal_op", placeholder="All")
        with fc5:
            valid_dates = df_active["Date"].dropna()
            f_min = valid_dates.min() if not valid_dates.empty else date.today()
            f_max = valid_dates.max() if not valid_dates.empty else date.today()
            sal_from = st.date_input("Date From", value=f_min, key="sal_from")
        with fc6:
            sal_to   = st.date_input("Date To",   value=f_max, key="sal_to")
        with fc7:
            st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
            if st.button("Clear", key="sal_clear", use_container_width=True):
                for k in ["sal_month","sal_cust","sal_site","sal_op","sal_from","sal_to"]:
                    st.session_state.pop(k, None)
                st.rerun()

    # Apply filters
    df = df_active.copy()
    if sel_mo:
        df = df[df["Billing Month"].isin(sel_mo)]
    if sel_cu:
        df = df[df["Customer"].isin(sel_cu)]
    if sel_si:
        df = df[df["Site"].isin(sel_si)]
    if sel_op:
        df = df[df["Operator"].isin(sel_op)]
    if sal_from and sal_to:
        df = df[(df["Date"] >= sal_from) & (df["Date"] <= sal_to)]

    working_df = df[df["Start Time"].notna() & (df["Start Time"] != "")]

    period_start = sal_from or (df["Date"].min() if not df["Date"].dropna().empty else date.today())
    period_end   = sal_to   or (df["Date"].max() if not df["Date"].dropna().empty else date.today())

    if working_df.empty:
        st.info("No working-day rows match the selected filters.")
        return

    # ── KPI strip ──────────────────────────────────────────────────────────────
    n_ops    = working_df["Emp Code"].nunique()
    n_days   = len(working_df)
    ot_hrs   = working_df["OT"].sum()
    bd_hrs   = working_df["Breakdown Hrs"].sum()
    total_sal = working_df.drop_duplicates("Emp Code")["Fixed Salary"].sum()

    st.markdown(
        f"<div class='kpi-grid-5'>"
        + _kpi_card("engineering",    "Active Operators", n_ops,
                    "in filtered view",    "#E87722")
        + _kpi_card("calendar_month", "Working Days",     f"{n_days:,}",
                    "total shift days",    "#10B981")
        + _kpi_card("more_time",      "OT Hours",         f"{ot_hrs:,.1f}",
                    "overtime hours",      "#EF4444")
        + _kpi_card("build",          "Breakdown Hrs",    f"{bd_hrs:,.1f}",
                    "downtime recorded",   "#6B7280")
        + _kpi_card("payments",       "Total Fixed Sal.", f"₹{total_sal:,.0f}",
                    "sum of fixed salaries","#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Section A: Operator Summary ────────────────────────────────────────────
    _rpt_title("Operator Summary", "per operator · active employees only")

    op_grp = (
        working_df
        .groupby(["Emp Code", "Operator", "Fixed Salary", "Joining Date",
                  "Name in Passbook", "IFSC", "Account No."], dropna=False)
        .agg(
            Working_Days = ("Net Time", "count"),
            OT_Hrs       = ("OT",       "sum"),
        )
        .reset_index()
    )
    op_grp["Available Days"] = op_grp["Joining Date"].apply(
        lambda jd: _available_days(jd, period_start, period_end)
    )

    summary_cols = [
        "Emp Code", "Operator", "Fixed Salary", "Available Days",
        "Working_Days", "OT_Hrs",
        "Name in Passbook", "IFSC", "Account No.",
    ]
    op_summary = op_grp[summary_cols].rename(columns={
        "Working_Days": "Working Days",
        "OT_Hrs":       "OT Hours",
    }).sort_values("Emp Code")

    _SUM_CFG = {
        "Emp Code":         st.column_config.TextColumn("Emp Code",     width="small"),
        "Operator":         st.column_config.TextColumn("Name",         width="medium"),
        "Fixed Salary":     st.column_config.NumberColumn("Fixed Salary",format="₹%,.0f"),
        "Available Days":   st.column_config.NumberColumn("Avail Days", width="small"),
        "Working Days":     st.column_config.NumberColumn("Work Days",  width="small"),
        "OT Hours":         st.column_config.NumberColumn("OT Hrs",     format="%.2f", width="small"),
        "Name in Passbook": st.column_config.TextColumn("Passbook Name",width="medium"),
        "IFSC":             st.column_config.TextColumn("IFSC",         width="small"),
        "Account No.":      st.column_config.TextColumn("Account No.",  width="medium"),
    }
    with st.container(border=True):
        sel_op_idx = render_drilldown_table(
            op_summary,
            "sal_sum_tbl",
            column_config=_SUM_CFG,
            style_fn=lambda s: s.format({"Fixed Salary": "{:,.0f}", "OT Hours": "{:.2f}"}),
        )
    render_export_buttons(
        op_summary,
        base_name="op_summary",
        excel_key="sal_sum_xlsx",
        pdf_key="sal_sum_pdf",
        title="Operator Summary",
        subtitle="per operator · active employees only",
        sheet_name="Operator Summary",
    )

    # ── Drill-down: click operator row → show their shift log ──────────────────
    if sel_op_idx is not None:
        sel_row  = op_summary.iloc[sel_op_idx]
        sel_code = sel_row.get("Emp Code", "")
        sel_name = sel_row.get("Operator", "")
        st.markdown(
            f"<div style='margin-top:14px;padding:10px 14px;"
            f"background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
            f"font-size:13px;color:#1E40AF;font-weight:600;'>"
            f"Shifts for <strong>{sel_code} — {sel_name}</strong></div>",
            unsafe_allow_html=True,
        )
        log_cols = ["Date","Weekday","Customer","Site","Machine",
                    "Start Time","End Time","Net Time","OT","Breakdown Hrs","Remarks"]
        log_cols = [c for c in log_cols if c in working_df.columns]
        mask = (working_df["Emp Code"] == sel_code) if sel_code else (working_df["Operator"] == sel_name)
        drill_df = working_df[mask][log_cols].sort_values("Date")
        st.dataframe(
            drill_df.style.format(
                {"Net Time":"{:.2f}","OT":"{:.1f}","Breakdown Hrs":"{:.2f}"}, na_rep="—"
            ),
            use_container_width=True, hide_index=True,
            column_config={
                "Date":          st.column_config.DateColumn("Date",   format="DD-MM-YYYY", width="small"),
                "Weekday":       st.column_config.TextColumn("Day",    width="small"),
                "Start Time":    st.column_config.TextColumn("Start",  width="small"),
                "End Time":      st.column_config.TextColumn("End",    width="small"),
                "Net Time":      st.column_config.NumberColumn("Net Hrs",  format="%.2f", width="small"),
                "OT":            st.column_config.NumberColumn("OT Hrs",   format="%.1f", width="small"),
                "Breakdown Hrs": st.column_config.NumberColumn("B/D Hrs",  format="%.2f", width="small"),
            },
        )

    # ── Section B: Operator Summary by Client ──────────────────────────────────
    _rpt_title("Operator Summary by Client", "per operator · per customer · per site · per machine")

    client_grp = (
        working_df
        .groupby(["Emp Code", "Operator", "Fixed Salary", "Joining Date",
                  "Name in Passbook", "IFSC", "Account No.",
                  "Customer", "Site", "Machine"], dropna=False)
        .agg(
            Working_Days = ("Net Time", "count"),
            OT_Hrs       = ("OT",       "sum"),
        )
        .reset_index()
    )
    client_grp["Available Days"] = client_grp["Joining Date"].apply(
        lambda jd: _available_days(jd, period_start, period_end)
    )

    by_client_cols = [
        "Emp Code", "Operator", "Customer", "Site", "Machine",
        "Fixed Salary", "Available Days", "Working_Days", "OT_Hrs",
        "Name in Passbook", "IFSC", "Account No.",
    ]
    by_client = client_grp[by_client_cols].rename(columns={
        "Working_Days": "Working Days",
        "OT_Hrs":       "OT Hours",
    }).sort_values(["Emp Code", "Customer", "Site", "Machine"])

    with st.container(border=True):
        st.dataframe(
            by_client.style.format({
                "Fixed Salary": "{:,.0f}",
                "OT Hours":     "{:.2f}",
            }),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Emp Code":        st.column_config.TextColumn("Emp Code",     width="small"),
                "Operator":        st.column_config.TextColumn("Name",         width="medium"),
                "Customer":        st.column_config.TextColumn("Customer",     width="medium"),
                "Site":            st.column_config.TextColumn("Site",         width="medium"),
                "Machine":         st.column_config.TextColumn("Machine",      width="medium"),
                "Fixed Salary":    st.column_config.NumberColumn("Fixed Salary",format="₹%,.0f"),
                "Available Days":  st.column_config.NumberColumn("Avail Days", width="small"),
                "Working Days":    st.column_config.NumberColumn("Work Days",  width="small"),
                "OT Hours":        st.column_config.NumberColumn("OT Hrs",     format="%.2f", width="small"),
                "Name in Passbook":st.column_config.TextColumn("Passbook Name",width="medium"),
                "IFSC":            st.column_config.TextColumn("IFSC",         width="small"),
                "Account No.":     st.column_config.TextColumn("Account No.",  width="medium"),
            },
        )
    render_export_buttons(
        by_client,
        base_name="op_summary_by_client",
        excel_key="sal_client_xlsx",
        pdf_key="sal_client_pdf",
        title="Operator Summary by Client",
        subtitle="per operator · per customer · per site · per machine",
        sheet_name="By Client",
    )

    # ── Section C: Detailed Shift Log ──────────────────────────────────────────
    with st.expander(f"View Detailed Shift Log  ({len(df):,} entries)", expanded=False):
        log_cols = [
            "Emp Code", "Operator", "Customer", "Site", "Machine",
            "Date", "Weekday", "Start Time", "End Time",
            "Net Time", "OT", "Breakdown Hrs", "Remarks",
        ]
        log_cols = [c for c in log_cols if c in df.columns]
        render_export_buttons(
            df[log_cols],
            base_name="op_shift_log",
            excel_key="sal_detail_xlsx",
            pdf_key="sal_detail_pdf",
            title="Operator Shift Log",
            subtitle="detailed daily entries",
            sheet_name="Shift Log",
        )

        detail_df = df[log_cols].sort_values(["Emp Code", "Date"], na_position="last")

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
                "Emp Code":      st.column_config.TextColumn("Emp Code",   width="small"),
                "Operator":      st.column_config.TextColumn("Name",       width="medium"),
                "Customer":      st.column_config.TextColumn("Customer",   width="medium"),
                "Site":          st.column_config.TextColumn("Site",       width="medium"),
                "Machine":       st.column_config.TextColumn("Machine",    width="medium"),
                "Date":          st.column_config.DateColumn("Date",       width="small", format="DD-MM-YYYY"),
                "Weekday":       st.column_config.TextColumn("Day",        width="small"),
                "Start Time":    st.column_config.TextColumn("Start",      width="small"),
                "End Time":      st.column_config.TextColumn("End",        width="small"),
                "Net Time":      st.column_config.NumberColumn("Net Hrs",  format="%.2f", width="small"),
                "OT":            st.column_config.NumberColumn("OT Hrs",   format="%.1f", width="small"),
                "Breakdown Hrs": st.column_config.NumberColumn("B/D Hrs",  format="%.2f", width="small"),
                "Remarks":       st.column_config.TextColumn("Remarks",    width="medium"),
            },
        )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Operator Report</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase connection failed.")
        st.write(str(exc))
        return

    @st.cache_data(ttl=60, show_spinner="Loading operator data…")
    def _load():
        results = {}
        for key, fn in [
            ("wls",   sb.list_all_worklogs),
            ("wos",   sb.list_work_orders),
            ("custs", sb.list_customers),
            ("sites", sb.list_sites),
            ("machs", sb.list_machines),
            ("ops",   sb.list_operators),
        ]:
            try:
                results[key] = fn()
            except Exception:
                results[key] = []
        return results

    data = _load()
    work_logs      = data["wls"]
    work_orders    = data["wos"]
    customers      = data["custs"]
    sites          = data["sites"]
    machines       = data["machs"]
    operators      = data["ops"]

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}
    machine_map  = {m.get("id"): m for m in machines  if m.get("id")}

    # Build operator lookups (case-insensitive by name, uppercase by code)
    op_by_code: dict[str, dict] = {}
    op_by_name: dict[str, dict] = {}
    for op in operators:
        if op.get("emp_code"):
            op_by_code[op["emp_code"].upper()] = op
        if op.get("operator_name"):
            op_by_name[op["operator_name"].strip().lower()] = op

    df_all = _flatten_for_salary(
        work_logs, work_orders, customer_map, site_map,
        machine_map, op_by_code, op_by_name,
    )

    today     = date.today()
    min_date  = df_all["Date"].min() if not df_all.empty and "Date" in df_all else today
    max_date  = today

    tab_master, tab_salary = st.tabs(["Operator Master", "Salary Report"])

    with tab_master:
        _render_operator_master(operators)

    with tab_salary:
        _render_salary_report(df_all, min_date, max_date)

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    if st.button("Refresh Data", key="opr_refresh"):
        st.cache_data.clear()
        st.rerun()
