"""
erp/views/closeworkorder.py
Close Work Order — review all associated details and machines,
then close the WO and release every machine back to Available.
"""
from __future__ import annotations

import json
from datetime import date

import streamlit as st

from ..supabase_client import SupabaseClient

# ── Closeable statuses (everything except already terminal) ───────────────────
_OPEN_STATUSES   = {"Draft", "Active", "Completed"}
_CLOSED_STATUSES = {"Closed", "Cancelled"}

# ── Machine status colour map ─────────────────────────────────────────────────
_STATUS_STYLE = {
    "Available":    ("#D1FAE5", "#065F46", "#6EE7B7"),
    "Reserved":     ("#FEF9C3", "#713F12", "#FCD34D"),
    "Mobilizing":   ("#DBEAFE", "#1E40AF", "#93C5FD"),
    "On Rent":      ("#F3E8FF", "#6B21A8", "#C084FC"),
    "Demobilizing": ("#FEE2E2", "#991B1B", "#FCA5A5"),
    "Sold":         ("#F3F4F6", "#374151", "#9CA3AF"),
}

# ── CSS ───────────────────────────────────────────────────────────────────────
_PAGE_CSS = """
<style>
/* ── KPI strip ──────────────────────────────────────────────────────── */
.cwo-kpi-grid {
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
    margin-bottom: 10px; display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 34px; font-weight: 800;
    color: #111827; line-height: 1; margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 11px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 16px; right: 18px;
    font-size: 22px; opacity: .12;
}

/* ── Search wrapper ─────────────────────────────────────────────────── */
.search-wrap { position: relative; margin-bottom: 8px; }
.search-icon-abs {
    position: absolute; left: 11px; top: 50%;
    transform: translateY(-50%);
    font-size: 16px; color: #9CA3AF;
    z-index: 10; pointer-events: none;
}
.search-wrap .stTextInput input {
    padding-left: 34px !important;
    border-radius: 8px !important;
}

/* ── WO list cards ──────────────────────────────────────────────────── */
.cwo-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 10px;
    padding: 10px 13px 9px;
    pointer-events: none;
    transition: box-shadow .16s, border-color .16s;
}
.cwo-card.cwo-sel {
    border-color: #DC2626 !important;
    background: #FFF5F5;
    border-left-width: 3px;
}
.cwo-num {
    font-size: 13px; font-weight: 700; color: #111827;
    flex: 1; min-width: 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cwo-sub {
    font-size: 11px; color: #6B7280;
    display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
    margin: 3px 0;
}
.cwo-dot {
    width: 3px; height: 3px; border-radius: 50%;
    background: #D1D5DB; flex-shrink: 0; display: inline-block;
}

/* ── Status badge ───────────────────────────────────────────────────── */
.wo-status-badge {
    font-size: 9px; font-weight: 700;
    padding: 2px 8px; border-radius: 20px;
    letter-spacing: .06em; text-transform: uppercase;
    white-space: nowrap;
}

/* ── Empty state ─────────────────────────────────────────────────────── */
.cwo-empty {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 72px 40px;
    background: #FAFBFC; border: 2px dashed #E2EBF0;
    border-radius: 16px; text-align: center;
}
.cwo-empty-ring {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(145deg, #FFF5F5, #FEE2E2);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px; margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(220,38,38,.14);
}
.cwo-empty h3 { font-size: 17px; font-weight: 700; color: #111827; margin: 0 0 8px; }
.cwo-empty p  { font-size: 13px; color: #9CA3AF; max-width: 270px; line-height: 1.6; margin: 0; }

/* ── Hero banner ─────────────────────────────────────────────────────── */
.cwo-hero {
    background: linear-gradient(135deg, #1A1F2E 0%, #3B0000 60%, #4C0519 100%);
    border-radius: 14px; padding: 22px 24px; margin-bottom: 18px;
    display: flex; align-items: flex-start; gap: 16px;
    position: relative; overflow: hidden;
    animation: cwo-fadeup .3s ease;
}
.cwo-hero::before {
    content: ''; position: absolute; top: -40px; right: -40px;
    width: 160px; height: 160px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.cwo-hero-icon {
    width: 52px; height: 52px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 24px; background: rgba(220,38,38,.25);
    border: 1px solid rgba(220,38,38,.40); flex-shrink: 0;
}
.cwo-hero-num  { font-size: 20px; font-weight: 800; color: #fff; line-height: 1.2; }
.cwo-hero-meta { font-size: 11px; color: rgba(255,255,255,.45); letter-spacing: .06em; margin-top: 4px; }
.cwo-hero-badges { margin-top: 7px; display: flex; gap: 6px; flex-wrap: wrap; }

/* ── Info grid ───────────────────────────────────────────────────────── */
.info-grid {
    display: grid; grid-template-columns: repeat(2, 1fr);
    gap: 10px; margin-bottom: 14px;
}
.info-field {
    background: #F8FAFC; border: 1px solid #E2EBF0;
    border-radius: 8px; padding: 11px 14px;
}
.info-field-label {
    font-size: 9px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 4px;
}
.info-field-value { font-size: 13px; font-weight: 600; color: #111827; word-break: break-word; }
.info-field-value.muted { font-weight: 400; color: #9CA3AF; }

/* ── Section header ──────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722; margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Machine card ────────────────────────────────────────────────────── */
.mc-card {
    background: #fff; border: 1px solid #E2EBF0;
    border-radius: 12px; padding: 16px 18px; margin-bottom: 10px;
}
.mc-card-top {
    display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
}
.mc-avatar {
    width: 42px; height: 42px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.mc-label { font-size: 14px; font-weight: 700; color: #111827; }
.mc-serial { font-size: 11px; color: #6B7280; margin-top: 2px; }
.mc-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 8px;
}
.mc-field { background: #F8FAFC; border-radius: 6px; padding: 8px 10px; }
.mc-field-label {
    font-size: 8px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 3px;
}
.mc-field-value { font-size: 12px; font-weight: 600; color: #111827; }

/* ── Warning box ─────────────────────────────────────────────────────── */
.close-warning {
    background: #FFF5F5; border: 1.5px solid #FECACA;
    border-radius: 12px; padding: 18px 20px; margin-bottom: 18px;
    display: flex; gap: 12px; align-items: flex-start;
}
.close-warning-icon { font-size: 22px; flex-shrink: 0; margin-top: 2px; }
.close-warning-title { font-size: 14px; font-weight: 700; color: #991B1B; margin-bottom: 4px; }
.close-warning-body  { font-size: 12px; color: #7F1D1D; line-height: 1.6; }

/* ── Already-closed banner ───────────────────────────────────────────── */
.closed-banner {
    background: #F0FDF4; border: 1.5px solid #86EFAC;
    border-radius: 12px; padding: 16px 20px;
    display: flex; gap: 12px; align-items: center;
    margin-bottom: 18px;
}

/* ── Tabs polish ─────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important; background: transparent !important;
    border-bottom: 2px solid #E2EBF0 !important; padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 12px !important; font-weight: 600 !important;
    color: #6B7280 !important; padding: 8px 18px !important;
    border-radius: 0 !important; background: transparent !important;
    border: none !important; margin: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: color .14s !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #374151 !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #DC2626 !important;
    border-bottom: 2px solid #DC2626 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-panel"]     { padding: 18px 0 0 !important; }

/* ── No-results ──────────────────────────────────────────────────────── */
.no-results { text-align: center; padding: 36px 12px; color: #9CA3AF; font-size: 13px; }
.no-results .nr-icon { font-size: 32px; margin-bottom: 8px; display: block; }

@keyframes cwo-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_machine_config(raw) -> list[dict]:
    if not raw:
        return []
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        return records if isinstance(records, list) else []
    except Exception:
        return []


def _kpi_card(icon: str, label: str, value: int | str, sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _status_badge(status: str) -> str:
    bg, fg, _ = _STATUS_STYLE.get(status, ("#F3F4F6", "#374151", "#9CA3AF"))
    return (
        f"<span class='wo-status-badge' "
        f"style='background:{bg};color:{fg};border:1px solid {_};'>"
        f"{status}</span>"
    )


def _wo_status_badge(status: str) -> str:
    styles = {
        "Draft":     ("#F3F4F6", "#374151"),
        "Active":    ("#DBEAFE", "#1E40AF"),
        "Completed": ("#F0FDF4", "#166534"),
        "Closed":    ("#FEF3C7", "#92400E"),
        "Cancelled": ("#FEE2E2", "#991B1B"),
    }
    bg, fg = styles.get(status, ("#F3F4F6", "#374151"))
    return f"<span class='wo-status-badge' style='background:{bg};color:{fg};'>{status}</span>"


def _info_field(label: str, value: str, wide: bool = False, muted: bool = False) -> str:
    val_cls = "info-field-value muted" if (muted or not value or value == "—") else "info-field-value"
    disp    = value if value else "—"
    return (
        f"<div class='info-field' style='grid-column:{'span 2' if wide else 'span 1'};'>"
        f"<div class='info-field-label'>{label}</div>"
        f"<div class='{val_cls}'>{disp}</div>"
        f"</div>"
    )


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


_AVATAR_PALETTE = [
    "#2563EB", "#8B5CF6", "#10B981", "#F59E0B",
    "#EF4444", "#EC4899", "#14B8A6", "#F97316",
]

def _avatar_color(name: str) -> str:
    return _AVATAR_PALETTE[sum(ord(c) for c in (name or "A")) % len(_AVATAR_PALETTE)]


def _machine_card(mc: dict, machine_rec: dict | None) -> str:
    label   = mc.get("machine_label", "—")
    make    = mc.get("make", "") or ""
    model   = mc.get("model", "") or ""
    serial  = mc.get("serial_number", "") or ""
    rental  = mc.get("rental_per_month") or 0
    billing = mc.get("billing_type", "") or ""
    days    = mc.get("no_of_days", "") or ""

    op_status = (machine_rec or {}).get("operational_status", "Unknown") if machine_rec else "Unknown"
    cond      = (machine_rec or {}).get("condition_status", "") if machine_rec else ""
    location  = (machine_rec or {}).get("current_location", "") if machine_rec else ""

    color  = _avatar_color(label)
    initials = (label[:2] or "??").upper()
    bg, fg, border = _STATUS_STYLE.get(op_status, ("#F3F4F6", "#374151", "#9CA3AF"))

    rental_fmt = f"₹ {float(rental):,.0f}" if rental else "—"
    days_fmt   = f"{days} days" if days else "—"

    return (
        f"<div class='mc-card'>"
        f"<div class='mc-card-top'>"
        f"<div class='mc-avatar' style='background:{color};'>{initials}</div>"
        f"<div style='flex:1;min-width:0;'>"
        f"<div class='mc-label'>{label}</div>"
        f"<div class='mc-serial'>"
        + (f"S/N: {serial}" if serial else "")
        + (f" &nbsp;|&nbsp; {make} {model}".strip(" |&nbsp;") if make or model else "")
        + f"</div>"
        f"</div>"
        f"<span class='wo-status-badge' style='background:{bg};color:{fg};border:1px solid {border};'>"
        f"{op_status}</span>"
        f"</div>"
        f"<div class='mc-grid'>"
        f"<div class='mc-field'><div class='mc-field-label'>Rental / Month</div>"
        f"<div class='mc-field-value'>{rental_fmt}</div></div>"
        f"<div class='mc-field'><div class='mc-field-label'>Billing Type</div>"
        f"<div class='mc-field-value'>{billing or '—'}</div></div>"
        f"<div class='mc-field'><div class='mc-field-label'>No. of Days</div>"
        f"<div class='mc-field-value'>{days_fmt}</div></div>"
        f"<div class='mc-field'><div class='mc-field-label'>Condition</div>"
        f"<div class='mc-field-value'>{cond or '—'}</div></div>"
        f"<div class='mc-field'><div class='mc-field-label'>Location</div>"
        f"<div class='mc-field-value'>{location or '—'}</div></div>"
        f"<div class='mc-field'><div class='mc-field-label'>After Close →</div>"
        f"<div class='mc-field-value' style='color:#065F46;'>Available</div></div>"
        f"</div></div>"
    )


# ── Main view ──────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div class='page-eyebrow'>// Fleet Operations</div>"
        "<div class='page-title'>Close Work Order</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    def fetch_work_orders() -> list[dict]:
        try:
            return sb.list_work_orders()
        except Exception as exc:
            st.error(f"Failed to load work orders: {exc}")
            return []

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception:
            return []

    def fetch_sites() -> list[dict]:
        try:
            return sb.list_sites()
        except Exception:
            return []

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception:
            return []

    work_orders   = fetch_work_orders()
    customers     = fetch_customers()
    sites         = fetch_sites()
    machines_list = fetch_machines()

    customer_map = {c["id"]: c for c in customers  if c.get("id")}
    site_map     = {s["id"]: s for s in sites       if s.get("id")}
    machine_map  = {m["id"]: m for m in machines_list if m.get("id")}

    # Only show WOs that are not already terminal
    closeable_wos = [
        wo for wo in work_orders
        if wo.get("status") not in _CLOSED_STATUSES
    ]
    closed_wos = [
        wo for wo in work_orders
        if wo.get("status") in _CLOSED_STATUSES
    ]

    n_total    = len(work_orders)
    n_open     = len(closeable_wos)
    n_closed   = len(closed_wos)
    n_machines = sum(
        len(_parse_machine_config(wo.get("machine_config")))
        for wo in closeable_wos
    )

    # ── KPI strip ──────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='cwo-kpi-grid'>"
        + _kpi_card("assignment",    "Total WOs",      n_total,    "all work orders",    "#2563EB")
        + _kpi_card("pending",       "Open / Active",  n_open,     "can be closed now",  "#F59E0B")
        + _kpi_card("task_alt",      "Closed / Done",  n_closed,   "already closed",     "#10B981")
        + _kpi_card("construction",  "Active Machines",n_machines, "across open WOs",    "#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Session state ──────────────────────────────────────────────────────────
    if "_cwo_sel_id" not in st.session_state:
        st.session_state["_cwo_sel_id"] = ""
    if "_cwo_confirm" not in st.session_state:
        st.session_state["_cwo_confirm"] = False

    selected_id   = st.session_state["_cwo_sel_id"]
    wo_map        = {wo["id"]: wo for wo in work_orders if wo.get("id")}
    selected_wo   = wo_map.get(selected_id)

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — WO directory
    # ══════════════════════════════════════════════════════════════════════════
    with left_col:
        st.markdown(
            "<div class='search-wrap'>"
            "<span class='search-icon-abs msr'>search</span>",
            unsafe_allow_html=True,
        )
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search WO number or customer…",
            key="cwo_search_q",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        q = search_q.strip().lower()

        # Show all WOs (open first, then closed) — filter by search
        def _matches(wo: dict) -> bool:
            if not q:
                return True
            wo_num  = str(wo.get("wo_number", "")).lower()
            cid     = wo.get("customer_id", "")
            cname   = customer_map.get(cid, {}).get("customer_name", "").lower()
            return q in wo_num or q in cname

        shown_open   = [wo for wo in closeable_wos if _matches(wo)]
        shown_closed = [wo for wo in closed_wos     if _matches(wo)]
        total_shown  = len(shown_open) + len(shown_closed)

        count_txt = (
            f"<span style='color:#DC2626;font-weight:700;'>{total_shown}</span>"
            f" of {n_total} work orders"
            if q else
            f"<span style='font-weight:700;color:#111827;'>{n_total}</span> work orders"
        )
        st.markdown(
            f"<div style='font-size:11px;color:#6B7280;margin:4px 0 10px;'>{count_txt}</div>",
            unsafe_allow_html=True,
        )

        with st.container(height=560):
            if not shown_open and not shown_closed:
                st.markdown(
                    "<div class='no-results'>"
                    "<span class='nr-icon msr'>search_off</span>"
                    "No work orders match your search.</div>",
                    unsafe_allow_html=True,
                )
            else:
                def _render_wo_card(wo: dict) -> None:
                    wid      = wo["id"]
                    wo_num   = wo.get("wo_number", wid)
                    status   = wo.get("status", "Draft")
                    cid      = wo.get("customer_id", "")
                    sid      = wo.get("site_id", "")
                    cname    = customer_map.get(cid, {}).get("customer_name", "") if cid else ""
                    sname    = site_map.get(sid, {}).get("site_name", "")         if sid else ""
                    start    = wo.get("start_date", "")
                    end      = wo.get("end_date", "")
                    mc_count = len(_parse_machine_config(wo.get("machine_config")))
                    is_sel   = (wid == selected_id)
                    sel_cls  = " cwo-sel" if is_sel else ""

                    st.markdown(
                        f"<div class='cwo-card{sel_cls}'>"
                        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
                        f"<span class='cwo-num'>{wo_num}</span>"
                        f"{_wo_status_badge(status)}"
                        f"</div>"
                        f"<div class='cwo-sub'>"
                        + (f"<span class='msr' style='font-size:11px;opacity:.6;'>groups</span>{cname}" if cname else "")
                        + (f"<span class='cwo-dot'></span><span class='msr' style='font-size:11px;opacity:.6;'>location_on</span>{sname}" if sname else "")
                        + f"</div>"
                        f"<div class='cwo-sub'>"
                        f"<span class='msr' style='font-size:11px;opacity:.6;'>construction</span>"
                        f"{mc_count} machine{'s' if mc_count != 1 else ''}"
                        + (f"<span class='cwo-dot'></span>{start} → {end or 'ongoing'}" if start else "")
                        + f"</div></div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "✓ Selected" if is_sel else "Review →",
                        key=f"cwosel_{wid}",
                        use_container_width=True,
                        type="primary" if is_sel else "secondary",
                        help=wo_num,
                    ):
                        st.session_state["_cwo_sel_id"]  = wid
                        st.session_state["_cwo_confirm"] = False
                        st.rerun()

                if shown_open:
                    st.markdown(
                        "<div style='font-size:10px;font-weight:700;letter-spacing:.10em;"
                        "text-transform:uppercase;color:#DC2626;margin:0 0 8px;'>Open</div>",
                        unsafe_allow_html=True,
                    )
                    for wo in shown_open:
                        _render_wo_card(wo)

                if shown_closed:
                    st.markdown(
                        "<div style='font-size:10px;font-weight:700;letter-spacing:.10em;"
                        "text-transform:uppercase;color:#6B7280;margin:12px 0 8px;'>Closed / Cancelled</div>",
                        unsafe_allow_html=True,
                    )
                    for wo in shown_closed:
                        _render_wo_card(wo)

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — Detail + close action
    # ══════════════════════════════════════════════════════════════════════════
    with right_col:

        if not selected_wo:
            st.markdown(
                "<div class='cwo-empty'>"
                "<div class='cwo-empty-ring'>🔒</div>"
                "<h3>Select a Work Order</h3>"
                "<p>Choose a work order from the list to review its full details "
                "and close it when the job is complete.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            wo = selected_wo
            wo_id    = wo["id"]
            wo_num   = wo.get("wo_number", wo_id)
            status   = wo.get("status", "Draft")
            cid      = wo.get("customer_id", "")
            sid      = wo.get("site_id", "")
            start    = wo.get("start_date", "")
            end      = wo.get("end_date", "")
            client_wo = wo.get("client_work_ordernumber", "")
            cname    = customer_map.get(cid, {}).get("customer_name", "—") if cid else "—"
            sname    = site_map.get(sid, {}).get("site_name", "—")         if sid else "—"
            scity    = site_map.get(sid, {}).get("city", "")               if sid else ""
            mc_list  = _parse_machine_config(wo.get("machine_config"))
            is_closed = status in _CLOSED_STATUSES

            # ── Hero banner ─────────────────────────────────────────────────
            badge_bg  = "rgba(220,38,38,.22)" if not is_closed else "rgba(16,185,129,.22)"
            badge_col = "#FCA5A5"             if not is_closed else "#6EE7B7"
            badge_bdr = "rgba(220,38,38,.35)" if not is_closed else "rgba(16,185,129,.35)"
            st.markdown(
                f"<div class='cwo-hero'>"
                f"<div class='cwo-hero-icon'>"
                f"<span class='msr' style='color:#FCA5A5;'>assignment</span></div>"
                f"<div style='flex:1;min-width:0;position:relative;z-index:1;'>"
                f"<div class='cwo-hero-num'>{wo_num}</div>"
                f"<div class='cwo-hero-meta'>"
                f"{cname} &nbsp;·&nbsp; {sname}{(' — ' + scity) if scity else ''}</div>"
                f"<div class='cwo-hero-badges'>"
                f"<span class='wo-status-badge' style='background:{badge_bg};color:{badge_col};"
                f"border:1px solid {badge_bdr};'>{status}</span>"
                f"<span class='wo-status-badge' style='background:rgba(255,255,255,.08);"
                f"color:rgba(255,255,255,.55);'>"
                f"{len(mc_list)} machine{'s' if len(mc_list) != 1 else ''}</span>"
                f"</div></div></div>",
                unsafe_allow_html=True,
            )

            # ── Already closed banner ────────────────────────────────────────
            if is_closed:
                st.markdown(
                    "<div class='closed-banner'>"
                    "<span class='msr' style='font-size:22px;color:#16A34A;'>check_circle</span>"
                    "<div><div style='font-size:14px;font-weight:700;color:#166534;margin-bottom:3px;'>"
                    f"Work Order {status}</div>"
                    "<div style='font-size:12px;color:#166534;'>This work order has already been closed. "
                    "Machine statuses have been released.</div></div></div>",
                    unsafe_allow_html=True,
                )

            # ── Tabs ─────────────────────────────────────────────────────────
            tab_overview, tab_machines, tab_close = st.tabs([
                "📋 WO Details",
                f"🔧 Machines ({len(mc_list)})",
                "🔒 Close WO" if not is_closed else "✅ Closed",
            ])

            # ── Tab 1: Overview ──────────────────────────────────────────────
            with tab_overview:
                _section_hdr("assignment", "Work Order Information")
                st.markdown(
                    "<div class='info-grid'>"
                    + _info_field("WO Number",       wo_num)
                    + _info_field("Status",          status)
                    + _info_field("Customer",        cname)
                    + _info_field("Site",            sname)
                    + _info_field("Start Date",      start)
                    + _info_field("End Date",        end or "Ongoing")
                    + _info_field("Client WO #",     client_wo)
                    + _info_field("No. of Machines", str(len(mc_list)))
                    + "</div>",
                    unsafe_allow_html=True,
                )

                if mc_list:
                    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
                    _section_hdr("construction", "Machine Summary")
                    rows = []
                    for mc in mc_list:
                        mid     = mc.get("machine_id", "")
                        m_rec   = machine_map.get(mid, {})
                        rows.append({
                            "Machine":    mc.get("machine_label", "—"),
                            "S/N":        mc.get("serial_number", "—"),
                            "Status":     m_rec.get("operational_status", "Unknown") if m_rec else "Unknown",
                            "Rental/Mo":  f"₹ {float(mc.get('rental_per_month') or 0):,.0f}",
                            "Billing":    mc.get("billing_type", "—"),
                        })
                    import pandas as pd
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )

            # ── Tab 2: Machines ──────────────────────────────────────────────
            with tab_machines:
                if not mc_list:
                    st.info("No machines configured on this work order.")
                else:
                    for mc in mc_list:
                        mid   = mc.get("machine_id", "")
                        m_rec = machine_map.get(mid)
                        st.markdown(_machine_card(mc, m_rec), unsafe_allow_html=True)

            # ── Tab 3: Close WO ──────────────────────────────────────────────
            with tab_close:
                if is_closed:
                    st.success(f"This work order is already **{status}**. No further action needed.")
                else:
                    # Warning summary
                    machine_lines = "".join(
                        f"<li><strong>{mc.get('machine_label', '—')}</strong> — "
                        f"current status: <em>"
                        f"{machine_map.get(mc.get('machine_id',''), {}).get('operational_status', 'Unknown')}"
                        f"</em> → will become <strong style='color:#065F46;'>Available</strong></li>"
                        for mc in mc_list
                    )
                    st.markdown(
                        "<div class='close-warning'>"
                        "<span class='close-warning-icon'>⚠️</span>"
                        "<div>"
                        "<div class='close-warning-title'>Review before closing</div>"
                        "<div class='close-warning-body'>"
                        "Closing this work order will make the following changes:<br>"
                        f"<ul style='margin:8px 0 0 0;padding-left:16px;'>"
                        f"<li>Work Order <strong>{wo_num}</strong> status → "
                        f"<strong style='color:#991B1B;'>Closed</strong></li>"
                        f"{machine_lines}"
                        f"</ul>"
                        f"<br>This action cannot be automatically undone. "
                        f"Machines can be re-assigned by editing them individually."
                        f"</div></div></div>",
                        unsafe_allow_html=True,
                    )

                    # Remarks input
                    closing_remarks = st.text_area(
                        "Closing Remarks (optional)",
                        placeholder="e.g. Job completed as per contract. All machines demobilized.",
                        height=90,
                        key="cwo_closing_remarks",
                    )

                    # Confirmation checkbox
                    confirmed = st.checkbox(
                        f"I confirm closing Work Order **{wo_num}** and releasing "
                        f"{len(mc_list)} machine{'s' if len(mc_list) != 1 else ''} back to Available.",
                        key="cwo_confirm_check",
                    )

                    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
                    cl1, cl2, _ = st.columns([3, 2, 3])

                    with cl1:
                        close_clicked = st.button(
                            "🔒  Close Work Order",
                            type="primary",
                            use_container_width=True,
                            disabled=not confirmed,
                            key="cwo_close_btn",
                        )
                    with cl2:
                        if st.button("↻ Refresh", use_container_width=True, key="cwo_refresh_btn"):
                            st.session_state["_cwo_confirm"] = False
                            st.rerun()

                    # ── Close logic ─────────────────────────────────────────
                    if close_clicked and confirmed:
                        _err = None
                        try:
                            import json as _json
                            from datetime import date as _date

                            # 1. Update WO status
                            wo_payload: dict = {"status": "Closed"}
                            if closing_remarks and closing_remarks.strip():
                                wo_payload["closing_remarks"] = closing_remarks.strip()
                            sb.update_work_order(wo_id, wo_payload)

                            # 2. Release each machine back to Available
                            for mc in mc_list:
                                mid = mc.get("machine_id")
                                if mid:
                                    sb.update_machine(mid, {
                                        "operational_status": "Available",
                                        "current_site_id":    None,
                                        "current_customer_id": None,
                                    })

                            # 3. Set billing_end_date = today for any machine that
                            #    is On Rent (has BSD but no BED) in the deployment record
                            try:
                                dep_rec = sb.get_deployment_by_wo(wo_id)
                                if dep_rec.get("id"):
                                    raw_mcd = dep_rec.get("machine_deployments")
                                    mcd_list = []
                                    if raw_mcd:
                                        try:
                                            mcd_list = _json.loads(raw_mcd) if isinstance(raw_mcd, str) else raw_mcd
                                            mcd_list = mcd_list if isinstance(mcd_list, list) else []
                                        except Exception:
                                            mcd_list = []

                                    today_str = _date.today().isoformat()
                                    updated = False
                                    for entry in mcd_list:
                                        if entry.get("billing_start_date") and not entry.get("billing_end_date"):
                                            entry["billing_end_date"] = today_str
                                            updated = True

                                    if updated:
                                        sb.update_deployment(dep_rec["id"], {
                                            "machine_deployments": _json.dumps(mcd_list),
                                        })
                            except Exception:
                                pass  # billing date update is best-effort; don't block closure

                        except Exception as exc:
                            _err = str(exc)

                        if _err:
                            st.error(f"Failed to close work order: {_err}")
                        else:
                            st.toast(
                                f"Work Order {wo_num} closed. "
                                f"{len(mc_list)} machine{'s' if len(mc_list) != 1 else ''} set to Available.",
                                icon="✅",
                            )
                            st.session_state["_cwo_confirm"] = False
                            st.rerun()
