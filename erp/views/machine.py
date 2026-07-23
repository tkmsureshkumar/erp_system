"""
erp/views/machine.py
Machine management — premium SaaS redesign.
Left  (36%): searchable machine directory with status-coded cards.
Right (64%): tabbed detail/edit panel.

Mode state  _mach_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from ..models import ConditionStatus, OperationalStatus
from ..supabase_client import SupabaseClient
from erp.views._lock import status_chip, deactivate_controls
from erp import auth

# ── Constants ─────────────────────────────────────────────────────────────────

OWNERSHIP_OPTIONS = ["Owned", "Leased"]

# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
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
.kpi-card:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,.08);
    transform: translateY(-2px);
}
.kpi-accent-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
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
.kpi-sub {
    font-size: 11px; color: #6B7280;
}
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

/* ── Machine list cards ──────────────────────────────────────────────── */
.ml-wrap { display: flex; flex-direction: column; gap: 6px; }
.ml-item {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 10px;
    padding: 10px 12px;
    display: flex; align-items: center; gap: 10px;
    transition: box-shadow .16s, border-color .16s, transform .16s;
    cursor: pointer;
    pointer-events: none;
}
.ml-item:hover {
    box-shadow: 0 4px 16px rgba(37,99,235,.10);
    border-color: #93C5FD;
    transform: translateY(-1px);
}
.ml-item.ml-sel {
    border-color: #E87722 !important;
    background: #FFF7ED;
    border-left-width: 3px;
}
.ml-avatar {
    width: 34px; height: 34px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.ml-info { flex: 1; min-width: 0; }
.ml-code {
    font-size: 13px; font-weight: 700; color: #111827;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ml-sub {
    font-size: 11px; color: #6B7280; margin-top: 2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 72px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px;
    text-align: center;
    animation: mach-fadeup .35s ease;
}
.empty-icon-ring {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(145deg, #FFF7ED, #FFEDD5);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px;
    margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(232,119,34,.14);
}
.empty-state-v2 h3 {
    font-size: 17px; font-weight: 700; color: #111827;
    margin: 0 0 8px;
}
.empty-state-v2 p {
    font-size: 13px; color: #9CA3AF;
    max-width: 270px; line-height: 1.6; margin: 0;
}

/* ── Machine hero banner ─────────────────────────────────────────────── */
.mach-hero {
    background: linear-gradient(135deg, #1E2938 0%, #1c3461 100%);
    border-radius: 14px; padding: 22px 24px;
    margin-bottom: 18px;
    display: flex; align-items: center; gap: 16px;
    position: relative; overflow: hidden;
    animation: mach-fadeup .3s ease;
}
.mach-hero::before {
    content: '';
    position: absolute; top: -40px; right: -40px;
    width: 160px; height: 160px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.mach-hero::after {
    content: '';
    position: absolute; bottom: -20px; right: 80px;
    width: 100px; height: 100px; border-radius: 50%;
    background: rgba(255,255,255,.03);
}
.mach-hero-avatar {
    width: 52px; height: 52px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 800; color: #fff;
    flex-shrink: 0;
    box-shadow: 0 4px 16px rgba(0,0,0,.30);
}
.mach-hero-code {
    font-size: 20px; font-weight: 800; color: #fff; line-height: 1.2;
    letter-spacing: .02em;
}
.mach-hero-meta {
    font-size: 11px; color: rgba(255,255,255,.45);
    letter-spacing: .06em; margin-top: 4px;
}
.mach-hero-badges {
    margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;
    align-items: center;
}
.mach-hero-badge {
    font-size: 10px; font-weight: 700;
    padding: 3px 10px; border-radius: 20px;
    letter-spacing: .05em; text-transform: uppercase;
}
.mhb-available   { background:rgba(16,185,129,.22); color:#6EE7B7; border:1px solid rgba(16,185,129,.35); }
.mhb-on-rent     { background:rgba(232,119,34,.22); color:#FED7AA; border:1px solid rgba(232,119,34,.35); }
.mhb-reserved    { background:rgba(99,102,241,.22); color:#C7D2FE; border:1px solid rgba(99,102,241,.35); }
.mhb-mobilizing  { background:rgba(59,130,246,.22); color:#BFDBFE; border:1px solid rgba(59,130,246,.35); }
.mhb-demobilizing{ background:rgba(245,158,11,.22); color:#FDE68A; border:1px solid rgba(245,158,11,.35); }
.mhb-sold        { background:rgba(156,163,175,.22); color:#D1D5DB; border:1px solid rgba(156,163,175,.35); }
.mhb-breakdown   { background:rgba(239,68,68,.22); color:#FCA5A5; border:1px solid rgba(239,68,68,.35); }
.mhb-new         { background:rgba(16,185,129,.20); color:#6EE7B7; border:1px solid rgba(16,185,129,.30); }
.mhb-edit        { background:rgba(245,158,11,.18); color:#FCD34D; border:1px solid rgba(245,158,11,.28); }

/* ── Form sections ───────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Overview info grid ──────────────────────────────────────────────── */
.info-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 14px;
}
.info-field {
    background: #F8FAFC;
    border: 1px solid #E2EBF0;
    border-radius: 8px;
    padding: 11px 14px;
}
.info-field-label {
    font-size: 9px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 4px;
}
.info-field-value {
    font-size: 13px; font-weight: 600; color: #111827;
    word-break: break-word;
}
.info-field-value.muted {
    font-weight: 400; color: #9CA3AF;
}

/* ── Tabs polish ─────────────────────────────────────────────────────── */
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
    color: #E87722 !important;
    border-bottom: 2px solid #E87722 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-panel"]     { padding: 18px 0 0 !important; }

/* ── No-results state ─────────────────────────────────────────────────── */
.no-results {
    text-align: center; padding: 36px 12px;
    color: #9CA3AF; font-size: 13px;
}
.no-results .nr-icon { font-size: 32px; margin-bottom: 8px; display: block; }

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes mach-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── Data helpers ──────────────────────────────────────────────────────────────

def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _generate_asset_code(prefix: str, existing_machines: list[dict]) -> str:
    prefix = (prefix or "M").strip().upper()
    max_seq = 0
    for m in existing_machines:
        code = (m.get("asset_code") or "").strip().upper()
        if code.startswith(prefix):
            suffix = code[len(prefix):]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
    return f"{prefix}{(max_seq + 1):03d}"


def _avatar_color(name: str) -> str:
    palette = [
        "#2563EB", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444",
        "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
    ]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


def _hero_badge_cls(status: str) -> str:
    """Return CSS class for a status badge on the dark hero banner."""
    _map = {
        "Available":    "mhb-available",
        "On Rent":      "mhb-on-rent",
        "Reserved":     "mhb-reserved",
        "Mobilizing":   "mhb-mobilizing",
        "Demobilizing": "mhb-demobilizing",
        "Sold":         "mhb-sold",
        "Breakdown":    "mhb-breakdown",
    }
    return _map.get(status, "mhb-available")


# ── HTML builders ─────────────────────────────────────────────────────────────

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


def _machine_card(m: dict, is_sel: bool) -> str:
    asset_code_v   = m.get("asset_code", "—")
    machine_type_v = m.get("machine_type", "")
    make_v         = m.get("make", "")
    model_v        = m.get("model", "")
    op_status      = m.get("operational_status", "")

    color    = _avatar_color(machine_type_v)
    initials = machine_type_v[:2].upper() if machine_type_v else "??"
    sel_cls  = " ml-sel" if is_sel else ""

    make_model = " · ".join(filter(None, [make_v, model_v])) or machine_type_v or "—"

    # Operational status badge (global .badge-* classes)
    badge_cls_map = {
        "Available":    "badge-available",
        "On Rent":      "badge-on-rent",
        "Reserved":     "badge-reserved",
        "Mobilizing":   "badge-mobilizing",
        "Demobilizing": "badge-demobilizing",
        "Sold":         "badge-sold",
    }
    badge_cls = badge_cls_map.get(op_status, "badge-available")
    badge_html = (
        f"<span class='{badge_cls}' "
        f"style='font-size:10px;white-space:nowrap;flex-shrink:0;'>{op_status}</span>"
    ) if op_status else ""

    return (
        f"<div class='ml-item{sel_cls}'>"
        f"<div class='ml-avatar' style='background:{color};'>{initials}</div>"
        f"<div class='ml-info'>"
        f"<div class='ml-code'>{asset_code_v}</div>"
        f"<div class='ml-sub'>{make_model}</div>"
        f"</div>"
        f"{badge_html}"
        f"</div>"
    )


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


def _placeholder_tab(icon: str, title: str, description: str) -> None:
    st.markdown(
        f"<div style='display:flex;flex-direction:column;align-items:center;"
        f"padding:52px 24px;text-align:center;'>"
        f"<div style='width:58px;height:58px;border-radius:14px;"
        f"background:#F8FAFC;border:1px solid #E2EBF0;"
        f"display:flex;align-items:center;justify-content:center;"
        f"font-size:26px;margin-bottom:14px;'>"
        f"<span class='msr' style='color:#9CA3AF;'>{icon}</span></div>"
        f"<div style='font-size:15px;font-weight:700;color:#374151;margin-bottom:6px;'>{title}</div>"
        f"<div style='font-size:12px;color:#9CA3AF;max-width:240px;line-height:1.6;'>{description}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── Main view ──────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        st.markdown(
            "<div class='page-eyebrow'>// Fleet Operations</div>"
            "<div class='page-title'>Machines</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception as e:
            st.error(f"Failed to load machines: {e}")
            return []

    def fetch_assets() -> list[dict]:
        try:
            return sb.list_assets()
        except Exception as e:
            st.warning(f"Could not load asset types: {e}")
            return []

    machines   = fetch_machines()
    assets     = fetch_assets()

    operational_status_values = [e.value for e in OperationalStatus]
    condition_status_values   = [e.value for e in ConditionStatus]

    asset_type_options: list[str] = [""] + [
        a.get("asset_name", "") for a in assets if a.get("asset_name")
    ]
    asset_prefix_map: dict[str, str] = {
        a.get("asset_name", ""): a.get("asset_prefix", "") for a in assets
    }

    machine_map = {m.get("id"): m for m in machines if m.get("id")}

    # ── Header button ──────────────────────────────────────────────────────────
    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New Machine", use_container_width=True,
                     type="primary", key="hdr_new_machine"):
            st.session_state["_mach_mode"]     = "new"
            st.session_state["_mach_sel_id"]   = ""
            st.session_state["_mach_sync_key"] = "__new__"
            for k in list(st.session_state.keys()):
                if k.startswith("m_"):
                    del st.session_state[k]
            st.rerun()

    # ── KPI strip ──────────────────────────────────────────────────────────────
    n_total      = len(machines)
    n_on_rent    = sum(1 for m in machines if m.get("operational_status") == "On Rent")
    n_available  = sum(1 for m in machines if m.get("operational_status") == "Available")
    n_breakdown  = sum(1 for m in machines if m.get("condition_status") == "Breakdown")

    st.markdown(
        f"<div class='kpi-grid'>"
        + _kpi_card("precision_manufacturing", "Total Machines", n_total,
                    f"across all asset types", "#2563EB")
        + _kpi_card("receipt_long", "On Rent", n_on_rent,
                    f"{round(n_on_rent/n_total*100) if n_total else 0}% of fleet deployed",
                    "#10B981")
        + _kpi_card("check_circle", "Available", n_available,
                    "ready for deployment", "#F59E0B")
        + _kpi_card("warning", "Breakdown", n_breakdown,
                    "require immediate attention", "#EF4444")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_mach_mode" not in st.session_state:
        st.session_state["_mach_mode"] = "none"
    if "_mach_sel_id" not in st.session_state:
        st.session_state["_mach_sel_id"] = ""

    mode                = st.session_state["_mach_mode"]       # "none" | "new" | "edit"
    selected_machine_id = st.session_state["_mach_sel_id"]
    selected_machine    = machine_map.get(selected_machine_id) if selected_machine_id else None

    # ── Sync form fields when selection or mode changes ────────────────────────
    sync_key = f"{mode}__{selected_machine_id}"
    if st.session_state.get("_mach_sync_key") != sync_key:
        st.session_state["_mach_sync_key"] = sync_key
        m = selected_machine or {}

        current_type = m.get("machine_type", "")
        st.session_state["m_machine_type"]              = (
            current_type if current_type in asset_type_options else ""
        )
        st.session_state["m_make"]                      = m.get("make", "")
        st.session_state["m_model"]                     = m.get("model", "")
        st.session_state["m_serial_number"]             = m.get("serial_number", "")
        st.session_state["m_original_serial_number"]    = m.get("original_serial_number", "")
        st.session_state["m_operational_serial_number"] = m.get("operational_serial_number", "")
        st.session_state["m_original_yom"]              = m.get("original_yom") or 0
        st.session_state["m_operational_yom"]           = str(m.get("operational_yom", "") or "")
        st.session_state["m_working_capacity"]          = str(m.get("working_capacity", "") or "")
        st.session_state["m_current_location"]          = m.get("current_location", "")
        st.session_state["m_purchase_date"]             = _parse_date(m.get("purchase_date"))
        st.session_state["m_purchase_cost"]             = float(m.get("purchase_cost") or 0.0)
        st.session_state["m_ownership"]                 = m.get("ownership", OWNERSHIP_OPTIONS[0])
        st.session_state["m_tpi_expiry"]                = _parse_date(m.get("TPI_expiry"))
        st.session_state["m_puc_expiry"]                = _parse_date(m.get("PUC_expiry"))
        st.session_state["m_form11_expiry"]             = _parse_date(m.get("Form_11_expiry"))
        st.session_state["m_insurance_expiry"]          = _parse_date(m.get("insurance_expiry"))
        st.session_state["m_operational_status"]        = m.get(
            "operational_status", OperationalStatus.AVAILABLE.value
        )
        st.session_state["m_condition_status"]          = m.get(
            "condition_status", ConditionStatus.RUNNING.value
        )

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — Machine directory
    # ══════════════════════════════════════════════════════════════════════════
    with left_col:

        # Search input with icon overlay
        st.markdown(
            "<div class='search-wrap'>"
            "<span class='search-icon-abs msr'>search</span>",
            unsafe_allow_html=True,
        )
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search asset, type or make…",
            key="mach_search_q",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        show_inactive = False
        if auth.is_admin():
            show_inactive = st.checkbox("Show Inactive", value=False, key="mach_show_inactive")

        q = search_q.strip().lower()
        filtered_map = {
            mid: m for mid, m in machine_map.items()
            if (show_inactive or m.get("is_active", True))
            and (
                not q
                or q in (m.get("asset_code") or "").lower()
                or q in m.get("machine_type", "").lower()
                or q in (m.get("make") or "").lower()
                or q in (m.get("model") or "").lower()
            )
        }

        count_txt = (
            f"<span style='color:#E87722;font-weight:700;'>{len(filtered_map)}</span>"
            f" of {n_total} machines"
            if q else
            f"<span style='font-weight:700;color:#111827;'>{n_total}</span>"
            f" machine{'s' if n_total != 1 else ''}"
        )
        st.markdown(
            f"<div style='font-size:11px;color:#6B7280;margin:4px 0 10px;'>{count_txt}</div>",
            unsafe_allow_html=True,
        )

        with st.container(height=530):
            if not filtered_map:
                st.markdown(
                    "<div class='no-results'>"
                    "<span class='nr-icon msr'>search_off</span>"
                    "No machines match your search."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                for mid, m in filtered_map.items():
                    is_sel         = (mid == selected_machine_id and mode == "edit")
                    machine_type_v = m.get("machine_type", "Unknown")

                    st.markdown(
                        _machine_card(m, is_sel),
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "Selected ✓" if is_sel else "Open →",
                        key=f"msel_{mid}",
                        use_container_width=True,
                        help=machine_type_v,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state["_mach_mode"]     = "edit"
                        st.session_state["_mach_sel_id"]   = mid
                        st.session_state["_mach_sync_key"] = None   # force sync
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — Detail / form panel
    # ══════════════════════════════════════════════════════════════════════════
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:36px;color:#E87722;'>precision_manufacturing</span>"
                "</div>"
                "<h3>No machine selected</h3>"
                "<p>Select a machine from the directory on the left, "
                "or click <strong>+ New Machine</strong> to register one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT PANEL ──────────────────────────────────────────────────
        else:
            # Resolve display values from session state (live-updating)
            asset_code_disp    = (
                selected_machine.get("asset_code", "") if selected_machine else ""
            )
            machine_type_disp  = (
                st.session_state.get("m_machine_type")
                or (selected_machine.get("machine_type", "") if selected_machine else "")
                or "New Machine"
            )
            op_status_disp     = st.session_state.get(
                "m_operational_status", OperationalStatus.AVAILABLE.value
            )
            cond_status_disp   = st.session_state.get(
                "m_condition_status", ConditionStatus.RUNNING.value
            )
            col_val            = _avatar_color(machine_type_disp)
            initials_banner    = machine_type_disp[:2].upper() if machine_type_disp else "??"

            hero_title  = asset_code_disp or machine_type_disp
            hero_meta   = machine_type_disp if asset_code_disp else "Unsaved — fill in details below"
            mode_badge  = (
                f"<span class='mach-hero-badge mhb-edit'>Editing</span>"
                if mode == "edit" else
                f"<span class='mach-hero-badge mhb-new'>New</span>"
            )
            op_badge    = (
                f"<span class='mach-hero-badge {_hero_badge_cls(op_status_disp)}'>"
                f"{op_status_disp}</span>"
            ) if op_status_disp else ""
            cond_badge  = (
                f"<span class='mach-hero-badge {_hero_badge_cls(cond_status_disp)}'>"
                f"{cond_status_disp}</span>"
            ) if cond_status_disp else ""

            # Hero banner
            st.markdown(
                f"<div class='mach-hero'>"
                f"<div class='mach-hero-avatar' style='background:{col_val};'>"
                f"{initials_banner}</div>"
                f"<div style='flex:1;min-width:0;position:relative;z-index:1;'>"
                f"<div class='mach-hero-code'>{hero_title}</div>"
                f"<div class='mach-hero-meta'>{hero_meta}</div>"
                f"<div class='mach-hero-badges'>"
                f"{op_badge}{cond_badge}{mode_badge}"
                f"</div></div></div>",
                unsafe_allow_html=True,
            )
            if mode == "edit" and selected_machine:
                st.markdown(
                    status_chip("Active" if selected_machine.get("is_active", True) else "Inactive"),
                    unsafe_allow_html=True,
                )

            # ── TABS ──────────────────────────────────────────────────────────
            tab_overview, tab_edit, tab_hist = st.tabs([
                "📋 Overview",
                "✏️ Edit Details",
                "📦 Deployments",
            ])

            # ── Tab 1: Overview ───────────────────────────────────────────────
            with tab_overview:
                if mode == "new":
                    st.markdown(
                        "<div style='color:#9CA3AF;font-size:13px;"
                        "text-align:center;padding:24px 0;'>"
                        "Save the machine first to see the overview.</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    sm = selected_machine or {}

                    # Identity
                    _section_hdr("badge", "Identity")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("Asset Code",    sm.get("asset_code"), wide=True)
                        + _info_field("Machine Type",  sm.get("machine_type"))
                        + _info_field("Make",          sm.get("make"))
                        + _info_field("Model",         sm.get("model"))
                        + _info_field("Current Location", sm.get("current_location"))
                        + _info_field("Working Capacity", sm.get("working_capacity"))
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    # Status
                    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
                    _section_hdr("sensors", "Status")
                    op_s   = sm.get("operational_status", "")
                    cnd_s  = sm.get("condition_status", "")
                    op_cls = {
                        "Available": "badge-available", "On Rent": "badge-on-rent",
                        "Reserved": "badge-reserved", "Mobilizing": "badge-mobilizing",
                        "Demobilizing": "badge-demobilizing", "Sold": "badge-sold",
                    }.get(op_s, "badge-available")
                    cnd_cls = {
                        "Breakdown": "badge-breakdown", "Running": "badge-available",
                        "Under Repair": "badge-on-rent", "BER (Beyond Economic Repair)": "badge-sold",
                    }.get(cnd_s, "badge-available")
                    st.markdown(
                        f"<div class='info-grid'>"
                        f"<div class='info-field'>"
                        f"<div class='info-field-label'>Operational Status</div>"
                        f"<div style='margin-top:4px;'><span class='{op_cls}'>{op_s or '—'}</span></div>"
                        f"</div>"
                        f"<div class='info-field'>"
                        f"<div class='info-field-label'>Condition Status</div>"
                        f"<div style='margin-top:4px;'><span class='{cnd_cls}'>{cnd_s or '—'}</span></div>"
                        f"</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    # Manufacturing
                    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
                    _section_hdr("precision_manufacturing", "Manufacturing")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("Original YOM",
                                      str(sm.get("original_yom")) if sm.get("original_yom") else "")
                        + _info_field("Operational YOM",
                                      str(sm.get("operational_yom") or ""))
                        + _info_field("Serial Number",             sm.get("serial_number"))
                        + _info_field("Original Serial Number",    sm.get("original_serial_number"))
                        + _info_field("Operational Serial Number", sm.get("operational_serial_number"),
                                      wide=True)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    # Ownership & Financials
                    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
                    _section_hdr("account_balance_wallet", "Ownership & Financials")
                    purchase_cost_v = sm.get("purchase_cost")
                    cost_disp = f"₹{purchase_cost_v:,.0f}" if purchase_cost_v else ""
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("Ownership",     sm.get("ownership"))
                        + _info_field("Purchase Date", str(sm.get("purchase_date") or ""))
                        + _info_field("Purchase Cost", cost_disp)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    # Compliance
                    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
                    _section_hdr("verified_user", "Compliance & Expiry Dates")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("TPI Expiry",       str(sm.get("TPI_expiry") or ""))
                        + _info_field("PUC Expiry",       str(sm.get("PUC_expiry") or ""))
                        + _info_field("Form 11 Expiry",   str(sm.get("Form_11_expiry") or ""))
                        + _info_field("Insurance Expiry", str(sm.get("insurance_expiry") or ""))
                        + "</div>",
                        unsafe_allow_html=True,
                    )

            # ── Tab 2: Edit Details ───────────────────────────────────────────
            with tab_edit:

                # Machine Type DDL — drives asset code preview
                machine_type = st.selectbox(
                    "Machine Type *",
                    options=asset_type_options,
                    format_func=lambda v: "Select machine type…" if not v
                        else (f"{v}  ({asset_prefix_map[v]})" if asset_prefix_map.get(v) else v),
                    key="m_machine_type",
                )

                # Asset code display / preview
                if selected_machine and asset_code_disp:
                    st.markdown(
                        f"<div style='display:inline-flex;align-items:center;gap:10px;"
                        f"background:#F8FAFC;border:1px solid #E2E8F0;"
                        f"border-radius:6px;padding:8px 16px;margin-bottom:8px;'>"
                        f"<span style='font-size:11px;font-weight:700;letter-spacing:.1em;"
                        f"color:#6B7280;text-transform:uppercase;'>Asset Code</span>"
                        f"<span style='font-size:18px;font-weight:800;color:#E87722;"
                        f"letter-spacing:.05em;'>{asset_code_disp}</span></div>",
                        unsafe_allow_html=True,
                    )
                elif machine_type:
                    prefix  = asset_prefix_map.get(machine_type, machine_type[:3]).strip().upper()
                    preview = _generate_asset_code(prefix, machines)
                    st.markdown(
                        f"<div style='display:inline-flex;align-items:center;gap:10px;"
                        f"background:#FFF7ED;border:1px solid #FED7AA;"
                        f"border-radius:6px;padding:8px 16px;margin-bottom:8px;'>"
                        f"<span style='font-size:11px;font-weight:700;letter-spacing:.1em;"
                        f"color:#9A3412;text-transform:uppercase;'>Asset Code (auto)</span>"
                        f"<span style='font-size:18px;font-weight:800;color:#E87722;"
                        f"letter-spacing:.05em;'>{preview}</span></div>",
                        unsafe_allow_html=True,
                    )

                st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)

                # Basic Details
                with st.container(border=True):
                    _section_hdr("settings", "Basic Details")
                    b1, b2 = st.columns(2)
                    with b1:
                        st.text_input("Make",  key="m_make",  placeholder="e.g. JLG")
                        st.number_input(
                            "Original Year of Manufacture",
                            min_value=0, step=1,
                            key="m_original_yom",
                        )
                        st.text_input(
                            "Working Capacity", key="m_working_capacity",
                            placeholder="e.g. 12m / 500kg",
                        )
                        st.number_input(
                            "Purchase Cost (₹)",
                            min_value=0.0, step=0.01,
                            key="m_purchase_cost",
                        )
                    with b2:
                        st.text_input("Model", key="m_model", placeholder="e.g. 450AJ")
                        st.text_input(
                            "Operational Year of Manufacture",
                            key="m_operational_yom", placeholder="e.g. 2020",
                        )
                        st.date_input("Purchase Date", key="m_purchase_date")
                        st.text_input(
                            "Current Location", key="m_current_location",
                            placeholder="e.g. Mumbai Yard",
                        )

                # Serial Numbers
                with st.container(border=True):
                    _section_hdr("tag", "Serial Numbers")
                    s1, s2, s3 = st.columns(3)
                    with s1:
                        st.text_input("Serial Number", key="m_serial_number")
                    with s2:
                        st.text_input("Original Serial No.", key="m_original_serial_number")
                    with s3:
                        st.text_input("Operational Serial No.", key="m_operational_serial_number")

                # Ownership
                with st.container(border=True):
                    _section_hdr("account_balance_wallet", "Ownership")
                    o1, _ = st.columns([1, 3])
                    with o1:
                        st.selectbox("Ownership *", options=OWNERSHIP_OPTIONS, key="m_ownership")

                # Compliance & Expiry Dates
                with st.container(border=True):
                    _section_hdr("verified_user", "Compliance & Expiry Dates")
                    e1, e2, e3, e4 = st.columns(4)
                    with e1:
                        st.date_input("TPI Expiry",      key="m_tpi_expiry")
                    with e2:
                        st.date_input("PUC Expiry",      key="m_puc_expiry")
                    with e3:
                        st.date_input("Form 11 Expiry",  key="m_form11_expiry")
                    with e4:
                        st.date_input("Insurance Expiry", key="m_insurance_expiry")

                # Status
                with st.container(border=True):
                    _section_hdr("sensors", "Status")
                    st1_col, st2_col = st.columns(2)
                    with st1_col:
                        _status_opts = operational_status_values
                        if not auth.is_admin():
                            _status_opts = [o for o in _status_opts if o not in ("Sold", "Scrapped")]
                        st.selectbox(
                            "Operational Status *",
                            options=_status_opts,
                            key="m_operational_status",
                        )
                    with st2_col:
                        st.selectbox(
                            "Condition Status *",
                            options=condition_status_values,
                            key="m_condition_status",
                        )

            # ── Tab 3: Deployments (placeholder) ─────────────────────────────
            with tab_hist:
                _placeholder_tab(
                    "local_shipping",
                    "Deployment history coming soon",
                    "Past and active deployments for this machine will appear here.",
                )

            # ── Action buttons (outside tabs) ─────────────────────────────────
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            sv1, sv2, sv3, _ = st.columns([3, 1, 1, 2])
            with sv1:
                save_clicked = st.button(
                    "💾  Update Machine" if mode == "edit" else "💾  Create Machine",
                    type="primary",
                    use_container_width=True,
                    key="mach_save_btn",
                )
            with sv2:
                if st.button("Cancel", use_container_width=True, key="mach_cancel_btn"):
                    st.session_state["_mach_mode"]     = "none"
                    st.session_state["_mach_sel_id"]   = ""
                    st.session_state["_mach_sync_key"] = None
                    st.rerun()
            with sv3:
                if st.button("↻ Refresh", use_container_width=True, key="mach_refresh_btn"):
                    st.session_state["_mach_sync_key"] = None
                    st.rerun()

            # ── Save logic ─────────────────────────────────────────────────────
            if save_clicked:
                # Read all values from session state
                machine_type_val          = st.session_state.get("m_machine_type", "")
                make_val                  = (st.session_state.get("m_make", "") or "").strip()
                model_val                 = (st.session_state.get("m_model", "") or "").strip()
                serial_number_val         = (st.session_state.get("m_serial_number", "") or "").strip()
                orig_sn_val               = (st.session_state.get("m_original_serial_number", "") or "").strip()
                op_sn_val                 = (st.session_state.get("m_operational_serial_number", "") or "").strip()
                original_yom_val          = st.session_state.get("m_original_yom", 0)
                operational_yom_val       = (st.session_state.get("m_operational_yom", "") or "").strip()
                working_capacity_val      = (st.session_state.get("m_working_capacity", "") or "").strip()
                current_location_val      = (st.session_state.get("m_current_location", "") or "").strip()
                purchase_date_val         = st.session_state.get("m_purchase_date")
                purchase_cost_val         = st.session_state.get("m_purchase_cost", 0.0)
                ownership_val             = st.session_state.get("m_ownership", OWNERSHIP_OPTIONS[0])
                tpi_expiry_val            = st.session_state.get("m_tpi_expiry")
                puc_expiry_val            = st.session_state.get("m_puc_expiry")
                form11_expiry_val         = st.session_state.get("m_form11_expiry")
                insurance_expiry_val      = st.session_state.get("m_insurance_expiry")
                operational_status_val    = st.session_state.get(
                    "m_operational_status", OperationalStatus.AVAILABLE.value
                )
                condition_status_val      = st.session_state.get(
                    "m_condition_status", ConditionStatus.RUNNING.value
                )

                # Validate required fields
                if not machine_type_val:
                    st.error("Machine Type is required.")
                elif not operational_status_val:
                    st.error("Operational Status is required.")
                elif not condition_status_val:
                    st.error("Condition Status is required.")
                else:
                    payload: dict = dict(
                        machine_type              = machine_type_val,
                        make                      = make_val or None,
                        model                     = model_val or None,
                        serial_number             = serial_number_val or None,
                        original_serial_number    = orig_sn_val or None,
                        operational_serial_number = op_sn_val or None,
                        original_yom              = int(original_yom_val) if original_yom_val else None,
                        operational_yom           = operational_yom_val or None,
                        working_capacity          = working_capacity_val or None,
                        current_location          = current_location_val or None,
                        purchase_date             = purchase_date_val.isoformat() if purchase_date_val else None,
                        purchase_cost             = float(purchase_cost_val) if purchase_cost_val else None,
                        ownership                 = ownership_val,
                        TPI_expiry                = tpi_expiry_val.isoformat() if tpi_expiry_val else None,
                        PUC_expiry                = puc_expiry_val.isoformat() if puc_expiry_val else None,
                        Form_11_expiry            = form11_expiry_val.isoformat() if form11_expiry_val else None,
                        insurance_expiry          = insurance_expiry_val.isoformat() if insurance_expiry_val else None,
                        operational_status        = operational_status_val,
                        condition_status          = condition_status_val,
                    )

                    if mode == "new":
                        prefix = asset_prefix_map.get(
                            machine_type_val, machine_type_val[:3]
                        ).strip().upper()
                        payload["asset_code"] = _generate_asset_code(prefix, machines)

                    _err       = None
                    _toast_msg = None
                    _new_id    = None
                    try:
                        if mode == "edit" and selected_machine:
                            sb.update_machine(selected_machine_id, payload)
                            _toast_msg = f"Machine updated — {asset_code_disp or machine_type_val}"
                        else:
                            created       = sb.insert_machine(payload)
                            _new_id       = created.get("id", "")
                            assigned_code = created.get("asset_code") or payload.get("asset_code", "")
                            _toast_msg    = f"Machine created — Asset Code: {assigned_code}"
                    except Exception as exc:
                        _err = str(exc)

                    if _err:
                        msg = _err
                        if "23505" in msg and "serial_number" in msg:
                            st.error(
                                "Serial Number already exists. "
                                "Each machine must have a unique serial number."
                            )
                        elif "23505" in msg and "asset_code" in msg:
                            st.error(
                                "Asset Code conflict detected — "
                                "please refresh and try again."
                            )
                        elif "23505" in msg:
                            st.error(
                                "A duplicate value was detected. "
                                "Please check your input for fields that must be unique."
                            )
                        else:
                            st.error(f"Could not save machine: {_err}")
                    else:
                        if _new_id:
                            st.session_state["_mach_mode"]     = "edit"
                            st.session_state["_mach_sel_id"]   = _new_id
                            st.session_state["_mach_sync_key"] = None
                        st.toast(_toast_msg, icon="✅")
                        st.rerun()

            if mode == "edit" and selected_machine:
                _is_active = selected_machine.get("is_active", True)
                _deact = deactivate_controls(
                    "Machine", selected_machine_id,
                    asset_code_disp or machine_type_disp,
                    _is_active, key_prefix="mach",
                )
                if _deact is True:
                    sb.update_machine(selected_machine_id, {"is_active": True})
                    st.rerun()
                elif _deact is False:
                    sb.update_machine(selected_machine_id, {"is_active": False})
                    st.rerun()
