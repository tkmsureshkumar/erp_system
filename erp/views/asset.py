"""
erp/views/asset.py
Asset management — premium SaaS redesign.
Left  (35%): searchable asset directory with modern cards.
Right (65%): empty state / hero banner / form panel.

Mode state  _asset_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

import streamlit as st

from ..supabase_client import SupabaseClient


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
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

/* ── Asset list cards ────────────────────────────────────────────────── */
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
    box-shadow: 0 4px 16px rgba(37,99,235,.10);
    border-color: #93C5FD;
    transform: translateY(-1px);
}
.cl-item.cl-sel {
    border-color: #2563EB !important;
    background: #EFF6FF;
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
.cl-prefix-badge {
    font-size: 9px; font-weight: 700;
    background: #F1F5F9; color: #64748B;
    padding: 2px 8px; border-radius: 20px;
    white-space: nowrap; flex-shrink: 0;
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
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px;
    margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 {
    font-size: 17px; font-weight: 700; color: #111827;
    margin: 0 0 8px;
}
.empty-state-v2 p {
    font-size: 13px; color: #9CA3AF;
    max-width: 270px; line-height: 1.6; margin: 0;
}

/* ── Asset hero banner ───────────────────────────────────────────────── */
.cust-hero {
    background: linear-gradient(135deg, #1E2938 0%, #1c3461 100%);
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
    background: rgba(245,158,11,.18); color: #FCD34D;
    border: 1px solid rgba(245,158,11,.28);
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

/* ── No-results state ─────────────────────────────────────────────────── */
.no-results {
    text-align: center; padding: 36px 12px;
    color: #9CA3AF; font-size: 13px;
}
.no-results .nr-icon { font-size: 32px; margin-bottom: 8px; display: block; }

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper() if name else "??"


def _avatar_color(name: str) -> str:
    palette = [
        "#2563EB", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444",
        "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
    ]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


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


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _asset_card(a: dict, is_sel: bool) -> str:
    name    = a.get("asset_name", "Unknown")
    prefix  = a.get("asset_prefix", "")
    active  = a.get("is_active", True)
    color   = _avatar_color(name)
    sel_cls = " cl-sel" if is_sel else ""

    status_badge = (
        "<span class='badge badge-active'>Active</span>"
        if active else
        "<span class='badge badge-breakdown'>Inactive</span>"
    )
    prefix_html = (
        f"<span class='cl-prefix-badge'>{prefix}</span>"
        if prefix else ""
    )

    return (
        f"<div class='cl-item{sel_cls}'>"
        f"<div class='cl-avatar' style='background:{color};'>{_initials(name)}</div>"
        f"<div class='cl-info'>"
        f"<div class='cl-name'>{name}</div>"
        f"<div class='cl-sub'>"
        f"{prefix_html}"
        f"{'<span style=\"width:3px;height:3px;border-radius:50%;background:#D1D5DB;flex-shrink:0;\"></span>' if prefix else ''}"
        f"{status_badge}"
        f"</div>"
        f"</div>"
        f"</div>"
    )


def _open_new_form() -> None:
    """Switch UI to new-asset mode and reset form fields."""
    st.session_state["_asset_mode"]     = "new"
    st.session_state["_asset_sel_id"]   = ""
    st.session_state["_asset_sync_key"] = "__new__"
    st.session_state["asset_name"]      = ""
    st.session_state["asset_prefix"]    = ""
    st.session_state["asset_note"]      = ""
    st.session_state["asset_active"]    = True


# ── Main view ─────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        st.markdown(
            "<div class='page-eyebrow'>// Fleet Operations</div>"
            "<div class='page-title'>Asset Master</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    def fetch_assets() -> list[dict]:
        try:
            return sb.list_assets()
        except Exception as exc:
            st.error(f"Failed to load assets: {exc}")
            return []

    assets    = fetch_assets()
    asset_map = {a["id"]: a for a in assets if a.get("id")}

    # ── Header button ─────────────────────────────────────────────────────────
    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New Asset", use_container_width=True,
                     type="primary", key="hdr_new_asset"):
            _open_new_form()
            st.rerun()

    # ── KPI strip ──────────────────────────────────────────────────────────────
    n_total  = len(assets)
    n_active = sum(1 for a in assets if a.get("is_active") is True)

    st.markdown(
        f"<div class='kpi-grid'>"
        + _kpi_card("category",      "Total Assets",  n_total,
                    "in the master list", "#2563EB")
        + _kpi_card("check_circle",  "Active Assets", n_active,
                    f"{n_total - n_active} inactive", "#10B981")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_asset_mode" not in st.session_state:
        st.session_state["_asset_mode"]   = "none"
    if "_asset_sel_id" not in st.session_state:
        st.session_state["_asset_sel_id"] = ""

    mode           = st.session_state["_asset_mode"]   # "none" | "new" | "edit"
    selected_id    = st.session_state["_asset_sel_id"]
    selected_asset = asset_map.get(selected_id) if selected_id else None

    # ── Sync form fields when selection or mode changes ────────────────────────
    sync_key = f"{mode}__{selected_id}"
    if st.session_state.get("_asset_sync_key") != sync_key:
        st.session_state["_asset_sync_key"] = sync_key
        c = selected_asset or {}
        st.session_state["asset_name"]   = c.get("asset_name", "")
        st.session_state["asset_prefix"] = c.get("asset_prefix", "")
        st.session_state["asset_note"]   = c.get("note", "")
        st.session_state["asset_active"] = bool(c.get("is_active", True))

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — Asset directory
    # ══════════════════════════════════════════════════════════════════════════
    with left_col:

        # Search with icon overlay
        st.markdown(
            "<div class='search-wrap'>"
            "<span class='search-icon-abs msr'>search</span>",
            unsafe_allow_html=True,
        )
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search assets…",
            key="asset_search_q",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        q = search_q.strip().lower()
        filtered_map = {
            aid: a for aid, a in asset_map.items()
            if not q or q in a.get("asset_name", "").lower()
        }

        count_txt = (
            f"<span style='color:#2563EB;font-weight:700;'>{len(filtered_map)}</span>"
            f" of {n_total} assets"
            if q else
            f"<span style='font-weight:700;color:#111827;'>{n_total}</span> assets"
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
                    "No assets match your search."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                for aid, a in filtered_map.items():
                    is_sel = (aid == selected_id and mode == "edit")
                    name   = a.get("asset_name", "Unknown")

                    st.markdown(_asset_card(a, is_sel), unsafe_allow_html=True)
                    if st.button(
                        "✓ Selected" if is_sel else "Open →",
                        key=f"csel_{aid}",
                        use_container_width=True,
                        help=name,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state["_asset_mode"]     = "edit"
                        st.session_state["_asset_sel_id"]   = aid
                        st.session_state["_asset_sync_key"] = None  # force sync
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — Detail / form panel
    # ══════════════════════════════════════════════════════════════════════════
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>🏗️</div>"
                "<h3>No asset selected</h3>"
                "<p>Select an asset from the directory on the left, "
                "or click <strong>+ New Asset</strong> to add one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT FORM ───────────────────────────────────────────────────
        else:
            display_name = (
                st.session_state.get("asset_name")
                or (selected_asset.get("asset_name", "") if selected_asset else "")
                or "New Asset"
            )
            col_val   = _avatar_color(display_name)
            badge_cls = "hero-badge-edit" if mode == "edit" else "hero-badge-new"
            badge_lbl = "Editing" if mode == "edit" else "New Asset"
            prefix_disp = (
                selected_asset.get("asset_prefix", "") if selected_asset else ""
            )
            meta_line = (
                f"PREFIX: {prefix_disp}" if prefix_disp
                else "Unsaved — fill in details below"
            )

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

            # ── Asset Details form ─────────────────────────────────────────────
            with st.container(border=True):
                _section_hdr("category", "Asset Details")

                asset_name = st.text_input(
                    "Asset Name *", key="asset_name",
                    placeholder="e.g. Excavator Unit 01",
                )
                d1, d2 = st.columns([3, 2])
                with d1:
                    asset_prefix = st.text_input(
                        "Prefix", key="asset_prefix",
                        placeholder="e.g. EXC",
                    )
                with d2:
                    is_active = st.checkbox("Active", key="asset_active")
                note = st.text_area(
                    "Note", key="asset_note",
                    placeholder="Optional remarks…", height=80,
                )

            # ── Action buttons ─────────────────────────────────────────────────
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            sv1, sv2, sv3, _ = st.columns([3, 1, 1, 2])
            with sv1:
                save_clicked = st.button(
                    "💾  Update Asset" if mode == "edit" else "💾  Create Asset",
                    type="primary",
                    use_container_width=True,
                    key="asset_save_btn",
                )
            with sv2:
                if st.button("Cancel", use_container_width=True, key="asset_cancel_btn"):
                    st.session_state["_asset_mode"]     = "none"
                    st.session_state["_asset_sel_id"]   = ""
                    st.session_state["_asset_sync_key"] = None
                    st.rerun()
            with sv3:
                if st.button("↻ Refresh", use_container_width=True, key="asset_refresh_btn"):
                    st.session_state["_asset_sync_key"] = None
                    st.rerun()

            # ── Save logic ─────────────────────────────────────────────────────
            if save_clicked:
                name_val = asset_name.strip()
                if not name_val:
                    st.error("Asset Name is required.")
                else:
                    payload = dict(
                        asset_name=name_val,
                        asset_prefix=asset_prefix.strip() or None,
                        note=note.strip() or None,
                        is_active=is_active,
                    )

                    # Keep st.rerun() OUTSIDE try/except —
                    # RerunException(Exception) would otherwise be swallowed.
                    _err       = None
                    _toast_msg = None
                    _new_id    = None
                    try:
                        if mode == "edit" and selected_asset:
                            sb.update_asset(selected_id, payload)
                            _toast_msg = f"'{name_val}' updated successfully."
                        else:
                            created    = sb.insert_asset(payload)
                            _new_id    = created.get("id", "")
                            _toast_msg = f"Asset '{name_val}' created successfully."
                    except Exception as exc:
                        _err = str(exc)

                    if _err:
                        st.error(f"Could not save asset: {_err}")
                    else:
                        if _new_id:
                            st.session_state["_asset_mode"]     = "edit"
                            st.session_state["_asset_sel_id"]   = _new_id
                            st.session_state["_asset_sync_key"] = None
                        st.toast(_toast_msg, icon="✅")
                        st.rerun()
