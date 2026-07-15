"""
erp/views/fleetutil.py
Fleet Utilization Report — on-rent vs idle vs breakdown days.

Utilization (%) = On Rent Days ÷ Total Available Days × 100
Idle + Breakdown + On Rent = Total Available Days
"""
from __future__ import annotations

import calendar as _cal
import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient


# ── Page CSS ──────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ──────────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin: 0 0 24px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 18px 22px 14px;
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
    margin-bottom: 10px;
    display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 34px; font-weight: 800;
    color: #111827; line-height: 1;
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 11px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 16px; right: 18px;
    font-size: 22px; opacity: .12;
}

/* ── Period comparison cards ─────────────────────────────────────────── */
.period-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 20px 22px 16px;
    position: relative;
    overflow: hidden;
    min-height: 110px;
    transition: box-shadow .18s, transform .18s;
}
.period-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,.07);
    transform: translateY(-2px);
}
.period-card-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 10px;
}
.period-card-value {
    font-size: 32px; font-weight: 800; line-height: 1;
    font-variant-numeric: tabular-nums; margin-bottom: 6px;
}
.period-card-sub { font-size: 11px; color: #6B7280; }

/* ── Section header ──────────────────────────────────────────────────── */
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
    padding: 52px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px;
    text-align: center;
    animation: cs-fadeup .35s ease;
    margin: 8px 0;
}
.empty-icon-ring {
    width: 64px; height: 64px; border-radius: 50%;
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 30px; margin-bottom: 16px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 {
    font-size: 15px; font-weight: 700; color: #111827;
    margin: 0 0 6px;
}
.empty-state-v2 p {
    font-size: 12px; color: #9CA3AF;
    max-width: 260px; line-height: 1.6; margin: 0;
}

/* ── Info note ───────────────────────────────────────────────────────── */
.info-note {
    background: #EFF6FF; border: 1px solid #BFDBFE;
    border-radius: 10px; padding: 14px 18px;
    display: flex; gap: 10px; align-items: flex-start;
    font-size: 12px; color: #1E40AF; line-height: 1.6;
    margin-top: 20px;
}
.info-note-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }

/* ── Tab polish ──────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    background: transparent !important;
    border-bottom: 2px solid #E2EBF0 !important;
    padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 12px !important; font-weight: 600 !important;
    color: #6B7280 !important; padding: 8px 18px !important;
    border-radius: 0 !important;
    background: transparent !important; border: none !important;
    margin: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: color .14s !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #374151 !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #2563EB !important;
    border-bottom: 2px solid #2563EB !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-panel"]     { padding: 18px 0 0 !important; }

/* ── Animations ──────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── Core calculation helpers ──────────────────────────────────────────────────

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
    """Merge overlapping date intervals so days are never double-counted."""
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


def _on_rent_days_in_period(
    wo_list: list[dict],
    period_start: date,
    period_end: date,
) -> int:
    """Count distinct on-rent days within [period_start, period_end] across all WOs."""
    intervals: list[tuple[date, date]] = []
    for wo in wo_list:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date")) or period_end
        if sd is None:
            continue
        ov_start = max(sd, period_start)
        ov_end   = min(ed, period_end)
        if ov_start <= ov_end:
            intervals.append((ov_start, ov_end))
    total = 0
    for s, e in _merge_intervals(intervals):
        total += (e - s).days + 1
    return total


def _machine_stats(
    machine_id: str,
    wo_by_machine: dict[str, list[dict]],
    period_start: date,
    period_end: date,
) -> dict:
    """Per-machine utilization stats for a period."""
    total_days = (period_end - period_start).days + 1
    on_rent    = _on_rent_days_in_period(
        wo_by_machine.get(machine_id, []), period_start, period_end
    )
    on_rent    = min(on_rent, total_days)
    idle       = total_days - on_rent
    util_pct   = round(on_rent / total_days * 100, 1) if total_days else 0.0
    return {
        "on_rent_days":   on_rent,
        "idle_days":      idle,
        "breakdown_days": 0,    # not tracked historically
        "total_days":     total_days,
        "util_pct":       util_pct,
    }


def _fleet_stats(
    machines: list[dict],
    wo_by_machine: dict[str, list[dict]],
    period_start: date,
    period_end: date,
) -> dict:
    """Aggregate fleet-level utilization stats for a period."""
    fleet_on_rent = 0
    fleet_total   = 0
    for m in machines:
        s = _machine_stats(m.get("id", ""), wo_by_machine, period_start, period_end)
        fleet_on_rent += s["on_rent_days"]
        fleet_total   += s["total_days"]
    idle_days = fleet_total - fleet_on_rent
    util_pct  = round(fleet_on_rent / fleet_total * 100, 1) if fleet_total else 0.0
    return {
        "num_machines": len(machines),
        "on_rent_days": fleet_on_rent,
        "idle_days":    idle_days,
        "total_days":   fleet_total,
        "util_pct":     util_pct,
    }


# ── UI helpers ────────────────────────────────────────────────────────────────

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
    on_rent: int,
    total: int,
    accent: str = "#6B7280",
    featured: bool = False,
) -> str:
    if util_pct >= 75:
        clr = "#2563EB"
    elif util_pct >= 50:
        clr = "#E87722"
    else:
        clr = "#EF4444"
    val_size = "38px" if featured else "30px"
    return (
        f"<div class='period-card'>"
        f"<div style='position:absolute;top:0;left:0;right:0;height:3px;"
        f"background:{accent};border-radius:12px 12px 0 0;'></div>"
        f"<div class='period-card-label'>{label}</div>"
        f"<div class='period-card-value' style='color:{clr};font-size:{val_size};'>"
        f"{util_pct:.1f}%</div>"
        f"<div class='period-card-sub'>"
        f"{on_rent:,} on-rent days &nbsp;/&nbsp; {total:,} available days</div>"
        f"</div>"
    )


def _fmt_pct(v) -> str:
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "—"


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Fleet Utilization</div>"
        "<div style='font-size:13px;color:#6B7280;margin-top:4px;margin-bottom:28px;'>"
        "On-rent vs idle day analysis across your entire fleet.</div>",
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

    # ── Lookup maps ───────────────────────────────────────────────────────────
    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}

    # machine_id → ALL work orders (historical + current) for on-rent day calculation
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

    # ── Period constants ──────────────────────────────────────────────────────
    today      = date.today()
    cur_first  = today.replace(day=1)
    cur_last   = today.replace(day=_cal.monthrange(today.year, today.month)[1])
    prev_last  = cur_first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    ytd_first  = today.replace(month=1, day=1)

    # ── Live fleet status (as of today) ──────────────────────────────────────
    machines_on_rent_today: set[str] = set()
    active_wo_count = 0
    for wo in work_orders:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd is None:
            continue
        if sd <= today and (ed is None or ed >= today):
            active_wo_count += 1
            mc_raw = wo.get("machine_config")
            if not mc_raw:
                continue
            try:
                mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            except Exception:
                continue
            for mc_row in (mc_list if isinstance(mc_list, list) else []):
                mid = mc_row.get("machine_id")
                if mid:
                    machines_on_rent_today.add(mid)

    fleet_size    = len(machines)
    on_rent_now   = len(machines_on_rent_today)
    available_now = max(0, fleet_size - on_rent_now)

    # ── Period stats ──────────────────────────────────────────────────────────
    s_cur  = _fleet_stats(machines, wo_by_machine, cur_first,  cur_last)
    s_prev = _fleet_stats(machines, wo_by_machine, prev_first, prev_last)
    s_ytd  = _fleet_stats(machines, wo_by_machine, ytd_first,  today)

    # ════════════════════════════════════════════════════════════════════
    # KPI STRIP
    # ════════════════════════════════════════════════════════════════════
    st.markdown(
        "<div class='kpi-grid'>"
        + _kpi_card(
            "donut_large", "Fleet Utilization",
            f"{s_cur['util_pct']:.1f}%",
            f"current month — {today.strftime('%b %Y')}", "#2563EB",
        )
        + _kpi_card(
            "construction", "Machines On Rent",
            on_rent_now,
            "deployed as of today", "#10B981",
        )
        + _kpi_card(
            "garage_home", "Available Now",
            available_now,
            f"of {fleet_size} total machines", "#F59E0B",
        )
        + _kpi_card(
            "assignment_turned_in", "Active Work Orders",
            active_wo_count,
            "in-progress deployments", "#8B5CF6",
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # ════════════════════════════════════════════════════════════════════
    # A. PERIOD COMPARISON
    # ════════════════════════════════════════════════════════════════════
    with st.container(border=True):
        _section_hdr("date_range", "Period Comparison")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                _period_card(
                    f"Current Month — {today.strftime('%b %Y')}",
                    s_cur["util_pct"], s_cur["on_rent_days"], s_cur["total_days"],
                    accent="#2563EB", featured=True,
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _period_card(
                    f"Previous Month — {prev_last.strftime('%b %Y')}",
                    s_prev["util_pct"], s_prev["on_rent_days"], s_prev["total_days"],
                    accent="#6B7280",
                ),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                _period_card(
                    f"Year-to-Date — {today.strftime('%Y')}",
                    s_ytd["util_pct"], s_ytd["on_rent_days"], s_ytd["total_days"],
                    accent="#E87722",
                ),
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # B. MONTHLY UTILIZATION TREND
    # ════════════════════════════════════════════════════════════════════
    with st.container(border=True):
        tr_l, tr_r = st.columns([6, 1])
        with tr_l:
            _section_hdr("show_chart", "Monthly Utilization Trend")
        with tr_r:
            st.markdown('<p class="filter-label">Year</p>', unsafe_allow_html=True)
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
            s = _fleet_stats(machines, wo_by_machine, m_start, m_end)
            trend_rows.append({
                "Month":         m_start.strftime("%b"),
                "On Rent":       s["on_rent_days"],
                "Idle":          s["idle_days"],
                "Utilization %": s["util_pct"],
            })

        if trend_rows:
            trend_df = pd.DataFrame(trend_rows).set_index("Month")
            tab_bar, tab_pct = st.tabs(["Days Breakdown", "Utilization %"])
            with tab_bar:
                st.bar_chart(
                    trend_df[["On Rent", "Idle"]],
                    use_container_width=True,
                    height=260,
                    color=["#2563eb", "#e5e7eb"],
                )
            with tab_pct:
                st.line_chart(
                    trend_df[["Utilization %"]],
                    use_container_width=True,
                    height=260,
                    color=["#E87722"],
                )
        else:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='color:#2563EB;'>bar_chart</span>"
                "</div>"
                "<h3>No trend data</h3>"
                "<p>No work order data found for the selected year.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # C. UTILIZATION DETAILS
    # ════════════════════════════════════════════════════════════════════
    with st.container(border=True):
        _section_hdr("table_chart", "Utilization Details")

        dp1, dp2, _ = st.columns([2, 2, 4])
        with dp1:
            st.markdown('<p class="filter-label">From</p>', unsafe_allow_html=True)
            det_start = st.date_input(
                "From", value=cur_first, key="fu_det_start", label_visibility="collapsed"
            )
        with dp2:
            st.markdown('<p class="filter-label">To</p>', unsafe_allow_html=True)
            det_end = st.date_input(
                "To", value=cur_last, key="fu_det_end", label_visibility="collapsed"
            )

        if not (isinstance(det_start, date) and isinstance(det_end, date)):
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='color:#2563EB;'>date_range</span>"
                "</div>"
                "<h3>Select a date range</h3>"
                "<p>Choose From and To dates above to view utilization details.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        if det_start > det_end:
            st.warning("'From' date must be on or before 'To' date.")
            return

        period_days = (det_end - det_start).days + 1

        tab_mach, tab_cust, tab_site, tab_cat = st.tabs(
            ["Machine-wise", "Customer-wise", "Site-wise", "Category-wise"]
        )

        # ── Machine-wise ──────────────────────────────────────────────────────
        with tab_mach:
            mach_rows: list[dict] = []
            for m in machines:
                mid   = m.get("id", "")
                stats = _machine_stats(mid, wo_by_machine, det_start, det_end)
                mach_rows.append({
                    "Serial Number":  m.get("serial_number") or "—",
                    "Machine":        m.get("asset_code")    or m.get("machine_type", "—"),
                    "Make":           m.get("make", "—")     or "—",
                    "Model":          m.get("model", "—")    or "—",
                    "On Rent Days":   stats["on_rent_days"],
                    "Idle Days":      stats["idle_days"],
                    "Breakdown Days": stats["breakdown_days"],
                    "Utilization %":  stats["util_pct"],
                })
            mach_rows.sort(key=lambda r: r["Utilization %"], reverse=True)
            if mach_rows:
                mdf = pd.DataFrame(mach_rows)
                st.dataframe(
                    mdf,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Serial Number":  st.column_config.TextColumn("Serial No."),
                        "Machine":        st.column_config.TextColumn("Machine"),
                        "Make":           st.column_config.TextColumn("Make"),
                        "Model":          st.column_config.TextColumn("Model"),
                        "On Rent Days":   st.column_config.NumberColumn("On Rent (d)"),
                        "Idle Days":      st.column_config.NumberColumn("Idle (d)"),
                        "Breakdown Days": st.column_config.NumberColumn("Breakdown (d)"),
                        "Utilization %":  st.column_config.NumberColumn(
                            "Util %", format="%.1f%%"
                        ),
                    },
                )
                st.download_button(
                    "↓ Export CSV",
                    data=mdf.to_csv(index=False).encode("utf-8"),
                    file_name=f"util_machine_{det_start}_{det_end}.csv",
                    mime="text/csv",
                    key="fu_mach_csv",
                )
            else:
                st.markdown(
                    "<div class='empty-state-v2'>"
                    "<div class='empty-icon-ring'>"
                    "<span class='msr' style='color:#2563EB;'>precision_manufacturing</span>"
                    "</div>"
                    "<h3>No machine data</h3>"
                    "<p>No machines found in the fleet.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        # ── Customer-wise ─────────────────────────────────────────────────────
        with tab_cust:
            cust_agg: dict[str, dict] = {}
            for wo in work_orders:
                cid = wo.get("customer_id", "")
                if not cid:
                    continue
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
                    ov_start = max(sd, det_start)
                    ov_end   = min(ed, det_end)
                    if ov_start > ov_end:
                        continue
                    days = (ov_end - ov_start).days + 1
                    agg  = cust_agg.setdefault(cid, {"machines": set(), "on_rent_days": 0})
                    agg["machines"].add(mid)
                    agg["on_rent_days"] += days

            cust_rows: list[dict] = []
            for cid, agg in cust_agg.items():
                num_m    = len(agg["machines"])
                on_rent  = agg["on_rent_days"]
                total    = period_days * num_m
                idle     = max(0, total - on_rent)
                util_pct = round(on_rent / total * 100, 1) if total else 0.0
                cust_rows.append({
                    "Customer":        cust_map.get(cid, "—"),
                    "No. of Machines": num_m,
                    "On Rent Days":    on_rent,
                    "Idle Days":       idle,
                    "Breakdown Days":  0,
                    "Utilization %":   util_pct,
                })
            cust_rows.sort(key=lambda r: r["Utilization %"], reverse=True)
            if cust_rows:
                cdf = pd.DataFrame(cust_rows)
                st.dataframe(
                    cdf,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Customer":        st.column_config.TextColumn("Customer"),
                        "No. of Machines": st.column_config.NumberColumn("Machines"),
                        "On Rent Days":    st.column_config.NumberColumn("On Rent (d)"),
                        "Idle Days":       st.column_config.NumberColumn("Idle (d)"),
                        "Breakdown Days":  st.column_config.NumberColumn("Breakdown (d)"),
                        "Utilization %":   st.column_config.NumberColumn(
                            "Util %", format="%.1f%%"
                        ),
                    },
                )
                st.download_button(
                    "↓ Export CSV",
                    data=cdf.to_csv(index=False).encode("utf-8"),
                    file_name=f"util_customer_{det_start}_{det_end}.csv",
                    mime="text/csv",
                    key="fu_cust_csv",
                )
            else:
                st.markdown(
                    "<div class='empty-state-v2'>"
                    "<div class='empty-icon-ring'>"
                    "<span class='msr' style='color:#2563EB;'>groups</span>"
                    "</div>"
                    "<h3>No customer data</h3>"
                    "<p>No customer work orders found for the selected period.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        # ── Site-wise ─────────────────────────────────────────────────────────
        with tab_site:
            site_agg: dict[str, dict] = {}
            for wo in work_orders:
                sid = wo.get("site_id", "")
                if not sid:
                    continue
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
                    ov_start = max(sd, det_start)
                    ov_end   = min(ed, det_end)
                    if ov_start > ov_end:
                        continue
                    days = (ov_end - ov_start).days + 1
                    agg  = site_agg.setdefault(sid, {"machines": set(), "on_rent_days": 0})
                    agg["machines"].add(mid)
                    agg["on_rent_days"] += days

            site_rows: list[dict] = []
            for sid, agg in site_agg.items():
                num_m    = len(agg["machines"])
                on_rent  = agg["on_rent_days"]
                total    = period_days * num_m
                idle     = max(0, total - on_rent)
                util_pct = round(on_rent / total * 100, 1) if total else 0.0
                site_rows.append({
                    "Site":            site_map.get(sid, "—"),
                    "No. of Machines": num_m,
                    "On Rent Days":    on_rent,
                    "Idle Days":       idle,
                    "Breakdown Days":  0,
                    "Utilization %":   util_pct,
                })
            site_rows.sort(key=lambda r: r["Utilization %"], reverse=True)
            if site_rows:
                sdf = pd.DataFrame(site_rows)
                st.dataframe(
                    sdf,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Site":            st.column_config.TextColumn("Site"),
                        "No. of Machines": st.column_config.NumberColumn("Machines"),
                        "On Rent Days":    st.column_config.NumberColumn("On Rent (d)"),
                        "Idle Days":       st.column_config.NumberColumn("Idle (d)"),
                        "Breakdown Days":  st.column_config.NumberColumn("Breakdown (d)"),
                        "Utilization %":   st.column_config.NumberColumn(
                            "Util %", format="%.1f%%"
                        ),
                    },
                )
                st.download_button(
                    "↓ Export CSV",
                    data=sdf.to_csv(index=False).encode("utf-8"),
                    file_name=f"util_site_{det_start}_{det_end}.csv",
                    mime="text/csv",
                    key="fu_site_csv",
                )
            else:
                st.markdown(
                    "<div class='empty-state-v2'>"
                    "<div class='empty-icon-ring'>"
                    "<span class='msr' style='color:#2563EB;'>location_on</span>"
                    "</div>"
                    "<h3>No site data</h3>"
                    "<p>No site work orders found for the selected period.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        # ── Category-wise ─────────────────────────────────────────────────────
        with tab_cat:
            cat_agg: dict[str, dict] = {}
            for m in machines:
                mid = m.get("id", "")
                cat = m.get("machine_type") or "Unknown"
                s   = _machine_stats(mid, wo_by_machine, det_start, det_end)
                a   = cat_agg.setdefault(cat, {"count": 0, "on_rent": 0, "total": 0})
                a["count"]   += 1
                a["on_rent"] += s["on_rent_days"]
                a["total"]   += s["total_days"]

            cat_rows: list[dict] = []
            for cat, agg in cat_agg.items():
                idle     = agg["total"] - agg["on_rent"]
                util_pct = round(agg["on_rent"] / agg["total"] * 100, 1) if agg["total"] else 0.0
                cat_rows.append({
                    "Category":        cat,
                    "No. of Machines": agg["count"],
                    "On Rent Days":    agg["on_rent"],
                    "Idle Days":       idle,
                    "Breakdown Days":  0,
                    "Utilization %":   util_pct,
                })
            cat_rows.sort(key=lambda r: r["Utilization %"], reverse=True)
            if cat_rows:
                catdf = pd.DataFrame(cat_rows)
                st.dataframe(
                    catdf,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Category":        st.column_config.TextColumn("Category"),
                        "No. of Machines": st.column_config.NumberColumn("Machines"),
                        "On Rent Days":    st.column_config.NumberColumn("On Rent (d)"),
                        "Idle Days":       st.column_config.NumberColumn("Idle (d)"),
                        "Breakdown Days":  st.column_config.NumberColumn("Breakdown (d)"),
                        "Utilization %":   st.column_config.NumberColumn(
                            "Util %", format="%.1f%%"
                        ),
                    },
                )
                st.download_button(
                    "↓ Export CSV",
                    data=catdf.to_csv(index=False).encode("utf-8"),
                    file_name=f"util_category_{det_start}_{det_end}.csv",
                    mime="text/csv",
                    key="fu_cat_csv",
                )
            else:
                st.markdown(
                    "<div class='empty-state-v2'>"
                    "<div class='empty-icon-ring'>"
                    "<span class='msr' style='color:#2563EB;'>category</span>"
                    "</div>"
                    "<h3>No category data</h3>"
                    "<p>No machines found for the selected period.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )

    # ── Data quality note ─────────────────────────────────────────────────────
    st.markdown(
        "<div class='info-note'>"
        "<span class='msr info-note-icon'>info</span>"
        "<div><strong>Breakdown Days</strong> is currently shown as 0 — historical breakdown "
        "tracking is not yet implemented. <strong>Idle Days</strong> = Total Available Days "
        "− On Rent Days, and includes any untracked breakdown periods. Utilization is "
        "calculated from Work Order dates only.</div>"
        "</div>",
        unsafe_allow_html=True,
    )
