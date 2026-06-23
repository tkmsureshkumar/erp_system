"""
erp/views/asset.py
Manage asset_master — create and edit asset types stored in Supabase.
"""
from __future__ import annotations

import streamlit as st

from ..supabase_client import SupabaseClient


def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Asset Master</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_assets() -> list[dict]:
        try:
            return sb.list_assets()
        except Exception as exc:
            st.error(f"Failed to load assets from Supabase: {exc}")
            return []

    assets = fetch_assets()

    # ---- Edit selector ----
    asset_map = {a.get("id"): a for a in assets if a.get("id")}
    asset_ids = [""] + list(asset_map)
    selected_id = st.selectbox(
        "Edit existing asset",
        options=asset_ids,
        format_func=lambda aid: "New asset" if not aid
            else f"{asset_map[aid].get('asset_name', 'Unknown')} [{asset_map[aid].get('asset_prefix', '')}]",
        key="selected_asset_id",
    )
    selected = asset_map.get(selected_id)

    # ---- Sync session state when selection changes ----
    if st.session_state.get("_editing_asset_id") != selected_id:
        st.session_state["_editing_asset_id"] = selected_id
        st.session_state["asset_name"]   = selected.get("asset_name", "")   if selected else ""
        st.session_state["asset_prefix"] = selected.get("asset_prefix", "") if selected else ""
        st.session_state["asset_note"]   = selected.get("note", "")          if selected else ""
        st.session_state["asset_active"] = selected.get("is_active", True)   if selected else True

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    # ---- Form ----
    col_form, col_list = st.columns([2, 3])

    with col_form:
        with st.form("asset_form"):
            asset_name = st.text_input(
                "Asset Name *",
                key="asset_name",
                placeholder="e.g. Boom Lift",
            )
            asset_prefix = st.text_input(
                "Asset Prefix",
                key="asset_prefix",
                placeholder="e.g. BL",
            )
            note = st.text_area(
                "Note",
                key="asset_note",
                placeholder="Optional description or remarks",
                height=100,
            )
            is_active = st.checkbox("Active", key="asset_active")

            action_label = "Update Asset" if selected else "Create Asset"
            submitted = st.form_submit_button(action_label)

            if submitted:
                if not asset_name.strip():
                    st.error("Asset Name is required.")
                else:
                    payload = dict(
                        asset_name=asset_name.strip(),
                        asset_prefix=asset_prefix.strip() or None,
                        note=note.strip() or None,
                        is_active=is_active,
                    )
                    try:
                        if selected:
                            sb.update_asset(selected_id, payload)
                            st.success(f"Asset '{asset_name}' updated.")
                        else:
                            created = sb.insert_asset(payload)
                            label = created.get("asset_name") or asset_name
                            st.success(f"Asset '{label}' created.")
                        assets = fetch_assets()
                    except Exception as exc:
                        st.error(f"Could not save asset: {exc}")

    # ---- Asset list ----
    with col_list:
        col_cap, col_btn = st.columns([3, 1])
        with col_cap:
            st.markdown('<p class="filter-label">All Assets</p>', unsafe_allow_html=True)
        with col_btn:
            if st.button("Refresh", key="refresh_assets"):
                assets = fetch_assets()

        if assets:
            st.dataframe(
                [
                    {
                        "Asset Name":   a.get("asset_name", ""),
                        "Prefix":       a.get("asset_prefix", ""),
                        "Note":         a.get("note", ""),
                        "Active":       "Yes" if a.get("is_active") else "No",
                    }
                    for a in assets
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No assets found. Create one using the form.")
