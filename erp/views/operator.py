"""
erp/views/operator.py
Operator management — premium SaaS redesign.
Left  (35%): searchable operator directory with modern cards.
Right (65%): tabbed detail/edit panel.

Mode state  _op_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st

from ..models import OperatorStatus
from ..supabase_client import SupabaseClient

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

/* ── Operator list cards ────────────────────────────────────────────── */
.cl-wrap { display: flex; flex-direction: column; gap: 6px; }
.cl-item {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 10px;
    padding: 11px 13px;
    display: flex; align-items: center; gap: 11px;
    transition: box-shadow .16s, border-color .16s, transform .16s;
    cursor: pointer;
    pointer-events: none;
}
.cl-item:hover {
    box-shadow: 0 4px 16px rgba(232,119,34,.10);
    border-color: #FDB97A;
    transform: translateY(-1px);
}
.cl-item.cl-sel {
    border-color: #E87722 !important;
    background: #FFF7ED;
    border-left-width: 3px;
}
.cl-avatar {
    width: 36px; height: 36px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.cl-info { flex: 1; min-width: 0; }
.cl-name {
    font-size: 13px; font-weight: 600; color: #111827;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cl-sub {
    font-size: 11px; color: #6B7280; margin-top: 2px;
    display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
}
.cl-dot {
    width: 3px; height: 3px; border-radius: 50%;
    background: #D1D5DB; flex-shrink: 0;
}
.cl-code {
    font-size: 9px; font-weight: 700;
    background: #F1F5F9; color: #64748B;
    padding: 2px 8px; border-radius: 20px;
    white-space: nowrap; flex-shrink: 0;
    margin-left: auto;
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
    animation: cs-fadeup .35s ease;
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

/* ── Operator hero banner ─────────────────────────────────────────────── */
.cust-hero {
    background: linear-gradient(135deg, #1E2938 0%, #2D3748 100%);
    border-radius: 14px; padding: 22px 24px;
    margin-bottom: 18px;
    display: flex; align-items: center; gap: 16px;
    position: relative; overflow: hidden;
    animation: cs-fadeup .3s ease;
}
.cust-hero::before {
    content: '';
    position: absolute; top: -40px; right: -40px;
    width: 160px; height: 160px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.cust-hero::after {
    content: '';
    position: absolute; bottom: -20px; right: 80px;
    width: 100px; height: 100px; border-radius: 50%;
    background: rgba(255,255,255,.03);
}
.cust-hero-avatar {
    width: 52px; height: 52px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 800; color: #fff;
    flex-shrink: 0;
    box-shadow: 0 4px 16px rgba(0,0,0,.30);
}
.cust-hero-name {
    font-size: 20px; font-weight: 800; color: #fff; line-height: 1.2;
}
.cust-hero-meta {
    font-size: 11px; color: rgba(255,255,255,.42);
    letter-spacing: .07em; margin-top: 4px;
}
.cust-hero-badges {
    margin-top: 7px; display: flex; gap: 6px; flex-wrap: wrap;
}
.hero-badge {
    font-size: 10px; font-weight: 700;
    padding: 2px 10px; border-radius: 20px;
    letter-spacing: .05em; text-transform: uppercase;
}
.hero-badge-new {
    background: rgba(16,185,129,.20); color: #6EE7B7;
    border: 1px solid rgba(16,185,129,.30);
}
.hero-badge-edit {
    background: rgba(232,119,34,.18); color: #FCD34D;
    border: 1px solid rgba(232,119,34,.28);
}

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

/* ── No-results state ────────────────────────────────────────────────── */
.no-results {
    text-align: center; padding: 36px 12px;
    color: #9CA3AF; font-size: 13px;
}
.no-results .nr-icon { font-size: 32px; margin-bottom: 8px; display: block; }

/* ── Animations ──────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── Data helpers ──────────────────────────────────────────────────────────────

def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "??"


def _avatar_color(name: str) -> str:
    palette = [
        "#E87722", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444",
        "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
    ]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


def _open_new_form() -> None:
    """Switch UI to new-operator mode and reset form fields."""
    st.session_state["_op_mode"]     = "new"
    st.session_state["_op_sel_id"]   = ""
    st.session_state["_op_sync_key"] = "__new__"
    # Personal
    st.session_state["op_name"]          = ""
    st.session_state["op_mobile"]        = ""
    st.session_state["op_aadhar"]        = ""
    st.session_state["op_joining_date"]  = None
    st.session_state["op_status"]        = OperatorStatus.ACTIVE.value
    # Licence
    st.session_state["op_license_number"]      = ""
    st.session_state["op_license_type"]        = ""
    st.session_state["op_license_expiry"]      = None
    st.session_state["op_heavy_license_start"] = None
    st.session_state["op_light_license_start"] = None
    # Bank
    st.session_state["op_bank_account"]   = ""
    st.session_state["op_ifsc"]           = ""
    st.session_state["op_bank_name"]      = ""
    st.session_state["op_name_passbook"]  = ""
    st.session_state["op_fixed_salary"]   = 0.0


# ── HTML builders ─────────────────────────────────────────────────────────────

def _kpi_card(icon: str, label: str, value: int | str,
              sub: str = "", accent: str = "#E87722") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _operator_card(op: dict, is_sel: bool) -> str:
    name     = op.get("operator_name", "Unknown")
    mobile_v = op.get("mobile_number", "")
    status_v = op.get("status", "")
    lic_type = op.get("license_type", "")
    color    = _avatar_color(name)
    sel_cls  = " cl-sel" if is_sel else ""
    lic_html = f"<span class='cl-code'>{lic_type}</span>" if lic_type else ""

    status_badge = ""
    if status_v:
        if status_v == OperatorStatus.ACTIVE.value:
            bg, col, bdr = "#F0FDF4", "#166534", "#BBF7D0"
        else:
            bg, col, bdr = "#F3F4F6", "#6B7280", "#E5E7EB"
        status_badge = (
            f"<span style='display:inline-flex;align-items:center;font-size:10px;"
            f"font-weight:600;background:{bg};color:{col};"
            f"border:1px solid {bdr};padding:1px 7px;border-radius:20px;"
            f"white-space:nowrap;'>{status_v}</span>"
        )

    return (
        f"<div class='cl-item{sel_cls}'>"
        f"<div class='cl-avatar' style='background:{color};'>{_initials(name)}</div>"
        f"<div class='cl-info'>"
        f"<div class='cl-name'>{name}</div>"
        f"<div class='cl-sub'>"
        f"<span class='msr' style='font-size:12px;opacity:.6;'>phone</span>"
        f"{mobile_v or '—'}"
        f"{('<span class=\"cl-dot\"></span>' + status_badge) if status_v else ''}"
        f"</div>"
        f"</div>"
        f"{lic_html}"
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


# ── Main view ─────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        st.markdown(
            "<div class='page-eyebrow'>// Fleet Operations</div>"
            "<div class='page-title'>Operators</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    def fetch_operators() -> list[dict]:
        try:
            return sb.list_operators()
        except Exception as exc:
            st.error(f"Failed to load operators: {exc}")
            return []

    operators              = fetch_operators()
    operator_map           = {op["id"]: op for op in operators if op.get("id")}
    operator_status_values = [e.value for e in OperatorStatus]

    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New Operator", use_container_width=True,
                     type="primary", key="hdr_new_op"):
            _open_new_form()
            st.rerun()

    # ── KPI strip ──────────────────────────────────────────────────────────────
    today         = date.today()
    expiry_window = today + timedelta(days=90)
    n_operators   = len(operators)
    n_active      = sum(1 for op in operators if op.get("status") == OperatorStatus.ACTIVE.value)
    n_expiring    = sum(
        1 for op in operators
        if _parse_date(op.get("license_expiry")) is not None
        and today <= _parse_date(op.get("license_expiry")) <= expiry_window
    )
    n_lic_types   = len({op.get("license_type") for op in operators if op.get("license_type")})

    st.markdown(
        f"<div class='kpi-grid'>"
        + _kpi_card("engineering",  "Total Operators",   n_operators,
                    f"{n_active} currently active",          "#E87722")
        + _kpi_card("check_circle", "Active",             n_active,
                    f"{n_operators - n_active} inactive",    "#10B981")
        + _kpi_card("warning",      "Licence Expiring",   n_expiring,
                    "within next 90 days",                   "#F59E0B")
        + _kpi_card("badge",        "Licence Types",      n_lic_types,
                    "unique categories",                     "#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_op_mode" not in st.session_state:
        st.session_state["_op_mode"]   = "none"
    if "_op_sel_id" not in st.session_state:
        st.session_state["_op_sel_id"] = ""

    mode              = st.session_state["_op_mode"]       # "none" | "new" | "edit"
    selected_id       = st.session_state["_op_sel_id"]
    selected_operator = operator_map.get(selected_id) if selected_id else None

    # ── Sync form fields when selection or mode changes ────────────────────────
    sync_key = f"{mode}__{selected_id}"
    if st.session_state.get("_op_sync_key") != sync_key:
        st.session_state["_op_sync_key"] = sync_key
        op = selected_operator or {}
        st.session_state["op_name"]          = op.get("operator_name", "")
        st.session_state["op_mobile"]        = op.get("mobile_number", "")
        st.session_state["op_aadhar"]        = op.get("aadhar_number", "")
        st.session_state["op_joining_date"]  = _parse_date(op.get("joining_date"))
        st.session_state["op_status"]        = op.get("status", OperatorStatus.ACTIVE.value)
        st.session_state["op_license_number"]      = op.get("license_number", "")
        st.session_state["op_license_type"]        = op.get("license_type", "")
        st.session_state["op_license_expiry"]      = _parse_date(op.get("license_expiry"))
        st.session_state["op_heavy_license_start"] = _parse_date(op.get("heavy_license_startdate"))
        st.session_state["op_light_license_start"] = _parse_date(op.get("light_license_startdate"))
        st.session_state["op_bank_account"]  = op.get("bank_account_number", "")
        st.session_state["op_ifsc"]          = op.get("ifsc_code", "")
        st.session_state["op_bank_name"]     = op.get("bank_name", "")
        st.session_state["op_name_passbook"] = op.get("name_in_passbook", "")
        st.session_state["op_fixed_salary"]  = float(op.get("fixed_salary") or 0.0)

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — Operator directory
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
            placeholder="Search by name or mobile…",
            key="op_search_q",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        q = search_q.strip().lower()
        filtered_map = {
            oid: op for oid, op in operator_map.items()
            if not q
            or q in op.get("operator_name", "").lower()
            or q in op.get("mobile_number", "").lower()
        }

        count_txt = (
            f"<span style='color:#E87722;font-weight:700;'>{len(filtered_map)}</span>"
            f" of {n_operators} operators"
            if q else
            f"<span style='font-weight:700;color:#111827;'>{n_operators}</span>"
            f" operator{'s' if n_operators != 1 else ''}"
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
                    "No operators match your search."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                for oid, op in filtered_map.items():
                    is_sel = (oid == selected_id and mode == "edit")
                    name   = op.get("operator_name", "Unknown")

                    st.markdown(_operator_card(op, is_sel), unsafe_allow_html=True)
                    if st.button(
                        "✓ Selected" if is_sel else "Open →",
                        key=f"csel_{oid}",
                        use_container_width=True,
                        help=name,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state["_op_mode"]     = "edit"
                        st.session_state["_op_sel_id"]   = oid
                        st.session_state["_op_sync_key"] = None   # force sync
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — Detail / form
    # ══════════════════════════════════════════════════════════════════════════
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>👷</div>"
                "<h3>No operator selected</h3>"
                "<p>Select an operator from the directory on the left, "
                "or click <strong>+ New Operator</strong> to add one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT FORM ───────────────────────────────────────────────────
        else:
            display_name = (
                st.session_state.get("op_name")
                or (selected_operator.get("operator_name", "") if selected_operator else "")
                or "New Operator"
            )
            col_val   = _avatar_color(display_name)
            badge_cls = "hero-badge-edit" if mode == "edit" else "hero-badge-new"
            badge_lbl = "Editing" if mode == "edit" else "New Operator"
            mob_disp  = selected_operator.get("mobile_number", "") if selected_operator else ""
            meta_line = f"Mobile: {mob_disp}" if mob_disp else "Unsaved — fill in details below"

            # Hero banner
            st.markdown(
                f"<div class='cust-hero'>"
                f"<div class='cust-hero-avatar' style='background:{col_val};'>"
                f"{_initials(display_name)}</div>"
                f"<div style='flex:1;min-width:0;position:relative;z-index:1;'>"
                f"<div class='cust-hero-name'>{display_name}</div>"
                f"<div class='cust-hero-meta'>{meta_line}</div>"
                f"<div class='cust-hero-badges'>"
                f"<span class='hero-badge {badge_cls}'>{badge_lbl}</span>"
                f"</div></div></div>",
                unsafe_allow_html=True,
            )

            # ── TABS ──────────────────────────────────────────────────────────
            tab_overview, tab_edit, tab_skills = st.tabs([
                "📋 Overview",
                "✏️ Edit Details",
                "🎓 Skills / Documents",
            ])

            # ── Tab 1: Overview ───────────────────────────────────────────────
            with tab_overview:
                if mode == "new":
                    st.markdown(
                        "<div style='color:#9CA3AF;font-size:13px;"
                        "text-align:center;padding:24px 0;'>"
                        "Save the operator first to see the overview.</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    so = selected_operator or {}

                    _section_hdr("person", "Personal Details")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("Operator Name",  so.get("operator_name"))
                        + _info_field("Mobile Number",  so.get("mobile_number"))
                        + _info_field("Aadhar Number",  so.get("aadhar_number"))
                        + _info_field("Joining Date",   str(so.get("joining_date") or "") or None)
                        + _info_field("Status",         so.get("status"), wide=True)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
                    _section_hdr("card_membership", "Licence Details")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("Licence Number",      so.get("license_number"))
                        + _info_field("Licence Type",        so.get("license_type"))
                        + _info_field("Licence Expiry",      str(so.get("license_expiry") or "") or None)
                        + _info_field("Heavy Licence Start", str(so.get("heavy_license_startdate") or "") or None)
                        + _info_field("Light Licence Start", str(so.get("light_license_startdate") or "") or None,
                                      wide=True)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
                    _section_hdr("account_balance", "Bank Details")
                    salary_raw  = so.get("fixed_salary")
                    salary_disp = f"₹ {float(salary_raw):.2f}" if salary_raw else None
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("Account Number",   so.get("bank_account_number"))
                        + _info_field("IFSC Code",        so.get("ifsc_code"))
                        + _info_field("Bank Name",        so.get("bank_name"))
                        + _info_field("Name in Passbook", so.get("name_in_passbook"))
                        + _info_field("Fixed Salary",     salary_disp, wide=True)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

            # ── Tab 2: Edit Details ───────────────────────────────────────────
            with tab_edit:
                # Section 1 — Personal Details
                with st.container(border=True):
                    _section_hdr("person", "Personal Details")
                    p1, p2 = st.columns(2)
                    with p1:
                        operator_name = st.text_input(
                            "Operator Name *", key="op_name",
                            placeholder="e.g. Vikram Singh",
                        )
                        aadhar_number = st.text_input(
                            "Aadhar Number", key="op_aadhar",
                            placeholder="12-digit Aadhar",
                        )
                    with p2:
                        mobile_number = st.text_input(
                            "Mobile Number", key="op_mobile",
                            placeholder="e.g. +91 98111 22233",
                        )
                        joining_date = st.date_input(
                            "Joining Date", key="op_joining_date",
                        )
                    status = st.selectbox(
                        "Status", options=operator_status_values, key="op_status",
                    )

                # Section 2 — Licence Details
                with st.container(border=True):
                    _section_hdr("card_membership", "Licence Details")
                    l1, l2 = st.columns(2)
                    with l1:
                        license_number = st.text_input(
                            "Driving Licence Number", key="op_license_number",
                        )
                        license_expiry = st.date_input(
                            "Licence Expiry Date", key="op_license_expiry",
                        )
                        light_license_start = st.date_input(
                            "Light Licence Start Date", key="op_light_license_start",
                        )
                    with l2:
                        license_type = st.text_input(
                            "Licence Type", key="op_license_type",
                            placeholder="e.g. Boom/Scissor",
                        )
                        heavy_license_start = st.date_input(
                            "Heavy Licence Start Date", key="op_heavy_license_start",
                        )

                # Section 3 — Bank Details
                with st.container(border=True):
                    _section_hdr("account_balance", "Bank Details")
                    b1, b2 = st.columns(2)
                    with b1:
                        bank_account_number = st.text_input(
                            "Account Number", key="op_bank_account",
                            placeholder="e.g. 0012345678901",
                        )
                        bank_name = st.text_input(
                            "Bank Name", key="op_bank_name",
                        )
                        st.number_input(
                            "Fixed Salary",
                            step=0.01,
                            min_value=0.0,
                            key="op_fixed_salary",
                        )
                    with b2:
                        ifsc_code = st.text_input(
                            "IFSC Code", key="op_ifsc",
                            placeholder="e.g. SBIN0001234",
                        )
                        name_in_passbook = st.text_input(
                            "Name as per Passbook", key="op_name_passbook",
                        )

            # ── Tab 3: Skills / Documents (placeholder) ───────────────────────
            with tab_skills:
                _placeholder_tab(
                    "school",
                    "Skills & Documents coming soon",
                    "Operator certifications, training records, and uploaded documents "
                    "will appear here.",
                )

            # ── Action buttons (outside tabs) ─────────────────────────────────
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            sv1, sv2, sv3, _ = st.columns([3, 1, 1, 2])
            with sv1:
                save_clicked = st.button(
                    "💾  Update Operator" if mode == "edit" else "💾  Create Operator",
                    type="primary",
                    use_container_width=True,
                    key="op_save_btn",
                )
            with sv2:
                if st.button("Cancel", use_container_width=True, key="op_cancel_btn"):
                    st.session_state["_op_mode"]     = "none"
                    st.session_state["_op_sel_id"]   = ""
                    st.session_state["_op_sync_key"] = None
                    st.rerun()
            with sv3:
                if st.button("↻ Refresh", use_container_width=True, key="op_refresh_btn"):
                    st.session_state["_op_sync_key"] = None
                    st.rerun()

            # ── Save logic ─────────────────────────────────────────────────────
            if save_clicked:
                name_val = operator_name.strip()
                if not name_val:
                    st.error("Operator Name is required.")
                else:
                    payload = dict(
                        operator_name=name_val,
                        mobile_number=mobile_number.strip() or None,
                        aadhar_number=aadhar_number.strip() or None,
                        joining_date=joining_date.isoformat() if joining_date else None,
                        status=status,
                        license_number=license_number.strip() or None,
                        license_type=license_type.strip() or None,
                        license_expiry=license_expiry.isoformat() if license_expiry else None,
                        heavy_license_startdate=heavy_license_start.isoformat() if heavy_license_start else None,
                        light_license_startdate=light_license_start.isoformat() if light_license_start else None,
                        bank_account_number=bank_account_number.strip() or None,
                        ifsc_code=ifsc_code.strip() or None,
                        bank_name=bank_name.strip() or None,
                        name_in_passbook=name_in_passbook.strip() or None,
                        fixed_salary=float(st.session_state.get("op_fixed_salary", 0.0)) or None,
                    )

                    _err       = None
                    _toast_msg = None
                    _new_id    = None
                    try:
                        if mode == "edit" and selected_operator:
                            sb.update_operator(selected_id, payload)
                            _toast_msg = f"'{name_val}' updated successfully."
                        else:
                            created    = sb.insert_operator(payload)
                            _new_id    = created.get("id", "")
                            _toast_msg = f"Operator '{name_val}' created."
                    except Exception as exc:
                        _err = str(exc)

                    if _err:
                        st.error(f"Could not save operator: {_err}")
                    else:
                        if _new_id:
                            st.session_state["_op_mode"]     = "edit"
                            st.session_state["_op_sel_id"]   = _new_id
                            st.session_state["_op_sync_key"] = None
                        st.toast(_toast_msg, icon="✅")
                        st.rerun()
