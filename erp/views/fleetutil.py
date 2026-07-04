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

def _section_header(title: str) -> None:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:14px;'>"
        f"{title}</div>",
        unsafe_allow_html=True,
    )


def _util_card(
    label: str,
    util_pct: float,
    on_rent: int,
    total: int,
    accent: bool = False,
) -> str:
    border_top = "3px solid #E87722" if accent else "1px solid #e5e7eb"
    val_size   = "32px" if accent else "26px"
    val_weight = "800"  if accent else "700"
    if util_pct >= 75:
        clr = "#2563eb"
    elif util_pct >= 50:
        clr = "#E87722"
    else:
        clr = "#ef4444"
    return (
        f"<div style='background:#fff;border:1px solid #e5e7eb;border-top:{border_top};"
        f"border-radius:6px;padding:20px 24px;box-shadow:0 1px 4px rgba(0,0,0,.06);"
        f"min-height:120px;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#9ca3af;margin-bottom:10px;'>{label}</div>"
        f"<div style='font-size:{val_size};font-weight:{val_weight};color:{clr};"
        f"font-variant-numeric:tabular-nums;line-height:1;'>{util_pct:.1f}%</div>"
        f"<div style='font-size:11px;color:#9ca3af;margin-top:8px;'>"
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
    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Fleet Utilization Report</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

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

    # ── Lookup maps ──────────────────────────────────────────────────────────
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

    # ── Year selector (for trend chart + detail tables) ───────────────────────
    _, py = st.columns([8, 1])
    with py:
        st.markdown('<p class="filter-label">Year</p>', unsafe_allow_html=True)
        year_opts = list(range(today.year, today.year - 5, -1))
        sel_year  = st.selectbox("Year", year_opts, label_visibility="collapsed", key="fu_year")

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # A. OVERALL FLEET UTILIZATION
    # ════════════════════════════════════════════════════════════════════
    _section_header("Overall Fleet Utilization")

    s_cur  = _fleet_stats(machines, wo_by_machine, cur_first,  cur_last)
    s_prev = _fleet_stats(machines, wo_by_machine, prev_first, prev_last)
    s_ytd  = _fleet_stats(machines, wo_by_machine, ytd_first,  today)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            _util_card(
                f"Current Month — {today.strftime('%b %Y')}",
                s_cur["util_pct"],
                s_cur["on_rent_days"],
                s_cur["total_days"],
                accent=True,
            ),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _util_card(
                f"Previous Month — {prev_last.strftime('%b %Y')}",
                s_prev["util_pct"],
                s_prev["on_rent_days"],
                s_prev["total_days"],
            ),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            _util_card(
                f"Year-to-Date — {today.strftime('%Y')}",
                s_ytd["util_pct"],
                s_ytd["on_rent_days"],
                s_ytd["total_days"],
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # B. MONTHLY UTILIZATION TREND
    # ════════════════════════════════════════════════════════════════════
    _section_header(f"Monthly Utilization Trend — {sel_year}")

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
        # Show stacked on-rent / idle bars + utilization % as second line
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
        st.info("No work order data for the selected year.")

    st.markdown("<div style='margin-top:32px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # DETAIL TABLES — shared period selector
    # ════════════════════════════════════════════════════════════════════
    _section_header("Utilization Details")

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
        st.info("Select a date range above.")
        return
    if det_start > det_end:
        st.warning("'From' date must be on or before 'To' date.")
        return

    period_days = (det_end - det_start).days + 1

    tab_mach, tab_cust, tab_site, tab_cat = st.tabs(
        ["Machine-wise", "Customer-wise", "Site-wise", "Category-wise"]
    )

    # ── E. Machine-wise ───────────────────────────────────────────────────────
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
        mdf = pd.DataFrame(mach_rows)
        st.dataframe(
            mdf.style.format({"Utilization %": _fmt_pct}),
            use_container_width=True,
            hide_index=True,
        )
        if mach_rows:
            st.download_button(
                "Export CSV",
                data=mdf.to_csv(index=False).encode("utf-8"),
                file_name=f"util_machine_{det_start}_{det_end}.csv",
                mime="text/csv",
                key="fu_mach_csv",
            )

    # ── C. Customer-wise ──────────────────────────────────────────────────────
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
                cdf.style.format({"Utilization %": _fmt_pct}),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Export CSV",
                data=cdf.to_csv(index=False).encode("utf-8"),
                file_name=f"util_customer_{det_start}_{det_end}.csv",
                mime="text/csv",
                key="fu_cust_csv",
            )
        else:
            st.info("No customer work orders found for the selected period.")

    # ── D. Site-wise ──────────────────────────────────────────────────────────
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
                sdf.style.format({"Utilization %": _fmt_pct}),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Export CSV",
                data=sdf.to_csv(index=False).encode("utf-8"),
                file_name=f"util_site_{det_start}_{det_end}.csv",
                mime="text/csv",
                key="fu_site_csv",
            )
        else:
            st.info("No site work orders found for the selected period.")

    # ── F. Category-wise ──────────────────────────────────────────────────────
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
                catdf.style.format({"Utilization %": _fmt_pct}),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Export CSV",
                data=catdf.to_csv(index=False).encode("utf-8"),
                file_name=f"util_category_{det_start}_{det_end}.csv",
                mime="text/csv",
                key="fu_cat_csv",
            )

    # ── Data quality note ─────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    st.info(
        "**Breakdown Days** is currently shown as 0 — historical breakdown tracking is not "
        "yet implemented. Idle Days = Total Available Days − On Rent Days, and includes any "
        "untracked breakdown periods. Utilization is calculated from Work Order dates only.",
        icon="ℹ️",
    )
