"""
erp/views/site.py
Form to add and edit sites with Supabase persistence.
"""
from __future__ import annotations

import streamlit as st

from ..state_config import load_state_names
from ..supabase_client import SupabaseClient


def render() -> None:
    st.subheader("Sites")

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_sites() -> list[dict[str, object]]:
        try:
            return sb.list_sites()
        except Exception as exc:
            st.error(f"Failed to load sites from Supabase: {exc}")
            return []

    def fetch_customers() -> list[dict[str, object]]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers from Supabase: {exc}")
            return []

    sites = fetch_sites()
    customers = fetch_customers()
    state_names = load_state_names() or ["Maharashtra", "Tamil Nadu", "Karnataka"]

    c1, c2 = st.columns([2, 1])
    site_map = {site.get("id"): site for site in sites if site.get("id")}
    site_ids = [""] + list(site_map)
    selected_site_id = st.selectbox(
        "Edit existing site",
        options=site_ids,
        format_func=lambda site_id: "New site" if not site_id else f"{site_map[site_id].get('site_name', 'Unknown')} ({site_id})",
        key="selected_site_id",
    )
    selected_site = site_map.get(selected_site_id)

    if st.session_state.get("editing_site_id") != selected_site_id:
        st.session_state["editing_site_id"] = selected_site_id
        st.session_state["site_name"] = selected_site.get("site_name", "") if selected_site else ""
        st.session_state["site_customer_id"] = selected_site.get("customer_id", "") if selected_site else ""
        st.session_state["site_address"] = selected_site.get("address", "") if selected_site else ""
        st.session_state["site_city"] = selected_site.get("city", "") if selected_site else ""
        st.session_state["site_state"] = selected_site.get("state", state_names[0]) if selected_site else state_names[0]
        st.session_state["site_pincode"] = selected_site.get("pincode", "") if selected_site else ""
        st.session_state["site_contact"] = selected_site.get("site_contact", "") if selected_site else ""
        st.session_state["site_contact_number"] = selected_site.get("site_contact_number", "") if selected_site else ""

    with c1:
        with st.form("site_form"):
            site_name = st.text_input("Site Name *", key="site_name")
            
            customer_options = {cust.get("id"): cust.get("customer_name") for cust in customers if cust.get("id")}
            customer_ids_list = [""] + list(customer_options.keys())
            customer_id = st.selectbox(
                "Customer *",
                options=customer_ids_list,
                format_func=lambda cid: "Select customer" if not cid else customer_options.get(cid, "Unknown"),
                key="site_customer_id",
            )
            
            address = st.text_input("Address", key="site_address")
            city = st.text_input("City", key="site_city")
            state = st.selectbox("State", options=state_names, key="site_state")
            pincode = st.text_input("Pincode", key="site_pincode")
            site_contact = st.text_input("Site Contact", key="site_contact")
            site_contact_number = st.text_input("Site Contact Number", key="site_contact_number")

            action_label = "Update Site" if selected_site else "Create Site"
            submit = st.form_submit_button(action_label)
            if submit:
                if not site_name:
                    st.error("Site Name is required.")
                elif not customer_id:
                    st.error("Customer is required.")
                else:
                    payload = dict(
                        site_name=site_name,
                        customer_id=customer_id,
                        address=address or None,
                        city=city or None,
                        state=state or None,
                        pincode=pincode or None,
                        site_contact=site_contact or None,
                        site_contact_number=site_contact_number or None,
                    )
                    try:
                        if selected_site:
                            sb.update_site(selected_site_id, payload)
                            st.success("Site updated in Supabase.")
                        else:
                            created = sb.insert_site(payload)
                            identifier = created.get("site_code") or created.get("id") or site_name
                            st.success(f"Created site in Supabase: {identifier}")
                        sites = fetch_sites()
                    except Exception as exc:
                        st.error(f"Could not save site to Supabase: {exc}")

    with c2:
        st.caption("Supabase sites (latest first)")
        if st.button("Refresh from Supabase", key="refresh_sites"):
            sites = fetch_sites()

        if sites:
            st.dataframe(sites)
        else:
            st.info("No sites found in Supabase.")
