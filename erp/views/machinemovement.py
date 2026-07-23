"""
erp/views/machinemovement.py
Machine Movement — record Load, Transit, and Unload movements for a machine.

SQL DDL (reference only — do not execute here):

CREATE TABLE machine_movements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    movement_code   TEXT NOT NULL UNIQUE,
    machine_id      UUID NOT NULL REFERENCES machines(id),
    asset_code      TEXT NOT NULL,
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('Load','Transit','Unload')),
    from_location   TEXT,
    to_location     TEXT,
    movement_date   DATE NOT NULL,
    comments        TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    created_by      TEXT
);
CREATE INDEX ON machine_movements(machine_id);
CREATE INDEX ON machine_movements(movement_date DESC);
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from erp.supabase_client import SupabaseClient
from erp import auth as _auth  # noqa: F401
from erp.views._lock import status_chip

# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ──────────────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin: 0 0 28px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 18px 22px 14px;
    position: relative;
    overflow: hidden;
    transition: box-shadow .18s, transform .18s;
}
.kpi-card:hover { box-shadow: 0 6px 20px rgba(0,0,0,.08); transform: translateY(-2px); }
.kpi-accent-bar {
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 10px; display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 34px; font-weight: 800; color: #111827;
    line-height: 1; margin-bottom: 6px; font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 11px; color: #6B7280; }
.kpi-icon { position: absolute; top: 16px; right: 18px; font-size: 22px; opacity: .12; }

/* ── Info chips ──────────────────────────────────────────────────────────── */
.info-chip {
    background: #F8FAFC; border: 1px solid #E2EBF0;
    border-radius: 8px; padding: 8px 12px; min-width: 100px;
}
.info-chip .ic-label { font-size: 11px; color: #64748B; font-weight: 500; margin-bottom: 2px; }
.info-chip .ic-value { font-size: 13px; color: #1E293B; font-weight: 600; }

/* ── Form section header ─────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
.empty-state-v2 {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 56px 40px;
    background: #FAFBFC; border: 2px dashed #E2EBF0;
    border-radius: 16px; text-align: center; animation: cs-fadeup .35s ease;
}
.empty-icon-ring {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px; margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 { font-size: 17px; font-weight: 700; color: #111827; margin: 0 0 8px; }
.empty-state-v2 p  { font-size: 13px; color: #9CA3AF; max-width: 270px; line-height: 1.6; margin: 0; }

/* ── Current Status Summary Card ─────────────────────────────────────────── */
.status-summary {
    border-radius: 14px;
    padding: 22px 26px;
    margin-bottom: 20px;
    display: flex; align-items: flex-start; gap: 20px;
    border: 1px solid transparent;
    animation: cs-fadeup .3s ease;
}
.status-summary.st-load    { background: linear-gradient(135deg,#DCFCE7,#F0FDF4); border-color: #86EFAC; }
.status-summary.st-transit { background: linear-gradient(135deg,#FEF3C7,#FFFBEB); border-color: #FCD34D; }
.status-summary.st-unload  { background: linear-gradient(135deg,#EFF6FF,#DBEAFE); border-color: #93C5FD; }
.status-summary.st-none    { background: linear-gradient(135deg,#F8FAFC,#F1F5F9); border-color: #E2EBF0; }
.ss-icon-ring {
    width: 54px; height: 54px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; font-size: 26px;
}
.ss-icon-ring.load    { background: #10B981; }
.ss-icon-ring.transit { background: #F59E0B; }
.ss-icon-ring.unload  { background: #2563EB; }
.ss-icon-ring.none    { background: #9CA3AF; }
.ss-body { flex: 1; }
.ss-status-label {
    font-size: 11px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; margin-bottom: 4px; color: #6B7280;
}
.ss-status-value {
    font-size: 22px; font-weight: 800; color: #111827;
    margin-bottom: 10px; line-height: 1.1;
}
.ss-meta { display: flex; gap: 24px; flex-wrap: wrap; }
.ss-meta-item { font-size: 12px; color: #374151; }
.ss-meta-item strong { font-weight: 700; color: #111827; }
.ss-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 700; letter-spacing: .04em;
}
.ss-badge.load    { background: #10B981; color: #fff; }
.ss-badge.transit { background: #F59E0B; color: #fff; }
.ss-badge.unload  { background: #2563EB; color: #fff; }
.ss-badge.none    { background: #E5E7EB; color: #374151; }

/* ── Journey Stepper ─────────────────────────────────────────────────────── */
.journey-stepper {
    display: flex; align-items: flex-start;
    gap: 0; margin: 0 0 24px; padding: 20px 24px;
    background: #fff; border: 1px solid #E2EBF0;
    border-radius: 14px; animation: cs-fadeup .35s ease;
}
.step-wrap { display: flex; flex-direction: column; align-items: center; flex: 1; position: relative; }
.step-connector {
    position: absolute; top: 22px; left: 50%; right: -50%;
    height: 2px; background: #E5E7EB; z-index: 0;
}
.step-connector.done { background: #10B981; }
.step-connector.active { background: linear-gradient(90deg, #10B981 0%, #E5E7EB 100%); }
.step-icon-outer {
    width: 44px; height: 44px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; z-index: 1; position: relative;
    transition: all .2s;
}
.step-icon-outer.done    { background: #10B981; box-shadow: 0 0 0 4px #DCFCE7; }
.step-icon-outer.active  { background: #F59E0B; box-shadow: 0 0 0 4px #FEF3C7; animation: pulse-ring 1.6s infinite; }
.step-icon-outer.pending { background: #F3F4F6; border: 2px solid #E5E7EB; }
.step-label {
    font-size: 11px; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; margin-top: 10px; text-align: center;
    color: #111827;
}
.step-label.pending { color: #9CA3AF; }
.step-sub  { font-size: 11px; color: #6B7280; text-align: center; margin-top: 3px; max-width: 110px; }
.step-sub.pending { color: #D1D5DB; }

@keyframes pulse-ring {
    0%   { box-shadow: 0 0 0 4px rgba(245,158,11,.35); }
    50%  { box-shadow: 0 0 0 8px rgba(245,158,11,.10); }
    100% { box-shadow: 0 0 0 4px rgba(245,158,11,.35); }
}

/* ── Movement Timeline ───────────────────────────────────────────────────── */
.tl-wrap { position: relative; padding: 4px 0 4px 0; margin-top: 6px; }
.tl-event {
    display: flex; gap: 16px;
    margin-bottom: 0; padding: 16px 20px 16px 0;
    position: relative; animation: cs-fadeup .3s ease;
}
.tl-left {
    display: flex; flex-direction: column; align-items: center;
    width: 44px; flex-shrink: 0;
}
.tl-dot {
    width: 40px; height: 40px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; flex-shrink: 0; z-index: 1;
}
.tl-dot.load    { background: #DCFCE7; color: #15803D; border: 2px solid #86EFAC; }
.tl-dot.transit { background: #FEF3C7; color: #B45309; border: 2px solid #FCD34D; }
.tl-dot.unload  { background: #EFF6FF; color: #1D4ED8; border: 2px solid #93C5FD; }
.tl-line {
    width: 2px; background: #E5E7EB; flex: 1; min-height: 20px;
    margin-top: 4px;
}
.tl-body { flex: 1; padding-bottom: 8px; }
.tl-friendly {
    font-size: 14px; font-weight: 700; color: #111827; margin-bottom: 3px;
    display: flex; align-items: center; gap: 10px;
}
.tl-badge {
    font-size: 10px; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; padding: 2px 8px; border-radius: 20px;
}
.tl-badge.load    { background: #DCFCE7; color: #15803D; }
.tl-badge.transit { background: #FEF3C7; color: #B45309; }
.tl-badge.unload  { background: #EFF6FF; color: #1D4ED8; }
.tl-date   { font-size: 12px; color: #6B7280; margin-bottom: 6px; }
.tl-locs   { font-size: 12px; color: #374151; display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 4px; }
.tl-loc-item { display: flex; align-items: center; gap: 4px; }
.tl-comment {
    font-size: 12px; color: #6B7280;
    background: #F8FAFC; border-left: 3px solid #E2EBF0;
    padding: 6px 10px; border-radius: 0 6px 6px 0;
    margin-top: 6px; font-style: italic;
}
.tl-code {
    font-size: 10px; color: #9CA3AF; margin-top: 4px;
    font-family: monospace; letter-spacing: .03em;
}

/* ── Animations ─────────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _kpi_card(icon: str, label: str, value, sub: str = "", accent: str = "#2563EB") -> str:
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


def _info_chip(label: str, value: str, badge_html: str = "") -> str:
    inner = badge_html if badge_html else f"<div class='ic-value'>{value or '—'}</div>"
    return (
        f"<div class='info-chip'>"
        f"<div class='ic-label'>{label}</div>"
        f"{inner}"
        f"</div>"
    )


def _op_badge_cls(status: str) -> str:
    return {
        "Available":    "badge-available",
        "On Rent":      "badge-on-rent",
        "Reserved":     "badge-reserved",
        "Mobilizing":   "badge-mobilizing",
        "Demobilizing": "badge-demobilizing",
        "Sold":         "badge-sold",
    }.get(status, "badge-available")


def _mov_code(asset_code: str) -> str:
    return f"MOV-{asset_code}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _site_label(s: dict) -> str:
    city = s.get("city") or ""
    city_part = f" ({city})" if city else ""
    return f"{s.get('site_code', '')} · {s.get('site_name', '')}{city_part}"


def _fmt_date(d) -> str:
    """Format a date string as '19 Jul 2026'."""
    if not d:
        return "—"
    try:
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        return d.strftime("%-d %b %Y")
    except Exception:
        try:
            if isinstance(d, str):
                d = date.fromisoformat(d[:10])
            return d.strftime("%d %b %Y").lstrip("0")
        except Exception:
            return str(d)


# ── Status Summary Card ───────────────────────────────────────────────────────

_STATUS_META = {
    "Load": {
        "cls": "load", "icon": "upload",
        "label": "Machine Loaded",
        "sub": "Machine has been loaded and is ready for dispatch",
    },
    "Transit": {
        "cls": "transit", "icon": "local_shipping",
        "label": "Machine In Transit",
        "sub": "Machine is currently on the move",
    },
    "Unload": {
        "cls": "unload", "icon": "download",
        "label": "Machine Arrived",
        "sub": "Machine has reached the destination and been unloaded",
    },
}

_FRIENDLY = {
    "Load":    "Machine Loaded",
    "Transit": "Machine In Transit",
    "Unload":  "Machine Unloaded / Arrived",
}

_FRIENDLY_DETAIL = {
    "Load":    "Loaded and dispatched",
    "Transit": "En route to destination",
    "Unload":  "Arrived at destination",
}


def _status_summary_html(movements: list) -> str:
    if not movements:
        return (
            "<div class='status-summary st-none'>"
            "<div class='ss-icon-ring none'>"
            "<span class='msr' style='color:#fff;font-size:26px;'>swap_vert</span>"
            "</div>"
            "<div class='ss-body'>"
            "<div class='ss-status-label'>Current Status</div>"
            "<div class='ss-status-value'>No Movements Yet</div>"
            "<div class='ss-meta'>"
            "<div class='ss-meta-item'>Record a Load event to start tracking this machine's journey.</div>"
            "</div></div></div>"
        )

    latest = movements[0]
    mtype  = latest.get("movement_type", "")
    meta   = _STATUS_META.get(mtype, _STATUS_META["Load"])

    from_loc  = latest.get("from_location") or "—"
    to_loc    = latest.get("to_location")   or "—"
    mov_date  = _fmt_date(latest.get("movement_date"))

    meta_items = (
        f"<div class='ss-meta-item'><strong>Current Location:</strong> {from_loc}</div>"
        f"<div class='ss-meta-item'><strong>Destination:</strong> {to_loc}</div>"
        f"<div class='ss-meta-item'><strong>Last Updated:</strong> {mov_date}</div>"
    )

    return (
        f"<div class='status-summary st-{meta['cls']}'>"
        f"<div class='ss-icon-ring {meta['cls']}'>"
        f"<span class='msr' style='color:#fff;font-size:26px;'>{meta['icon']}</span>"
        f"</div>"
        f"<div class='ss-body'>"
        f"<div class='ss-status-label'>Current Status</div>"
        f"<div class='ss-status-value'>"
        f"<span class='ss-badge {meta['cls']}'>"
        f"<span class='msr' style='font-size:12px;'>{meta['icon']}</span>"
        f"{meta['label']}"
        f"</span>"
        f"</div>"
        f"<div class='ss-meta'>{meta_items}</div>"
        f"</div>"
        f"</div>"
    )


# ── Journey Stepper ───────────────────────────────────────────────────────────

def _journey_stepper_html(movements: list) -> str:
    """Build a 3-step horizontal stepper from movement history."""
    if not movements:
        return ""

    latest_type = movements[0].get("movement_type", "")

    # Determine step states
    # Load = step 1, Transit = step 2, Unload = step 3
    step_state = ["pending", "pending", "pending"]
    load_m = transit_m = unload_m = None

    # Walk chronologically (reversed since list is latest-first)
    for m in reversed(movements):
        mt = m.get("movement_type", "")
        if mt == "Load":
            load_m    = m
        elif mt == "Transit":
            transit_m = m
        elif mt == "Unload":
            unload_m  = m

    if latest_type == "Load":
        step_state = ["active", "pending", "pending"]
    elif latest_type == "Transit":
        step_state = ["done", "active", "pending"]
    elif latest_type == "Unload":
        step_state = ["done", "done", "done"]

    def _step_icon(state: str, icon: str) -> str:
        if state == "done":
            return f"<span class='msr' style='color:#fff;font-size:20px;'>check_circle</span>"
        elif state == "active":
            return f"<span class='msr' style='color:#fff;font-size:20px;'>{icon}</span>"
        else:
            return f"<span class='msr' style='color:#9CA3AF;font-size:20px;'>{icon}</span>"

    def _connector_cls(left_state: str) -> str:
        if left_state == "done":
            return "done"
        if left_state == "active":
            return "active"
        return ""

    steps = [
        {"icon": "upload",         "label": "Loaded",     "movement": load_m},
        {"icon": "local_shipping", "label": "In Transit", "movement": transit_m},
        {"icon": "download",       "label": "Delivered",  "movement": unload_m},
    ]

    html = "<div class='journey-stepper'>"
    for i, (step, state) in enumerate(zip(steps, step_state)):
        m = step["movement"]
        sub_date = _fmt_date(m.get("movement_date")) if m else "—"
        sub_loc  = (m.get("to_location") or m.get("from_location") or "—") if m else "—"
        if len(sub_loc) > 22:
            sub_loc = sub_loc[:20] + "…"

        conn_cls = _connector_cls(step_state[i]) if i < 2 else ""

        html += f"<div class='step-wrap'>"
        if i < 2:
            html += f"<div class='step-connector {conn_cls}'></div>"
        html += (
            f"<div class='step-icon-outer {state}'>"
            f"{_step_icon(state, step['icon'])}"
            f"</div>"
            f"<div class='step-label {'pending' if state == 'pending' else ''}'>{step['label']}</div>"
            f"<div class='step-sub {'pending' if state == 'pending' else ''}'>{sub_date}</div>"
            f"<div class='step-sub {'pending' if state == 'pending' else ''}'>{sub_loc}</div>"
            f"</div>"
        )
    html += "</div>"
    return html


# ── Movement Timeline ─────────────────────────────────────────────────────────

def _timeline_html(movements: list) -> str:
    if not movements:
        return ""

    html = "<div class='tl-wrap'>"
    for idx, m in enumerate(movements):
        mtype     = m.get("movement_type", "")
        cls       = {"Load": "load", "Transit": "transit", "Unload": "unload"}.get(mtype, "load")
        icon      = {"Load": "upload", "Transit": "local_shipping", "Unload": "download"}.get(mtype, "swap_vert")
        friendly  = _FRIENDLY.get(mtype, mtype)
        detail    = _FRIENDLY_DETAIL.get(mtype, "")
        mov_date  = _fmt_date(m.get("movement_date"))
        from_loc  = m.get("from_location") or ""
        to_loc    = m.get("to_location")   or ""
        comment   = m.get("comments")      or ""
        code      = m.get("movement_code") or ""

        locs_html = ""
        if from_loc:
            locs_html += (
                f"<div class='tl-loc-item'>"
                f"<span class='msr' style='font-size:13px;color:#9CA3AF;'>location_on</span>"
                f"<span><strong style='color:#374151;'>From:</strong> {from_loc}</span>"
                f"</div>"
            )
        if to_loc:
            locs_html += (
                f"<div class='tl-loc-item'>"
                f"<span class='msr' style='font-size:13px;color:#9CA3AF;'>flag</span>"
                f"<span><strong style='color:#374151;'>To:</strong> {to_loc}</span>"
                f"</div>"
            )

        comment_html = (
            f"<div class='tl-comment'>"
            f"<span class='msr' style='font-size:12px;vertical-align:middle;margin-right:4px;'>chat</span>"
            f"{comment}</div>"
        ) if comment else ""

        code_html = (
            f"<div class='tl-code'>Ref: {code}</div>"
        ) if code else ""

        rec_chip_html = status_chip(m.get("record_status") or "Draft")

        is_last    = idx == len(movements) - 1
        line_html  = "" if is_last else "<div class='tl-line'></div>"

        html += (
            f"<div class='tl-event'>"
            f"  <div class='tl-left'>"
            f"    <div class='tl-dot {cls}'>"
            f"      <span class='msr' style='font-size:18px;'>{icon}</span>"
            f"    </div>"
            f"    {line_html}"
            f"  </div>"
            f"  <div class='tl-body'>"
            f"    <div class='tl-friendly'>"
            f"      {friendly}"
            f"      <span class='tl-badge {cls}'>{mtype}</span>"
            f"    </div>"
            f"    <div class='tl-date'>"
            f"      <span class='msr' style='font-size:12px;vertical-align:middle;'>calendar_today</span>"
            f"      {mov_date}"
            f"      {'<span style=\"margin-left:6px;font-size:11px;color:#9CA3AF;\">' + detail + '</span>' if detail else ''}"
            f"    </div>"
            f"    <div class='tl-locs'>{locs_html}</div>"
            f"    {comment_html}"
            f"    {code_html}"
            f"    <div style='margin-top:6px;'>{rec_chip_html}</div>"
            f"  </div>"
            f"</div>"
        )
    html += "</div>"
    return html


# ── Save helper ───────────────────────────────────────────────────────────────

def _save_movement(
    sb: SupabaseClient,
    machine: dict,
    movement_type: str,
    from_location,
    to_location,
    movement_date: date,
    comments,
) -> None:
    asset_code = machine.get("asset_code", "UNK")
    payload = {
        "movement_code": _mov_code(asset_code),
        "machine_id":    machine["id"],
        "asset_code":    asset_code,
        "movement_type": movement_type,
        "from_location": from_location or None,
        "to_location":   to_location   or None,
        "movement_date": movement_date.isoformat(),
        "comments":      (comments or "").strip() or None,
    }
    sb.insert_machine_movement(payload)


# ── Main view ─────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div class='page-eyebrow'>// Fleet Operations</div>"
        "<div class='page-title'>Machine Movement</div>",
        unsafe_allow_html=True,
    )

    # ── Data load ─────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    try:
        all_machines = sb.list_machines()
    except Exception as exc:
        st.error(f"Failed to load machines: {exc}")
        return

    try:
        all_sites = sb.list_sites()
    except Exception as exc:
        st.warning(f"Could not load sites: {exc}")
        all_sites = []

    # KPI strip from all movements
    try:
        all_movements = sb.list_machine_movements()
    except Exception:
        all_movements = []

    n_total   = len(all_movements)
    n_load    = sum(1 for m in all_movements if m.get("movement_type") == "Load")
    n_transit = sum(1 for m in all_movements if m.get("movement_type") == "Transit")
    n_unload  = sum(1 for m in all_movements if m.get("movement_type") == "Unload")

    st.markdown(
        "<div class='kpi-grid'>"
        + _kpi_card("swap_vert",      "Total Movements", n_total,   "all recorded movements",   "#2563EB")
        + _kpi_card("upload",         "Load Events",     n_load,    "machines loaded to site",  "#10B981")
        + _kpi_card("local_shipping", "Transit Updates", n_transit, "in-transit records",       "#F59E0B")
        + _kpi_card("download",       "Unload Events",   n_unload,  "machines returned",        "#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Session state ─────────────────────────────────────────────────────────
    if "_mm_sel_id" not in st.session_state:
        st.session_state["_mm_sel_id"] = ""

    # ── Machine Selector ──────────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("precision_manufacturing", "Select Machine")

        active_machines = sorted(
            [m for m in all_machines if m.get("asset_code")],
            key=lambda m: m.get("asset_code", ""),
        )
        machine_options = [""] + [
            f"{m['asset_code']} · {' '.join(filter(None, [m.get('make'), m.get('model')]))}"
            if (m.get("make") or m.get("model")) else m["asset_code"]
            for m in active_machines
        ]
        machine_id_map = {
            f"{m['asset_code']} · {' '.join(filter(None, [m.get('make'), m.get('model')]))}"
            if (m.get("make") or m.get("model")) else m["asset_code"]: m
            for m in active_machines
        }

        saved_id    = st.session_state.get("_mm_sel_id", "")
        saved_label = ""
        if saved_id:
            for lbl, mc in machine_id_map.items():
                if mc.get("id") == saved_id:
                    saved_label = lbl
                    break
        sel_idx = machine_options.index(saved_label) if saved_label in machine_options else 0

        selected_label = st.selectbox(
            "Asset Code",
            options=machine_options,
            index=sel_idx,
            format_func=lambda v: "Select a machine…" if not v else v,
            key="mm_machine_sel",
        )

        selected_machine = machine_id_map.get(selected_label) if selected_label else None

        if selected_machine:
            st.session_state["_mm_sel_id"] = selected_machine.get("id", "")
            op_status  = selected_machine.get("operational_status", "")
            badge_cls  = _op_badge_cls(op_status)
            badge_html = f"<span class='{badge_cls}' style='margin-top:2px;display:inline-block;'>{op_status}</span>"

            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.markdown(_info_chip("Machine Type", selected_machine.get("machine_type", "")), unsafe_allow_html=True)
            with c2:
                st.markdown(_info_chip("Make", selected_machine.get("make", "")), unsafe_allow_html=True)
            with c3:
                st.markdown(_info_chip("Model", selected_machine.get("model", "")), unsafe_allow_html=True)
            with c4:
                st.markdown(_info_chip("Current Location", selected_machine.get("current_location", "")), unsafe_allow_html=True)
            with c5:
                st.markdown(_info_chip("Operational Status", op_status, badge_html=badge_html), unsafe_allow_html=True)
        else:
            st.markdown(
                "<div class='empty-state-v2' style='padding:32px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:32px;color:#2563EB;'>precision_manufacturing</span>"
                "</div>"
                "<h3>No machine selected</h3>"
                "<p>Choose an asset code from the dropdown above to record a movement.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

    # ── Business rule enforcement ─────────────────────────────────────────────
    op_status = selected_machine.get("operational_status", "")

    if op_status == "On Rent":
        st.error("This machine is currently **On Rent** and cannot be moved.", icon="🚫")
        return

    if op_status == "Reserved":
        st.warning(
            "This machine is **Reserved**. It can be moved, but please verify with the "
            "deployment team before proceeding.",
            icon="⚠",
        )

    # ── Load this machine's movements ─────────────────────────────────────────
    try:
        movements = sb.list_machine_movements(machine_id=selected_machine["id"])
    except Exception as exc:
        st.warning(f"Could not load movement history: {exc}")
        movements = []

    # ── Current Status Summary + Journey Stepper ──────────────────────────────
    st.markdown(
        _status_summary_html(movements)
        + ("<div style='margin:0 0 4px;'>" + _journey_stepper_html(movements) + "</div>"
           if movements else ""),
        unsafe_allow_html=True,
    )

    # ── Site DDL ──────────────────────────────────────────────────────────────
    site_labels  = [_site_label(s) for s in all_sites if s.get("site_code")]
    site_options = sorted(site_labels)
    asset_code   = selected_machine.get("asset_code", "")
    from_loc     = selected_machine.get("current_location") or ""

    # ── Section A: Load Machine ───────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("upload", "Load Machine")
        la1, la2 = st.columns([3, 2])
        with la1:
            load_dest = st.selectbox("To Location (Site)", options=site_options, key="mm_load_to_site")
        with la2:
            load_date = st.date_input("Movement Date", value=date.today(), key="mm_load_date")
        if st.button("Machine Load", type="primary", key="mm_load_save"):
            to_loc = load_dest
            if not to_loc:
                st.error("Please specify a destination location.")
            else:
                try:
                    _save_movement(sb, selected_machine, "Load", from_loc or None, to_loc, load_date, None)
                    try:
                        sb.update_machine(selected_machine["id"], {"operational_status": "Mobilizing"})
                    except Exception:
                        pass
                    st.toast(f"Load movement recorded for {asset_code}. Status set to Mobilizing.", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save movement: {exc}")

    # ── Section B: Transit Update ─────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("local_shipping", "Transit Update")
        tb1, tb2 = st.columns([3, 2])
        with tb1:
            transit_comments = st.text_area(
                "Transit details / route / remarks",
                placeholder="e.g. En route Mumbai → Pune via NH-48, ETA tomorrow",
                height=90,
                key="mm_transit_comments",
            )
        with tb2:
            transit_date = st.date_input("Movement Date", value=date.today(), key="mm_transit_date")
        if st.button("Record Transit", type="primary", key="mm_transit_save"):
            try:
                _save_movement(sb, selected_machine, "Transit", from_loc or None, None, transit_date, transit_comments)
                st.toast(f"Transit update recorded for {asset_code}.", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save movement: {exc}")

    # ── Section C: Unload Machine ─────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("download", "Unload Machine")
        uc1, uc2 = st.columns([3, 2])
        with uc1:
            unload_dest = st.selectbox("To Location (Site)", options=site_options, key="mm_unload_to_site")
        with uc2:
            unload_date = st.date_input("Movement Date", value=date.today(), key="mm_unload_date")
        if st.button("Record Unload", type="primary", key="mm_unload_save"):
            to_loc = unload_dest
            if not to_loc:
                st.error("Please specify a destination location.")
            else:
                try:
                    _save_movement(sb, selected_machine, "Unload", from_loc or None, to_loc, unload_date, None)
                    try:
                        sb.update_machine(selected_machine["id"], {
                            "current_location": to_loc,
                            "operational_status": "Reserved",
                        })
                    except Exception:
                        pass
                    st.toast(f"Unload recorded for {asset_code}. Status set to Reserved.", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save movement: {exc}")

    # ── Movement Timeline ─────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        _section_hdr("timeline", "Machine Journey Timeline")
        if not movements:
            st.markdown(
                "<div style='text-align:center;padding:32px 12px;color:#9CA3AF;font-size:13px;'>"
                "<span class='msr' style='font-size:36px;display:block;margin-bottom:10px;"
                "color:#D1D5DB;'>route</span>"
                "<strong style='color:#6B7280;display:block;margin-bottom:4px;'>No journey recorded yet</strong>"
                "Use the forms above to record the first movement for this machine."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(_timeline_html(movements), unsafe_allow_html=True)
