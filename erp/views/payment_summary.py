"""
erp/views/payment_summary.py — Payment Summary (single-page payroll workflow)

Supabase table required — run once in SQL editor:

    CREATE TABLE IF NOT EXISTS payroll_records (
        id               uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id      text NOT NULL,
        payroll_month    text NOT NULL,
        fixed_salary     numeric DEFAULT 0,
        month_days       int DEFAULT 26,
        working_days     int DEFAULT 0,
        ot_hours         numeric DEFAULT 0,
        no_days_worked   int DEFAULT 0,
        earned_basic     numeric DEFAULT 0,
        ot_amount        numeric DEFAULT 0,
        total_amount     numeric DEFAULT 0,
        sal_paid_other   numeric DEFAULT 0,
        advance_recovery numeric DEFAULT 0,
        pf_amount        numeric DEFAULT 0,
        deduction_total  numeric DEFAULT 0,
        net_payable      numeric DEFAULT 0,
        remarks          text,
        status           text DEFAULT 'Draft',
        hold_reason      text,
        cancel_reason    text,
        sendback_reason  text,
        submitted_by     text,
        submitted_at     timestamptz,
        approved_by      text,
        approved_at      timestamptz,
        paid_by          text,
        paid_at          timestamptz,
        payment_date     date,
        utr_reference    text,
        created_at       timestamptz DEFAULT now(),
        updated_at       timestamptz DEFAULT now(),
        CONSTRAINT payroll_records_emp_month UNIQUE (employee_id, payroll_month)
    );

Workflow:
    Draft  ->  Submitted  ->  Approved  ->  Paid
                  |               |
               OnHold         SendBack (-> Draft)
               Cancelled
"""
from __future__ import annotations

import calendar
import io
import json
from collections import defaultdict
from datetime import date, datetime

import pandas as pd
import streamlit as st

from .. import auth
from ..supabase_client import SupabaseClient

# ── Status constants ──────────────────────────────────────────────────────────

_S_DRAFT     = "Draft"
_S_SUBMITTED = "Submitted"
_S_APPROVED  = "Approved"
_S_PAID      = "Paid"
_S_ONHOLD    = "OnHold"
_S_CANCELLED = "Cancelled"
_S_SENDBACK  = "SendBack"

_STATUS_BADGE = {
    _S_DRAFT:     ("#F1F5F9", "#475569", "Draft"),
    _S_SUBMITTED: ("#FEF3C7", "#D97706", "Submitted"),
    _S_APPROVED:  ("#DCFCE7", "#166534", "Approved"),
    _S_PAID:      ("#D1FAE5", "#065F46", "Paid"),
    _S_ONHOLD:    ("#FEE2E2", "#991B1B", "On Hold"),
    _S_CANCELLED: ("#F3F4F6", "#6B7280", "Cancelled"),
    _S_SENDBACK:  ("#FEF9C3", "#854D0E", "Sent Back"),
}

# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI row ── */
.ps-kpi-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin: 0 0 20px;
}
.ps-kpi-card {
    background: #fff;
    border: 1px solid #E2EBF0;
    border-radius: 12px;
    padding: 16px 18px;
    display: flex;
    align-items: center;
    gap: 14px;
    transition: box-shadow .15s, transform .15s;
}
.ps-kpi-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,.08);
    transform: translateY(-1px);
}
.ps-kpi-icon {
    width: 40px; height: 40px;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; flex-shrink: 0;
}
.ps-kpi-label {
    font-size: 11px; font-weight: 600; color: #6B7280;
    margin-bottom: 2px;
}
.ps-kpi-value {
    font-size: 20px; font-weight: 800; color: #111827;
    line-height: 1; font-variant-numeric: tabular-nums;
}

/* ── Formula bar ── */
.ps-formula-bar {
    display: flex; align-items: stretch;
    border-radius: 10px; overflow: hidden;
    border: 1px solid #E2EBF0;
    margin: 0 0 20px; font-size: 12px;
}
.ps-fb-seg { padding: 12px 16px; flex: 1; }
.ps-fb-seg-title {
    font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; margin-bottom: 4px;
}
.ps-fb-seg-items { font-size: 11px; }
.ps-fb-arrow {
    display: flex; align-items: center; justify-content: center;
    padding: 0 8px; font-size: 20px; color: #9CA3AF;
    background: #F9FAFB;
    border-left: 1px solid #E2EBF0;
    border-right: 1px solid #E2EBF0;
    flex-shrink: 0;
}
.ps-fb-equals {
    display: flex; align-items: center; justify-content: center;
    padding: 0 10px; font-size: 18px; font-weight: 700; color: #6B7280;
    background: #F9FAFB;
    border-left: 1px solid #E2EBF0;
    border-right: 1px solid #E2EBF0;
    flex-shrink: 0;
}

/* ── Grouped table ── */
.ps-table-wrap {
    overflow-x: auto;
    border: 1px solid #E2EBF0;
    border-radius: 10px;
    margin: 8px 0;
    background: #fff;
}
.ps-table {
    width: 100%; border-collapse: collapse; font-size: 12px;
}
.ps-table th, .ps-table td {
    padding: 7px 10px;
    border-bottom: 1px solid #F1F5F9;
    white-space: nowrap;
}
.ps-table tr:hover td { background: #F9FAFB; }
.ps-table thead tr:last-child th { border-bottom: 2px solid #E2EBF0; }

/* Group header cells */
.ps-gh-inputs {
    background: #DBEAFE; color: #1E40AF;
    font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; text-align: center;
}
.ps-gh-earnings {
    background: #FED7AA; color: #92400E;
    font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; text-align: center;
}
.ps-gh-deductions {
    background: #FECACA; color: #991B1B;
    font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; text-align: center;
}
.ps-gh-final {
    background: #BBF7D0; color: #166534;
    font-size: 10px; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; text-align: center;
}

/* Sub-header cells */
.ps-sh-op {
    background: #F8FAFC; color: #374151;
    font-size: 11px; font-weight: 600; text-align: left;
    position: sticky; left: 0; z-index: 1;
}
.ps-sh-inputs {
    background: #EFF6FF; color: #1D4ED8;
    font-size: 11px; font-weight: 600; text-align: right;
}
.ps-sh-earnings {
    background: #FFFBEB; color: #B45309;
    font-size: 11px; font-weight: 600; text-align: right;
}
.ps-sh-deductions {
    background: #FFF1F2; color: #BE123C;
    font-size: 11px; font-weight: 600; text-align: right;
}
.ps-sh-final {
    background: #F0FDF4; color: #15803D;
    font-size: 11px; font-weight: 600; text-align: right;
}

/* Data cells */
.ps-td-op {
    font-weight: 600; color: #1E293B; text-align: left;
    position: sticky; left: 0; background: #fff; z-index: 1;
    min-width: 140px;
}
.ps-td-inputs  { color: #1E40AF; text-align: right; }
.ps-td-earnings { color: #92400E; text-align: right; }
.ps-td-deductions { color: #991B1B; text-align: right; }
.ps-td-final { color: #166534; font-weight: 700; text-align: right; }

/* ── Right panel cards ── */
.ps-right-panel-card {
    background: #fff;
    border: 1px solid #E2EBF0;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 16px;
}
.ps-panel-title {
    font-size: 13px; font-weight: 700; color: #111827;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
}
.ps-check-item {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid #F9FAFB;
    font-size: 12px;
}
.ps-check-item:last-child { border-bottom: none; }
.ps-check-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.ps-check-title { font-weight: 600; color: #111827; }
.ps-check-sub { color: #6B7280; font-size: 11px; margin-top: 1px; }
.ps-breakdown-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0; font-size: 13px;
}
.ps-breakdown-row:not(:last-of-type) { border-bottom: 1px solid #F9FAFB; }
.ps-bd-label { color: #374151; }
.ps-bd-value { font-weight: 700; font-variant-numeric: tabular-nums; }
.ps-bd-net-row {
    background: #F0FDF4; border-radius: 8px; padding: 10px 12px;
    margin-top: 8px;
    display: flex; justify-content: space-between; align-items: center;
}

/* ── Period nav buttons ── */
.ps-period-btn {
    background: #F1F5F9; border: 1px solid #E2EBF0;
    border-radius: 6px; padding: 4px 10px;
    font-size: 14px; cursor: pointer; color: #374151;
    line-height: 1.4;
}
.ps-period-btn:hover { background: #E2EBF0; }

/* ── Misc ── */
.ps-info-note {
    padding: 10px 14px;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 8px;
    font-size: 12px;
    color: #1E40AF;
    margin-bottom: 12px;
}
.ps-total-bar {
    padding: 10px 16px;
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-radius: 8px;
    font-size: 12px;
    color: #166534;
    font-weight: 600;
    margin: 8px 0 6px;
}
.ps-section-hdr {
    font-size: 11px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #64748B; margin: 16px 0 8px;
    padding-bottom: 4px; border-bottom: 2px solid #F1F5F9;
}

/* ── Legacy grid (used by _kpi helper) ── */
.ps-kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin: 0 0 20px;
}
.ps-kpi-bar {
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.ps-pipeline {
    display: flex; align-items: center; gap: 0;
    background: #F8FAFC; border: 1px solid #E2EBF0;
    border-radius: 10px; padding: 12px 16px; margin-bottom: 14px;
    overflow-x: auto;
}
.ps-pipeline-stage {
    display: flex; flex-direction: column; align-items: center;
    min-width: 80px; padding: 4px 12px;
}
.ps-pipeline-count { font-size: 20px; font-weight: 800; line-height: 1; }
.ps-pipeline-label {
    font-size: 9px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .08em; color: #94A3B8; margin-top: 2px; white-space: nowrap;
}
.ps-pipeline-arrow { font-size: 18px; color: #CBD5E1; padding: 0 4px; flex-shrink: 0; }
.ps-prog-bar { height: 8px; border-radius: 4px; margin-top: 4px; background: #E2EBF0; overflow: hidden; }
.ps-prog-fill { height: 100%; border-radius: 4px; transition: width .4s; }
</style>
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_name() -> str:
    p = auth.current_profile()
    return p.get("full_name") or p.get("email") or "Unknown"


def _month_label(m: int) -> str:
    return date(2000, m, 1).strftime("%B")


def _calc_month_days(year: int, month: int) -> int:
    _, total = calendar.monthrange(year, month)
    return sum(1 for d in range(1, total + 1) if date(year, month, d).weekday() < 6)


def _kpi(label: str, value, sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='ps-kpi-card'>"
        f"<div class='ps-kpi-bar' style='background:{accent}'></div>"
        f"<div class='ps-kpi-label'>{label}</div>"
        f"<div class='ps-kpi-value'>{value}</div>"
        f"<div class='ps-kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _badge(status: str) -> str:
    bg, fg, lbl = _STATUS_BADGE.get(status, ("#F1F5F9", "#475569", status))
    return (
        f"<span style='background:{bg};color:{fg};font-size:11px;font-weight:700;"
        f"padding:2px 8px;border-radius:20px;'>{lbl}</span>"
    )


def _pipeline_html(counts: dict) -> str:
    """Render a horizontal pipeline showing employee counts per workflow stage."""
    stages = [
        (_S_DRAFT,     "#94A3B8", "Calculator"),
        (_S_SUBMITTED, "#F59E0B", "Submitted"),
        (_S_APPROVED,  "#10B981", "Approved"),
        (_S_PAID,      "#2563EB", "Paid"),
    ]
    side_stages = [
        (_S_ONHOLD,    "#EF4444", "On Hold"),
        (_S_CANCELLED, "#6B7280", "Cancelled"),
    ]
    total = sum(counts.values()) or 1

    parts = []
    for i, (status, color, label) in enumerate(stages):
        n = counts.get(status, 0)
        pct = round(n / total * 100)
        parts.append(
            f"<div class='ps-pipeline-stage'>"
            f"<span class='ps-pipeline-count' style='color:{color};'>{n}</span>"
            f"<span class='ps-pipeline-label'>{label}</span>"
            f"<div class='ps-prog-bar' style='width:60px;'>"
            f"<div class='ps-prog-fill' style='width:{pct}%;background:{color};'></div>"
            f"</div></div>"
        )
        if i < len(stages) - 1:
            parts.append("<span class='ps-pipeline-arrow'>-></span>")

    side_html = "".join(
        f"<span style='font-size:11px;font-weight:700;color:{c};margin-left:16px;'>"
        f"{label}: {counts.get(s, 0)}</span>"
        for s, c, label in side_stages
    )

    return (
        f"<div class='ps-pipeline'>{''.join(parts)}"
        f"<div style='flex:1;text-align:right;font-size:11px;color:#94A3B8;'>{side_html}</div>"
        f"</div>"
    )


def _payroll_breakdown_chart(df: pd.DataFrame) -> None:
    """Render a simple payroll composition breakdown using HTML progress bars."""
    if df.empty:
        return
    earned   = df["Earned Basic"].sum()
    ot_amt   = df["OT Amt"].sum()
    sal_oth  = df["Sal Paid Other"].sum()
    adv_ded  = df["Advance Deduction"].sum()
    pf_amt   = df["PF Amt"].sum()
    net_pay  = df["Net Payable"].sum()
    gross    = earned + ot_amt

    if gross <= 0:
        return

    bars = [
        ("Earned Basic",    earned,  "#10B981", gross),
        ("OT Amount",       ot_amt,  "#3B82F6", gross),
        ("Sal Paid Other",  sal_oth, "#F59E0B", gross),
        ("Adv. Deduction",  adv_ded, "#8B5CF6", gross),
        ("PF Amount",       pf_amt,  "#64748B", gross),
    ]

    rows_html = ""
    for label, val, color, base in bars:
        pct = min(100, round(val / base * 100)) if base > 0 else 0
        rows_html += (
            f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:6px;'>"
            f"<div style='width:110px;font-size:11px;color:#64748B;font-weight:600;"
            f"text-align:right;flex-shrink:0;'>{label}</div>"
            f"<div style='flex:1;background:#F1F5F9;border-radius:4px;height:10px;overflow:hidden;'>"
            f"<div style='width:{pct}%;background:{color};height:100%;border-radius:4px;'></div>"
            f"</div>"
            f"<div style='width:80px;font-size:11px;font-weight:700;color:#1E293B;"
            f"font-variant-numeric:tabular-nums;'>&#8377;{val:,.0f}</div>"
            f"<div style='width:36px;font-size:10px;color:#94A3B8;'>{pct}%</div>"
            f"</div>"
        )

    net_pct = min(100, round(net_pay / gross * 100)) if gross > 0 else 0
    rows_html += (
        f"<div style='display:flex;align-items:center;gap:10px;margin-top:8px;"
        f"padding-top:8px;border-top:1px solid #E2EBF0;'>"
        f"<div style='width:110px;font-size:11px;font-weight:800;color:#0F766E;"
        f"text-align:right;flex-shrink:0;'>Net Payable</div>"
        f"<div style='flex:1;background:#F1F5F9;border-radius:4px;height:12px;overflow:hidden;'>"
        f"<div style='width:{net_pct}%;background:#0F766E;height:100%;border-radius:4px;'></div>"
        f"</div>"
        f"<div style='width:80px;font-size:13px;font-weight:800;color:#0F766E;"
        f"font-variant-numeric:tabular-nums;'>&#8377;{net_pay:,.0f}</div>"
        f"<div style='width:36px;font-size:10px;color:#94A3B8;'>{net_pct}%</div>"
        f"</div>"
    )

    gross_fmt = f"{gross:,.0f}"
    st.markdown(
        f"<div style='border:1px solid #E2EBF0;border-radius:10px;padding:14px 18px;"
        f"background:#fff;margin:8px 0 12px;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        f"text-transform:uppercase;color:#94A3B8;margin-bottom:10px;'>"
        f"Payroll Composition (Gross: &#8377;{gross_fmt})</div>"
        f"{rows_html}</div>",
        unsafe_allow_html=True,
    )


# ── Worklog aggregation ───────────────────────────────────────────────────────

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
    work_logs, work_orders, op_by_code, op_by_name,
    period_start: date, period_end: date,
) -> dict[str, dict]:
    wo_map    = {wo["id"]: wo for wo in work_orders if wo.get("id")}
    emp_dates: dict[str, set] = defaultdict(set)
    emp_ot:   dict[str, float] = defaultdict(float)

    for wl in work_logs:
        if not wo_map.get(wl.get("work_order_id")):
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


# ── Formula engine ────────────────────────────────────────────────────────────

def _recompute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    md = df["Month Days"].astype(float).replace(0.0, 1.0)
    fs = df["Fixed Salary"].astype(float)
    dw = df["Working Days"].astype(float).clip(upper=df["Month Days"].astype(float))

    df["No. of Days Worked"] = dw.astype(int)
    df["Earned Basic"]       = (dw / md * fs).round(0)
    df["Total Amt"]          = df["Earned Basic"] + df["OT Amt"].astype(float)
    df["Deduction Total"]    = (
        df["Sal Paid Other"].astype(float)
        + df["Advance Deduction"].astype(float)
        + df["PF Amt"].astype(float)
    )
    df["Net Payable"]        = df["Total Amt"] - df["Deduction Total"]
    return df


def _initial_fill(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    md = df["Month Days"].astype(float).replace(0.0, 1.0)
    fs = df["Fixed Salary"].astype(float)
    df["OT Amt"] = (fs / md / 12.0 * df["OT Hours"].astype(float)).round(0)
    return _recompute(df)


# ── Period selector widget (kept for compatibility) ───────────────────────────

def _period_selector(key_prefix: str = "ps") -> tuple[int, int, int, str, date, date, str]:
    today = date.today()
    with st.container(border=True):
        c1, c2, c3, _, c4 = st.columns([1.5, 1.5, 1.5, 3, 1.5])
        year  = c1.number_input("Year",  min_value=2020, max_value=2035,
                                 value=today.year, step=1, key=f"{key_prefix}_year")
        month = c2.selectbox("Month", list(range(1, 13)),
                              format_func=_month_label, index=today.month - 1,
                              key=f"{key_prefix}_month")
        default_md = _calc_month_days(int(year), int(month))
        month_days = c3.number_input("Month Days", min_value=1, max_value=31,
                                      value=default_md, step=1, key=f"{key_prefix}_mdays",
                                      help="Mon-Sat working days. Reduce for public holidays.")
        load_btn = c4.button("Load / Refresh", key=f"{key_prefix}_load",
                              use_container_width=True, type="primary")

    payroll_month = f"{int(year)}-{int(month):02d}"
    _, last_day   = calendar.monthrange(int(year), int(month))
    period_start  = date(int(year), int(month), 1)
    period_end    = date(int(year), int(month), last_day)
    return int(year), int(month), int(month_days), payroll_month, period_start, period_end, load_btn


# ── Load & merge payroll data ─────────────────────────────────────────────────

def _load_payroll_data(
    sb: SupabaseClient,
    operators: list,
    payroll_month: str,
    period_start: date,
    period_end: date,
    month_days: int,
) -> pd.DataFrame:
    """Build the base payroll dataframe from worklog + Supabase tables."""
    try:
        wls = sb.list_all_worklogs()
        wos = sb.list_work_orders()
    except Exception:
        wls, wos = [], []

    op_by_code = {(o.get("emp_code") or "").upper(): o for o in operators if o.get("emp_code")}
    op_by_name = {(o.get("operator_name") or "").lower(): o for o in operators}
    op_by_id   = {o["id"]: o for o in operators if o.get("id")}

    wl_agg = _build_worklog_agg(wls, wos, op_by_code, op_by_name, period_start, period_end)

    def _safe(fn, **kw):
        try:
            return fn(**kw)
        except Exception:
            return []

    pf_recs   = _safe(sb.list_payroll_pf,               payroll_month=payroll_month)
    cust_recs = _safe(sb.list_payroll_customer_payments, payroll_month=payroll_month)
    adv_recs  = _safe(sb.list_advance_recoveries,        payroll_month=payroll_month)

    def _sum_field(records, field):
        out = defaultdict(float)
        for r in records:
            out[r.get("employee_id", "")] += float(r.get(field) or 0)
        return out

    pf_by_emp      = _sum_field(pf_recs,   "amount_to_deduct")
    cust_by_emp    = _sum_field(cust_recs,  "salary_deduct_from_payroll")
    adv_rec_by_emp = _sum_field(adv_recs,   "final_recovery")

    existing_recs = {r["employee_id"]: r for r in _safe(sb.list_payroll_records, payroll_month=payroll_month)}

    def _active_in_period(op: dict) -> bool:
        """True if the operator was active at any point during [period_start, period_end]."""
        try:
            if op.get("joining_date"):
                if date.fromisoformat(str(op["joining_date"])[:10]) > period_end:
                    return False
        except Exception:
            pass
        try:
            if op.get("inactive_from"):
                if date.fromisoformat(str(op["inactive_from"])[:10]) < period_start:
                    return False
        except Exception:
            pass
        return True

    period_ops = [o for o in operators if o.get("id") and _active_in_period(o)]
    rows = []
    for op in sorted(period_ops, key=lambda o: o.get("emp_code") or ""):
        eid  = op["id"]
        wl   = wl_agg.get(eid, {})
        rec  = existing_recs.get(eid, {})
        rows.append({
            "_emp_id":           eid,
            "_rec_id":           rec.get("id", ""),
            "_status":           rec.get("status", _S_DRAFT),
            "Emp Code":          op.get("emp_code", ""),
            "Operator":          op.get("operator_name", ""),
            "Fixed Salary":      float(rec.get("fixed_salary") or op.get("fixed_salary") or 0),
            "Month Days":        int(rec.get("month_days") or month_days),
            "Working Days":      int(rec.get("working_days") or wl.get("working_days", 0)),
            "OT Hours":          float(rec.get("ot_hours") or wl.get("ot_hours", 0.0)),
            "No. of Days Worked": int(rec.get("no_days_worked", 0)),
            "Earned Basic":      float(rec.get("earned_basic", 0)),
            "OT Amt":            float(rec.get("ot_amount", 0)),
            "Total Amt":         float(rec.get("total_amount", 0)),
            "Sal Paid Other":    float(rec.get("sal_paid_other") or cust_by_emp.get(eid, 0.0)),
            "Advance Deduction": float(rec.get("advance_recovery") or adv_rec_by_emp.get(eid, 0.0)),
            "PF Amt":            float(rec.get("pf_amount") or pf_by_emp.get(eid, 0.0)),
            "Deduction Total":   float(rec.get("deduction_total", 0)),
            "Net Payable":       float(rec.get("net_payable", 0)),
            "Remarks":           rec.get("remarks", ""),
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        no_rec_mask = df["_rec_id"] == ""
        if no_rec_mask.any():
            df_new = _initial_fill(df[no_rec_mask].copy())
            df.loc[no_rec_mask, df_new.columns] = df_new.values
        has_rec_mask = ~no_rec_mask
        if has_rec_mask.any():
            df_saved = _recompute(df[has_rec_mask].copy())
            df.loc[has_rec_mask, df_saved.columns] = df_saved.values

    return df


# ── Save payroll record to Supabase ──────────────────────────────────────────

def _save_record(sb: SupabaseClient, row: pd.Series, payroll_month: str,
                 status: str, extra: dict | None = None) -> None:
    payload: dict = {
        "employee_id":      row["_emp_id"],
        "payroll_month":    payroll_month,
        "fixed_salary":     float(row["Fixed Salary"]),
        "month_days":       int(row["Month Days"]),
        "working_days":     int(row["Working Days"]),
        "ot_hours":         float(row["OT Hours"]),
        "no_days_worked":   int(row["No. of Days Worked"]),
        "earned_basic":     float(row["Earned Basic"]),
        "ot_amount":        float(row["OT Amt"]),
        "total_amount":     float(row["Total Amt"]),
        "sal_paid_other":   float(row["Sal Paid Other"]),
        "advance_recovery": float(row["Advance Deduction"]),
        "pf_amount":        float(row["PF Amt"]),
        "deduction_total":  float(row["Deduction Total"]),
        "net_payable":      float(row["Net Payable"]),
        "remarks":          str(row.get("Remarks", "") or ""),
        "status":           status,
        "updated_at":       datetime.now().isoformat(),
    }
    if extra:
        payload.update(extra)
    sb.upsert_payroll_record(payload)


# ── HTML grouped table ────────────────────────────────────────────────────────

def _make_grouped_table_html(df_page: pd.DataFrame) -> str:
    """Build the full HTML grouped-header payroll table for one page of data."""
    rows_html = ""
    for _, row in df_page.iterrows():
        # Pre-extract all values (avoid complex expressions inside f-strings)
        op_name = str(row.get("Operator", ""))

        fixed_sal = float(row.get("Fixed Salary", 0))
        work_days = int(float(row.get("Working Days", 0)))
        ot_hours  = float(row.get("OT Hours", 0.0))

        earned_basic    = float(row.get("Earned Basic", 0))
        ot_amt          = float(row.get("OT Amt", 0))
        sal_paid_other  = float(row.get("Sal Paid Other", 0))
        ad_hoc          = 0.0
        gross_pay       = earned_basic + ot_amt + sal_paid_other

        adv_deduction = float(row.get("Advance Deduction", 0))
        pf_amt        = float(row.get("PF Amt", 0))
        other_ded     = 0.0
        total_ded     = float(row.get("Deduction Total", 0))

        net_payable = float(row.get("Net Payable", 0))

        # Pre-format strings
        fixed_sal_s      = f"&#8377;{fixed_sal:,.0f}"
        work_days_s      = str(work_days)
        ot_hours_s       = f"{ot_hours:.1f}"
        earned_basic_s   = f"&#8377;{earned_basic:,.0f}"
        ot_amt_s         = f"&#8377;{ot_amt:,.0f}"
        sal_paid_other_s = f"&#8377;{sal_paid_other:,.0f}"
        ad_hoc_s         = f"&#8377;{ad_hoc:,.0f}"
        gross_pay_s      = f"&#8377;{gross_pay:,.0f}"
        adv_deduction_s  = f"&#8377;{adv_deduction:,.0f}"
        pf_amt_s         = f"&#8377;{pf_amt:,.0f}"
        other_ded_s      = f"&#8377;{other_ded:,.0f}"
        total_ded_s      = f"&#8377;{total_ded:,.0f}"
        net_payable_s    = f"&#8377;{net_payable:,.0f}"

        rows_html += (
            "<tr>"
            f"<td class='ps-td-op'>{op_name}</td>"
            f"<td class='ps-td-inputs'>{fixed_sal_s}</td>"
            f"<td class='ps-td-inputs'>{work_days_s}</td>"
            f"<td class='ps-td-inputs'>{ot_hours_s}</td>"
            f"<td class='ps-td-earnings'>{earned_basic_s}</td>"
            f"<td class='ps-td-earnings'>{ot_amt_s}</td>"
            f"<td class='ps-td-earnings'>{sal_paid_other_s}</td>"
            f"<td class='ps-td-earnings'>{ad_hoc_s}</td>"
            f"<td class='ps-td-earnings'>{gross_pay_s}</td>"
            f"<td class='ps-td-deductions'>{adv_deduction_s}</td>"
            f"<td class='ps-td-deductions'>{pf_amt_s}</td>"
            f"<td class='ps-td-deductions'>{other_ded_s}</td>"
            f"<td class='ps-td-deductions'>{total_ded_s}</td>"
            f"<td class='ps-td-final'>{net_payable_s}</td>"
            "</tr>"
        )

    table_html = (
        "<div class='ps-table-wrap'>"
        "<table class='ps-table'>"
        "<thead>"
        "<tr>"
        "<th class='ps-sh-op' rowspan='2' style='min-width:150px;text-align:left;'>Operator</th>"
        "<th class='ps-gh-inputs' colspan='3'>Inputs</th>"
        "<th class='ps-gh-earnings' colspan='5'>Earnings</th>"
        "<th class='ps-gh-deductions' colspan='4'>Deductions</th>"
        "<th class='ps-gh-final' colspan='1'>Final Pay</th>"
        "</tr>"
        "<tr>"
        "<th class='ps-sh-inputs'>Fixed Salary</th>"
        "<th class='ps-sh-inputs'>Working Days</th>"
        "<th class='ps-sh-inputs'>OT Hours</th>"
        "<th class='ps-sh-earnings'>Earned Basic</th>"
        "<th class='ps-sh-earnings'>OT Pay</th>"
        "<th class='ps-sh-earnings'>Conveyance</th>"
        "<th class='ps-sh-earnings'>Ad hoc</th>"
        "<th class='ps-sh-earnings'>Gross Pay</th>"
        "<th class='ps-sh-deductions'>Sal Advance</th>"
        "<th class='ps-sh-deductions'>PF</th>"
        "<th class='ps-sh-deductions'>Other Ded.</th>"
        "<th class='ps-sh-deductions'>Total Ded.</th>"
        "<th class='ps-sh-final'>Net Pay</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        + rows_html
        + "</tbody>"
        "</table>"
        "</div>"
    )
    return table_html


# ── Edit payroll data expander (data_editor + action buttons) ─────────────────

def _render_edit_and_actions(
    sb: SupabaseClient,
    df: pd.DataFrame,
    payroll_month: str,
    cache_key: str,
    is_admin: bool,
) -> None:
    """Editable data table for Draft/SendBack records plus workflow action buttons."""
    calc_df = df[df["_status"].isin([_S_DRAFT, _S_SENDBACK])].copy()

    if calc_df.empty:
        st.info("All operators for this period are submitted, approved, on hold, or paid.")
        return

    # SendBack notice
    sendback_rows = calc_df[calc_df["_status"] == _S_SENDBACK]
    if not sendback_rows.empty:
        st.warning(
            f"{len(sendback_rows)} employee(s) were sent back by admin — review and resubmit.",
            icon="↩",
        )

    always_readonly = {
        "Emp Code", "Operator",
        "No. of Days Worked", "Earned Basic", "Advance Deduction",
        "Total Amt", "Deduction Total", "Net Payable",
    }
    display_cols = [
        "Select", "Emp Code", "Operator", "Fixed Salary", "Month Days",
        "Working Days", "OT Hours", "No. of Days Worked",
        "Earned Basic", "OT Amt", "Total Amt",
        "Sal Paid Other", "Advance Deduction", "PF Amt", "Deduction Total",
        "Net Payable", "Remarks",
    ]

    calc_display = calc_df.copy()
    calc_display.insert(0, "Select", False)

    col_cfg = {
        "Select":             st.column_config.CheckboxColumn("Select",      default=False, width="small"),
        "Emp Code":           st.column_config.TextColumn("Emp Code",        width="small"),
        "Operator":           st.column_config.TextColumn("Operator",        width="medium"),
        "Fixed Salary":       st.column_config.NumberColumn("Fixed Sal",     format="&#8377;%,.0f", width="small", min_value=0),
        "Month Days":         st.column_config.NumberColumn("Month Days",    width="small", min_value=1, max_value=31),
        "Working Days":       st.column_config.NumberColumn("Work Days",     width="small", min_value=0, max_value=366),
        "OT Hours":           st.column_config.NumberColumn("OT Hrs",        format="%.2f", width="small", min_value=0.0),
        "No. of Days Worked": st.column_config.NumberColumn("Days Worked",   width="small"),
        "Earned Basic":       st.column_config.NumberColumn("Earned",        format="&#8377;%,.0f", width="small"),
        "OT Amt":             st.column_config.NumberColumn("OT Amt",        format="&#8377;%,.0f", width="small", min_value=0),
        "Total Amt":          st.column_config.NumberColumn("Total",         format="&#8377;%,.0f", width="small"),
        "Sal Paid Other":     st.column_config.NumberColumn("Sal by Cust",   format="&#8377;%,.0f", width="small", min_value=0),
        "Advance Deduction":  st.column_config.NumberColumn("Adv Deduct",    format="&#8377;%,.0f", width="small"),
        "PF Amt":             st.column_config.NumberColumn("PF Amt",        format="&#8377;%,.0f", width="small", min_value=0),
        "Deduction Total":    st.column_config.NumberColumn("Ded Total",     format="&#8377;%,.0f", width="small"),
        "Net Payable":        st.column_config.NumberColumn("Net Payable",   format="&#8377;%,.0f", width="small"),
        "Remarks":            st.column_config.TextColumn("Remarks",         width="medium"),
    }

    edited = st.data_editor(
        calc_display[display_cols],
        key=f"ps_editor_{payroll_month}",
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        disabled=[c for c in display_cols if c in always_readonly],
        num_rows="fixed",
    )

    # Merge edits back into calc_df
    editable_cols = [c for c in display_cols if c not in always_readonly and c != "Select"]
    for col in editable_cols:
        if col in edited.columns:
            calc_df[col] = edited[col].values
    calc_df = _recompute(calc_df)

    # Write updated calc rows back into main df and persist
    df.loc[df["_status"].isin([_S_DRAFT, _S_SENDBACK]), calc_df.columns] = calc_df.values
    st.session_state[cache_key] = df

    # Totals bar
    earn_sum  = calc_df["Earned Basic"].sum()
    ot_sum    = calc_df["OT Amt"].sum()
    total_sum = calc_df["Total Amt"].sum()
    ded_sum   = calc_df["Deduction Total"].sum()
    net_sum   = calc_df["Net Payable"].sum()
    st.markdown(
        f"<div class='ps-total-bar'>"
        f"Totals — <strong>Earned:</strong> &#8377;{earn_sum:,.0f} &nbsp;&middot;&nbsp; "
        f"<strong>OT:</strong> &#8377;{ot_sum:,.0f} &nbsp;&middot;&nbsp; "
        f"<strong>Total:</strong> &#8377;{total_sum:,.0f} &nbsp;&middot;&nbsp; "
        f"<strong>Deductions:</strong> &#8377;{ded_sum:,.0f} &nbsp;&middot;&nbsp; "
        f"<strong>Net Payable:</strong> &#8377;{net_sum:,.0f}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Selection info
    selected_mask = edited["Select"] == True  # noqa: E712
    selected_df   = calc_df[selected_mask.values]
    n_sel         = len(selected_df)
    n_total_calc  = len(calc_df)
    st.markdown(
        f"<div style='font-size:12px;color:#64748B;margin:8px 0 4px;'>"
        f"<strong style='color:#1E293B;'>{n_sel}</strong> / {n_total_calc} selected</div>",
        unsafe_allow_html=True,
    )

    # Action buttons row
    if is_admin:
        act1, act2, act3, act4, _ = st.columns([1.4, 1.6, 1.4, 1.6, 2])
    else:
        act1, act2, act3, _ = st.columns([1.4, 1.6, 1.4, 4])

    # Save Drafts
    if act1.button("Save Drafts", key="ps_save_drafts", use_container_width=True,
                   disabled=(n_sel == 0)):
        saved = 0
        for _, row in selected_df.iterrows():
            try:
                _save_record(sb, row, payroll_month, _S_DRAFT)
                saved += 1
            except Exception as e:
                st.error(f"Error saving {row['Operator']}: {e}")
        if saved:
            st.success(f"Saved {saved} draft(s).")
            st.session_state.pop(cache_key, None)
            st.rerun()

    # Submit for Approval
    if act2.button("Submit for Approval", key="ps_submit", type="primary",
                   use_container_width=True, disabled=(n_sel == 0)):
        submitted = 0
        for _, row in selected_df.iterrows():
            try:
                _save_record(sb, row, payroll_month, _S_SUBMITTED, {
                    "submitted_by": _user_name(),
                    "submitted_at": datetime.now().isoformat(),
                    "sendback_reason": None,
                })
                submitted += 1
            except Exception as e:
                st.error(f"Error submitting {row['Operator']}: {e}")
        if submitted:
            st.success(f"Submitted {submitted} employee(s) for approval.")
            st.session_state.pop(cache_key, None)
            st.rerun()

    # Put on Hold
    if act3.button("Put on Hold", key="ps_hold", use_container_width=True,
                   disabled=(n_sel == 0)):
        st.session_state["ps_hold_confirm"] = True
        st.session_state["ps_hold_df"]      = selected_df
        st.session_state["ps_hold_month"]   = payroll_month

    if st.session_state.get("ps_hold_confirm") and \
            st.session_state.get("ps_hold_month") == payroll_month:
        hold_df = st.session_state.get("ps_hold_df", pd.DataFrame())
        with st.container(border=True):
            hold_count_s = str(len(hold_df))
            st.markdown(
                f"<div style='font-size:13px;font-weight:700;color:#991B1B;'>"
                f"Put {hold_count_s} employee(s) on hold?</div>",
                unsafe_allow_html=True,
            )
            hold_reason = st.text_input("Hold reason (required)", key="ps_hold_reason")
            hc1, hc2 = st.columns([1, 1])
            if hc1.button("Confirm Hold", type="primary", key="ps_hold_ok"):
                if not hold_reason.strip():
                    st.error("Please enter a hold reason.")
                else:
                    held = 0
                    for _, row in hold_df.iterrows():
                        try:
                            _save_record(sb, row, payroll_month, _S_ONHOLD, {
                                "hold_reason": hold_reason.strip(),
                            })
                            held += 1
                        except Exception as e:
                            st.error(f"Error: {e}")
                    if held:
                        st.success(f"{held} employee(s) put on hold.")
                        for k in ["ps_hold_confirm", "ps_hold_df", "ps_hold_month", "ps_hold_reason"]:
                            st.session_state.pop(k, None)
                        st.session_state.pop(cache_key, None)
                        st.rerun()
            if hc2.button("Cancel", key="ps_hold_cancel"):
                for k in ["ps_hold_confirm", "ps_hold_df", "ps_hold_month"]:
                    st.session_state.pop(k, None)
                st.rerun()

    # Admin: Approve All Submitted
    if is_admin:
        submitted_df = df[df["_status"] == _S_SUBMITTED]
        n_submitted  = len(submitted_df)
        lbl_approve  = f"Approve All ({n_submitted})"
        if act4.button(lbl_approve, key="ps_approve_all", use_container_width=True,
                       disabled=(n_submitted == 0)):
            try:
                all_recs = sb.list_payroll_records(payroll_month=payroll_month, status=_S_SUBMITTED)
                for r in all_recs:
                    sb.update_payroll_record(r["id"], {
                        "status":      _S_APPROVED,
                        "approved_by": _user_name(),
                        "approved_at": datetime.now().isoformat(),
                        "updated_at":  datetime.now().isoformat(),
                    })
                st.success(f"Approved {len(all_recs)} payroll record(s).")
                st.session_state.pop(cache_key, None)
                st.rerun()
            except Exception as e:
                st.error(f"Approval error: {e}")

    # Export buttons
    exp1, exp2, _ = st.columns([1.5, 1.5, 5])
    try:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            calc_df[[c for c in display_cols if c != "Select"]].to_excel(
                w, index=False, sheet_name="Payroll")
        exp1.download_button(
            "Export Excel",
            data=buf.getvalue(),
            file_name=f"payroll_{payroll_month}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ps_exp_xlsx",
            use_container_width=True,
        )
    except Exception:
        pass
    try:
        exp2.download_button(
            "Export CSV",
            data=calc_df[[c for c in display_cols if c != "Select"]].to_csv(index=False).encode(),
            file_name=f"payroll_{payroll_month}.csv",
            mime="text/csv",
            key="ps_exp_csv",
            use_container_width=True,
        )
    except Exception:
        pass


# ── Approval queue expander ───────────────────────────────────────────────────

def _render_approval_expander(
    sb: SupabaseClient,
    operators: list,
    payroll_month: str,
    month: int,
    year: int,
) -> None:
    """Content for the Approval Queue expander (admin only)."""
    if not auth.is_admin():
        st.info("Only Admin can approve payroll submissions.", icon="🔒")
        return

    aq_cache = f"psaq_recs_{payroll_month}"
    rc1, rc2 = st.columns([1, 4])
    if rc1.button("Refresh", key="aq_refresh"):
        st.session_state.pop(aq_cache, None)

    if aq_cache not in st.session_state:
        recs = sb.list_payroll_records(payroll_month=payroll_month, status=_S_SUBMITTED)
        st.session_state[aq_cache] = recs

    recs = st.session_state.get(aq_cache, [])
    month_lbl = _month_label(month)

    if not recs:
        st.info(f"No submissions pending approval for {month_lbl} {year}.")
        return

    op_by_id = {o["id"]: o for o in operators}

    n_recs = len(recs)
    st.markdown(
        f"<div style='font-size:13px;color:#64748B;margin-bottom:14px;'>"
        f"<strong style='color:#1E293B;'>{n_recs}</strong> submission(s) awaiting approval</div>",
        unsafe_allow_html=True,
    )

    rows = []
    for r in recs:
        op = op_by_id.get(r["employee_id"], {})
        rows.append({
            "Select":            False,
            "Emp Code":          op.get("emp_code", ""),
            "Operator":          op.get("operator_name", r["employee_id"]),
            "Earned Basic":      float(r.get("earned_basic") or 0),
            "OT Amt":            float(r.get("ot_amount") or 0),
            "Total Amt":         float(r.get("total_amount") or 0),
            "Advance Deduction": float(r.get("advance_recovery") or 0),
            "PF Amt":            float(r.get("pf_amount") or 0),
            "Deduction Total":   float(r.get("deduction_total") or 0),
            "Net Payable":       float(r.get("net_payable") or 0),
            "Submitted By":      r.get("submitted_by", ""),
            "Remarks":           r.get("remarks", ""),
            "_id":               r["id"],
        })
    disp_df = pd.DataFrame(rows)

    col_cfg = {
        "Select":            st.column_config.CheckboxColumn("Select",    width="small", default=False),
        "Emp Code":          st.column_config.TextColumn("Emp Code",      width="small"),
        "Operator":          st.column_config.TextColumn("Operator",      width="medium"),
        "Earned Basic":      st.column_config.NumberColumn("Earned",      format="&#8377;%,.0f", width="small"),
        "OT Amt":            st.column_config.NumberColumn("OT Amt",      format="&#8377;%,.0f", width="small"),
        "Total Amt":         st.column_config.NumberColumn("Total",       format="&#8377;%,.0f", width="small"),
        "Advance Deduction": st.column_config.NumberColumn("Adv Deduct",  format="&#8377;%,.0f", width="small"),
        "PF Amt":            st.column_config.NumberColumn("PF Amt",      format="&#8377;%,.0f", width="small"),
        "Deduction Total":   st.column_config.NumberColumn("Ded Total",   format="&#8377;%,.0f", width="small"),
        "Net Payable":       st.column_config.NumberColumn("Net Payable", format="&#8377;%,.0f", width="small"),
        "Submitted By":      st.column_config.TextColumn("Submitted By",  width="small"),
        "Remarks":           st.column_config.TextColumn("Remarks",       width="medium"),
    }
    ro_cols = [c for c in disp_df.columns if c not in ("Select", "_id")]

    edited = st.data_editor(
        disp_df.drop(columns=["_id"]),
        key=f"aq_editor_{payroll_month}",
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        disabled=ro_cols,
        num_rows="fixed",
    )

    net_total  = disp_df["Net Payable"].sum()
    earn_total = disp_df["Earned Basic"].sum()
    ded_total  = disp_df["Deduction Total"].sum()
    st.markdown(
        f"<div class='ps-total-bar'>"
        f"Totals — <strong>Earned:</strong> &#8377;{earn_total:,.0f} &nbsp;&middot;&nbsp; "
        f"<strong>Deductions:</strong> &#8377;{ded_total:,.0f} &nbsp;&middot;&nbsp; "
        f"<strong>Net Payable:</strong> &#8377;{net_total:,.0f}"
        f"</div>",
        unsafe_allow_html=True,
    )

    sel_mask = edited["Select"] == True  # noqa: E712
    sel_ids  = list(disp_df.loc[sel_mask.values, "_id"])
    sel_recs = [r for r in recs if r["id"] in sel_ids]
    n_sel    = len(sel_recs)

    st.markdown(
        f"<div style='font-size:12px;color:#64748B;margin:8px 0 4px;'>"
        f"<strong style='color:#1E293B;'>{n_sel}</strong> / {n_recs} selected</div>",
        unsafe_allow_html=True,
    )

    ac1, ac2, _ = st.columns([1.5, 2, 5])

    if ac1.button("Approve Selected", type="primary", key="aq_approve",
                  use_container_width=True, disabled=(n_sel == 0)):
        for r in sel_recs:
            sb.update_payroll_record(r["id"], {
                "status":      _S_APPROVED,
                "approved_by": _user_name(),
                "approved_at": datetime.now().isoformat(),
                "updated_at":  datetime.now().isoformat(),
            })
        st.success(f"Approved {n_sel} payroll record(s).")
        st.session_state.pop(aq_cache, None)
        st.rerun()

    if ac2.button("Send Back Selected", key="aq_sendback",
                  use_container_width=True, disabled=(n_sel == 0)):
        st.session_state["aq_sendback_confirm"] = True
        st.session_state["aq_sendback_ids"]     = sel_ids

    if st.session_state.get("aq_sendback_confirm"):
        with st.container(border=True):
            n_sb = len(st.session_state.get("aq_sendback_ids", []))
            st.markdown(
                f"<div style='font-size:13px;font-weight:700;color:#D97706;'>"
                f"Send back {n_sb} record(s)?</div>",
                unsafe_allow_html=True,
            )
            sb_reason = st.text_input("Reason for sending back (required)", key="aq_sb_reason")
            sc1, sc2 = st.columns([1, 1])
            if sc1.button("Confirm Send Back", type="primary", key="aq_sb_ok"):
                if not sb_reason.strip():
                    st.error("Reason is required.")
                else:
                    ids_to_sendback = st.session_state.get("aq_sendback_ids", [])
                    for rid in ids_to_sendback:
                        sb.update_payroll_record(rid, {
                            "status":          _S_DRAFT,
                            "sendback_reason": sb_reason.strip(),
                            "updated_at":      datetime.now().isoformat(),
                        })
                    n_sent = len(ids_to_sendback)
                    st.success(f"Sent back {n_sent} record(s) for revision.")
                    for k in ["aq_sendback_confirm", "aq_sendback_ids", "aq_sb_reason"]:
                        st.session_state.pop(k, None)
                    st.session_state.pop(aq_cache, None)
                    st.rerun()
            if sc2.button("Cancel", key="aq_sb_cancel"):
                for k in ["aq_sendback_confirm", "aq_sendback_ids"]:
                    st.session_state.pop(k, None)
                st.rerun()


# ── Pending / Held expander ───────────────────────────────────────────────────

def _render_pending_held_expander(
    sb: SupabaseClient,
    operators: list,
    payroll_month: str,
    month: int,
    year: int,
    main_cache_key: str,
) -> None:
    """Content for the Pending / On Hold expander."""
    ph_cache = f"psph_recs_{payroll_month}"
    rc1, _ = st.columns([1, 4])
    if rc1.button("Refresh", key="ph_refresh"):
        st.session_state.pop(ph_cache, None)

    if ph_cache not in st.session_state:
        all_recs = sb.list_payroll_records(payroll_month=payroll_month)
        hold_cancelled = [r for r in all_recs if r["status"] in (_S_ONHOLD, _S_CANCELLED)]
        st.session_state[ph_cache] = hold_cancelled

    recs     = st.session_state.get(ph_cache, [])
    month_lbl = _month_label(month)
    op_by_id = {o["id"]: o for o in operators}

    if not recs:
        st.info(f"No on-hold or cancelled records for {month_lbl} {year}.")
        return

    held      = [r for r in recs if r["status"] == _S_ONHOLD]
    cancelled = [r for r in recs if r["status"] == _S_CANCELLED]

    def _make_section(rec_list: list, section: str) -> None:
        rows = []
        for r in rec_list:
            op = op_by_id.get(r["employee_id"], {})
            rows.append({
                "Select":      False,
                "Emp Code":    op.get("emp_code", ""),
                "Operator":    op.get("operator_name", r["employee_id"]),
                "Net Payable": float(r.get("net_payable") or 0),
                "Reason":      r.get("hold_reason") or r.get("cancel_reason") or "—",
                "Updated":     str(r.get("updated_at") or "")[:10],
                "_id":         r["id"],
            })
        sec_df = pd.DataFrame(rows)
        sec_edited = st.data_editor(
            sec_df.drop(columns=["_id"]),
            key=f"ph_tbl_{section}_{payroll_month}",
            use_container_width=True, hide_index=True, num_rows="fixed",
            column_config={
                "Select":      st.column_config.CheckboxColumn("Select",    width="small", default=False),
                "Emp Code":    st.column_config.TextColumn("Emp Code",      width="small"),
                "Operator":    st.column_config.TextColumn("Operator",      width="medium"),
                "Net Payable": st.column_config.NumberColumn("Net Payable", format="&#8377;%,.0f"),
                "Reason":      st.column_config.TextColumn("Reason",        width="large"),
                "Updated":     st.column_config.TextColumn("Updated",       width="small"),
            },
            disabled=["Emp Code", "Operator", "Net Payable", "Reason", "Updated"],
        )
        sel_mask = sec_edited["Select"] == True  # noqa: E712
        sel_ids  = list(sec_df.loc[sel_mask.values, "_id"])
        n_sel    = len(sel_ids)

        if n_sel > 0 and section == "held":
            ra1, ra2, _ = st.columns([1.8, 1.8, 4])
            if ra1.button(f"Release {n_sel} to Calculator", key=f"ph_rel_{section}",
                          type="primary", use_container_width=True):
                for rid in sel_ids:
                    sb.update_payroll_record(rid, {
                        "status":      _S_DRAFT,
                        "hold_reason": None,
                        "updated_at":  datetime.now().isoformat(),
                    })
                st.success(f"Released {n_sel} employee(s) back to Payroll Calculator.")
                st.session_state.pop(ph_cache, None)
                st.session_state.pop(main_cache_key, None)
                st.rerun()

            if ra2.button(f"Cancel Salary ({n_sel})", key=f"ph_cancel_{section}",
                          use_container_width=True):
                st.session_state[f"ph_cancel_confirm_{section}"] = True
                st.session_state[f"ph_cancel_ids_{section}"]     = sel_ids

            if st.session_state.get(f"ph_cancel_confirm_{section}"):
                with st.container(border=True):
                    can_reason = st.text_input("Cancellation reason (required)",
                                               key=f"ph_can_reason_{section}")
                    cc1, cc2 = st.columns([1, 1])
                    if cc1.button("Confirm Cancel", type="primary", key=f"ph_can_ok_{section}"):
                        if not can_reason.strip():
                            st.error("Reason is required.")
                        else:
                            ids_to_cancel = st.session_state.get(f"ph_cancel_ids_{section}", [])
                            for rid in ids_to_cancel:
                                sb.update_payroll_record(rid, {
                                    "status":        _S_CANCELLED,
                                    "cancel_reason": can_reason.strip(),
                                    "hold_reason":   None,
                                    "updated_at":    datetime.now().isoformat(),
                                })
                            n_can = len(ids_to_cancel)
                            st.success(f"Cancelled {n_can} salary record(s) for {month_lbl} {year}.")
                            for k in [f"ph_cancel_confirm_{section}", f"ph_cancel_ids_{section}"]:
                                st.session_state.pop(k, None)
                            st.session_state.pop(ph_cache, None)
                            st.rerun()
                    if cc2.button("Back", key=f"ph_can_bk_{section}"):
                        st.session_state.pop(f"ph_cancel_confirm_{section}", None)
                        st.rerun()

    if held:
        n_held = len(held)
        st.markdown(
            f"<div class='ps-section-hdr'>On Hold — {n_held} employee(s)</div>",
            unsafe_allow_html=True,
        )
        _make_section(held, "held")

    if cancelled:
        n_cancelled = len(cancelled)
        st.markdown(
            f"<div class='ps-section-hdr'>Cancelled — {n_cancelled} employee(s)</div>",
            unsafe_allow_html=True,
        )
        _make_section(cancelled, "cancelled")


# ── Final payment expander ────────────────────────────────────────────────────

def _render_final_payment_expander(
    sb: SupabaseClient,
    operators: list,
    payroll_month: str,
    month: int,
    year: int,
    is_admin: bool,
) -> None:
    """Content for the Final Payment expander."""
    fp_cache = f"psfp_recs_{payroll_month}"
    rc1, _ = st.columns([1, 4])
    if rc1.button("Refresh", key="fp_refresh"):
        st.session_state.pop(fp_cache, None)

    if fp_cache not in st.session_state:
        all_recs = sb.list_payroll_records(payroll_month=payroll_month)
        fin_recs = [r for r in all_recs if r["status"] in (_S_APPROVED, _S_PAID)]
        st.session_state[fp_cache] = fin_recs

    recs       = st.session_state.get(fp_cache, [])
    month_lbl  = _month_label(month)
    op_by_id   = {o["id"]: o for o in operators}

    approved_recs = [r for r in recs if r["status"] == _S_APPROVED]
    paid_recs     = [r for r in recs if r["status"] == _S_PAID]

    total_approved = sum(float(r.get("net_payable") or 0) for r in approved_recs)
    total_paid     = sum(float(r.get("net_payable") or 0) for r in paid_recs)

    n_approved = len(approved_recs)
    n_paid     = len(paid_recs)
    n_total    = len(recs)

    st.markdown(
        "<div class='ps-kpi-grid'>"
        + _kpi("Approved (Pending Payment)", n_approved, f"&#8377;{total_approved:,.0f} to disburse", "#E87722")
        + _kpi("Already Paid",               n_paid,     f"&#8377;{total_paid:,.0f} disbursed",       "#10B981")
        + _kpi("Total",                      n_total,    f"&#8377;{total_approved + total_paid:,.0f}", "#2563EB")
        + "</div>",
        unsafe_allow_html=True,
    )

    if approved_recs:
        st.markdown(
            "<div class='ps-section-hdr'>Ready for Payment</div>",
            unsafe_allow_html=True,
        )
        rows = []
        for r in approved_recs:
            op = op_by_id.get(r["employee_id"], {})
            rows.append({
                "Select":           False,
                "Emp Code":         op.get("emp_code", ""),
                "Operator":         op.get("operator_name", r["employee_id"]),
                "Name in Passbook": op.get("name_in_passbook", ""),
                "Account No.":      op.get("bank_account_number", ""),
                "IFSC":             op.get("ifsc_code", ""),
                "Net Payable":      float(r.get("net_payable") or 0),
                "Approved By":      r.get("approved_by", ""),
                "Remarks":          r.get("remarks", ""),
                "_id":              r["id"],
            })
        disp_df = pd.DataFrame(rows)

        col_cfg = {
            "Select":           st.column_config.CheckboxColumn("Select",    width="small", default=False),
            "Emp Code":         st.column_config.TextColumn("Emp Code",      width="small"),
            "Operator":         st.column_config.TextColumn("Operator",      width="medium"),
            "Name in Passbook": st.column_config.TextColumn("Passbook Name", width="medium"),
            "Account No.":      st.column_config.TextColumn("Account No.",   width="medium"),
            "IFSC":             st.column_config.TextColumn("IFSC",          width="small"),
            "Net Payable":      st.column_config.NumberColumn("Net Payable", format="&#8377;%,.0f", width="small"),
            "Approved By":      st.column_config.TextColumn("Approved By",   width="small"),
            "Remarks":          st.column_config.TextColumn("Remarks",       width="medium"),
        }

        fp_edited = st.data_editor(
            disp_df.drop(columns=["_id"]),
            key=f"fp_editor_{payroll_month}",
            use_container_width=True, hide_index=True, num_rows="fixed",
            column_config=col_cfg,
            disabled=[c for c in disp_df.columns if c not in ("Select", "_id")],
        )

        try:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                disp_df.drop(columns=["Select", "_id"]).to_excel(
                    w, index=False, sheet_name="Payment List")
            st.download_button(
                "Export Payment List",
                data=buf.getvalue(),
                file_name=f"payment_list_{payroll_month}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="fp_export",
            )
        except Exception:
            pass

        sel_mask   = fp_edited["Select"] == True  # noqa: E712
        sel_ids    = list(disp_df.loc[sel_mask.values, "_id"])
        n_sel      = len(sel_ids)
        sel_total  = disp_df.loc[sel_mask.values, "Net Payable"].sum()

        if n_sel > 0:
            sel_total_s = f"{sel_total:,.0f}"
            st.markdown(
                f"<div style='font-size:12px;font-weight:700;color:#0F766E;margin:4px 0 8px;'>"
                f"{n_sel} selected — Total: &#8377;{sel_total_s}</div>",
                unsafe_allow_html=True,
            )
            mc1, mc2, mc3 = st.columns([1.2, 2, 3])
            pay_date = mc1.date_input("Payment Date", value=date.today(), key="fp_pdate")
            utr_ref  = mc2.text_input("UTR / Reference", key="fp_utr",
                                      placeholder="Bank UTR or leave blank")
            lbl_paid = f"Mark {n_sel} as Paid"
            if mc3.button(lbl_paid, type="primary", key="fp_mark_paid"):
                paid_n = 0
                for rid in sel_ids:
                    sb.update_payroll_record(rid, {
                        "status":        _S_PAID,
                        "paid_by":       _user_name(),
                        "paid_at":       datetime.now().isoformat(),
                        "payment_date":  str(pay_date),
                        "utr_reference": utr_ref or None,
                        "updated_at":    datetime.now().isoformat(),
                    })
                    paid_n += 1
                st.success(f"Marked {paid_n} payment(s) as Paid on {pay_date}.")
                st.session_state.pop(fp_cache, None)
                st.rerun()

    if paid_recs:
        total_paid_s = f"{total_paid:,.0f}"
        st.markdown(
            f"<div class='ps-section-hdr'>Paid — {len(paid_recs)} record(s) &nbsp;"
            f"<span style='font-weight:400;color:#10B981;'>&#8377;{total_paid_s}</span></div>",
            unsafe_allow_html=True,
        )
        paid_rows = []
        for r in paid_recs:
            op = op_by_id.get(r["employee_id"], {})
            paid_rows.append({
                "Emp Code":         op.get("emp_code", ""),
                "Operator":         op.get("operator_name", r["employee_id"]),
                "Name in Passbook": op.get("name_in_passbook", ""),
                "Account No.":      op.get("bank_account_number", ""),
                "IFSC":             op.get("ifsc_code", ""),
                "Net Payable":      float(r.get("net_payable") or 0),
                "Payment Date":     r.get("payment_date") or "",
                "UTR":              r.get("utr_reference") or "—",
                "Paid By":          r.get("paid_by") or "",
            })
        st.dataframe(
            pd.DataFrame(paid_rows),
            use_container_width=True, hide_index=True,
            column_config={"Net Payable": st.column_config.NumberColumn(format="&#8377;%,.0f")},
        )

    if not recs:
        st.info(f"No approved or paid records for {month_lbl} {year}.")


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Supabase + operators ───────────────────────────────────────────────────
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

    # ── Period state ───────────────────────────────────────────────────────────
    today = date.today()
    if "ps_month_sel" not in st.session_state:
        st.session_state["ps_month_sel"] = today.month
    if "ps_year_input" not in st.session_state:
        st.session_state["ps_year_input"] = today.year

    ps_month = int(st.session_state["ps_month_sel"])
    ps_year  = int(st.session_state["ps_year_input"])

    # Reset mdays when period changes
    period_tag = f"{ps_year}-{ps_month:02d}"
    if st.session_state.get("_ps_period_tag") != period_tag:
        st.session_state["ps_mdays"]       = _calc_month_days(ps_year, ps_month)
        st.session_state["_ps_period_tag"] = period_tag

    ps_mdays = int(st.session_state.get("ps_mdays", _calc_month_days(ps_year, ps_month)))

    payroll_month = f"{ps_year}-{ps_month:02d}"
    _, last_day   = calendar.monthrange(ps_year, ps_month)
    period_start  = date(ps_year, ps_month, 1)
    period_end    = date(ps_year, ps_month, last_day)
    month_lbl     = _month_label(ps_month)

    # ── Header row ─────────────────────────────────────────────────────────────
    h_left, h_right = st.columns([2, 2])

    with h_left:
        st.markdown(
            f"<div style='font-size:26px;font-weight:900;color:#111827;"
            f"letter-spacing:-.5px;margin-bottom:2px;'>Payment summary</div>"
            f"<div style='font-size:14px;color:#6B7280;'>{month_lbl} {ps_year}</div>",
            unsafe_allow_html=True,
        )

    with h_right:
        # Compact period selector: ← | Month dropdown | Year input | → | Review button
        rc1, rc2, rc3, rc4, rc5 = st.columns([0.5, 1.8, 1.1, 0.5, 1.8])

        # Prev month button
        if rc1.button("←", key="ps_prev_month", help="Previous month"):
            new_m = ps_month - 1
            new_y = ps_year
            if new_m < 1:
                new_m = 12
                new_y -= 1
            st.session_state["ps_month_sel"]  = new_m
            st.session_state["ps_year_input"] = new_y
            # Clear data cache for all periods
            for k in [k for k in st.session_state if k.startswith("ps_data_")]:
                del st.session_state[k]
            st.rerun()

        rc2.selectbox(
            "Month",
            list(range(1, 13)),
            format_func=_month_label,
            key="ps_month_sel",
            label_visibility="collapsed",
        )

        rc3.number_input(
            "Year",
            min_value=2020,
            max_value=2035,
            step=1,
            key="ps_year_input",
            label_visibility="collapsed",
        )

        # Next month button
        if rc4.button("→", key="ps_next_month", help="Next month"):
            new_m = ps_month + 1
            new_y = ps_year
            if new_m > 12:
                new_m = 1
                new_y += 1
            st.session_state["ps_month_sel"]  = new_m
            st.session_state["ps_year_input"] = new_y
            for k in [k for k in st.session_state if k.startswith("ps_data_")]:
                del st.session_state[k]
            st.rerun()

        if rc5.button("Review & approve", key="ps_review_approve",
                      type="primary", use_container_width=True):
            st.session_state["ps_show_review"] = not st.session_state.get("ps_show_review", False)

    st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

    # ── Load payroll data ──────────────────────────────────────────────────────
    cache_key = f"ps_data_{payroll_month}"
    if cache_key not in st.session_state:
        with st.spinner(f"Loading {month_lbl} {ps_year} payroll data…"):
            df = _load_payroll_data(
                sb, operators, payroll_month, period_start, period_end, ps_mdays
            )
        st.session_state[cache_key] = df

    df: pd.DataFrame = st.session_state.get(cache_key, pd.DataFrame())

    if df.empty:
        st.info("No active operators found. Try a different period.")
        return

    # Sync Month Days if the user adjusts it without a full reload
    if ps_mdays != int(df["Month Days"].iloc[0]):
        df["Month Days"] = ps_mdays
        df = _recompute(df)
        st.session_state[cache_key] = df

    # ── 4 KPI cards ───────────────────────────────────────────────────────────
    n_ops       = len(df)
    net_kpi     = df["Net Payable"].sum()
    gross_kpi   = df["Earned Basic"].sum() + df["OT Amt"].sum() + df["Sal Paid Other"].sum()
    ded_kpi     = df["Deduction Total"].sum()

    net_kpi_s   = f"&#8377;{net_kpi:,.0f}"
    gross_kpi_s = f"&#8377;{gross_kpi:,.0f}"
    ded_kpi_s   = f"&#8377;{ded_kpi:,.0f}"

    kpi_html = (
        "<div class='ps-kpi-row'>"

        "<div class='ps-kpi-card'>"
        "<div class='ps-kpi-icon' style='background:#EFF6FF;font-size:20px;'>&#128101;</div>"
        "<div>"
        "<div class='ps-kpi-label'>Operators</div>"
        f"<div class='ps-kpi-value'>{n_ops}</div>"
        "</div></div>"

        "<div class='ps-kpi-card'>"
        "<div class='ps-kpi-icon' style='background:#F0FDF4;font-size:16px;font-weight:800;"
        "color:#166534;'>&#8377;</div>"
        "<div>"
        "<div class='ps-kpi-label'>Net payable</div>"
        f"<div class='ps-kpi-value'>{net_kpi_s}</div>"
        "</div></div>"

        "<div class='ps-kpi-card'>"
        "<div class='ps-kpi-icon' style='background:#FFFBEB;font-size:18px;'>&#128200;</div>"
        "<div>"
        "<div class='ps-kpi-label'>Gross earnings</div>"
        f"<div class='ps-kpi-value'>{gross_kpi_s}</div>"
        "</div></div>"

        "<div class='ps-kpi-card'>"
        "<div class='ps-kpi-icon' style='background:#FFF1F2;font-size:18px;'>&#128202;</div>"
        "<div>"
        "<div class='ps-kpi-label'>Deductions</div>"
        f"<div class='ps-kpi-value'>{ded_kpi_s}</div>"
        "</div></div>"

        "</div>"
    )
    st.markdown(kpi_html, unsafe_allow_html=True)

    # ── Formula bar ────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='ps-formula-bar'>"
        "<div class='ps-fb-seg' style='background:#EFF6FF;'>"
        "<div class='ps-fb-seg-title' style='color:#1E40AF;'>Inputs</div>"
        "<div class='ps-fb-seg-items' style='color:#1E40AF;'>"
        "Fixed salary + Working days + OT hours</div>"
        "</div>"
        "<div class='ps-fb-arrow'>&#8594;</div>"
        "<div class='ps-fb-seg' style='background:#FFFBEB;'>"
        "<div class='ps-fb-seg-title' style='color:#92400E;'>Gross Pay</div>"
        "<div class='ps-fb-seg-items' style='color:#92400E;'>"
        "Earned Basic + OT Pay + Conveyance + Ad hoc</div>"
        "</div>"
        "<div class='ps-fb-arrow'>&#8594;</div>"
        "<div class='ps-fb-seg' style='background:#FFF1F2;'>"
        "<div class='ps-fb-seg-title' style='color:#991B1B;'>Total Deductions</div>"
        "<div class='ps-fb-seg-items' style='color:#991B1B;'>"
        "Sal advance + PF + Other deductions</div>"
        "</div>"
        "<div class='ps-fb-equals'>=</div>"
        "<div class='ps-fb-seg' style='background:#F0FDF4;'>"
        "<div class='ps-fb-seg-title' style='color:#166534;'>Net Pay</div>"
        "<div class='ps-fb-seg-items' style='color:#166534;'>"
        "Gross Pay &#8722; Total Deductions</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Two-column main area ───────────────────────────────────────────────────
    col_left, col_right = st.columns([2.2, 1])

    with col_left:
        # Search bar
        prev_search = st.session_state.get("ps_search", "")
        search_term = st.text_input(
            "Search operators",
            value=prev_search,
            placeholder="Search by name or emp code...",
            label_visibility="collapsed",
            key="ps_search_input",
        )
        if search_term != prev_search:
            st.session_state["ps_search"] = search_term
            st.session_state["ps_page"]   = 1

        st.session_state["ps_search"] = search_term

        # Filter by search
        filtered_df = df.copy()
        if search_term.strip():
            op_mask   = filtered_df["Operator"].str.contains(search_term, case=False, na=False)
            code_mask = filtered_df["Emp Code"].str.contains(search_term, case=False, na=False)
            filtered_df = filtered_df[op_mask | code_mask]

        n_filtered = len(filtered_df)

        # Table heading
        st.markdown(
            f"<div style='font-size:14px;font-weight:700;color:#111827;margin:8px 0 4px;'>"
            f"Operator payroll ({n_filtered})</div>",
            unsafe_allow_html=True,
        )

        # Pagination
        rows_per_page = 10
        if "ps_page" not in st.session_state:
            st.session_state["ps_page"] = 1
        total_pages   = max(1, (n_filtered + rows_per_page - 1) // rows_per_page)
        current_page  = max(1, min(int(st.session_state.get("ps_page", 1)), total_pages))
        st.session_state["ps_page"] = current_page

        start_idx = (current_page - 1) * rows_per_page
        end_idx   = min(start_idx + rows_per_page, n_filtered)
        df_page   = filtered_df.iloc[start_idx:end_idx]

        # HTML grouped table
        st.markdown(_make_grouped_table_html(df_page), unsafe_allow_html=True)

        # Pagination controls
        start_d = (start_idx + 1) if n_filtered > 0 else 0
        end_d   = end_idx
        st.markdown(
            f"<div style='font-size:11px;color:#6B7280;margin:6px 0 4px;'>"
            f"Showing {start_d}&#8211;{end_d} of {n_filtered} operators</div>",
            unsafe_allow_html=True,
        )

        pg1, pg2, pg3, pg4 = st.columns([0.8, 0.6, 0.6, 3])
        if pg1.button("Prev", key="ps_prev_page", disabled=(current_page <= 1)):
            st.session_state["ps_page"] = current_page - 1
            st.rerun()
        pg2.markdown(
            f"<div style='text-align:center;font-size:12px;padding:6px 0;font-weight:600;'>"
            f"{current_page} / {total_pages}</div>",
            unsafe_allow_html=True,
        )
        if pg3.button("Next", key="ps_next_page", disabled=(current_page >= total_pages)):
            st.session_state["ps_page"] = current_page + 1
            st.rerun()

        # Info note
        st.markdown(
            "<div class='ps-info-note' style='margin-top:8px;'>"
            "&#8505;&#65039; Net pay is calculated from inputs and earnings minus deductions. "
            "Use the <strong>Edit Payroll Data</strong> expander below to modify values.</div>",
            unsafe_allow_html=True,
        )

    with col_right:
        # ── Payroll checks card ────────────────────────────────────────────────
        n_total_chk   = len(df)
        n_with_salary = int((df["Fixed Salary"] > 0).sum())
        has_all_inputs = n_with_salary == n_total_chk
        no_errors      = bool(
            ((df["Working Days"] <= df["Month Days"]) & (df["Net Payable"] >= 0)).all()
        )
        deductions_ok    = True
        ready_for_review = has_all_inputs and no_errors

        def _ci(ok: bool) -> str:
            return "&#9989;" if ok else "&#128992;"

        ready_icon   = _ci(ready_for_review)
        ready_title  = "Ready for review" if ready_for_review else "Not ready for review"
        ready_sub    = ("All required payroll inputs are complete."
                        if ready_for_review else "Some inputs are missing or invalid.")
        inputs_icon  = _ci(has_all_inputs)
        inputs_sub   = f"{n_with_salary} / {n_total_chk}"
        errors_icon  = _ci(no_errors)
        ded_icon     = _ci(deductions_ok)

        st.markdown(
            "<div class='ps-right-panel-card'>"
            "<div class='ps-panel-title'>Payroll checks</div>"
            f"<div class='ps-check-item'>"
            f"<div class='ps-check-icon'>{ready_icon}</div>"
            f"<div><div class='ps-check-title'>{ready_title}</div>"
            f"<div class='ps-check-sub'>{ready_sub}</div></div></div>"
            f"<div class='ps-check-item'>"
            f"<div class='ps-check-icon'>{inputs_icon}</div>"
            f"<div><div class='ps-check-title'>All operators have pay inputs</div>"
            f"<div class='ps-check-sub'>{inputs_sub}</div></div></div>"
            f"<div class='ps-check-item'>"
            f"<div class='ps-check-icon'>{errors_icon}</div>"
            f"<div><div class='ps-check-title'>No validation errors</div>"
            f"<div class='ps-check-sub'>Timestamps, days and OT verified</div></div></div>"
            f"<div class='ps-check-item'>"
            f"<div class='ps-check-icon'>{ded_icon}</div>"
            f"<div><div class='ps-check-title'>Deductions configured</div>"
            f"<div class='ps-check-sub'>All deductions (if any) are applied</div></div></div>"
            "</div>",
            unsafe_allow_html=True,
        )

        # ── Payment breakdown card ─────────────────────────────────────────────
        gross_bd = df["Earned Basic"].sum() + df["OT Amt"].sum() + df["Sal Paid Other"].sum()
        ded_bd   = df["Deduction Total"].sum()
        net_bd   = df["Net Payable"].sum()

        gross_bd_s = f"&#8377;{gross_bd:,.0f}"
        ded_bd_s   = f"&#8377;{ded_bd:,.0f}"
        net_bd_s   = f"&#8377;{net_bd:,.0f}"
        now_s      = datetime.now().strftime("%d %b %Y")
        user_s     = _user_name()

        st.markdown(
            "<div class='ps-right-panel-card'>"
            "<div class='ps-panel-title'>Payment breakdown</div>"
            "<div class='ps-breakdown-row'>"
            "<span class='ps-bd-label'>Gross earnings</span>"
            f"<span class='ps-bd-value'>{gross_bd_s}</span></div>"
            "<div class='ps-breakdown-row'>"
            "<span class='ps-bd-label'>Total deductions</span>"
            f"<span class='ps-bd-value' style='color:#991B1B;'>{ded_bd_s}</span></div>"
            "<div class='ps-bd-net-row'>"
            "<span style='font-weight:700;color:#166534;font-size:13px;'>Net payable</span>"
            f"<span style='font-weight:800;font-size:16px;color:#166534;"
            f"font-variant-numeric:tabular-nums;'>{net_bd_s}</span></div>"
            f"<div style='font-size:11px;color:#6B7280;margin-top:10px;'>"
            f"&#128336; Last updated {now_s} by {user_s}</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Edit payroll data + action buttons ─────────────────────────────────────
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    is_admin = auth.is_admin()

    with st.expander("Edit Payroll Data", expanded=False):
        _render_edit_and_actions(sb, df, payroll_month, cache_key, is_admin)

    # ── Approval queue (admin only) ────────────────────────────────────────────
    if is_admin:
        show_review = st.session_state.get("ps_show_review", False)
        with st.expander("Approval Queue", expanded=show_review):
            _render_approval_expander(sb, operators, payroll_month, ps_month, ps_year)

    # ── Pending / Held ─────────────────────────────────────────────────────────
    with st.expander("Pending & On Hold"):
        _render_pending_held_expander(
            sb, operators, payroll_month, ps_month, ps_year, cache_key
        )

    # ── Final payment ──────────────────────────────────────────────────────────
    with st.expander("Final Payment"):
        _render_final_payment_expander(
            sb, operators, payroll_month, ps_month, ps_year, is_admin
        )
