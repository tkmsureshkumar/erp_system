"""
erp/views/dashboard.py
Fleet Dashboard — Fleet KPIs and Revenue Run Rate.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
import calendar as _cal

import streamlit as st

from ..supabase_client import SupabaseClient


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


def _mc_rental_total(raw) -> float:
    """Sum rental_per_month across all machines in a WO's machine_config JSON."""
    if not raw:
        return 0.0
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(records, list):
            return sum(float(r.get("rental_per_month") or 0) for r in records)
    except Exception:
        pass
    return 0.0


def _rr_for_period(work_orders: list[dict], period_start: date, period_end: date) -> float:
    """Sum rental values of all WOs active during [period_start, period_end].

    A WO is active in the period when:
      start_date <= period_end  AND  (end_date is None OR end_date >= period_start)
    This intentionally avoids touching work_logs / billing — RR is purely
    derived from active WO rental rates.
    """
    total = 0.0
    for wo in work_orders:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd is None:
            continue
        if sd <= period_end and (ed is None or ed >= period_start):
            total += _mc_rental_total(wo.get("machine_config"))
    return total


def _metric_card(label: str, value, color: str, icon: str, subtitle: str = "") -> str:
    sub_html = (
        f"<div style='font-size:11px;color:#9ca3af;margin-top:6px;"
        f"font-weight:500;'>{subtitle}</div>"
        if subtitle else ""
    )
    return (
        f"<div class='metric-card'>"
        f"<div class='metric-label'>{label}</div>"
        f"<div class='metric-value' style='color:{color};'>{value}</div>"
        f"{sub_html}"
        f"<div class='metric-icon' style='color:{color};'>{icon}</div>"
        f"</div>"
    )


def _rr_card(label: str, amount: float, accent: bool = False,
             delta: float | None = None, delta_pct: float | None = None,
             prev_label: str = "") -> str:
    border_top  = "3px solid #E87722" if accent else "1px solid #e5e7eb"
    val_size    = "30px" if accent else "24px"
    val_weight  = "800" if accent else "700"
    amount_str  = f"&#8377; {amount:,.0f}"

    delta_html = ""
    if delta is not None and delta_pct is not None:
        arrow       = "&#8593;" if delta >= 0 else "&#8595;"
        clr         = "#006300" if delta >= 0 else "#d03b3b"
        sign        = "+" if delta >= 0 else ""
        delta_html  = (
            f"<div style='margin-top:10px;font-size:13px;font-weight:700;color:{clr};'>"
            f"{arrow}&nbsp;{sign}{delta_pct:.1f}%"
            f"<span style='font-size:11px;font-weight:500;color:#9ca3af;margin-left:8px;'>"
            f"vs {prev_label}</span></div>"
        )

    return (
        f"<div style='background:#fff;border:1px solid #e5e7eb;border-top:{border_top};"
        f"border-radius:6px;padding:20px 24px;box-shadow:0 1px 4px rgba(0,0,0,.06);"
        f"min-height:110px;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#9ca3af;margin-bottom:10px;'>{label}</div>"
        f"<div style='font-size:{val_size};font-weight:{val_weight};color:#111827;"
        f"font-variant-numeric:tabular-nums;line-height:1;'>{amount_str}</div>"
        f"{delta_html}"
        f"</div>"
    )


def _section_header(title: str) -> None:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:14px;'>"
        f"{title}</div>",
        unsafe_allow_html=True,
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    # ── Page header ──────────────────────────────────────────────────────────
    col_head, col_btn = st.columns([6, 1])
    with col_head:
        st.markdown(
            "<div class='page-eyebrow'>// Access Fleet Operations</div>"
            "<div class='page-title'>Fleet Dashboard</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        st.markdown(
            '<a href="?page=machines" target="_self" class="btn-orange">+ ADD MACHINE</a>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # ── Load data ────────────────────────────────────────────────────────────
    machines:       list[dict] = []
    customers_list: list[dict] = []
    work_orders:    list[dict] = []
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        customers_list = sb.list_customers()
        work_orders    = sb.list_work_orders()
    except Exception as exc:
        st.error(f"Could not connect to Supabase: {exc}")
        return

    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}

    # ── Fleet counts ─────────────────────────────────────────────────────────
    total      = len(machines)
    on_rent    = sum(1 for m in machines if m.get("operational_status") == "On Rent")
    idle       = sum(1 for m in machines if m.get("operational_status") == "Available")
    breakdown  = sum(1 for m in machines if m.get("condition_status")   == "Breakdown")
    in_transit = sum(1 for m in machines
                     if m.get("operational_status") in ("Mobilizing", "Demobilizing"))
    reserved   = sum(1 for m in machines if m.get("operational_status") == "Reserved")
    utilization = round(on_rent / total * 100, 1) if total else 0.0

    # ── Revenue Run Rate ─────────────────────────────────────────────────────
    today      = date.today()
    cur_first  = today.replace(day=1)
    cur_last   = today.replace(day=_cal.monthrange(today.year, today.month)[1])
    prev_last  = cur_first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    prev_label = prev_last.strftime("%b %Y")

    rr_cur     = _rr_for_period(work_orders, cur_first,  cur_last)
    rr_prev    = _rr_for_period(work_orders, prev_first, prev_last)
    rr_delta   = rr_cur - rr_prev
    rr_delta_pct = (rr_delta / rr_prev * 100) if rr_prev else 0.0

    # ════════════════════════════════════════════════════════════════════
    # FLEET OVERVIEW
    # ════════════════════════════════════════════════════════════════════
    _section_header("Fleet Overview")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_metric_card("Total Fleet",  total,    "#111827", "&#9782;"),   unsafe_allow_html=True)
    with c2:
        st.markdown(_metric_card("On Rent",      on_rent,  "#2563eb", "&#9146;"),   unsafe_allow_html=True)
    with c3:
        st.markdown(_metric_card("Idle",         idle,     "#16a34a", "&#9711;"),   unsafe_allow_html=True)
    with c4:
        st.markdown(_metric_card("Reserved",     reserved, "#7c3aed", "&#128204;"), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    c5, c6, c7, _ = st.columns(4)
    with c5:
        st.markdown(_metric_card("Breakdown",  breakdown,  "#ef4444", "&#9651;"),   unsafe_allow_html=True)
    with c6:
        st.markdown(_metric_card("In Transit", in_transit, "#E87722", "&#128666;"), unsafe_allow_html=True)
    with c7:
        st.markdown(
            _metric_card(
                "Fleet Utilization", f"{utilization}%", "#2563eb", "&#128200;",
                subtitle=f"{on_rent} of {total} on rent",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # REVENUE RUN RATE
    # ════════════════════════════════════════════════════════════════════
    _section_header("Revenue Run Rate")

    rr1, rr2, rr3 = st.columns(3)

    with rr1:
        st.markdown(
            _rr_card(
                f"Current RR — {today.strftime('%b %Y')}",
                rr_cur,
                accent=True,
                delta=rr_delta,
                delta_pct=rr_delta_pct,
                prev_label=prev_label,
            ),
            unsafe_allow_html=True,
        )

    with rr2:
        st.markdown(
            _rr_card(f"Previous Month — {prev_label}", rr_prev),
            unsafe_allow_html=True,
        )

    with rr3:
        arrow      = "&#8593;" if rr_delta >= 0 else "&#8595;"
        clr        = "#006300" if rr_delta >= 0 else "#d03b3b"
        sign       = "+" if rr_delta >= 0 else ""
        st.markdown(
            f"<div style='background:#fff;border:1px solid #e5e7eb;border-radius:6px;"
            f"padding:20px 24px;box-shadow:0 1px 4px rgba(0,0,0,.06);min-height:110px;'>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
            f"text-transform:uppercase;color:#9ca3af;margin-bottom:10px;'>"
            f"Month-on-Month Change</div>"
            f"<div style='font-size:30px;font-weight:800;color:{clr};"
            f"font-variant-numeric:tabular-nums;line-height:1;'>"
            f"{arrow}&nbsp;{sign}{rr_delta_pct:.1f}%</div>"
            f"<div style='font-size:12px;color:#6b7280;margin-top:8px;'>"
            f"&#8377;&nbsp;{sign}{rr_delta:,.0f} vs {prev_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # MACHINE FLEET TABLE
    # ════════════════════════════════════════════════════════════════════
    _section_header("Machine Fleet")

    cf1, cf2 = st.columns(2)
    with cf1:
        st.markdown('<p class="filter-label">Customer</p>', unsafe_allow_html=True)
        cust_opts = ["All"] + sorted(
            c.get("customer_name", "") for c in customers_list if c.get("customer_name")
        )
        sel_cust = st.selectbox(
            "Customer", cust_opts, label_visibility="collapsed", key="dash_customer"
        )
    with cf2:
        st.markdown('<p class="filter-label">Location</p>', unsafe_allow_html=True)
        locs     = sorted({m.get("current_location", "") for m in machines if m.get("current_location")})
        sel_loc  = st.selectbox(
            "Location", ["All"] + locs, label_visibility="collapsed", key="dash_location"
        )

    filtered = machines
    if sel_cust != "All":
        cid      = next((c["id"] for c in customers_list if c.get("customer_name") == sel_cust), None)
        if cid:
            filtered = [m for m in filtered if m.get("current_customer_id") == cid]
    if sel_loc != "All":
        filtered = [m for m in filtered if m.get("current_location") == sel_loc]

    if filtered:
        st.dataframe(
            [
                {
                    "Asset Code":  m.get("asset_code", ""),
                    "Type":        m.get("machine_type", ""),
                    "Operational": m.get("operational_status", ""),
                    "Condition":   m.get("condition_status", ""),
                    "Location":    m.get("current_location", "—"),
                    "Customer":    cust_map.get(m.get("current_customer_id", ""), "—"),
                }
                for m in filtered
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No machines match the selected filters.")
