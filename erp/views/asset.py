"""
erp/views/asset.py
Asset management — modern enterprise UI.
Left:  searchable asset directory.
Right: form (Asset Details).

Mode state  _asset_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

import streamlit as st

from ..supabase_client import SupabaseClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper() if name else "??"


def _avatar_color(name: str) -> str:
    palette = ["#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
               "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16"]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


def _section_hdr(title: str, note: str = "") -> None:
    note_html = (
        f"<span style='font-size:11px;color:#6b7280;font-weight:400;"
        f"margin-left:8px;'>{note}</span>" if note else ""
    )
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:10px;'>"
        f"{title}{note_html}</div>",
        unsafe_allow_html=True,
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


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:

    # ── CSS ───────────────────────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        .cust-stat-row {
            display:flex; gap:12px; flex-wrap:wrap; margin:14px 0 20px;
        }
        .cust-stat-pill {
            background:#f8fafc; border:1px solid #e5e7eb;
            border-radius:20px; padding:5px 16px;
            display:flex; align-items:center; gap:6px;
        }
        .cust-stat-val { font-size:15px; font-weight:800; color:#E87722; }
        .cust-stat-lbl { font-size:11px; color:#6b7280; font-weight:500; }

        .cust-banner {
            background:linear-gradient(135deg,#1c1c2e 0%,#2d2d44 100%);
            border-radius:10px; padding:18px 20px; margin-bottom:16px;
            display:flex; align-items:center; gap:14px;
        }
        .cust-banner-avatar {
            width:46px; height:46px; border-radius:50%;
            display:flex; align-items:center; justify-content:center;
            font-size:15px; font-weight:800; color:#fff; flex-shrink:0;
        }
        .cust-banner-name { font-size:19px; font-weight:800; color:#fff; line-height:1.2; }
        .cust-banner-code { font-size:11px; color:rgba(255,255,255,.45);
                            letter-spacing:.08em; margin-top:2px; }
        .badge-new  { background:#dcfce7; color:#166534; font-size:10px; font-weight:700;
                      padding:3px 10px; border-radius:20px; text-transform:uppercase;
                      letter-spacing:.06em; margin-left:auto; white-space:nowrap; }
        .badge-edit { background:#fff7ed; color:#9a3412; font-size:10px; font-weight:700;
                      padding:3px 10px; border-radius:20px; text-transform:uppercase;
                      letter-spacing:.06em; margin-left:auto; white-space:nowrap; }

        .cust-empty {
            background:#f8fafc; border:2px dashed #e5e7eb;
            border-radius:12px; text-align:center;
            padding:60px 32px; color:#9ca3af;
        }
        .cust-empty-icon  { font-size:52px; margin-bottom:14px; }
        .cust-empty-title { font-size:18px; font-weight:700; color:#374151; margin-bottom:8px; }
        .cust-empty-sub   { font-size:13px; margin-bottom:24px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

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

    # ── Header button (after data is available) ────────────────────────────────
    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New Asset", use_container_width=True,
                     type="primary", key="hdr_new_asset"):
            _open_new_form()
            st.rerun()

    # ── Stats bar ──────────────────────────────────────────────────────────────
    n_total  = len(assets)
    n_active = sum(1 for a in assets if a.get("is_active") is True)
    st.markdown(
        f"<div class='cust-stat-row'>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_total}</span>"
        f"<span class='cust-stat-lbl'>Total Assets</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_active}</span>"
        f"<span class='cust-stat-lbl'>Active</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_asset_mode" not in st.session_state:
        st.session_state["_asset_mode"]   = "none"
    if "_asset_sel_id" not in st.session_state:
        st.session_state["_asset_sel_id"] = ""

    mode        = st.session_state["_asset_mode"]          # "none" | "new" | "edit"
    selected_id = st.session_state["_asset_sel_id"]
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

    # ──────────────────────────────────────────────────────────────────────────
    # LEFT — Asset directory
    # ──────────────────────────────────────────────────────────────────────────
    with left_col:
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search by asset name…",
            key="asset_search_q",
        )
        q = search_q.strip().lower()
        filtered_map = {
            aid: a for aid, a in asset_map.items()
            if not q or q in a.get("asset_name", "").lower()
        }

        count_txt = (
            f"{len(filtered_map)} of {n_total}" if q
            else f"{n_total} assets"
        )
        st.markdown(
            f"<p style='font-size:11px;color:#9ca3af;margin:2px 0 8px;'>{count_txt}</p>",
            unsafe_allow_html=True,
        )

        with st.container(height=530):
            if not filtered_map:
                st.markdown(
                    "<p style='color:#9ca3af;font-size:13px;text-align:center;"
                    "padding:40px 0;'>No matches found.</p>",
                    unsafe_allow_html=True,
                )
            for aid, a in filtered_map.items():
                is_sel  = (aid == selected_id and mode == "edit")
                name    = a.get("asset_name", "Unknown")
                prefix  = a.get("asset_prefix", "")
                active  = a.get("is_active", True)
                color   = _avatar_color(name)

                sel_border = "border-left:3px solid #E87722;" if is_sel else "border-left:3px solid transparent;"
                sel_bg     = "background:#fff7ed;" if is_sel else "background:#ffffff;"
                name_w     = "font-weight:700;" if is_sel else "font-weight:500;"

                status_badge = (
                    "<span style='font-size:9px;font-weight:700;background:#dcfce7;"
                    "color:#166534;padding:2px 7px;border-radius:10px;"
                    "white-space:nowrap;'>Active</span>"
                    if active else
                    "<span style='font-size:9px;font-weight:700;background:#fee2e2;"
                    "color:#991b1b;padding:2px 7px;border-radius:10px;"
                    "white-space:nowrap;'>Inactive</span>"
                )
                prefix_txt = f"{prefix}&nbsp;&middot;&nbsp;" if prefix else ""

                st.markdown(
                    f"<div style='{sel_bg}{sel_border}border:1px solid #e5e7eb;"
                    f"padding:9px 12px;display:flex;align-items:center;gap:10px;"
                    f"pointer-events:none;'>"
                    f"<div style='width:34px;height:34px;border-radius:50%;"
                    f"background:{color};display:flex;align-items:center;"
                    f"justify-content:center;font-size:12px;font-weight:800;"
                    f"color:#fff;flex-shrink:0;'>{_initials(name)}</div>"
                    f"<div style='min-width:0;flex:1;'>"
                    f"<div style='font-size:13px;{name_w}color:#111827;"
                    f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{name}</div>"
                    f"<div style='font-size:11px;color:#6b7280;margin-top:1px;'>"
                    f"{prefix_txt}{status_badge}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Selected ✓" if is_sel else "Open",
                    key=f"csel_{aid}",
                    use_container_width=True,
                    help=name,
                ):
                    st.session_state["_asset_mode"]     = "edit"
                    st.session_state["_asset_sel_id"]   = aid
                    st.session_state["_asset_sync_key"] = None  # force sync
                    st.rerun()

    # ──────────────────────────────────────────────────────────────────────────
    # RIGHT — Detail / form panel
    # ──────────────────────────────────────────────────────────────────────────
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='cust-empty'>"
                "<div class='cust-empty-icon'>&#127959;</div>"
                "<div class='cust-empty-title'>No asset selected</div>"
                "<p class='cust-empty-sub'>Pick an asset from the directory "
                "or click <strong>+ New Asset</strong> above to add one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT FORM ───────────────────────────────────────────────────
        else:
            # Header banner
            display_name = (
                st.session_state.get("asset_name")
                or (selected_asset.get("asset_name", "") if selected_asset else "")
                or "New Asset"
            )
            col_val = _avatar_color(display_name)
            badge = (
                "<span class='badge-edit'>Editing</span>"
                if mode == "edit" else "<span class='badge-new'>New Asset</span>"
            )
            st.markdown(
                f"<div class='cust-banner'>"
                f"<div class='cust-banner-avatar' style='background:{col_val};'>"
                f"{_initials(display_name)}</div>"
                f"<div style='flex:1;min-width:0;'>"
                f"<div class='cust-banner-name'>{display_name}</div></div>"
                f"{badge}</div>",
                unsafe_allow_html=True,
            )

            # Section — Asset Details
            with st.container(border=True):
                _section_hdr("Asset Details")
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

            # Action buttons
            sv1, sv2, sv3 = st.columns([4, 1, 1])
            with sv1:
                save_clicked = st.button(
                    "Update Asset" if mode == "edit" else "Create Asset",
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
                if st.button("Refresh", use_container_width=True, key="asset_refresh_btn"):
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
