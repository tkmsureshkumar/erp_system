"""
erp/views/machinehistory.py
Machine History Report — deployment timeline with idle-period detection.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient
from ._report_utils import render_export_buttons


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────── */
.mh-kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin: 0 0 24px;
}
.mh-kpi {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 16px 18px 12px;
    position: relative;
    overflow: hidden;
}
.mh-kpi-bar {
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.mh-kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 8px;
}
.mh-kpi-value {
    font-size: 28px; font-weight: 800;
    color: #111827; line-height: 1; margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
}
.mh-kpi-sub { font-size: 11px; color: #6B7280; }
.mh-kpi-icon {
    position: absolute; top: 14px; right: 14px;
    font-size: 22px; opacity: .09;
}
/* ── Machine hero ───────────────────────────────────────────── */
.mh-hero {
    background: linear-gradient(135deg, #1E2938 0%, #1c3461 100%);
    border-radius: 14px 14px 0 0;
    padding: 20px 24px;
    display: flex; align-items: center; gap: 18px;
    position: relative; overflow: hidden;
}
.mh-hero::after {
    content: '';
    position: absolute; top: -50px; right: -50px;
    width: 180px; height: 180px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.mh-hero-icon {
    width: 48px; height: 48px; border-radius: 12px;
    background: rgba(255,255,255,.12);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}
.mh-hero-name {
    font-size: 18px; font-weight: 700; color: #fff; line-height: 1.2;
}
.mh-hero-sub {
    font-size: 11px; color: rgba(255,255,255,.45);
    letter-spacing: .06em; margin-top: 3px;
}
/* ── Info grid ──────────────────────────────────────────────── */
.mh-info-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    border: 1px solid #E2EBF0;
    border-top: none;
    border-radius: 0 0 14px 14px;
    overflow: hidden;
    margin-bottom: 24px;
}
.mh-info-cell {
    padding: 11px 16px;
    border-right: 1px solid #E2EBF0;
    border-bottom: 1px solid #E2EBF0;
    background: #fff;
}
.mh-info-cell:nth-child(4n) { border-right: none; }
.mh-info-cell:nth-last-child(-n+4) { border-bottom: none; }
.mh-info-cell-label {
    font-size: 9px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 3px;
}
.mh-info-cell-value {
    font-size: 13px; font-weight: 600; color: #111827;
    word-break: break-word;
}
.mh-info-cell-value.muted { color: #9CA3AF; font-weight: 400; }
/* ── Section header ─────────────────────────────────────────── */
.mh-sec-hdr {
    font-size: 10px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #E87722;
    padding-bottom: 8px; margin-bottom: 14px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}
/* ── Timeline table ─────────────────────────────────────────── */
.mh-tl-hdr {
    display: grid;
    grid-template-columns: 5px 100px 1fr 1fr 130px 130px 70px 120px;
    gap: 8px;
    padding: 6px 10px 8px;
    border-bottom: 2px solid #E2EBF0;
    font-size: 9px; font-weight: 700; letter-spacing: .10em;
    text-transform: uppercase; color: #9CA3AF;
}
.mh-tl-row {
    display: grid;
    grid-template-columns: 5px 100px 1fr 1fr 130px 130px 70px 120px;
    gap: 8px;
    padding: 10px 10px;
    border-bottom: 1px solid #F8FAFC;
    align-items: center;
    font-size: 12px;
}
.mh-tl-row:hover { background: #F9FAFB; }
.mh-tl-bar   { border-radius: 4px; align-self: stretch; min-height: 36px; }
.mh-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 600; white-space: nowrap;
}
.mh-badge-rent  { background: #DBEAFE; color: #1E40AF; }
.mh-badge-idle  { background: #F3F4F6; color: #6B7280; }
.mh-badge-trans { background: #EDE9FE; color: #5B21B6; }
.mh-badge-active {
    background: #DCFCE7; color: #166534;
    animation: mh-pulse 2s infinite;
}
@keyframes mh-pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: .65; }
}
/* ── Empty state ────────────────────────────────────────────── */
.mh-empty {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 56px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 14px;
    text-align: center;
}
.mh-empty-ring {
    width: 64px; height: 64px; border-radius: 50%;
    background: linear-gradient(145deg, #FFF7ED, #FFEDD5);
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 16px;
}
.mh-empty h3 { font-size: 15px; font-weight: 700; color: #111827; margin: 0 0 6px; }
.mh-empty p  { font-size: 12px; color: #9CA3AF; max-width: 240px; line-height: 1.6; margin: 0; }
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


def _fmt(d) -> str:
    parsed = _parse_date(d)
    return parsed.strftime("%d %b %Y") if parsed else "—"


def _duration_label(start: date, end: date | None, today: date) -> str:
    effective_end = end or today
    days = (effective_end - start).days + 1
    if days < 0:
        return "—"
    if days >= 365:
        y = days // 365
        m = (days % 365) // 30
        return f"{y}y {m}m" if m else f"{y}y"
    if days >= 30:
        m = days // 30
        d = days % 30
        return f"{m}m {d}d" if d else f"{m}m"
    return f"{days}d"


def _machine_in_config(mc_raw, machine_id: str) -> dict | None:
    if not mc_raw or not machine_id:
        return None
    try:
        records = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        if isinstance(records, list):
            return next((r for r in records if r.get("machine_id") == machine_id), None)
    except Exception:
        pass
    return None


def _info_cell(label: str, value: str) -> str:
    muted = not value or value == "—"
    val_cls = "mh-info-cell-value muted" if muted else "mh-info-cell-value"
    return (
        f"<div class='mh-info-cell'>"
        f"<div class='mh-info-cell-label'>{label}</div>"
        f"<div class='{val_cls}'>{value or '—'}</div>"
        f"</div>"
    )


def _kpi(icon: str, label: str, value: str, sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='mh-kpi'>"
        f"<div class='mh-kpi-bar' style='background:{accent};'></div>"
        f"<span class='mh-kpi-icon msr'>{icon}</span>"
        f"<div class='mh-kpi-label'>{label}</div>"
        f"<div class='mh-kpi-value'>{value}</div>"
        f"<div class='mh-kpi-sub'>{sub}</div>"
        f"</div>"
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Machine History</div>"
        "<div style='font-size:13px;color:#6B7280;margin-top:4px;margin-bottom:24px;'>"
        "Full deployment timeline including idle periods between work orders.</div>",
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

    if not machines:
        st.info("No machines found.")
        return

    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}

    today = date.today()

    # ── Machine selector ──────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div class='mh-sec-hdr'>"
            "<span class='msr' style='font-size:14px;color:#E87722;'>manage_search</span>"
            "Select Machine</div>",
            unsafe_allow_html=True,
        )

        def _label(m: dict) -> str:
            parts = [p for p in [m.get("make"), m.get("model")] if p]
            desc  = " ".join(parts)
            code  = m.get("asset_code", "") or m.get("machine_type", "Unknown")
            return f"{code}  —  {desc}" if desc else code

        sorted_machines = sorted(machines, key=lambda m: m.get("asset_code") or "")
        labels          = [_label(m) for m in sorted_machines]
        ids             = [m.get("id", "") for m in sorted_machines]

        sel_label = st.selectbox("Machine", labels, label_visibility="collapsed", key="mh_machine")
        idx       = labels.index(sel_label)
        sel_id    = ids[idx]
        m         = sorted_machines[idx]

    # ── Machine profile ───────────────────────────────────────────────────────
    code_disp = m.get("asset_code", "") or ""
    type_disp = m.get("machine_type", "") or ""
    make_model = " ".join(p for p in [m.get("make", ""), m.get("model", "")] if p) or code_disp
    hero_sub   = " · ".join(p for p in [type_disp, code_disp] if p) or "Machine"
    op_st      = m.get("operational_status", "") or "—"
    cond_st    = m.get("condition_status",   "") or "—"
    if op_st in ("Mobilizing", "Demobilizing"):
        op_st = "In Transit"

    st.markdown(
        f"<div class='mh-hero'>"
        f"<div class='mh-hero-icon'>"
        f"<span class='msr' style='font-size:26px;color:#fff;'>precision_manufacturing</span>"
        f"</div>"
        f"<div style='flex:1;min-width:0;position:relative;z-index:1;'>"
        f"<div class='mh-hero-name'>{make_model or type_disp or code_disp}</div>"
        f"<div class='mh-hero-sub'>{hero_sub}</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='mh-info-grid'>"
        + _info_cell("Asset Code",    m.get("asset_code",       "—"))
        + _info_cell("Type",          m.get("machine_type",     "—"))
        + _info_cell("Make",          m.get("make",             "—"))
        + _info_cell("Model",         m.get("model",            "—"))
        + _info_cell("Serial Number", m.get("serial_number",    "—"))
        + _info_cell("Ownership",     m.get("ownership",        "—"))
        + _info_cell("Op. Status",    op_st)
        + _info_cell("Condition",     cond_st)
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Build deployment events ───────────────────────────────────────────────
    deployments: list[dict] = []
    for wo in work_orders:
        mc_row = _machine_in_config(wo.get("machine_config"), sel_id)
        if mc_row is None:
            continue
        sd     = _parse_date(wo.get("start_date"))
        ed     = _parse_date(wo.get("end_date"))
        rental = mc_row.get("rental_per_month")
        wo_st  = (wo.get("status") or "").strip()
        is_active = (
            wo_st.lower() in ("active", "running", "approved")
            or (ed is None or ed >= today)
        ) and (sd is not None and sd <= today)

        wo_num = wo.get("wo_number") or "—"
        client_wo = wo.get("client_work_ordernumber") or ""
        wo_display = f"{wo_num} / {client_wo}" if client_wo and client_wo != wo_num else wo_num

        deployments.append({
            "type":      "deployment",
            "start":     sd or date.min,
            "end":       ed,
            "customer":  cust_map.get(wo.get("customer_id", ""), "—"),
            "site":      site_map.get(wo.get("site_id",      ""), "—"),
            "wo":        wo_display,
            "rental":    float(rental) if rental is not None else None,
            "is_active": is_active,
            "wo_status": wo_st,
        })

    # Sort chronologically ascending to detect gaps
    deployments.sort(key=lambda e: e["start"])

    # ── Build full timeline (deployments + idle gaps) ─────────────────────────
    timeline: list[dict] = []
    purchase_d = _parse_date(m.get("purchase_date"))

    for i, dep in enumerate(deployments):
        # Gap before this deployment
        if i == 0:
            gap_start = purchase_d + timedelta(days=1) if purchase_d else None
        else:
            prev_end = deployments[i - 1].get("end")
            gap_start = (prev_end + timedelta(days=1)) if prev_end else None

        if gap_start and dep["start"] > gap_start:
            gap_days = (dep["start"] - gap_start).days
            if gap_days >= 1:
                timeline.append({
                    "type":      "idle",
                    "start":     gap_start,
                    "end":       dep["start"] - timedelta(days=1),
                    "days":      gap_days,
                    "customer":  "—",
                    "site":      "—",
                    "wo":        "—",
                    "rental":    None,
                    "is_active": False,
                })
        timeline.append(dep)

    # Trailing idle: if last deployment has ended
    if deployments:
        last_end = deployments[-1].get("end")
        if last_end and last_end < today:
            gap_days = (today - last_end).days
            if gap_days >= 1:
                timeline.append({
                    "type":      "idle",
                    "start":     last_end + timedelta(days=1),
                    "end":       today,
                    "days":      gap_days,
                    "customer":  "—",
                    "site":      "—",
                    "wo":        "—",
                    "rental":    None,
                    "is_active": False,
                })

    # Sort descending (most recent first for display)
    timeline.sort(key=lambda e: e["start"], reverse=True)

    # ── KPI strip ─────────────────────────────────────────────────────────────
    n_deps       = sum(1 for e in timeline if e["type"] == "deployment")
    n_active     = sum(1 for e in timeline if e.get("is_active"))
    n_customers  = len({e["customer"] for e in timeline
                        if e["type"] == "deployment" and e["customer"] != "—"})
    rentals      = [e["rental"] for e in timeline if e["rental"] is not None]
    avg_rental   = f"₹ {sum(rentals)/len(rentals):,.0f}" if rentals else "—"
    total_rent_d = sum(
        (min(e.get("end") or today, today) - e["start"]).days + 1
        for e in timeline
        if e["type"] == "deployment" and e["start"] <= today
    )

    st.markdown(
        "<div class='mh-kpi-grid'>"
        + _kpi("history",   "Total Deployments", str(n_deps),    "work orders assigned",     "#2563EB")
        + _kpi("check_circle","Active Now",      str(n_active),  "open deployments",          "#10B981")
        + _kpi("groups",    "Unique Customers",  str(n_customers),"served over lifetime",     "#8B5CF6")
        + _kpi("calendar_month","Rental Days",   f"{total_rent_d:,}","total on-rent days",   "#E87722")
        + _kpi("payments",  "Avg Monthly Rental", avg_rental,    "per deployment",            "#F59E0B")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Timeline display ───────────────────────────────────────────────────────
    if not timeline:
        st.markdown(
            "<div class='mh-empty'>"
            "<div class='mh-empty-ring'>"
            "<span class='msr' style='color:#F97316;font-size:32px;'>history</span>"
            "</div>"
            "<h3>No history found</h3>"
            "<p>This machine has not been assigned to any work orders yet.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Sort controls ─────────────────────────────────────────────────────────
    _MH_SORT_COLS = ["Date", "Customer", "Site", "Monthly Rental", "Duration"]
    _mh1, _mh2, _ = st.columns([2, 1, 5])
    with _mh1:
        _mh_col = st.selectbox("Sort by", _MH_SORT_COLS, key="mh_sort_col")
    with _mh2:
        _mh_dir = st.selectbox("Order", ["↓ Desc", "↑ Asc"], key="mh_sort_dir",
                               label_visibility="collapsed")
    _mh_rev = (_mh_dir == "↓ Desc")
    if _mh_col == "Date":
        timeline.sort(key=lambda e: e["start"], reverse=_mh_rev)
    elif _mh_col == "Customer":
        timeline.sort(key=lambda e: (e.get("customer") or "").lower(), reverse=_mh_rev)
    elif _mh_col == "Site":
        timeline.sort(key=lambda e: (e.get("site") or "").lower(), reverse=_mh_rev)
    elif _mh_col == "Monthly Rental":
        timeline.sort(key=lambda e: e.get("rental") or 0, reverse=_mh_rev)
    elif _mh_col == "Duration":
        timeline.sort(
            key=lambda e: (min(e.get("end") or today, today) - e["start"]).days,
            reverse=_mh_rev,
        )

    # Header + Export
    n_idle       = sum(1 for e in timeline if e["type"] == "idle")
    dep_label    = f"{n_deps} deployment{'s' if n_deps != 1 else ''}"
    idle_label   = f", {n_idle} idle period{'s' if n_idle != 1 else ''}" if n_idle else ""
    tl_title     = f"Timeline — {dep_label}{idle_label}"

    st.markdown(
        f"<div class='mh-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>timeline</span>"
        f"{tl_title}</div>",
        unsafe_allow_html=True,
    )

    tl_export_rows = [
        {
            "Type":           "On Rent" if e["type"] == "deployment" else "Idle",
            "Customer":       e["customer"],
            "Site":           e["site"],
            "Work Order":     e["wo"],
            "Start Date":     _fmt(e["start"]),
            "End Date":       (_fmt(e.get("end")) if e.get("end")
                               else ("Active" if e.get("is_active") else "—")),
            "Duration":       _duration_label(e["start"], e.get("end"), today),
            "Monthly Rental": f"₹ {e['rental']:,.0f}" if e.get("rental") is not None else "—",
        }
        for e in timeline
    ]
    tl_df = pd.DataFrame(tl_export_rows)
    render_export_buttons(
        tl_df,
        f"machine_history_{m.get('asset_code', sel_id)}",
        "mh_xl", "mh_pdf",
        "Machine History", make_model,
    )

    # Table header
    st.markdown(
        "<div class='mh-tl-hdr'>"
        "<div></div>"
        "<div>Type</div>"
        "<div>Customer</div>"
        "<div>Site</div>"
        "<div>Start Date</div>"
        "<div>End Date</div>"
        "<div>Duration</div>"
        "<div>Monthly Rental</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Table rows
    rows_html = ""
    for e in timeline:
        is_dep    = e["type"] == "deployment"
        is_active = e.get("is_active", False)
        start_d   = e["start"]
        end_d     = e.get("end")
        duration  = _duration_label(start_d, end_d, today)

        # Left bar color
        if is_dep and is_active:
            bar_clr = "#10B981"
        elif is_dep:
            bar_clr = "#2563EB"
        else:
            bar_clr = "#D1D5DB"

        # Badge
        if is_dep and is_active:
            badge = "<span class='mh-badge mh-badge-active'>● Active</span>"
        elif is_dep:
            badge = "<span class='mh-badge mh-badge-rent'>On Rent</span>"
        else:
            badge = "<span class='mh-badge mh-badge-idle'>Idle</span>"

        end_disp = (
            "<span style='color:#10B981;font-weight:600;'>Active</span>"
            if (is_dep and is_active and not end_d)
            else _fmt(end_d) if end_d else "—"
        )

        rental_disp = (
            f"<span style='color:#E87722;font-weight:700;font-variant-numeric:tabular-nums;'>"
            f"₹ {e['rental']:,.0f}</span>"
            if e.get("rental") is not None else
            "<span style='color:#9CA3AF;'>—</span>"
        )

        cust_disp = (
            f"<div style='font-size:12px;font-weight:600;color:#111827;'>{e['customer']}</div>"
            if e["customer"] != "—" else
            "<div style='font-size:12px;color:#9CA3AF;'>—</div>"
        )
        site_disp = (
            f"<div style='font-size:12px;color:#374151;'>{e['site']}</div>"
            if e["site"] != "—" else
            "<div style='font-size:12px;color:#9CA3AF;'>—</div>"
        )

        wo_hint = (
            f"<div style='font-size:10px;color:#9CA3AF;margin-top:1px;'>{e['wo']}</div>"
            if is_dep and e["wo"] != "—" else ""
        )

        row_bg = "#FAFFFE" if (is_dep and is_active) else ("#F9FAFC" if not is_dep else "#fff")

        rows_html += (
            f"<div class='mh-tl-row' style='background:{row_bg};'>"
            f"<div class='mh-tl-bar' style='background:{bar_clr};'></div>"
            f"<div>{badge}</div>"
            f"<div>{cust_disp}{wo_hint}</div>"
            f"<div>{site_disp}</div>"
            f"<div style='font-size:12px;color:#374151;'>{_fmt(start_d)}</div>"
            f"<div style='font-size:12px;color:#374151;'>{end_disp}</div>"
            f"<div style='font-size:12px;font-weight:600;color:#374151;'>{duration}</div>"
            f"<div>{rental_disp}</div>"
            f"</div>"
        )

    st.markdown(rows_html, unsafe_allow_html=True)
