"""
erp/views/payment_summary.py — Payment Summary & Payroll Calculator

Supabase table required (for save/audit trail):

    CREATE TABLE IF NOT EXISTS payroll_summary (
        id                uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id       text NOT NULL,
        payroll_month     text NOT NULL,
        fixed_salary      numeric DEFAULT 0,
        month_days        int DEFAULT 26,
        days_worked       int DEFAULT 0,
        ot_hours          numeric DEFAULT 0,
        earned_basic      numeric DEFAULT 0,
        ot_amount         numeric DEFAULT 0,
        additions         numeric DEFAULT 0,
        total_amount      numeric DEFAULT 0,
        salary_paid_other numeric DEFAULT 0,
        advance_recovery  numeric DEFAULT 0,
        pf_amount         numeric DEFAULT 0,
        other_deductions  numeric DEFAULT 0,
        deduction_total   numeric DEFAULT 0,
        net_payable       numeric DEFAULT 0,
        remarks           text,
        status            text DEFAULT 'Draft',
        finalized_by      text,
        finalized_at      timestamptz,
        created_at        timestamptz DEFAULT now(),
        CONSTRAINT payroll_summary_emp_month UNIQUE (employee_id, payroll_month)
    );

Calculation formulas:
    Earned Basic     = Fixed Salary × min(Working Days, Month Days) / Month Days
    OT Amt           = OT Hours × Fixed Salary / Month Days / 12   (12-hr shift basis)
    Total Amt        = Earned Basic + OT Amt + Additions (Approved)
    Deduction Total  = Sal Paid Other + Advance Deduction + PF Amt + Other Deductions (Approved)
    Net Payable      = Total Amt − Deduction Total
"""
from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, datetime, time, timezone

import pandas as pd
import streamlit as st

from .. import auth
from ..supabase_client import SupabaseClient


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
.ps-kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin: 0 0 24px;
}
.ps-kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 16px 20px 12px;
    position: relative;
    overflow: hidden;
    transition: box-shadow .18s, transform .18s;
}
.ps-kpi-card:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,.08);
    transform: translateY(-2px);
}
.ps-kpi-bar {
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.ps-kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 8px;
}
.ps-kpi-value {
    font-size: 24px; font-weight: 800; color: #111827;
    line-height: 1; margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
}
.ps-kpi-sub { font-size: 11px; color: #6B7280; }
.ps-kpi-icon {
    position: absolute; top: 14px; right: 16px;
    font-size: 22px; opacity: .10;
    font-family: "Material Symbols Rounded";
    font-variation-settings: "FILL" 1;
}
.ps-total-bar {
    padding: 10px 16px;
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-radius: 8px;
    font-size: 12px;
    color: #166534;
    font-weight: 600;
    margin: 8px 0 4px;
}
.ps-info-note {
    padding: 10px 14px;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 8px;
    font-size: 12px;
    color: #1E40AF;
    margin-bottom: 14px;
}
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_name() -> str:
    p = auth.current_profile()
    return p.get("full_name") or p.get("email") or "Unknown"


def _month_label(m: int) -> str:
    return date(2000, m, 1).strftime("%B")


def _calc_month_days(year: int, month: int) -> int:
    """Mon-Sat count in month (excludes Sundays only)."""
    _, total = calendar.monthrange(year, month)
    return sum(1 for d in range(1, total + 1) if date(year, month, d).weekday() < 6)


def _kpi(icon: str, label: str, value, sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='ps-kpi-card'>"
        f"<div class='ps-kpi-bar' style='background:{accent}'></div>"
        f"<span class='ps-kpi-icon'>{icon}</span>"
        f"<div class='ps-kpi-label'>{label}</div>"
        f"<div class='ps-kpi-value'>{value}</div>"
        f"<div class='ps-kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _available_days(joining_date_str, period_start: date, period_end: date) -> int:
    if not joining_date_str:
        return (period_end - period_start).days + 1
    try:
        jd = date.fromisoformat(str(joining_date_str)[:10])
    except Exception:
        return (period_end - period_start).days + 1
    eff = max(period_start, jd)
    return max(0, (period_end - eff).days + 1)


# ── Worklog parsing (mirrors operatorreport logic) ────────────────────────────

def _iter_schedule_rows(schedule_data) -> list[dict]:
    if not schedule_data:
        return []
    try:
        data = json.loads(schedule_data) if isinstance(schedule_data, str) else schedule_data
    except Exception:
        return []
    if isinstance(data, dict):
        st_ = data.get("shift_type")
        if st_ == "double":
            rows = list(data.get("shift1") or []) + list(data.get("shift2") or [])
        elif st_ == "single":
            rows = data.get("rows") or []
        else:
            return []
    elif isinstance(data, list):
        rows = data
    else:
        return []
    return [r for r in rows if isinstance(r, dict)]


def _resolve_operator(stored: str, op_by_code: dict, op_by_name: dict) -> dict:
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


def _build_worklog_agg(
    work_logs: list[dict],
    work_orders: list[dict],
    op_by_code: dict,
    op_by_name: dict,
    period_start: date,
    period_end: date,
) -> dict[str, dict]:
    """
    Returns {employee_uuid: {working_days: int, ot_hours: float}}.
    Working day = any shift where Net Time > 0 OR Breakdown Hrs > 0.
    OT counted independently from all shifts where OT > 0.
    """
    wo_map = {wo["id"]: wo for wo in work_orders if wo.get("id")}

    emp_dates: dict[str, set] = defaultdict(set)
    emp_ot:    dict[str, float] = defaultdict(float)

    for wl in work_logs:
        wo = wo_map.get(wl.get("work_order_id"), {})
        if not wo:
            continue
        for entry in _iter_schedule_rows(wl.get("schedule_data")):
            op_raw = str(entry.get("operator") or "").strip()
            if not op_raw:
                continue
            op_rec = _resolve_operator(op_raw, op_by_code, op_by_name)
            if not op_rec.get("id"):
                continue
            try:
                entry_date = date.fromisoformat(str(entry.get("date") or ""))
            except Exception:
                continue
            if not (period_start <= entry_date <= period_end):
                continue
            emp_id = op_rec["id"]
            net = float(entry.get("net_time") or 0)
            bd  = float(entry.get("breakdown_hours") or 0)
            ot  = float(entry.get("ot") or 0)
            if net > 0 or bd > 0:
                emp_dates[emp_id].add(entry_date)
            if ot > 0:
                emp_ot[emp_id] += ot

    result: dict[str, dict] = {}
    for emp_id in set(emp_dates) | set(emp_ot):
        result[emp_id] = {
            "working_days": len(emp_dates.get(emp_id, set())),
            "ot_hours":     round(emp_ot.get(emp_id, 0.0), 2),
        }
    return result


# ── Calculation ───────────────────────────────────────────────────────────────

def _recompute(df: pd.DataFrame) -> pd.DataFrame:
    """Auto-calculate summary columns from component values.

    Earned Basic and OT Amt are pre-filled on load and freely editable.
    Total Amt, Deduction Total, Net Payable are always derived:
        No. of Days Worked = min(Working Days, Month Days)          [display only]
        Total Amt          = Earned Basic + OT Amt
        Deduction Total    = Sal Paid Other + Advance Deduction + PF Amt
        Net Payable        = Total Amt − Deduction Total
    """
    df = df.copy()
    dw = df["Working Days"].astype(float).clip(upper=df["Month Days"].astype(float))
    df["No. of Days Worked"] = dw.astype(int)
    df["Total Amt"]       = df["Earned Basic"].astype(float) + df["OT Amt"].astype(float)
    df["Deduction Total"] = (
        df["Sal Paid Other"].astype(float)
        + df["Advance Deduction"].astype(float)
        + df["PF Amt"].astype(float)
    )
    df["Net Payable"]     = df["Total Amt"] - df["Deduction Total"]
    return df


def _initial_fill(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-fill Earned Basic and OT Amt from formula on first load."""
    df = df.copy()
    md = df["Month Days"].astype(float).replace(0.0, 1.0)
    fs = df["Fixed Salary"].astype(float)
    dw = df["Working Days"].astype(float).clip(upper=md)
    df["Earned Basic"] = (fs * dw / md).round(0)
    df["OT Amt"]       = (fs / md / 12.0 * df["OT Hours"].astype(float)).round(0)
    return _recompute(df)


# ── Tab 1: Payroll Calculator ─────────────────────────────────────────────────

def _tab_calculator(sb: SupabaseClient, operators: list) -> None:
    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    today = date.today()

    # ── Period selector ────────────────────────────────────────────────────────
    with st.container(border=True):
        c1, c2, c3, _, c4 = st.columns([1.5, 1.5, 1.5, 3, 1.5])
        year  = c1.number_input("Year", min_value=2020, max_value=2035,
                                 value=today.year, step=1, key="ps_year")
        month = c2.selectbox("Month", list(range(1, 13)),
                              format_func=_month_label, index=today.month - 1, key="ps_month")
        default_md  = _calc_month_days(int(year), int(month))
        month_days  = c3.number_input("Month Days", min_value=1, max_value=31,
                                       value=default_md, step=1, key="ps_mdays",
                                       help="Mon-Sat working days. Reduce for public holidays.")
        load_btn = c4.button("Load / Refresh", key="ps_load",
                              use_container_width=True, type="primary")

    payroll_month = f"{int(year)}-{int(month):02d}"
    _, last_day   = calendar.monthrange(int(year), int(month))
    period_start  = date(int(year), int(month), 1)
    period_end    = date(int(year), int(month), last_day)
    cache_key     = f"ps_data_{payroll_month}"

    # ── Load data ──────────────────────────────────────────────────────────────
    if load_btn or cache_key not in st.session_state:
        with st.spinner(f"Loading {_month_label(int(month))} {int(year)} payroll data…"):
            try:
                wls = sb.list_all_worklogs()
                wos = sb.list_work_orders()
            except Exception:
                wls, wos = [], []

            op_by_code = {(o.get("emp_code") or "").upper(): o for o in operators if o.get("emp_code")}
            op_by_name = {(o.get("operator_name") or "").lower(): o for o in operators}
            op_by_id   = {o["id"]: o for o in operators if o.get("id")}

            wl_agg = _build_worklog_agg(wls, wos, op_by_code, op_by_name, period_start, period_end)

            # Payroll data for this month
            def _safe(fn, **kw):
                try:
                    return fn(**kw)
                except Exception:
                    return []

            pf_recs    = _safe(sb.list_payroll_pf,                payroll_month=payroll_month)
            cust_recs  = _safe(sb.list_payroll_customer_payments,  payroll_month=payroll_month)
            adv_recs   = _safe(sb.list_advance_recoveries,         payroll_month=payroll_month)
            add_recs   = _safe(sb.list_payroll_additions,          payroll_month=payroll_month, status="Approved")
            ded_recs   = _safe(sb.list_payroll_deductions,         payroll_month=payroll_month, status="Approved")
            openings   = _safe(sb.list_advance_opening_balances)
            adv_paid   = _safe(sb.list_advance_payments,           payment_status="Paid")
            all_recs   = _safe(sb.list_advance_recoveries)

            # Aggregate by employee_id (UUID)
            def _sum_field(records, field):
                out = defaultdict(float)
                for r in records:
                    out[r.get("employee_id", "")] += float(r.get(field) or 0)
                return out

            pf_by_emp      = _sum_field(pf_recs,   "amount_to_deduct")
            cust_by_emp    = _sum_field(cust_recs,  "salary_deduct_from_payroll")
            adv_rec_by_emp = _sum_field(adv_recs,   "final_recovery")
            add_by_emp     = _sum_field(add_recs,   "amount")
            ded_by_emp     = _sum_field(ded_recs,   "amount")

            # Advance balance as of month start (exclude current month recoveries)
            open_by = defaultdict(float)
            for r in openings:
                if r.get("as_on_date") and str(r["as_on_date"]) < str(period_start):
                    open_by[r["employee_id"]] += float(r.get("balance") or 0)
            paid_by = defaultdict(float)
            for p in adv_paid:
                if p.get("payment_date") and str(p["payment_date"]) < str(period_start):
                    paid_by[p["employee_id"]] += float(p.get("amount") or 0)
            rec_by = defaultdict(float)
            for r in all_recs:
                d = str(r.get("processed_at") or "")[:10]
                if d and d < str(period_start):
                    rec_by[r["employee_id"]] += float(r.get("final_recovery") or 0)
            adv_bal = {eid: open_by[eid] + paid_by[eid] - rec_by[eid] for eid in op_by_id}

            # Build one row per active operator
            active_ops = [o for o in operators if o.get("status") == "Active" and o.get("id")]
            rows = []
            for op in sorted(active_ops, key=lambda o: o.get("emp_code") or ""):
                eid = op["id"]
                wl  = wl_agg.get(eid, {})
                rows.append({
                    "_emp_id":           eid,
                    "Emp Code":          op.get("emp_code", ""),
                    "Operator":          op.get("operator_name", ""),
                    "Fixed Salary":      float(op.get("fixed_salary") or 0),
                    "Avail Days":        _available_days(op.get("joining_date"), period_start, period_end),
                    "Working Days":      wl.get("working_days", 0),
                    "OT Hours":          wl.get("ot_hours", 0.0),
                    "Name in Passbook":  op.get("name_in_passbook", ""),
                    "IFSC":              op.get("ifsc_code", ""),
                    "Account No.":       op.get("bank_account_number", ""),
                    "Month Days":        int(month_days),
                    "No. of Days Worked": 0,
                    "Earned Basic":      0.0,
                    "OT Amt":            0.0,
                    "Additions":         round(add_by_emp.get(eid, 0.0), 0),
                    "Total Amt":         0.0,
                    "Sal Paid Other":    round(cust_by_emp.get(eid, 0.0), 0),
                    "Current Advance":   round(adv_bal.get(eid, 0.0), 0),
                    "Advance Deduction": round(adv_rec_by_emp.get(eid, 0.0), 0),
                    "PF Amt":            round(pf_by_emp.get(eid, 0.0), 0),
                    "Other Deductions":  round(ded_by_emp.get(eid, 0.0), 0),
                    "Deduction Total":   0.0,
                    "Net Payable":       0.0,
                    "Remarks":           "",
                })

            df = pd.DataFrame(rows) if rows else pd.DataFrame()
            if not df.empty:
                df = _initial_fill(df)   # formula-fill Earned Basic & OT Amt, then summarise
            st.session_state[cache_key] = df

    df: pd.DataFrame = st.session_state.get(cache_key, pd.DataFrame())

    if df.empty:
        st.info(
            f"No active operators found for {_month_label(int(month))} {int(year)}. "
            "Click **Load / Refresh** to fetch data."
        )
        return

    # Sync Month Days if user changes slider without reloading
    if int(month_days) != int(df["Month Days"].iloc[0]):
        df["Month Days"] = int(month_days)
        df = _recompute(df)
        st.session_state[cache_key] = df

    # ── KPIs ───────────────────────────────────────────────────────────────────
    n_ops     = len(df)
    net_total = df["Net Payable"].sum()
    earn_tot  = df["Earned Basic"].sum()
    ded_tot   = df["Deduction Total"].sum()
    adv_tot   = df["Advance Deduction"].sum()
    pf_tot    = df["PF Amt"].sum()

    st.markdown(
        "<div class='ps-kpi-grid'>"
        + _kpi("engineering",      "Operators",         n_ops,                   "active this month",    "#2563EB")
        + _kpi("payments",         "Net Payable",       f"₹{net_total:,.0f}",    "to be paid out",       "#10B981")
        + _kpi("account_balance",  "Earned Basic",      f"₹{earn_tot:,.0f}",     "gross earned",         "#E87722")
        + _kpi("remove_circle",    "Total Deductions",  f"₹{ded_tot:,.0f}",      "all deductions",       "#EF4444")
        + _kpi("currency_rupee",   "Advance Recovery",  f"₹{adv_tot:,.0f}",      "recovered this month", "#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='ps-info-note'>"
        "✏️ <strong>All numeric columns are editable.</strong> "
        "Earned Basic and OT Amt are pre-filled from formula on load and can be overridden.<br>"
        "🔄 <strong>Auto-calculated on every edit:</strong> "
        "Total Amt = Earned + OT &nbsp;·&nbsp; "
        "Deduction Total = Sal by Cust + Advance + PF &nbsp;·&nbsp; "
        "Net Payable = Total − Deductions"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Editor ─────────────────────────────────────────────────────────────────
    # Text identity columns stay read-only; No. of Days Worked, Total Amt,
    # Deduction Total, Net Payable are always auto-calculated.
    # Every OTHER column (all numeric) is editable.
    always_readonly = {
        "Emp Code", "Operator", "Name in Passbook", "IFSC", "Account No.",
        "No. of Days Worked", "Total Amt", "Deduction Total", "Net Payable",
    }
    display_cols  = [c for c in df.columns if c != "_emp_id"]
    readonly_cols = [c for c in display_cols if c in always_readonly]

    col_cfg: dict = {
        "Emp Code":          st.column_config.TextColumn("Emp Code",          width="small"),
        "Operator":          st.column_config.TextColumn("Operator",          width="medium"),
        "Fixed Salary":      st.column_config.NumberColumn("Fixed Sal",       format="₹%,.0f", width="small",   min_value=0),
        "Avail Days":        st.column_config.NumberColumn("Avail Days",      width="small",   min_value=0),
        "Working Days":      st.column_config.NumberColumn("Work Days",       width="small",   min_value=0, max_value=366,
                              help="Auto-filled from worklog. Edit to override."),
        "OT Hours":          st.column_config.NumberColumn("OT Hrs",          format="%.2f",   width="small",   min_value=0.0,
                              help="Auto-filled from worklog. Edit to override."),
        "Name in Passbook":  st.column_config.TextColumn("Passbook Name",     width="medium"),
        "IFSC":              st.column_config.TextColumn("IFSC",              width="small"),
        "Account No.":       st.column_config.TextColumn("Account No.",       width="medium"),
        "Month Days":        st.column_config.NumberColumn("Month Days",      width="small",   min_value=1, max_value=31),
        "No. of Days Worked":st.column_config.NumberColumn("Days Worked",     width="small"),
        "Earned Basic":      st.column_config.NumberColumn("Earned Basic",    format="₹%,.0f", width="small",   min_value=0,
                              help="Pre-filled from formula. Edit to override."),
        "OT Amt":            st.column_config.NumberColumn("OT Amt",          format="₹%,.0f", width="small",   min_value=0,
                              help="Pre-filled from formula. Edit to override."),
        "Additions":         st.column_config.NumberColumn("Additions",       format="₹%,.0f", width="small",   min_value=0),
        "Total Amt":         st.column_config.NumberColumn("Total Amt",       format="₹%,.0f", width="small"),
        "Sal Paid Other":    st.column_config.NumberColumn("Sal by Cust",     format="₹%,.0f", width="small",   min_value=0,
                              help="Salary paid directly by customer."),
        "Current Advance":   st.column_config.NumberColumn("Curr Adv",        format="₹%,.0f", width="small",   min_value=0),
        "Advance Deduction": st.column_config.NumberColumn("Adv Deduct",      format="₹%,.0f", width="small",   min_value=0,
                              help="Advance recovery for this payroll month."),
        "PF Amt":            st.column_config.NumberColumn("PF Amt",          format="₹%,.0f", width="small",   min_value=0),
        "Other Deductions":  st.column_config.NumberColumn("Other Ded",       format="₹%,.0f", width="small",   min_value=0),
        "Deduction Total":   st.column_config.NumberColumn("Ded Total",       format="₹%,.0f", width="small"),
        "Net Payable":       st.column_config.NumberColumn("Net Payable",     format="₹%,.0f", width="small"),
        "Remarks":           st.column_config.TextColumn("Remarks",           width="medium"),
    }

    edited = st.data_editor(
        df[display_cols],
        key=f"ps_editor_{payroll_month}",
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        disabled=readonly_cols,
        num_rows="fixed",
    )

    # Merge all edited columns back (everything except the auto-calculated ones)
    editable_cols = [c for c in display_cols if c not in always_readonly]
    for col in editable_cols:
        if col in edited.columns:
            df[col] = edited[col].values
    # Always recalculate summary columns
    df = _recompute(df)
    st.session_state[cache_key] = df

    # ── Totals bar ─────────────────────────────────────────────────────────────
    sum_cols = ["Earned Basic", "OT Amt", "Additions", "Total Amt",
                "Sal Paid Other", "Advance Deduction", "PF Amt",
                "Other Deductions", "Deduction Total", "Net Payable"]
    totals = {c: df[c].sum() for c in sum_cols if c in df.columns}
    highlight = ["Earned Basic", "Total Amt", "Deduction Total", "Net Payable"]
    parts = [f"<strong>{c}:</strong> ₹{totals[c]:,.0f}" for c in highlight if c in totals]
    st.markdown(
        f"<div class='ps-total-bar'>Totals — {' &nbsp;·&nbsp; '.join(parts)}</div>",
        unsafe_allow_html=True,
    )

    # ── Export ─────────────────────────────────────────────────────────────────
    e1, e2, _ = st.columns([1.5, 1.5, 5])
    try:
        import io
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df[display_cols].to_excel(w, index=False, sheet_name="Payroll Summary")
        e1.download_button(
            "Export Excel",
            data=buf.getvalue(),
            file_name=f"payroll_{payroll_month}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ps_export_xlsx",
            use_container_width=True,
        )
    except Exception:
        pass

    try:
        csv_buf = df[display_cols].to_csv(index=False).encode("utf-8")
        e2.download_button(
            "Export CSV",
            data=csv_buf,
            file_name=f"payroll_{payroll_month}.csv",
            mime="text/csv",
            key="ps_export_csv",
            use_container_width=True,
        )
    except Exception:
        pass


# ── Tab 2: Bank Transfer List ─────────────────────────────────────────────────

def _tab_bank_list() -> None:
    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    cache_keys = sorted(
        [k for k in st.session_state if k.startswith("ps_data_")],
        reverse=True,
    )
    if not cache_keys:
        st.info("Load a payroll month from the **Payroll Calculator** tab first.")
        return

    month_opts = [k.replace("ps_data_", "") for k in cache_keys]
    sel = st.selectbox("Payroll Month", month_opts, key="bank_month_sel")
    df: pd.DataFrame = st.session_state.get(f"ps_data_{sel}", pd.DataFrame())

    if df.empty:
        st.info("No data for selected month.")
        return

    bank_cols = ["Emp Code", "Operator", "Name in Passbook", "Account No.", "IFSC",
                 "Net Payable", "Remarks"]
    bank_df = df[[c for c in bank_cols if c in df.columns]].copy()
    bank_df = bank_df[bank_df["Net Payable"] > 0].reset_index(drop=True)

    st.markdown(
        f"<div class='ps-info-note'>"
        f"<strong>{len(bank_df)} operators</strong> with Net Payable > 0 &nbsp;·&nbsp; "
        f"<strong>Total: ₹{bank_df['Net Payable'].sum():,.0f}</strong>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.dataframe(
        bank_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Emp Code":        st.column_config.TextColumn("Emp Code",    width="small"),
            "Operator":        st.column_config.TextColumn("Name",        width="medium"),
            "Name in Passbook":st.column_config.TextColumn("Passbook",    width="medium"),
            "Account No.":     st.column_config.TextColumn("Account No.", width="medium"),
            "IFSC":            st.column_config.TextColumn("IFSC",        width="small"),
            "Net Payable":     st.column_config.NumberColumn("Net Payable",format="₹%,.0f"),
            "Remarks":         st.column_config.TextColumn("Remarks",     width="medium"),
        },
    )

    try:
        import io
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            bank_df.to_excel(w, index=False, sheet_name="Bank Transfer")
        st.download_button(
            "Export Bank Transfer List",
            data=buf.getvalue(),
            file_name=f"bank_transfer_{sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="bank_export_xlsx",
        )
    except Exception:
        pass


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        "text-transform:uppercase;color:#6B7280;margin-bottom:4px;'>// Payroll</div>"
        "<div style='font-size:26px;font-weight:900;color:#111827;"
        "letter-spacing:-.5px;margin-bottom:20px;'>Payment Summary</div>",
        unsafe_allow_html=True,
    )

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase connection failed.")
        st.write(str(exc))
        return

    try:
        operators = sb.list_operators()
    except Exception:
        operators = []

    tab1, tab2 = st.tabs(["Payroll Calculator", "Bank Transfer List"])
    with tab1:
        _tab_calculator(sb, operators)
    with tab2:
        _tab_bank_list()
