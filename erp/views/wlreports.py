"""
erp/views/wlreports.py
Pending Worklogs — monthly worklogs, mobilization & de-mobilization.
"""
from __future__ import annotations

import calendar as _cal
import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient
from ._report_utils import render_export_buttons, render_drilldown_table


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
.kpi-grid-6 {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 12px;
    margin: 0 0 26px;
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
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 9px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 8px; display: flex; align-items: center; gap: 5px;
}
.kpi-value {
    font-size: 28px; font-weight: 800; color: #111827; line-height: 1;
    margin-bottom: 4px; font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 10px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 14px; right: 14px;
    font-size: 20px; opacity: .12;
}

.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 64px 40px;
    background: #FAFBFC; border: 2px dashed #E2EBF0;
    border-radius: 16px; text-align: center;
    animation: cs-fadeup .35s ease;
}
.empty-icon-ring {
    width: 72px; height: 72px; border-radius: 50%;
    background: linear-gradient(145deg,#EFF6FF,#DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 34px; margin-bottom: 18px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 { font-size:16px; font-weight:700; color:#111827; margin:0 0 6px; }
.empty-state-v2 p  { font-size:13px; color:#9CA3AF; max-width:270px; line-height:1.6; margin:0; }

.form-sec-hdr {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* pending section title */
.pending-section-title {
    font-size: 16px; font-weight: 800; color: #1E2938;
    margin: 18px 0 10px; letter-spacing: -.2px;
}

@keyframes cs-fadeup {
    from { opacity:0; transform:translateY(10px); }
    to   { opacity:1; transform:translateY(0); }
}
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _billing_month_str(yr: int, mo: int) -> str:
    return f"{_cal.month_name[mo]} {yr}"


def _months_range(start: date, end: date, max_months: int = 24):
    cur   = start.replace(day=1)
    end_m = end.replace(day=1)
    count = 0
    while cur <= end_m and count < max_months:
        yield (cur.year, cur.month)
        count += 1
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)


def _billing_due_date(yr: int, mo: int, mc_row: dict) -> date:
    """Return the first day on which a billing-month worklog becomes past-due.

    Calendar Month  → 1st of the following month  (Aug → Sep 1)
    Custom cycle    → cycle_start_day of the following month (16th–15th: Jul → Aug 16)
    """
    billing_cycle = (mc_row.get("billing_cycle") or "Calendar Month")
    start_day = 1
    if billing_cycle == "Custom":
        _raw = mc_row.get("billing_cycle_start_date")
        if _raw:
            try:
                start_day = int(str(_raw).split("-")[2])
            except Exception:
                start_day = 1
    next_yr, next_mo = (yr + 1, 1) if mo == 12 else (yr, mo + 1)
    return date(next_yr, next_mo, start_day)


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


def _status_chip(label: str, color: str) -> str:
    palettes = {
        "Missing":         ("#FEE2E2", "#991B1B"),
        "Draft":           ("#FEF3C7", "#92400E"),
        "Submitted":       ("#DCFCE7", "#166534"),
        "Pending Billing": ("#FEF3C7", "#92400E"),
        "Pending":         ("#FEE2E2", "#991B1B"),
    }
    bg, fg = palettes.get(label, ("#F1F5F9", "#374151"))
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;"
        f"border-radius:12px;font-size:11px;font-weight:700;'>{label}</span>"
    )


def _month_to_date(bm_str: str) -> date | None:
    try:
        return datetime.strptime(bm_str, "%B %Y").date()
    except Exception:
        return None


# ── Worklog schedule parser ───────────────────────────────────────────────────

def _parse_wl_schedule(raw) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict):
            if data.get("shift_type") == "double":
                return (data.get("shift1") or []) + (data.get("shift2") or [])
            return data.get("rows") or []
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _billing_snap_from_wl(wl: dict) -> dict | None:
    raw = wl.get("schedule_data")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict):
            return data.get("billing_snapshot")
    except Exception:
        pass
    return None


# ── WL Summary popup dialog ───────────────────────────────────────────────────

@st.dialog("Worklog Summary", width="large")
def _show_wl_summary(pr: dict, wl: dict | None, mach: dict) -> None:
    mc         = pr.get("_mc_row", {})
    asset_code = mach.get("asset_code") or mc.get("machine_label") or "—"
    make_val   = (mach.get("make")  or "").strip()
    model_val  = (mach.get("model") or "").strip()
    make_model = f"{make_val} {model_val}".strip() or "—"
    serial     = mach.get("serial_number") or "—"
    status     = pr.get("Status", "—")

    _SC = {
        "Submitted":       ("#DCFCE7", "#166534"),
        "Draft":           ("#FEF3C7", "#92400E"),
        "Missing":         ("#FEE2E2", "#991B1B"),
        "Invoiced":        ("#EDE9FE", "#5B21B6"),
        "Pending Billing": ("#FEF3C7", "#92400E"),
    }
    s_bg, s_fg = _SC.get(status, ("#F1F5F9", "#374151"))

    # ── Machine banner ────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='background:linear-gradient(135deg,#1E3A5F,#2563EB);"
        f"border-radius:10px;padding:14px 20px;margin-bottom:16px;"
        f"display:flex;justify-content:space-between;align-items:center;'>"
        f"<div>"
        f"<div style='font-size:18px;font-weight:800;color:#fff;'>{asset_code}</div>"
        f"<div style='font-size:12px;color:rgba(255,255,255,.75);margin-top:3px;'>"
        f"{make_model} &nbsp;·&nbsp; S/N: {serial}</div>"
        f"</div>"
        f"<span style='background:{s_bg};color:{s_fg};padding:4px 14px;"
        f"border-radius:20px;font-size:12px;font-weight:700;'>{status}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Deployment info ───────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
            "text-transform:uppercase;color:#9CA3AF;margin-bottom:4px;'>Customer</div>"
            f"<div style='font-size:14px;font-weight:600;color:#111827;'>{pr['Customer']}</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
            "text-transform:uppercase;color:#9CA3AF;margin-bottom:4px;'>Site</div>"
            f"<div style='font-size:14px;font-weight:600;color:#111827;'>{pr['Site']}</div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
            "text-transform:uppercase;color:#9CA3AF;margin-bottom:4px;'>Billing Period</div>"
            f"<div style='font-size:14px;font-weight:700;color:#2563EB;'>{pr['Month']}</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    if wl is None:
        st.info("No worklog recorded for this period.", icon="ℹ️")
        return

    # ── Work summary ──────────────────────────────────────────────────────────
    sched_rows = _parse_wl_schedule(wl.get("schedule_data"))
    snap       = _billing_snap_from_wl(wl)

    net_hrs  = sum(float(r.get("net_time")          or 0) for r in sched_rows)
    ot_hrs   = sum(float(r.get("ot")                or 0) for r in sched_rows)
    bd_hrs   = sum(float(r.get("breakdown_hours")   or 0) for r in sched_rows)
    days_cnt = sum(1 for r in sched_rows if float(r.get("net_time") or 0) > 0)

    # Billing amounts
    rental    = float(mc.get("rental_per_month") or 0)
    ot_rate   = float(wl.get("ot_rate")          or 0)
    deduction = float(wl.get("deduction")         or 0)

    if snap:
        qty      = float(snap.get("qty")      or 0)
        ot_hrs_b = float(snap.get("ot_hours") or ot_hrs)
    else:
        shift_hr = float(mc.get("machine_shift_hour") or 8)
        no_days  = float(mc.get("no_of_days")         or 26)
        work_hrs = no_days * shift_hr
        qty      = round(net_hrs / work_hrs, 3) if work_hrs > 0 else 0.0
        ot_hrs_b = ot_hrs

    hiring       = round(rental * qty, 2)
    ot_amt       = round(ot_hrs_b * ot_rate, 2)
    add_op_qty   = float(wl.get("add_operator_qty")       or 0)
    add_op_rate  = float(wl.get("add_operator_rate")      or 0)
    add_op_amt   = round(add_op_qty * add_op_rate,   2)
    add_acc_qty  = float(wl.get("add_accommodation_qty")  or 0)
    add_acc_rate = float(wl.get("add_accommodation_rate") or 0)
    add_acc_amt  = round(add_acc_qty * add_acc_rate, 2)
    net_pay      = max(0.0, hiring + ot_amt + add_op_amt + add_acc_amt - deduction)

    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        "text-transform:uppercase;color:#6B7280;margin-bottom:10px;'>Work Summary</div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Work Hrs",  f"{net_hrs:.1f} h")
    m2.metric("OT Hours",      f"{ot_hrs:.1f} h")
    m3.metric("Breakdown Hrs", f"{bd_hrs:.1f} h")
    m4.metric("Days Logged",   days_cnt)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Billing breakdown table ───────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        "text-transform:uppercase;color:#6B7280;margin-bottom:10px;'>Billing Breakdown</div>",
        unsafe_allow_html=True,
    )

    def _trow(label: str, rate_str: str, qty_str: str, amount: float,
              bold: bool = False, negative: bool = False) -> str:
        fw  = "800" if bold else "500"
        bg  = "#DFE8F4" if bold else "transparent"
        fg  = "#991B1B" if negative else ("#111827" if not bold else "#1E3A5F")
        bd_top = "border-top:2px solid #E2EBF0;" if bold else ""
        a_str  = f"(₹{abs(amount):,.2f})" if negative else f"₹{amount:,.2f}"
        return (
            f"<tr style='background:{bg};{bd_top}'>"
            f"<td style='padding:8px 12px;font-weight:{fw};color:{fg};'>{label}</td>"
            f"<td style='padding:8px 12px;text-align:right;color:#6B7280;font-size:12px;'>{rate_str}</td>"
            f"<td style='padding:8px 12px;text-align:center;color:#6B7280;font-size:12px;'>{qty_str}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-weight:{fw};color:{fg};'>{a_str}</td>"
            f"</tr>"
        )

    trows = _trow(
        "Hiring Charges",
        f"₹{rental:,.2f} / mo",
        f"{qty:.3f} mo",
        hiring,
    )
    if ot_amt > 0 or ot_rate > 0:
        trows += _trow(
            "OT Charges",
            f"₹{ot_rate:,.2f} / hr",
            f"{ot_hrs_b:.1f} h",
            ot_amt,
        )
    if add_op_amt > 0:
        trows += _trow(
            "Additional Operator",
            f"₹{add_op_rate:,.2f}",
            f"{add_op_qty:.0f}",
            add_op_amt,
        )
    if add_acc_amt > 0:
        trows += _trow(
            "Accommodation",
            f"₹{add_acc_rate:,.2f}",
            f"{add_acc_qty:.0f}",
            add_acc_amt,
        )
    if deduction > 0:
        trows += _trow("Deduction", "—", "—", deduction, negative=True)
    trows += _trow("Net Payable", "", "", net_pay, bold=True)

    hs = (
        "padding:9px 12px;background:#1E3A5F;color:#fff;"
        "font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;"
    )
    st.markdown(
        "<div style='border:1px solid #E2EBF0;border-radius:10px;overflow:hidden;'>"
        "<table style='width:100%;border-collapse:collapse;font-family:inherit;font-size:13px;'>"
        "<thead><tr>"
        f"<th style='{hs}text-align:left;border-radius:10px 0 0 0;'>Description</th>"
        f"<th style='{hs}text-align:right;'>Rate</th>"
        f"<th style='{hs}text-align:center;'>Qty / Hrs</th>"
        f"<th style='{hs}text-align:right;border-radius:0 10px 0 0;'>Amount</th>"
        "</tr></thead>"
        f"<tbody>{trows}</tbody>"
        "</table></div>",
        unsafe_allow_html=True,
    )

    # GST note
    billing_type = mc.get("billing_type", "")
    if billing_type:
        gst_note = {
            "IGST":      "IGST @ 18% applicable",
            "CGST/SGST": "CGST 9% + SGST 9% applicable",
        }.get(billing_type, f"GST: {billing_type}")
        st.markdown(
            f"<div style='margin-top:6px;font-size:11px;color:#9CA3AF;text-align:right;'>"
            f"{gst_note} (not included above)</div>",
            unsafe_allow_html=True,
        )

    # Remarks
    remarks = (wl.get("remarks") or "").strip()
    if remarks:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.info(f"**Remarks:** {remarks}", icon="📝")


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Pending Worklogs</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # ── Load data ──────────────────────────────────────────────────────────────
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
        work_logs      = sb.list_all_worklogs()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    today    = date.today()
    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    mach_map = {m["id"]: m for m in machines if m.get("id")}

    # work_log lookup: (wo_id, machine_id, billing_month_str) → worklog dict
    wl_lookup: dict[tuple[str, str, str], dict] = {}
    for wl in work_logs:
        key = (
            wl.get("work_order_id", ""),
            wl.get("machine_id",    ""),
            wl.get("year",          ""),
        )
        wl_lookup[key] = wl

    # ── Build all rows ─────────────────────────────────────────────────────────
    pending_rows:   list[dict] = []
    completed_rows: list[dict] = []
    mob_rows:       list[dict] = []
    demob_rows:     list[dict] = []

    for wo in work_orders:
        wo_id      = wo.get("id", "")
        customer   = cust_map.get(wo.get("customer_id", ""), "—")
        site       = site_map.get(wo.get("site_id",     ""), "—")
        wo_start   = _parse_date(wo.get("start_date"))
        wo_end     = _parse_date(wo.get("end_date"))

        if not wo_start:
            continue

        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        except Exception:
            continue
        if not isinstance(mc_list, list):
            continue

        for mc_row in mc_list:
            mid       = mc_row.get("machine_id", "")
            mach      = mach_map.get(mid, {})
            asset_code = mach.get("asset_code") or mc_row.get("machine_label") or "—"
            make      = mach.get("make",  "") or mc_row.get("make",  "") or ""
            model     = mach.get("model", "") or mc_row.get("model", "") or ""
            serial_no = mach.get("serial_number") or mc_row.get("serial_number") or "—"
            suffix    = " ".join(p for p in [make, model] if p)
            machine_label = f"{asset_code} — {suffix}" if suffix else asset_code

            mob_cost   = float(mc_row.get("mobilization_cost")   or 0)
            demob_cost = float(mc_row.get("demobilization_cost")  or 0)

            # ── Monthly worklog rows (active WOs only) ────────────────────────
            wo_is_active = (
                wo_start <= today
                and (wo_end is None or wo_end >= today)
            )
            if wo_is_active:
                for yr, mo in _months_range(wo_start, today):
                    bm_str = _billing_month_str(yr, mo)
                    wl     = wl_lookup.get((wo_id, mid, bm_str))

                    if wl is None:
                        status   = "Missing"
                    elif wl.get("is_draft", True):
                        status   = "Draft"
                    elif wl.get("invoiced"):
                        status   = "Invoiced"
                    else:
                        status   = "Submitted"

                    row = {
                        "Customer":        customer,
                        "Site":            site,
                        "Asset Code":      asset_code,
                        "Machine":         machine_label,
                        "Serial No.":      serial_no,
                        "Month":           bm_str,
                        "_date":           date(yr, mo, 1),
                        "Status":          status,
                        "Invoice No.":     wl.get("invoice_number", "") if wl else "",
                        "_wo_id":          wo_id,
                        "_machine_id":     mid,
                        "_customer_id":    wo.get("customer_id", ""),
                        "_yr":             yr,
                        "_mo":             mo,
                        "_mc_row":         mc_row,
                    }

                    if status in ("Missing", "Draft"):
                        _due = _billing_due_date(yr, mo, mc_row)
                        if today >= _due:
                            pending_rows.append(row)
                    elif status == "Invoiced":
                        pass  # exclude from all lists — already billed
                    else:
                        completed_rows.append(row)

            # ── Pending Mobilization ──────────────────────────────────────────
            # Pending once WO has started and mob cost > 0
            if mob_cost > 0 and wo_start <= today:
                mob_rows.append({
                    "Customer":   customer,
                    "Site":       site,
                    "Asset Code": asset_code,
                    "Machine":    machine_label,
                    "Serial No.": serial_no,
                    "WO Start":   wo_start.isoformat(),
                    "_date":      wo_start,
                    "Amount (₹)": mob_cost,
                    "Status":     "Pending",
                    "_wo_id":     wo_id,
                    "_machine_id":mid,
                })

            # ── Pending De-Mobilization ───────────────────────────────────────
            # Pending once WO end date has passed and demob cost > 0
            if demob_cost > 0 and wo_end and wo_end <= today:
                demob_rows.append({
                    "Customer":   customer,
                    "Site":       site,
                    "Asset Code": asset_code,
                    "Machine":    machine_label,
                    "Serial No.": serial_no,
                    "WO End":     wo_end.isoformat(),
                    "_date":      wo_end,
                    "Amount (₹)": demob_cost,
                    "Status":     "Pending",
                    "_wo_id":     wo_id,
                    "_machine_id":mid,
                })

    # Sort
    pending_rows.sort(key=lambda r: (r["_yr"], r["_mo"]))
    completed_rows.sort(key=lambda r: (r["_yr"], r["_mo"]), reverse=True)
    mob_rows.sort(key=lambda r: r["_date"])
    demob_rows.sort(key=lambda r: r["_date"])

    # ── Global Filters ─────────────────────────────────────────────────────────
    all_custs  = sorted({r["Customer"]   for r in pending_rows + completed_rows + mob_rows + demob_rows if r["Customer"]   != "—"})
    all_sites  = sorted({r["Site"]       for r in pending_rows + completed_rows + mob_rows + demob_rows if r["Site"]       != "—"})
    all_assets = sorted({r["Asset Code"] for r in pending_rows + completed_rows + mob_rows + demob_rows if r["Asset Code"] != "—"})

    with st.container(border=True):
        _section_hdr("tune", "Filters")
        fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2, 2, 2, 1])

        with fc1:
            sel_cust  = st.multiselect("Customer", all_custs,  key="wlr_cust",  placeholder="All")
        with fc2:
            sel_site  = st.multiselect("Site",      all_sites,  key="wlr_site",  placeholder="All")
        with fc3:
            sel_mach  = st.multiselect("Machine",   all_assets, key="wlr_mach",  placeholder="All")
        with fc4:
            all_dates = [r["_date"] for r in pending_rows + completed_rows + mob_rows + demob_rows if r.get("_date")]
            min_d = min(all_dates) if all_dates else date.today()
            max_d = date.today()
            sel_from = st.date_input("Date From", value=min_d, key="wlr_from")
        with fc5:
            sel_to   = st.date_input("Date To",   value=max_d, key="wlr_to")
        with fc6:
            st.markdown("<div></div>", unsafe_allow_html=True)
        with fc7:
            st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
            if st.button("Clear", key="wlr_clear"):
                for k in ["wlr_cust","wlr_site","wlr_mach","wlr_from","wlr_to"]:
                    st.session_state.pop(k, None)
                st.rerun()

    def _apply_filters(rows: list[dict]) -> list[dict]:
        out = rows
        if sel_cust:
            out = [r for r in out if r["Customer"] in sel_cust]
        if sel_site:
            out = [r for r in out if r["Site"] in sel_site]
        if sel_mach:
            out = [r for r in out if r["Asset Code"] in sel_mach]
        if sel_from and sel_to and sel_from <= sel_to:
            out = [r for r in out if r.get("_date") and sel_from <= r["_date"] <= sel_to]
        return out

    f_pending   = _apply_filters(pending_rows)
    f_completed = _apply_filters(completed_rows)
    f_mob       = _apply_filters(mob_rows)
    f_demob     = _apply_filters(demob_rows)

    # ── KPI strip ──────────────────────────────────────────────────────────────
    n_missing   = sum(1 for r in f_pending if r["Status"] == "Missing")
    n_draft     = sum(1 for r in f_pending if r["Status"] == "Draft")

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='kpi-grid-6'>"
        + _kpi_card("pending",      "Pending WL",     len(f_pending),
                    "missing or draft",   "#EF4444")
        + _kpi_card("warning",      "Missing",        n_missing,
                    "no worklog yet",     "#F59E0B")
        + _kpi_card("edit_note",    "Draft",          n_draft,
                    "saved, not submitted","#E87722")
        + _kpi_card("task_alt",     "Submitted",      len(f_completed),
                    "completed worklogs", "#10B981")
        + _kpi_card("local_shipping","Pending Mob",   len(f_mob),
                    "mobilization due",   "#8B5CF6")
        + _kpi_card("local_shipping","Pending Demob", len(f_demob),
                    "de-mobilization due","#6366F1")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Tabs ───────────────────────────────────────────────────────────────────
    n_pending_all = len(f_pending) + len(f_mob) + len(f_demob)
    tab_pending, tab_completed, tab_billing = st.tabs([
        f"Pending ({n_pending_all})",
        f"Completed ({len(f_completed)})",
        f"Pending for Billing ({len(f_completed)})",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — PENDING
    # ══════════════════════════════════════════════════════════════════════════
    with tab_pending:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        # ── Pending Worklogs section ──────────────────────────────────────────
        st.markdown(
            "<div class='pending-section-title'>Pending Monthly Worklogs</div>",
            unsafe_allow_html=True,
        )

        if not f_pending:
            st.markdown(
                "<div class='empty-state-v2' style='padding:36px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:34px;color:#2563EB;'>task_alt</span>"
                "</div>"
                "<h3>All worklogs up to date</h3>"
                "<p>No missing or draft worklogs for the selected filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            # Sub-filter: current month only toggle
            show_all = st.checkbox(
                "Show all months (including prior)",
                value=False,
                key="wlr_show_all",
            )
            cur_bm  = _billing_month_str(today.year, today.month)
            display = f_pending if show_all else [r for r in f_pending if r["Month"] == cur_bm]

            if not display and not show_all:
                st.info(f"No pending worklogs for {cur_bm}. Enable 'Show all months' to see prior months.")
            else:
                _WL_COLS = ["Customer", "Site", "Machine", "Serial No.", "Month", "Status"]
                pdf = pd.DataFrame([{k: r[k] for k in _WL_COLS} for r in display], columns=_WL_COLS)

                def _pstyle(col):
                    if col.name != "Status":
                        return [""] * len(col)
                    return [
                        ("color:#ef4444;font-weight:700;" if v == "Missing"
                         else "color:#E87722;font-weight:700;" if v == "Draft"
                         else "")
                        for v in col
                    ]

                with st.container(border=True):
                    _pend_idx = render_drilldown_table(
                        pdf,
                        "wlr_pend_tbl",
                        column_config={
                            "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                            "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                            "Month":      st.column_config.TextColumn("Month",      width="small"),
                            "Status":     st.column_config.TextColumn("Status",     width="small"),
                        },
                        style_fn=lambda s: s.apply(_pstyle, axis=0),
                    )

                if _pend_idx is not None and _pend_idx < len(display):
                    _pr = display[_pend_idx]
                    st.markdown(
                        f"<div style='margin-top:10px;padding:9px 14px;"
                        f"background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
                        f"font-size:13px;color:#1E40AF;'>"
                        f"Selected: <strong>{_pr['Machine']}</strong> &bull; "
                        f"<strong>{_pr['Month']}</strong> &bull; {_pr['Status']}</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "✏️ Open Worklog →",
                        key="wlr_pend_open_wl",
                        type="primary",
                        help="Open this worklog for entry / editing",
                    ):
                        _cid = _pr["_customer_id"]
                        _valid_yrs = [today.year - 1, today.year, today.year + 1]
                        st.session_state["wl_selected_customer_id"] = _cid
                        st.session_state["_wl_prev_customer"]        = _cid
                        st.session_state["wl_selected_wo_id"]        = _pr["_wo_id"]
                        st.session_state.pop("wl_selected_machine", None)
                        st.session_state["wl_selected_month"]        = _cal.month_name[_pr["_mo"]]
                        if _pr["_yr"] in _valid_yrs:
                            st.session_state["wl_selected_year"] = _pr["_yr"]
                        st.query_params["page"] = "worklog"
                        st.rerun()

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Missing",  sum(1 for r in display if r["Status"] == "Missing"))
                m2.metric("Draft",    sum(1 for r in display if r["Status"] == "Draft"))
                m3.metric("Machines", len({r["_machine_id"] for r in display}))
                m4.metric("Customers", len({r["Customer"] for r in display}))

                render_export_buttons(
                    pdf, "pending_worklogs",
                    "wlr_pend_xl", "wlr_pend_pdf", "Pending Worklogs",
                )

        # ── Pending Mobilization section ──────────────────────────────────────
        st.markdown(
            "<div class='pending-section-title'>Pending Mobilization</div>",
            unsafe_allow_html=True,
        )

        if not f_mob:
            st.markdown(
                "<div style='padding:16px;background:#F8FAFC;border:1px solid #E2EBF0;"
                "border-radius:10px;font-size:13px;color:#6B7280;'>"
                "No pending mobilization charges for the selected filters.</div>",
                unsafe_allow_html=True,
            )
        else:
            _MOB_COLS = ["Customer", "Site", "Machine", "Serial No.", "WO Start", "Amount (₹)", "Status"]
            mob_df = pd.DataFrame([{k: r[k] for k in _MOB_COLS} for r in f_mob], columns=_MOB_COLS)

            with st.container(border=True):
                st.dataframe(
                    mob_df.style
                    .map(lambda v: "color:#991B1B;font-weight:700;", subset=["Status"])
                    .format({"Amount (₹)": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "WO Start":   st.column_config.TextColumn("WO Start",   width="small"),
                        "Amount (₹)": st.column_config.NumberColumn("Amount (₹)", format="₹%,.0f"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                )

            ma1, ma2 = st.columns(2)
            ma1.metric("Machines Pending Mob",  len(f_mob))
            ma2.metric("Total Mob Amount (₹)", f"{sum(r['Amount (₹)'] for r in f_mob):,.0f}")

        # ── Pending De-Mobilization section ───────────────────────────────────
        st.markdown(
            "<div class='pending-section-title'>Pending De-Mobilization</div>",
            unsafe_allow_html=True,
        )

        if not f_demob:
            st.markdown(
                "<div style='padding:16px;background:#F8FAFC;border:1px solid #E2EBF0;"
                "border-radius:10px;font-size:13px;color:#6B7280;'>"
                "No pending de-mobilization charges for the selected filters.</div>",
                unsafe_allow_html=True,
            )
        else:
            _DEMOB_COLS = ["Customer", "Site", "Machine", "Serial No.", "WO End", "Amount (₹)", "Status"]
            demob_df = pd.DataFrame([{k: r[k] for k in _DEMOB_COLS} for r in f_demob], columns=_DEMOB_COLS)

            with st.container(border=True):
                st.dataframe(
                    demob_df.style
                    .map(lambda v: "color:#991B1B;font-weight:700;", subset=["Status"])
                    .format({"Amount (₹)": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "WO End":     st.column_config.TextColumn("WO End",     width="small"),
                        "Amount (₹)": st.column_config.NumberColumn("Amount (₹)", format="₹%,.0f"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                )

            da1, da2 = st.columns(2)
            da1.metric("Machines Pending Demob",  len(f_demob))
            da2.metric("Total Demob Amount (₹)", f"{sum(r['Amount (₹)'] for r in f_demob):,.0f}")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — COMPLETED WORKLOGS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_completed:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        if not f_completed:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:34px;color:#2563EB;'>assignment</span>"
                "</div>"
                "<h3>No completed worklogs</h3>"
                "<p>No submitted worklogs match the selected filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            available_months = sorted(
                {r["Month"] for r in f_completed},
                key=lambda s: datetime.strptime(s, "%B %Y"),
                reverse=True,
            )
            with st.container(border=True):
                _section_hdr("tune", "Month Filter")
                fp1, _ = st.columns([2, 6])
                with fp1:
                    sel_month = st.multiselect(
                        "Month", available_months,
                        label_visibility="collapsed",
                        key="wlr_comp_month",
                        placeholder="All",
                    )

            display = (
                f_completed if not sel_month
                else [r for r in f_completed if r["Month"] in sel_month]
            )

            _COMP_COLS = ["Customer", "Site", "Machine", "Serial No.", "Month", "Status"]
            cdf = pd.DataFrame([{k: r[k] for k in _COMP_COLS} for r in display], columns=_COMP_COLS)

            with st.container(border=True):
                _section_hdr("task_alt", "Completed Worklogs")
                _comp_idx = render_drilldown_table(
                    cdf,
                    "wlr_comp_tbl",
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "Month":      st.column_config.TextColumn("Month",      width="small"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                    style_fn=lambda s: s.apply(
                        lambda col: (
                            ["color:#16a34a;font-weight:700;"] * len(col)
                            if col.name == "Status" else [""] * len(col)
                        ),
                        axis=0,
                    ),
                )

            if _comp_idx is not None and _comp_idx < len(display):
                _cr = display[_comp_idx]
                st.markdown(
                    f"<div style='margin-top:10px;padding:9px 14px;"
                    f"background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;"
                    f"font-size:13px;color:#166534;'>"
                    f"Selected: <strong>{_cr['Machine']}</strong> &bull; "
                    f"<strong>{_cr['Month']}</strong> &bull; {_cr['Status']}</div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "✏️ Open Worklog →",
                    key="wlr_comp_open_wl",
                    type="primary",
                    help="Open this worklog for viewing",
                ):
                    _cid = _cr["_customer_id"]
                    _valid_yrs = [today.year - 1, today.year, today.year + 1]
                    st.session_state["wl_selected_customer_id"] = _cid
                    st.session_state["_wl_prev_customer"]        = _cid
                    st.session_state["wl_selected_wo_id"]        = _cr["_wo_id"]
                    st.session_state.pop("wl_selected_machine", None)
                    st.session_state["wl_selected_month"]        = _cal.month_name[_cr["_mo"]]
                    if _cr["_yr"] in _valid_yrs:
                        st.session_state["wl_selected_year"] = _cr["_yr"]
                    st.query_params["page"] = "worklog"
                    st.rerun()

            render_export_buttons(
                cdf, "completed_worklogs",
                "wlr_comp_xl", "wlr_comp_pdf", "Completed Worklogs",
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — PENDING FOR BILLING
    # ══════════════════════════════════════════════════════════════════════════
    with tab_billing:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;"
            "padding:12px 16px;margin-bottom:14px;font-size:13px;color:#1E40AF;"
            "display:flex;align-items:center;gap:8px;'>"
            "<span class='msr' style='font-size:18px;'>info</span>"
            "Showing all submitted worklogs — these are pending invoice generation.</div>",
            unsafe_allow_html=True,
        )

        if not f_completed:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:34px;color:#2563EB;'>receipt_long</span>"
                "</div>"
                "<h3>No worklogs pending billing</h3>"
                "<p>No submitted worklogs match the selected filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            avail_b = sorted(
                {r["Month"] for r in f_completed},
                key=lambda s: datetime.strptime(s, "%B %Y"),
                reverse=True,
            )
            with st.container(border=True):
                _section_hdr("tune", "Month Filter")
                fp2, _ = st.columns([2, 6])
                with fp2:
                    sel_b = st.multiselect(
                        "Month", avail_b,
                        label_visibility="collapsed",
                        key="wlr_bill_month",
                        placeholder="All",
                    )

            billing_display = (
                f_completed if not sel_b
                else [r for r in f_completed if r["Month"] in sel_b]
            )

            _BILL_COLS = ["Customer", "Site", "Machine", "Serial No.", "Month", "Status"]
            bdf = pd.DataFrame([{k: r[k] for k in _BILL_COLS} for r in billing_display], columns=_BILL_COLS)
            bdf["Status"] = "Pending Billing"

            with st.container(border=True):
                _section_hdr("receipt_long", "Pending for Billing")
                st.caption("Click any row to view its Worklog Summary")
                _bill_idx = render_drilldown_table(
                    bdf,
                    "wlr_bill_tbl",
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "Month":      st.column_config.TextColumn("Month",      width="small"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                    style_fn=lambda s: s.apply(
                        lambda col: (
                            ["color:#E87722;font-weight:700;"] * len(col)
                            if col.name == "Status" else [""] * len(col)
                        ),
                        axis=0,
                    ),
                )

            # Popup on row click — opens on first click; "Re-open" button after dismiss
            _prev_bill_idx = st.session_state.get("_wlr_prev_bill_idx")
            if _bill_idx is not None and _bill_idx < len(billing_display):
                _br   = billing_display[_bill_idx]
                _wl   = wl_lookup.get((_br["_wo_id"], _br["_machine_id"], _br["Month"]))
                _mach = mach_map.get(_br["_machine_id"], {})
                if _bill_idx != _prev_bill_idx:
                    st.session_state["_wlr_prev_bill_idx"] = _bill_idx
                    _show_wl_summary(_br, _wl, _mach)
                else:
                    if st.button("📋 View WL Summary", key="wlr_bill_reopen",
                                 help="Re-open the summary for the selected row"):
                        _show_wl_summary(_br, _wl, _mach)
            elif _bill_idx is None:
                st.session_state["_wlr_prev_bill_idx"] = None

            b1, b2 = st.columns(2)
            b1.metric("Worklogs Pending Billing", len(billing_display))
            b2.metric("Machines Affected", len({r["_machine_id"] for r in billing_display}))

            render_export_buttons(
                bdf, "pending_billing",
                "wlr_bill_xl", "wlr_bill_pdf", "Pending for Billing",
            )

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    if st.button("Refresh Data", key="wlr_refresh"):
        st.rerun()
