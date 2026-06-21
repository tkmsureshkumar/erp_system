"""
erp/views/customers.py
Form to add customers and persist only to Supabase.
"""
from __future__ import annotations

import streamlit as st

from ..state_config import load_state_names
from ..supabase_client import SupabaseClient


def render() -> None:
    st.subheader("Customers")

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_customers() -> list[dict[str, object]]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers from Supabase: {exc}")
            return []

    customers = fetch_customers()
    state_names = load_state_names() or ["Maharashtra", "Tamil Nadu", "Karnataka"]

    c1, c2 = st.columns([2, 1])
    customer_map = {cust.get("id"): cust for cust in customers if cust.get("id")}
    customer_ids = [""] + list(customer_map)
    selected_customer_id = st.selectbox(
        "Edit existing customer",
        options=customer_ids,
        format_func=lambda cust_id: "New customer" if not cust_id else f"{customer_map[cust_id].get('customer_name', 'Unknown')} ({cust_id})",
        key="selected_customer_id",
    )
    selected_customer = customer_map.get(selected_customer_id)

    if st.session_state.get("editing_customer_id") != selected_customer_id:
        st.session_state["editing_customer_id"] = selected_customer_id
        st.session_state["cust_name"] = selected_customer.get("customer_name", "") if selected_customer else ""
        st.session_state["cust_contact"] = selected_customer.get("contact_person", "") if selected_customer else ""
        st.session_state["cust_mobile"] = selected_customer.get("mobile", "") if selected_customer else ""
        st.session_state["cust_email"] = selected_customer.get("email", "") if selected_customer else ""
        st.session_state["cust_gst"] = selected_customer.get("gst_number", "") if selected_customer else ""
        st.session_state["cust_billing"] = selected_customer.get("billing_address", "") if selected_customer else ""
        st.session_state["cust_city"] = selected_customer.get("city", "") if selected_customer else ""
        st.session_state["cust_state"] = selected_customer.get("state", state_names[0]) if selected_customer else state_names[0]
        st.session_state["cust_terms"] = selected_customer.get("payment_terms") or 0 if selected_customer else 0

    with c1:
        with st.form("customer_form"):
            customer_name = st.text_input("Customer Name *", key="cust_name")
            contact_person = st.text_input("Contact Person", key="cust_contact")
            mobile = st.text_input("Mobile", key="cust_mobile")
            email = st.text_input("Email", key="cust_email")
            gst_number = st.text_input("GST Number", key="cust_gst")
            billing_address = st.text_area("Billing Address", key="cust_billing")
            city = st.text_input("City", key="cust_city")
            state = st.selectbox("State", options=state_names, key="cust_state")
            payment_terms = st.number_input("Payment Terms (days)", value=st.session_state.get("cust_terms", 0), step=1, key="cust_terms")

            action_label = "Update Customer" if selected_customer else "Create Customer"
            submit = st.form_submit_button(action_label)
            if submit:
                if not customer_name:
                    st.error("Customer Name is required.")
                else:
                    payload = dict(
                        customer_name=customer_name,
                        contact_person=contact_person or None,
                        mobile=mobile or None,
                        email=email or None,
                        gst_number=gst_number or None,
                        billing_address=billing_address or None,
                        city=city or None,
                        state=state or None,
                        payment_terms=int(payment_terms) if payment_terms else None,
                    )
                    try:
                        if selected_customer:
                            sb.update_customer(selected_customer_id, payload)
                            st.success("Customer updated in Supabase.")
                        else:
                            created = sb.insert_customer(payload)
                            identifier = created.get("customer_code") or created.get("id") or customer_name
                            st.success(f"Created customer in Supabase: {identifier}")
                        customers = fetch_customers()
                    except Exception as exc:
                        st.error(f"Could not save customer to Supabase: {exc}")

    with c2:
        st.caption("Supabase customers (latest first)")
        if st.button("Refresh from Supabase", key="refresh_customers"):
            customers = fetch_customers()

        if customers:
            st.dataframe(customers)
        else:
            st.info("No customers found in Supabase.")
