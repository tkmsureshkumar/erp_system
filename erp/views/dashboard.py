"""
erp/views/dashboard.py
Executive Management Dashboard — Fleet KPIs, Revenue KPIs, Operational KPIs.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
import calendar as _cal

import streamlit as st

from erp import auth as _auth
from ..supabase_client import SupabaseClient

try:
    import plotly.graph_objects as go
    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False


# ── Helpers ────────────────────────────────────────────────────────────────────

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
    if not raw:
        return 0.0
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(records, list):
            return sum(float(r.get("rental_per_month") or 0) for r in records)
    except Exception:
        pass
    return 0.0


def _mc_machine_ids(raw) -> set[str]:
    if not raw:
        return set()
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(records, list):
            return {r["machine_id"] for r in records if r.get("machine_id")}
    except Exception:
        pass
    return set()


def _rr_for_period(work_orders, period_start, period_end) -> float:
    total = 0.0
    for wo in work_orders:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd is None:
            continue
        if sd <= period_end and (ed is None or ed >= period_start):
            total += _mc_rental_total(wo.get("machine_config"))
    return total


def _util_for_period(
    work_orders, owned_ids: set[str], total_owned: int, period_start, period_end
) -> float:
    if not total_owned:
        return 0.0
    on_rent: set[str] = set()
    for wo in work_orders:
        if wo.get("cross_rental") == "Yes":
            continue
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd is None:
            continue
        if sd <= period_end and (ed is None or ed >= period_start):
            on_rent |= (_mc_machine_ids(wo.get("machine_config")) & owned_ids)
    return round(len(on_rent) / total_owned * 100, 1)


def _fmt_inr(amount: float) -> str:
    if amount >= 1e7:
        return f"₹{amount / 1e7:.2f} Cr"
    if amount >= 1e5:
        return f"₹{amount / 1e5:.2f} L"
    return f"₹{amount:,.0f}"


def _kpi_card(
    label: str, value: str, delta_text: str = "",
    delta_up: bool | None = None, icon: str = "monitoring",
    accent: str = "#2563EB",
) -> str:
    icon_bg = f"{accent}18"
    if delta_text:
        arrow = "arrow_upward" if delta_up else "arrow_downward"
        delta_html = (
            f"<div class='metric-delta {'up' if delta_up else 'down'}'>"
            f"<span class='msr' style='font-size:13px;'>{arrow}</span>"
            f"{delta_text}</div>"
        )
    else:
        delta_html = "<div style='margin-top:6px;height:16px;'></div>"
    return (
        f"<div class='metric-card'>"
        f"<div style='display:flex;align-items:flex-start;"
        f"justify-content:space-between;margin-bottom:10px;'>"
        f"<div class='metric-label'>{label}</div>"
        f"<div style='width:30px;height:30px;border-radius:8px;background:{icon_bg};"
        f"display:flex;align-items:center;justify-content:center;flex-shrink:0;'>"
        f"<span class='msr' style='font-size:16px;color:{accent};'>{icon}</span>"
        f"</div></div>"
        f"<div style='font-size:26px;font-weight:800;color:#111827;"
        f"line-height:1;font-variant-numeric:tabular-nums;'>{value}</div>"
        f"{delta_html}"
        f"</div>"
    )


def _mini_tile(label: str, value: str, note: str = "", accent: str = "#2563EB") -> str:
    note_html = (
        f"<div style='font-size:10px;color:#9CA3AF;margin-top:4px;'>{note}</div>"
        if note else ""
    )
    return (
        f"<div style='padding:12px 14px;background:#F8FAFC;border-radius:10px;"
        f"border:1px solid #E5E7EB;'>"
        f"<div style='font-size:10px;font-weight:700;color:#6B7280;"
        f"text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px;'>{label}</div>"
        f"<div style='font-size:21px;font-weight:800;color:{accent};line-height:1;"
        f"font-variant-numeric:tabular-nums;'>{value}</div>"
        f"{note_html}"
        f"</div>"
    )


def _section_hdr(title: str, sub: str = "") -> str:
    sub_html = (
        f"<span style='font-size:11px;font-weight:500;color:#9CA3AF;margin-left:8px;'>{sub}</span>"
        if sub else ""
    )
    return (
        f"<div style='display:flex;align-items:center;gap:10px;margin:8px 0 14px;'>"
        f"<span style='font-size:12px;font-weight:700;color:#374151;"
        f"text-transform:uppercase;letter-spacing:.08em;white-space:nowrap;'>{title}{sub_html}</span>"
        f"<div style='flex:1;height:1px;background:#E5E7EB;'></div>"
        f"</div>"
    )


def _panel_title(title: str, sub: str = "") -> str:
    sub_html = (
        f" <span style='font-size:11px;font-weight:500;color:#9CA3AF;'>{sub}</span>"
        if sub else ""
    )
    return (
        f"<div style='font-size:13px;font-weight:700;color:#1E2938;"
        f"margin-bottom:12px;'>{title}{sub_html}</div>"
    )


def _alert_row(icon: str, color: str, text: str, link_label: str, link_page: str) -> str:
    return (
        f"<div style='display:flex;align-items:center;gap:10px;"
        f"padding:9px 0;border-bottom:1px solid #F1F5F9;'>"
        f"<div style='width:30px;height:30px;border-radius:7px;background:{color}1a;"
        f"display:flex;align-items:center;justify-content:center;flex-shrink:0;'>"
        f"<span class='msr' style='font-size:15px;color:{color};'>{icon}</span></div>"
        f"<div style='flex:1;font-size:12px;font-weight:500;color:#374151;'>{text}</div>"
        f"<a href='?page={link_page}' target='_self' style='font-size:11px;"
        f"font-weight:600;color:#2563EB;text-decoration:none;white-space:nowrap;'>"
        f"→ {link_label}</a>"
        f"</div>"
    )


# ── Main render ────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--card) !important;
            border-color: var(--border) !important;
            border-radius: var(--radius) !important;
            box-shadow: var(--shadow-sm) !important;
            padding: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    today = date.today()
    _hour = datetime.now().hour
    _greet = "Good Morning" if _hour < 12 else "Good Afternoon" if _hour < 17 else "Good Evening"

    profile = _auth.current_profile() or {}
    _full   = profile.get("full_name") or ""
    _fname  = _full.split()[0] if _full.strip() else "there"

    # ── Greeting header ──────────────────────────────────────────────────────
    g_left, g_right = st.columns([6, 2])
    with g_left:
        st.markdown(
            f"<div style='font-size:24px;font-weight:800;color:#1E2938;line-height:1.2;'>"
            f"{_greet}, {_fname}! 👋</div>"
            f"<div style='font-size:13px;color:#6B7280;margin-top:4px;'>"
            f"Here's what's happening with your fleet today.</div>",
            unsafe_allow_html=True,
        )
    with g_right:
        st.markdown(
            f"<div style='display:flex;justify-content:flex-end;align-items:center;"
            f"height:100%;padding-top:4px;'>"
            f"<div style='display:inline-flex;align-items:center;gap:7px;"
            f"border:1px solid var(--border);border-radius:var(--radius-sm);"
            f"padding:7px 14px;font-size:13px;font-weight:600;color:#374151;"
            f"background:#fff;box-shadow:var(--shadow-xs);'>"
            f"<span class='msr' style='font-size:16px;color:#9CA3AF;'>calendar_today</span>"
            f"{today.strftime('%d %b %Y')}</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    # ── Load data ────────────────────────────────────────────────────────────
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        customers_list = sb.list_customers()
        work_orders    = sb.list_work_orders()
    except Exception as exc:
        st.error(f"Could not connect to Supabase: {exc}")
        return

    try:
        work_logs = sb.list_all_worklogs()
    except Exception:
        work_logs = []

    try:
        all_invoices = sb.list_all_invoices()
    except Exception:
        all_invoices = []

    try:
        compliance_records = sb.list_compliance_records()
    except Exception:
        compliance_records = []

    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}

    # ── Fleet splits (Owned vs Cross Rental / Leased) ────────────────────────
    owned_machines = [m for m in machines if m.get("ownership", "Owned") != "Leased"]
    cross_machines = [m for m in machines if m.get("ownership") == "Leased"]
    total_owned    = len(owned_machines)
    total_cross    = len(cross_machines)
    total_all      = len(machines)
    owned_ids      = {m["id"] for m in owned_machines if m.get("id")}

    owned_on_rent  = sum(1 for m in owned_machines if m.get("operational_status") == "On Rent")
    idle_cnt       = sum(1 for m in owned_machines if m.get("operational_status") == "Available")
    breakdown_cnt  = sum(1 for m in owned_machines if m.get("condition_status")   == "Breakdown")
    reserved_cnt   = sum(1 for m in owned_machines if m.get("operational_status") == "Reserved")
    in_transit_cnt = sum(1 for m in owned_machines
                         if m.get("operational_status") in ("Mobilizing", "Demobilizing"))
    fleet_util     = round(owned_on_rent / total_owned * 100, 1) if total_owned else 0.0

    # For donut (all machines)
    all_on_rent   = sum(1 for m in machines if m.get("operational_status") == "On Rent")
    all_idle      = sum(1 for m in machines if m.get("operational_status") == "Available")
    all_breakdown = sum(1 for m in machines if m.get("condition_status")   == "Breakdown")
    all_reserved  = sum(1 for m in machines if m.get("operational_status") == "Reserved")
    all_transit   = sum(1 for m in machines
                        if m.get("operational_status") in ("Mobilizing", "Demobilizing"))

    # ── Date periods ─────────────────────────────────────────────────────────
    cur_first  = today.replace(day=1)
    prev_last  = cur_first - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    prev_label = prev_last.strftime("%b %Y")
    ytd_start  = date(today.year, 1, 1)

    # ── WO splits (Own fleet vs Cross Rental WOs) ────────────────────────────
    own_wos = [wo for wo in work_orders if wo.get("cross_rental") != "Yes"]
    cr_wos  = [wo for wo in work_orders if wo.get("cross_rental") == "Yes"]

    def _is_active(wo) -> bool:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        return sd is not None and sd <= today and (ed is None or ed >= today)

    active_own = [wo for wo in own_wos if _is_active(wo)]
    active_cr  = [wo for wo in cr_wos  if _is_active(wo)]
    active_all = active_own + active_cr

    # ── Revenue run rates ─────────────────────────────────────────────────────
    rr_cur_own  = sum(_mc_rental_total(wo.get("machine_config")) for wo in active_own)
    rr_prev_own = _rr_for_period(own_wos, prev_first, prev_last)
    rr_cur_cr   = sum(_mc_rental_total(wo.get("machine_config")) for wo in active_cr)
    rr_delta     = rr_cur_own - rr_prev_own
    rr_delta_pct = (rr_delta / rr_prev_own * 100) if rr_prev_own else 0.0

    # Fleet utilization trend delta
    util_prev  = _util_for_period(own_wos, owned_ids, total_owned, prev_first, prev_last)
    util_delta = fleet_util - util_prev

    # ── Billed revenue from invoices ──────────────────────────────────────────
    own_wo_ids = {wo.get("id") for wo in own_wos}
    cr_wo_ids  = {wo.get("id") for wo in cr_wos}

    def _inv_total(inv_list, wo_id_set, start_d, end_d) -> float:
        total = 0.0
        for inv in inv_list:
            if inv.get("work_order_id") not in wo_id_set:
                continue
            inv_d = _parse_date(inv.get("invoice_date"))
            if inv_d and start_d <= inv_d <= end_d:
                try:
                    total += float(inv.get("grand_total") or 0)
                except (TypeError, ValueError):
                    pass
        return total

    billed_prev_own = _inv_total(all_invoices, own_wo_ids, prev_first, prev_last)
    billed_ytd_own  = _inv_total(all_invoices, own_wo_ids, ytd_start, today)
    billed_ytd_cr   = _inv_total(all_invoices, cr_wo_ids,  ytd_start, today)

    pending_inv_cnt = sum(
        1 for inv in all_invoices
        if inv.get("status") not in ("Paid", "Cancelled")
    )

    # ── Compliance expiring (next 30 days) ────────────────────────────────────
    comp_expiry_soon = sum(
        1 for cr in compliance_records
        if _parse_date(cr.get("expiry_date")) is not None
        and today <= _parse_date(cr.get("expiry_date")) <= today + timedelta(days=30)
    )

    # ── Pending worklogs ──────────────────────────────────────────────────────
    pending_wl = sum(1 for wl in work_logs if wl.get("is_draft") is True)

    # ── WOs expiring within 7 days ────────────────────────────────────────────
    expiring_soon = [
        wo for wo in active_all
        if _parse_date(wo.get("end_date")) is not None
        and today < _parse_date(wo.get("end_date")) <= today + timedelta(days=7)
    ]

    # ── Top clients by active revenue ─────────────────────────────────────────
    cust_rr: dict[str, float] = {}
    for wo in active_all:
        name = cust_map.get(wo.get("customer_id", ""), "Unknown")
        cust_rr[name] = cust_rr.get(name, 0.0) + _mc_rental_total(wo.get("machine_config"))
    top_clients = sorted(cust_rr.items(), key=lambda x: x[1], reverse=True)[:5]

    # ── Recent work orders ────────────────────────────────────────────────────
    recent_wos = sorted(
        work_orders,
        key=lambda wo: wo.get("created_at") or wo.get("start_date") or "",
        reverse=True,
    )[:5]

    # ── Trend data (last 6 months, own fleet) ─────────────────────────────────
    trend_labels: list[str] = []
    trend_rr:     list[float] = []
    trend_util:   list[float] = []
    for i in range(5, -1, -1):
        _y, _m = today.year, today.month - i
        while _m <= 0:
            _m += 12
            _y -= 1
        _first = date(_y, _m, 1)
        _last  = date(_y, _m, _cal.monthrange(_y, _m)[1])
        trend_labels.append(_first.strftime("%b"))
        trend_rr.append(_rr_for_period(own_wos, _first, _last))
        trend_util.append(_util_for_period(own_wos, owned_ids, total_owned, _first, _last))

    # ════════════════════════════════════════════════════════════════════════
    # SECTION A — FLEET KPIs
    # ════════════════════════════════════════════════════════════════════════
    st.markdown(
        _section_hdr("A — Fleet KPIs", "Owned fleet · Cross Rental excluded from utilization"),
        unsafe_allow_html=True,
    )

    # Row A1: Total Owned | On Rent | Fleet Util% | Idle
    fa1, fa2, fa3, fa4 = st.columns(4)
    for col, lbl, val, dtxt, dup, icon, clr in [
        (fa1, "Total Owned Fleet",  str(total_owned),
         "",                                None,          "precision_manufacturing", "#1E2938"),
        (fa2, "Machines On Rent",   str(owned_on_rent),
         f"{fleet_util:.0f}% utilization", fleet_util >= 60, "handshake",            "#2563EB"),
        (fa3, "Fleet Utilization",  f"{fleet_util:.1f}%",
         f"{util_delta:+.1f}% vs {prev_label}" if util_prev else "",
         util_delta >= 0,                  "speed",                                  "#10B981"),
        (fa4, "Idle (Available)",   str(idle_cnt),
         "",                                None,          "inventory_2",             "#6B7280"),
    ]:
        with col:
            st.markdown(_kpi_card(lbl, val, dtxt, dup, icon, clr), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    # Row A2: Breakdown | Reserved | In Transit | Cross Rental
    fa5, fa6, fa7, fa8 = st.columns(4)
    for col, lbl, val, dtxt, dup, icon, clr in [
        (fa5, "Breakdown",    str(breakdown_cnt),  "", None, "build",           "#DC2626"),
        (fa6, "Reserved",     str(reserved_cnt),   "", None, "bookmark",        "#F59E0B"),
        (fa7, "In Transit",   str(in_transit_cnt), "", None, "local_shipping",  "#8B5CF6"),
        (fa8, "Cross Rental", str(total_cross), "leased / 3rd-party", None, "swap_horiz", "#E87722"),
    ]:
        with col:
            st.markdown(_kpi_card(lbl, val, dtxt, dup, icon, clr), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION B — REVENUE KPIs
    # ════════════════════════════════════════════════════════════════════════
    st.markdown(_section_hdr("B — Revenue KPIs"), unsafe_allow_html=True)

    rv_left, rv_right = st.columns([7, 5])

    with rv_left:
        with st.container(border=True):
            st.markdown(_panel_title("Own Fleet Revenue"), unsafe_allow_html=True)
            rg1, rg2, rg3, rg4 = st.columns(4)
            ytd_note = f"Jan–{today.strftime('%b')} {today.year}"
            for col, lbl, val, note, clr in [
                (rg1, "Current Month Run Rate", _fmt_inr(rr_cur_own),
                 f"{rr_delta_pct:+.1f}% vs {prev_label}" if rr_prev_own else "—", "#2563EB"),
                (rg2, "Last Month Run Rate",    _fmt_inr(rr_prev_own),  prev_label, "#6B7280"),
                (rg3, "Last Month Billed",      _fmt_inr(billed_prev_own), prev_label, "#10B981"),
                (rg4, "YTD Billed Revenue",     _fmt_inr(billed_ytd_own), ytd_note, "#E87722"),
            ]:
                with col:
                    st.markdown(_mini_tile(lbl, val, note, clr), unsafe_allow_html=True)

    with rv_right:
        with st.container(border=True):
            st.markdown(_panel_title("Cross Rental Revenue"), unsafe_allow_html=True)
            cg1, cg2, cg3 = st.columns(3)
            for col, lbl, val, note, clr in [
                (cg1, "Run Rate",   _fmt_inr(rr_cur_cr),    "This month",           "#E87722"),
                (cg2, "YTD Billed", _fmt_inr(billed_ytd_cr), ytd_note,              "#8B5CF6"),
                (cg3, "Profit",     "N/A",                   "Module pending",       "#9CA3AF"),
            ]:
                with col:
                    st.markdown(_mini_tile(lbl, val, note, clr), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # CHARTS + ALERTS
    # ════════════════════════════════════════════════════════════════════════
    ch1, ch2, ch3 = st.columns([5, 5, 4])

    with ch1:
        with st.container(border=True):
            st.markdown(
                _panel_title("Revenue Trend", "(Last 6 Months — Own Fleet)"),
                unsafe_allow_html=True,
            )
            if _HAS_PLOTLY:
                fig_rev = go.Figure()
                fig_rev.add_trace(go.Scatter(
                    x=trend_labels, y=trend_rr,
                    mode="lines+markers",
                    line=dict(color="#2563EB", width=2.5),
                    marker=dict(size=7, color="#2563EB"),
                    fill="tozeroy",
                    fillcolor="rgba(37,99,235,0.07)",
                    hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>",
                ))
                fig_rev.update_layout(
                    margin=dict(l=0, r=0, t=4, b=0), height=180,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    xaxis=dict(showgrid=False, tickfont=dict(size=10, color="#9CA3AF")),
                    yaxis=dict(showgrid=True, gridcolor="#F1F5F9",
                               tickfont=dict(size=10, color="#9CA3AF"), tickformat=",.0f"),
                )
                st.plotly_chart(fig_rev, use_container_width=True,
                                config={"displayModeBar": False})
            else:
                st.info("Install plotly (`pip install plotly`) to enable charts.")

    with ch2:
        with st.container(border=True):
            st.markdown(
                _panel_title("Fleet Utilization Trend", "(Last 6 Months)"),
                unsafe_allow_html=True,
            )
            if _HAS_PLOTLY:
                fig_util = go.Figure()
                fig_util.add_trace(go.Scatter(
                    x=trend_labels, y=trend_util,
                    mode="lines+markers",
                    line=dict(color="#10B981", width=2.5),
                    marker=dict(size=7, color="#10B981"),
                    fill="tozeroy",
                    fillcolor="rgba(16,185,129,0.07)",
                    hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
                ))
                fig_util.update_layout(
                    margin=dict(l=0, r=0, t=4, b=0), height=180,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    xaxis=dict(showgrid=False, tickfont=dict(size=10, color="#9CA3AF")),
                    yaxis=dict(showgrid=True, gridcolor="#F1F5F9",
                               tickfont=dict(size=10, color="#9CA3AF"),
                               ticksuffix="%", range=[0, 110]),
                )
                st.plotly_chart(fig_util, use_container_width=True,
                                config={"displayModeBar": False})
            else:
                st.info("Install plotly to enable charts.")

    with ch3:
        with st.container(border=True):
            st.markdown(_panel_title("Top Alerts"), unsafe_allow_html=True)
            alerts_html = ""
            if breakdown_cnt:
                alerts_html += _alert_row(
                    "build", "#DC2626",
                    f"{breakdown_cnt} machine{'s' if breakdown_cnt > 1 else ''} in Breakdown",
                    "View", "machines",
                )
            if expiring_soon:
                alerts_html += _alert_row(
                    "schedule", "#F59E0B",
                    f"{len(expiring_soon)} WO{'s' if len(expiring_soon) > 1 else ''} expiring within 7 days",
                    "View", "workorders",
                )
            if pending_wl:
                alerts_html += _alert_row(
                    "edit_note", "#2563EB",
                    f"{pending_wl} worklog{'s' if pending_wl > 1 else ''} pending",
                    "View", "worklog",
                )
            if comp_expiry_soon:
                alerts_html += _alert_row(
                    "warning", "#F59E0B",
                    f"{comp_expiry_soon} compliance record{'s' if comp_expiry_soon > 1 else ''} expiring soon",
                    "View", "machinecompliance",
                )
            if in_transit_cnt:
                alerts_html += _alert_row(
                    "local_shipping", "#8B5CF6",
                    f"{in_transit_cnt} machine{'s' if in_transit_cnt > 1 else ''} in transit",
                    "View", "machines",
                )
            if not alerts_html:
                alerts_html = (
                    "<div style='text-align:center;padding:28px 0;color:#9CA3AF;font-size:12px;'>"
                    "<span class='msr' style='font-size:32px;display:block;margin-bottom:8px;"
                    "color:#10B981;'>check_circle</span>All clear — no alerts</div>"
                )
            st.markdown(alerts_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # BOTTOM ROW: Machines by Status | Top Clients | Recent Work Orders
    # ════════════════════════════════════════════════════════════════════════
    b1, b2, b3 = st.columns([4, 4, 5])

    with b1:
        with st.container(border=True):
            st.markdown(_panel_title("Machines by Status"), unsafe_allow_html=True)
            if _HAS_PLOTLY and total_all:
                _lbls  = ["On Rent", "Available", "Breakdown", "Reserved", "Transit", "Cross Rental"]
                _vals  = [all_on_rent, all_idle, all_breakdown, all_reserved, all_transit, total_cross]
                _clrs  = ["#2563EB", "#16A344",  "#DC2626",    "#F59E0B",   "#E87722", "#8B5CF6"]
                _pairs = [(l, v, c) for l, v, c in zip(_lbls, _vals, _clrs) if v > 0]
                if _pairs:
                    _sl, _sv, _sc = zip(*_pairs)
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=list(_sl), values=list(_sv), hole=0.62,
                        marker=dict(colors=list(_sc), line=dict(color="#fff", width=2)),
                        textinfo="percent",
                        textfont=dict(size=10, color="#fff"),
                        hovertemplate="%{label}: %{value}<extra></extra>",
                    )])
                    fig_pie.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0), height=220,
                        paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
                        legend=dict(orientation="v", x=1.02, y=0.5,
                                    font=dict(size=10, color="#6B7280"),
                                    bgcolor="rgba(0,0,0,0)"),
                        annotations=[dict(
                            text=f"<b>{total_all}</b><br><span style='font-size:10px;'>Total</span>",
                            x=0.5, y=0.5, font_size=14, font_color="#111827",
                            showarrow=False,
                        )],
                    )
                    st.plotly_chart(fig_pie, use_container_width=True,
                                    config={"displayModeBar": False})
                else:
                    st.info("No machines found.")
            elif not _HAS_PLOTLY:
                st.info("Install plotly to enable this chart.")
            else:
                st.info("No machines found.")

    with b2:
        with st.container(border=True):
            st.markdown(
                _panel_title("Top Clients by Revenue", "(This Month)"),
                unsafe_allow_html=True,
            )
            if top_clients:
                max_rev = top_clients[0][1] or 1
                rows_html = ""
                for i, (name, rev) in enumerate(top_clients, 1):
                    bar_w = int(rev / max_rev * 100)
                    rows_html += (
                        f"<div style='margin-bottom:11px;'>"
                        f"<div style='display:flex;justify-content:space-between;"
                        f"align-items:baseline;margin-bottom:4px;'>"
                        f"<span style='font-size:12px;font-weight:600;color:#374151;"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:63%;'>"
                        f"<span style='color:#9CA3AF;margin-right:5px;font-weight:500;'>{i}.</span>"
                        f"{name}</span>"
                        f"<span style='font-size:12px;font-weight:700;color:#E87722;"
                        f"font-variant-numeric:tabular-nums;white-space:nowrap;margin-left:6px;'>"
                        f"{_fmt_inr(rev)}</span>"
                        f"</div>"
                        f"<div style='height:4px;background:#F1F5F9;border-radius:99px;'>"
                        f"<div style='width:{bar_w}%;height:4px;"
                        f"background:linear-gradient(90deg,#2563EB,#0EA5E9);"
                        f"border-radius:99px;'></div>"
                        f"</div></div>"
                    )
                st.markdown(rows_html, unsafe_allow_html=True)
            else:
                st.markdown(
                    "<div style='color:#9CA3AF;font-size:12px;text-align:center;"
                    "padding:28px 0;'>No active work orders</div>",
                    unsafe_allow_html=True,
                )

    with b3:
        with st.container(border=True):
            _rh, _rl = st.columns([4, 1])
            with _rh:
                st.markdown(_panel_title("Recent Work Orders"), unsafe_allow_html=True)
            with _rl:
                st.markdown(
                    "<div style='text-align:right;margin-top:-2px;'>"
                    "<a href='?page=workorders' target='_self' style='font-size:11px;"
                    "font-weight:600;color:#2563EB;text-decoration:none;'>View All →</a></div>",
                    unsafe_allow_html=True,
                )
            _STATUS_CLS: dict[str, str] = {
                "Running":   "badge-running",
                "Active":    "badge-active",
                "Approved":  "badge-approved",
                "Draft":     "badge-draft",
                "Completed": "badge-completed",
                "Closed":    "badge-closed",
            }
            if recent_wos:
                hdr = (
                    "<div style='display:grid;grid-template-columns:1fr 1.2fr 90px 90px;"
                    "gap:8px;padding:0 0 8px;border-bottom:2px solid #E2EBF0;"
                    "font-size:9px;font-weight:700;letter-spacing:.10em;"
                    "text-transform:uppercase;color:#9CA3AF;'>"
                    "<div>WO No</div><div>Client</div><div>Status</div><div>End Date</div></div>"
                )
                rows_wo = ""
                for wo in recent_wos:
                    wo_num = wo.get("wo_number") or "—"
                    client = cust_map.get(wo.get("customer_id", ""), "—")
                    status = wo.get("status", "Active")
                    end_d  = wo.get("end_date") or "—"
                    cls    = _STATUS_CLS.get(status, "badge-draft")
                    rows_wo += (
                        f"<div style='display:grid;grid-template-columns:1fr 1.2fr 90px 90px;"
                        f"gap:8px;padding:8px 0;border-bottom:1px solid #F8FAFC;align-items:center;'>"
                        f"<div style='font-size:11px;font-weight:700;color:#2563EB;"
                        f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{wo_num}</div>"
                        f"<div style='font-size:11px;color:#374151;white-space:nowrap;"
                        f"overflow:hidden;text-overflow:ellipsis;'>{client}</div>"
                        f"<div><span class='badge {cls}'>{status}</span></div>"
                        f"<div style='font-size:11px;color:#6B7280;'>{end_d}</div>"
                        f"</div>"
                    )
                st.markdown(hdr + rows_wo, unsafe_allow_html=True)
            else:
                st.markdown(
                    "<div style='color:#9CA3AF;font-size:12px;text-align:center;"
                    "padding:28px 0;'>No work orders found</div>",
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # SECTION C — OPERATIONAL KPIs
    # ════════════════════════════════════════════════════════════════════════
    st.markdown(_section_hdr("C — Operational KPIs"), unsafe_allow_html=True)

    op1, op2, op3, _ = st.columns([3, 3, 3, 3])

    with op1:
        st.markdown(
            _kpi_card(
                "Pending Worklogs", str(pending_wl),
                "drafts pending" if pending_wl else "all up to date",
                False if pending_wl else None,
                "edit_note", "#F59E0B" if pending_wl else "#10B981",
            ),
            unsafe_allow_html=True,
        )

    with op2:
        st.markdown(
            _kpi_card(
                "Pending Invoices", str(pending_inv_cnt),
                "awaiting payment" if pending_inv_cnt else "all cleared",
                False if pending_inv_cnt else None,
                "receipt_long", "#DC2626" if pending_inv_cnt else "#10B981",
            ),
            unsafe_allow_html=True,
        )

    with op3:
        st.markdown(
            _kpi_card(
                "Compliance Expiring", str(comp_expiry_soon),
                "expiring within 30 days" if comp_expiry_soon else "no upcoming expiry",
                False if comp_expiry_soon else None,
                "verified_user", "#DC2626" if comp_expiry_soon else "#10B981",
            ),
            unsafe_allow_html=True,
        )
