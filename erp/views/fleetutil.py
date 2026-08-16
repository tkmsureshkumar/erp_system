"""
erp/views/fleetutil.py
Fleet Utilization Report — day-level breakdown by operational status.

Utilization (%) = Rental Days ÷ Total Days × 100
Total Days      = Rental + Transit + Available (Available absorbs Idle and Reserved
                  since those cannot be tracked historically without a status-change log)

Breakdowns are NOT part of this report — they are recorded through Worklogs
and should be analysed in the Worklog / Breakdown report.
"""
from __future__ import annotations

import calendar as _cal
import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient
from ._report_utils import render_export_buttons, style_utilisation_col, style_op_status_col


# ── Page CSS ──────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin: 0 0 22px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 16px 18px 12px;
    position: relative;
    overflow: hidden;
}
.kpi-accent-bar {
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 8px;
}
.kpi-value {
    font-size: 30px; font-weight: 800;
    color: #111827; line-height: 1; margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 11px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 14px; right: 16px;
    font-size: 22px; opacity: .10;
}
.period-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 18px 20px 14px;
    position: relative; overflow: hidden;
    min-height: 105px;
}
.period-card-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 8px;
}
.period-card-value {
    font-size: 30px; font-weight: 800; line-height: 1;
    font-variant-numeric: tabular-nums; margin-bottom: 5px;
}
.period-card-sub { font-size: 11px; color: #6B7280; }
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 52px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px;
    text-align: center;
}
.empty-icon-ring {
    width: 64px; height: 64px; border-radius: 50%;
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 30px; margin-bottom: 16px;
}
.empty-state-v2 h3 { font-size: 15px; font-weight: 700; color: #111827; margin: 0 0 6px; }
.empty-state-v2 p  { font-size: 12px; color: #9CA3AF; max-width: 260px; line-height: 1.6; margin: 0; }
.info-note {
    background: #EFF6FF; border: 1px solid #BFDBFE;
    border-radius: 10px; padding: 14px 18px;
    display: flex; gap: 10px; align-items: flex-start;
    font-size: 12px; color: #1E40AF; line-height: 1.6;
    margin-top: 20px;
}
.info-note-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
/* status badges */
.st-available { background:#DCFCE7; color:#166534; padding:2px 10px; border-radius:99px;
                font-size:11px; font-weight:600; white-space:nowrap; }
.st-on-rent   { background:#DBEAFE; color:#1E40AF; padding:2px 10px; border-radius:99px;
                font-size:11px; font-weight:600; white-space:nowrap; }
.st-reserved  { background:#FEF3C7; color:#92400E; padding:2px 10px; border-radius:99px;
                font-size:11px; font-weight:600; white-space:nowrap; }
.st-transit   { background:#EDE9FE; color:#5B21B6; padding:2px 10px; border-radius:99px;
                font-size:11px; font-weight:600; white-space:nowrap; }
.st-sold      { background:#F3F4F6; color:#374151; padding:2px 10px; border-radius:99px;
                font-size:11px; font-weight:600; white-space:nowrap; }
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""

# ── Operational status options (no Breakdown — that is a condition, not operational status) ──
_OP_STATUS_OPTIONS = ["Available", "On Rent", "Reserved", "In Transit", "Sold"]


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


def _merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_iv[0]]
    for start, end in sorted_iv[1:]:
        if start <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _rental_days_in_period(
    wo_list: list[dict],
    period_start: date,
    period_end: date,
) -> int:
    intervals: list[tuple[date, date]] = []
    for wo in wo_list:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date")) or period_end
        if sd is None:
            continue
        ov_s = max(sd, period_start)
        ov_e = min(ed, period_end)
        if ov_s <= ov_e:
            intervals.append((ov_s, ov_e))
    total = 0
    for s, e in _merge_intervals(intervals):
        total += (e - s).days + 1
    return total


def _transit_days_in_period(
    movement_dates: list[date],
    period_start: date,
    period_end: date,
) -> int:
    return sum(
        1 for d in set(movement_dates)
        if period_start <= d <= period_end
    )


def _machine_stats(
    machine_id: str,
    wo_by_machine: dict[str, list[dict]],
    moves_by_machine: dict[str, list[date]],
    period_start: date,
    period_end: date,
) -> dict:
    total_days   = (period_end - period_start).days + 1
    rental_days  = min(
        _rental_days_in_period(wo_by_machine.get(machine_id, []), period_start, period_end),
        total_days,
    )
    transit_days = min(
        _transit_days_in_period(moves_by_machine.get(machine_id, []), period_start, period_end),
        total_days - rental_days,
    )
    avail_days   = max(0, total_days - rental_days - transit_days)
    util_pct     = round(rental_days / total_days * 100, 1) if total_days else 0.0
    return {
        "total_days":   total_days,
        "rental_days":  rental_days,
        "transit_days": transit_days,
        "avail_days":   avail_days,
        "util_pct":     util_pct,
    }


def _fleet_rental_util(
    machines: list[dict],
    wo_by_machine: dict[str, list[dict]],
    moves_by_machine: dict[str, list[date]],
    period_start: date,
    period_end: date,
) -> dict:
    fleet_rental = 0
    fleet_total  = 0
    for m in machines:
        s = _machine_stats(m.get("id", ""), wo_by_machine, moves_by_machine, period_start, period_end)
        fleet_rental += s["rental_days"]
        fleet_total  += s["total_days"]
    util_pct = round(fleet_rental / fleet_total * 100, 1) if fleet_total else 0.0
    return {
        "num_machines": len(machines),
        "rental_days":  fleet_rental,
        "avail_days":   fleet_total - fleet_rental,
        "total_days":   fleet_total,
        "util_pct":     util_pct,
    }


def _status_badge(status: str) -> str:
    cls_map = {
        "Available": "st-available",
        "On Rent":   "st-on-rent",
        "Reserved":  "st-reserved",
        "In Transit":     "st-transit",
        "Mobilizing":     "st-transit",
        "Demobilizing":   "st-transit",
        "Sold":      "st-sold",
    }
    cls = cls_map.get(status, "st-available")
    label = "In Transit" if status in ("Mobilizing", "Demobilizing") else status
    return f"<span class='{cls}'>{label}</span>"


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


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


def _period_card(
    label: str,
    util_pct: float,
    rental: int,
    total: int,
    accent: str = "#6B7280",
    featured: bool = False,
) -> str:
    clr = "#2563EB" if util_pct >= 75 else "#E87722" if util_pct >= 50 else "#EF4444"
    val_size = "36px" if featured else "28px"
    return (
        f"<div class='period-card'>"
        f"<div style='position:absolute;top:0;left:0;right:0;height:3px;"
        f"background:{accent};border-radius:12px 12px 0 0;'></div>"
        f"<div class='period-card-label'>{label}</div>"
        f"<div class='period-card-value' style='color:{clr};font-size:{val_size};'>"
        f"{util_pct:.1f}%</div>"
        f"<div class='period-card-sub'>"
        f"{rental:,} rental days &nbsp;/&nbsp; {total:,} fleet-days</div>"
        f"</div>"
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Fleet Utilization</div>"
        "<div style='font-size:13px;color:#6B7280;margin-top:4px;margin-bottom:28px;'>"
        "Rental, transit and availability days per machine. "
        "Breakdowns are excluded — see Worklog Report for breakdown analysis.</div>",
        unsafe_allow_html=True,
    )

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    try:
        all_movements = sb.list_machine_movements()
    except Exception:
        all_movements = []

    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}

    # ── Build machine → WOs map ───────────────────────────────────────────────
    wo_by_machine: dict[str, list[dict]] = {}
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
        for mc_row in mc_list:
            mid = mc_row.get("machine_id")
            if mid:
                wo_by_machine.setdefault(mid, []).append(wo)

    # ── Build machine → movement dates map ───────────────────────────────────
    moves_by_machine: dict[str, list[date]] = {}
    for mv in all_movements:
        mid = mv.get("machine_id")
        md  = _parse_date(mv.get("movement_date"))
        if mid and md:
            moves_by_machine.setdefault(mid, []).append(md)

    # ── Period constants ──────────────────────────────────────────────────────
    today      = date.today()
    cur_first  = today.replace(day=1)
    cur_last   = today.replace(day=_cal.monthrange(today.year, today.month)[1])
    prev_last  = cur_first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    ytd_first  = today.replace(month=1, day=1)

    # ── Live fleet status counts (active fleet only — excludes Sold) ─────────
    active_machines = [m for m in machines if m.get("operational_status") != "Sold"]
    n_total     = len(active_machines)
    n_on_rent   = sum(1 for m in active_machines if m.get("operational_status") == "On Rent")
    n_available = sum(1 for m in active_machines if m.get("operational_status") == "Available")
    n_reserved  = sum(1 for m in active_machines if m.get("operational_status") == "Reserved")
    n_transit   = sum(1 for m in active_machines
                      if m.get("operational_status") in ("In Transit", "Mobilizing", "Demobilizing"))
    n_sold      = sum(1 for m in machines if m.get("operational_status") == "Sold")

    # ── Period stats ──────────────────────────────────────────────────────────
    s_cur  = _fleet_rental_util(machines, wo_by_machine, moves_by_machine, cur_first,  cur_last)
    s_prev = _fleet_rental_util(machines, wo_by_machine, moves_by_machine, prev_first, prev_last)
    s_ytd  = _fleet_rental_util(machines, wo_by_machine, moves_by_machine, ytd_first,  today)

    # ════════════════════════════════════════════════════════════════════
    # KPI STRIP  — current fleet snapshot
    # ════════════════════════════════════════════════════════════════════
    st.markdown(
        "<div class='kpi-grid'>"
        + _kpi_card("speed", "Fleet Utilization",
                    f"{s_cur['util_pct']:.1f}%",
                    f"current month · {today.strftime('%b %Y')}", "#2563EB")
        + _kpi_card("handshake", "On Rent",
                    n_on_rent, f"of {n_total} machines", "#10B981")
        + _kpi_card("inventory_2", "Available",
                    n_available, "ready to deploy", "#6B7280")
        + _kpi_card("local_shipping", "In Transit",
                    n_transit, "mobilizing / demobilizing", "#8B5CF6")
        + _kpi_card("bookmark", "Reserved",
                    n_reserved, "confirmed bookings", "#F59E0B")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ════════════════════════════════════════════════════════════════════
    # PERIOD COMPARISON
    # ════════════════════════════════════════════════════════════════════
    with st.container(border=True):
        _section_hdr("date_range", "Period Comparison")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                _period_card(
                    f"Current Month — {today.strftime('%b %Y')}",
                    s_cur["util_pct"], s_cur["rental_days"], s_cur["total_days"],
                    accent="#2563EB", featured=True,
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _period_card(
                    f"Previous Month — {prev_last.strftime('%b %Y')}",
                    s_prev["util_pct"], s_prev["rental_days"], s_prev["total_days"],
                    accent="#6B7280",
                ),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                _period_card(
                    f"Year-to-Date — {today.strftime('%Y')}",
                    s_ytd["util_pct"], s_ytd["rental_days"], s_ytd["total_days"],
                    accent="#E87722",
                ),
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # MONTHLY TREND CHART
    # ════════════════════════════════════════════════════════════════════
    with st.container(border=True):
        tr_l, tr_r = st.columns([6, 1])
        with tr_l:
            _section_hdr("show_chart", "Monthly Utilization Trend")
        with tr_r:
            year_opts = list(range(today.year, today.year - 5, -1))
            sel_year  = st.selectbox(
                "Year", year_opts, label_visibility="collapsed", key="fu_year"
            )

        trend_rows: list[dict] = []
        for mo in range(1, 13):
            m_start = date(sel_year, mo, 1)
            m_end   = date(sel_year, mo, _cal.monthrange(sel_year, mo)[1])
            if m_start > today:
                break
            s = _fleet_rental_util(machines, wo_by_machine, moves_by_machine, m_start, m_end)
            trend_rows.append({
                "Month":         m_start.strftime("%b"),
                "Rental":        s["rental_days"],
                "Available":     s["avail_days"],
                "Utilization %": s["util_pct"],
            })

        if trend_rows:
            trend_df = pd.DataFrame(trend_rows).set_index("Month")
            tab_bar, tab_pct = st.tabs(["Days Breakdown", "Utilization %"])
            with tab_bar:
                st.bar_chart(
                    trend_df[["Rental", "Available"]],
                    use_container_width=True,
                    height=240,
                    color=["#2563eb", "#e5e7eb"],
                )
            with tab_pct:
                st.line_chart(
                    trend_df[["Utilization %"]],
                    use_container_width=True,
                    height=240,
                    color=["#E87722"],
                )
        else:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='color:#2563EB;'>bar_chart</span>"
                "</div><h3>No trend data</h3>"
                "<p>No work order data for the selected year.</p></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # MACHINE-WISE DETAIL TABLE
    # ════════════════════════════════════════════════════════════════════
    with st.container(border=True):
        _section_hdr("table_chart", "Machine-wise Utilization Details")

        # ── Filters ──────────────────────────────────────────────────────────
        f1, f2, f3, f4, f5, f6, f7 = st.columns([2, 2, 2, 2, 2, 2, 2])

        with f1:
            st.markdown('<p style="font-size:11px;font-weight:600;color:#6B7280;margin-bottom:4px;">From</p>', unsafe_allow_html=True)
            det_start = st.date_input("From", value=cur_first, key="fu_det_start", label_visibility="collapsed")

        with f2:
            st.markdown('<p style="font-size:11px;font-weight:600;color:#6B7280;margin-bottom:4px;">To</p>', unsafe_allow_html=True)
            det_end = st.date_input("To", value=cur_last, key="fu_det_end", label_visibility="collapsed")

        # Category options
        all_categories = sorted({m.get("machine_type") or "" for m in machines if m.get("machine_type")})
        with f3:
            st.markdown('<p style="font-size:11px;font-weight:600;color:#6B7280;margin-bottom:4px;">Category</p>', unsafe_allow_html=True)
            sel_category = st.multiselect(
                "Category", all_categories,
                label_visibility="collapsed", key="fu_category", placeholder="All",
            )

        # Machine options (filtered by category if set)
        _mach_pool = machines if not sel_category else [
            m for m in machines if m.get("machine_type") in sel_category
        ]
        mach_opts = sorted(
            {m.get("asset_code") or m.get("id", "") for m in _mach_pool if m.get("asset_code") or m.get("id")}
        )
        with f4:
            st.markdown('<p style="font-size:11px;font-weight:600;color:#6B7280;margin-bottom:4px;">Machine</p>', unsafe_allow_html=True)
            sel_machine = st.multiselect(
                "Machine", mach_opts,
                label_visibility="collapsed", key="fu_machine", placeholder="All",
            )

        # Customer options
        cust_name_list = sorted(
            [c.get("customer_name", "—") for c in customers_list if c.get("id")]
        )
        cust_id_map = {
            c.get("customer_name", "—"): c["id"]
            for c in customers_list if c.get("id")
        }
        with f5:
            st.markdown('<p style="font-size:11px;font-weight:600;color:#6B7280;margin-bottom:4px;">Customer</p>', unsafe_allow_html=True)
            sel_cust_labels = st.multiselect(
                "Customer", cust_name_list,
                label_visibility="collapsed", key="fu_customer", placeholder="All",
            )
        sel_cust_ids = {cust_id_map[l] for l in sel_cust_labels if l in cust_id_map}

        # Site options
        site_name_list = sorted(
            [s.get("site_name", "—") for s in sites_list if s.get("id")]
        )
        site_id_map = {
            s.get("site_name", "—"): s["id"]
            for s in sites_list if s.get("id")
        }
        with f6:
            st.markdown('<p style="font-size:11px;font-weight:600;color:#6B7280;margin-bottom:4px;">Site</p>', unsafe_allow_html=True)
            sel_site_labels = st.multiselect(
                "Site", site_name_list,
                label_visibility="collapsed", key="fu_site", placeholder="All",
            )
        sel_site_ids = {site_id_map[l] for l in sel_site_labels if l in site_id_map}

        # Operational Status filter
        with f7:
            st.markdown('<p style="font-size:11px;font-weight:600;color:#6B7280;margin-bottom:4px;">Op. Status</p>', unsafe_allow_html=True)
            sel_op_status = st.multiselect(
                "Op. Status", _OP_STATUS_OPTIONS,
                label_visibility="collapsed", key="fu_op_status", placeholder="All",
            )

        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        # ── Validate date range ───────────────────────────────────────────────
        if not (isinstance(det_start, date) and isinstance(det_end, date)):
            st.info("Select a date range above to view details.")
            return
        if det_start > det_end:
            st.warning("'From' date must be on or before 'To' date.")
            return

        # ── Build customer/site → machines map for period ─────────────────────
        machine_customers: dict[str, set[str]] = {}
        machine_sites:     dict[str, set[str]] = {}
        for wo in work_orders:
            sd = _parse_date(wo.get("start_date"))
            ed = _parse_date(wo.get("end_date")) or det_end
            if sd is None or not (sd <= det_end and ed >= det_start):
                continue
            mc_raw = wo.get("machine_config")
            if not mc_raw:
                continue
            try:
                mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            except Exception:
                continue
            for mc_row in (mc_list if isinstance(mc_list, list) else []):
                mid = mc_row.get("machine_id")
                if not mid:
                    continue
                if wo.get("customer_id"):
                    machine_customers.setdefault(mid, set()).add(wo["customer_id"])
                if wo.get("site_id"):
                    machine_sites.setdefault(mid, set()).add(wo["site_id"])

        # ── Filter machines ───────────────────────────────────────────────────
        filtered = list(machines)
        if sel_category:
            filtered = [m for m in filtered if m.get("machine_type") in sel_category]
        if sel_machine:
            filtered = [m for m in filtered
                        if m.get("asset_code") in sel_machine or m.get("id") in sel_machine]
        if sel_cust_ids:
            filtered = [m for m in filtered
                        if machine_customers.get(m.get("id", ""), set()) & sel_cust_ids]
        if sel_site_ids:
            filtered = [m for m in filtered
                        if machine_sites.get(m.get("id", ""), set()) & sel_site_ids]
        if sel_op_status:
            _expanded_statuses: set[str] = set()
            for _s in sel_op_status:
                if _s == "In Transit":
                    _expanded_statuses.update({"In Transit", "Mobilizing", "Demobilizing"})
                else:
                    _expanded_statuses.add(_s)
            filtered = [m for m in filtered
                        if m.get("operational_status") in _expanded_statuses]

        # ── Build report rows ─────────────────────────────────────────────────
        rows: list[dict] = []
        for m in filtered:
            mid   = m.get("id", "")
            stats = _machine_stats(mid, wo_by_machine, moves_by_machine, det_start, det_end)
            op_st = m.get("operational_status") or "Available"
            if op_st in ("Mobilizing", "Demobilizing"):
                op_st = "In Transit"
            rows.append({
                "Machine":             m.get("asset_code") or "—",
                "Serial Number":       m.get("serial_number") or "—",
                "Category":            m.get("machine_type") or "—",
                "Op. Status":          op_st,
                "Rental Days":         stats["rental_days"],
                "Transit Days":        stats["transit_days"],
                "Available Days":      stats["avail_days"],
                "Idle Days":           stats["avail_days"],   # same source, no separate log
                "Reserved Days":       0,
                "Total Days":          stats["total_days"],
                "Utilization %":       stats["util_pct"],
                "_id":                 mid,
            })

        rows.sort(key=lambda r: r["Utilization %"], reverse=True)

        if not rows:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='color:#2563EB;'>precision_manufacturing</span>"
                "</div><h3>No machines match the filters</h3>"
                "<p>Adjust the filters above or widen the date range.</p></div>",
                unsafe_allow_html=True,
            )
            return

        # ── Summary row above table ───────────────────────────────────────────
        total_rental = sum(r["Rental Days"] for r in rows)
        total_days   = sum(r["Total Days"]  for r in rows)
        fleet_util   = round(total_rental / total_days * 100, 1) if total_days else 0.0
        period_label = f"{det_start.strftime('%d %b %Y')} – {det_end.strftime('%d %b %Y')}"

        sm1, sm2, sm3, sm4 = st.columns([2, 2, 2, 2])
        with sm1:
            st.metric("Machines", len(rows))
        with sm2:
            st.metric("Rental Days", f"{total_rental:,}")
        with sm3:
            st.metric("Fleet Utilization", f"{fleet_util:.1f}%")
        with sm4:
            st.metric("Period", period_label)

        # Export
        display_rows = [{k: v for k, v in r.items() if k != "_id"} for r in rows]
        export_df = pd.DataFrame(display_rows)
        render_export_buttons(
            export_df,
            base_name=f"fleet_util_{det_start}_{det_end}",
            excel_key="fu_xlsx",
            pdf_key="fu_pdf",
            title="Fleet Utilization Report",
            subtitle=f"{det_start} to {det_end}",
            sheet_name="Fleet Utilization",
        )

        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

        # ── Sort controls ─────────────────────────────────────────────────────
        _FU_SORT_COLS = ["Machine", "Serial Number", "Category", "Op. Status",
                         "Rental Days", "Transit Days", "Available Days",
                         "Idle Days", "Reserved Days", "Utilization %"]
        _FU_SORT_NUM  = {"Rental Days", "Transit Days", "Available Days",
                         "Idle Days", "Reserved Days", "Utilization %"}
        _fu1, _fu2, _ = st.columns([2, 1, 5])
        with _fu1:
            _fu_col = st.selectbox("Sort by", _FU_SORT_COLS,
                                   index=_FU_SORT_COLS.index("Utilization %"),
                                   key="fu_sort_col")
        with _fu2:
            _fu_dir = st.selectbox("Order", ["↓ Desc", "↑ Asc"], key="fu_sort_dir",
                                   label_visibility="collapsed")
        def _fuk(r):
            v = r.get(_fu_col)
            if v is None:
                return (1, 0, "")
            if _fu_col in _FU_SORT_NUM and isinstance(v, (int, float)):
                return (0, v, "")
            return (0, 0, str(v).lower())
        rows = sorted(rows, key=_fuk, reverse=(_fu_dir == "↓ Desc"))

        # ── Main table using HTML for status badge ────────────────────────────
        hdr = (
            "<div style='display:grid;"
            "grid-template-columns:1.2fr 1.2fr 1.2fr 1fr 80px 80px 80px 80px 80px 70px;"
            "gap:6px;padding:6px 8px 8px;border-bottom:2px solid #E2EBF0;"
            "font-size:9px;font-weight:700;letter-spacing:.10em;"
            "text-transform:uppercase;color:#9CA3AF;'>"
            "<div>Machine</div>"
            "<div>Serial No.</div>"
            "<div>Category</div>"
            "<div>Op. Status</div>"
            "<div style='text-align:right;'>Rental</div>"
            "<div style='text-align:right;'>Transit</div>"
            "<div style='text-align:right;'>Available</div>"
            "<div style='text-align:right;'>Idle</div>"
            "<div style='text-align:right;'>Reserved</div>"
            "<div style='text-align:right;'>Util %</div>"
            "</div>"
        )

        table_rows = ""
        for r in rows:
            util = r["Utilization %"]
            util_clr = "#2563EB" if util >= 75 else "#E87722" if util >= 50 else "#DC2626"
            table_rows += (
                f"<div style='display:grid;"
                f"grid-template-columns:1.2fr 1.2fr 1.2fr 1fr 80px 80px 80px 80px 80px 70px;"
                f"gap:6px;padding:8px 8px;border-bottom:1px solid #F8FAFC;"
                f"align-items:center;font-size:12px;'>"
                f"<div style='font-weight:700;color:#1E40AF;font-family:monospace;"
                f"font-size:12px;'>{r['Machine']}</div>"
                f"<div style='color:#374151;'>{r['Serial Number']}</div>"
                f"<div style='color:#374151;'>{r['Category']}</div>"
                f"<div>{_status_badge(r['Op. Status'])}</div>"
                f"<div style='text-align:right;font-variant-numeric:tabular-nums;"
                f"font-weight:600;color:#374151;'>{r['Rental Days']}</div>"
                f"<div style='text-align:right;font-variant-numeric:tabular-nums;"
                f"color:#8B5CF6;'>{r['Transit Days']}</div>"
                f"<div style='text-align:right;font-variant-numeric:tabular-nums;"
                f"color:#374151;'>{r['Available Days']}</div>"
                f"<div style='text-align:right;font-variant-numeric:tabular-nums;"
                f"color:#374151;'>{r['Idle Days']}</div>"
                f"<div style='text-align:right;font-variant-numeric:tabular-nums;"
                f"color:#F59E0B;'>{r['Reserved Days']}</div>"
                f"<div style='text-align:right;font-weight:800;color:{util_clr};"
                f"font-variant-numeric:tabular-nums;'>{util:.1f}%</div>"
                f"</div>"
            )

        st.markdown(hdr + table_rows, unsafe_allow_html=True)

    # ── Notes ─────────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='info-note'>"
        "<span class='msr info-note-icon'>info</span>"
        "<div>"
        "<strong>Rental Days</strong>: derived from Work Order start/end dates. &nbsp;"
        "<strong>Transit Days</strong>: count of Machine Movement records in the period. &nbsp;"
        "<strong>Available Days</strong> = Total − Rental − Transit. &nbsp;"
        "<strong>Idle Days</strong> is shown equal to Available Days — a separate idle log "
        "is not maintained. &nbsp;"
        "<strong>Reserved Days</strong> = 0 (no reservation period log). &nbsp;"
        "Breakdowns are excluded from this report — see the Worklog Report for breakdown analysis."
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
