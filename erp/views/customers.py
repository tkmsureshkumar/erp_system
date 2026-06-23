"""
erp/views/customers.py
Manage customers with multiple contact persons.
contact_person column stores a JSON array:
  [{"name": "...", "email": "...", "mobile": "..."}, ...]
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ..state_config import load_state_names
from ..supabase_client import SupabaseClient

# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_contacts(raw) -> list[dict]:
    """Return a list of contact dicts from whatever is stored in contact_person."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [
            {"name": c.get("name", ""), "email": c.get("email", ""), "mobile": c.get("mobile", "")}
            for c in raw
        ]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [
                    {"name": c.get("name", ""), "email": c.get("email", ""), "mobile": c.get("mobile", "")}
                    for c in parsed
                ]
        except (json.JSONDecodeError, ValueError):
            # Legacy plain-string — treat as a single contact name
            return [{"name": raw, "email": "", "mobile": ""}]
    return []


def _contacts_to_df(contacts: list[dict]) -> pd.DataFrame:
    rows = contacts or [{"name": "", "email": "", "mobile": ""}]
    return pd.DataFrame(rows, columns=["name", "email", "mobile"])


def _df_to_contacts(df: pd.DataFrame) -> list[dict]:
    """Strip empty rows and return serialisable list."""
    result = []
    for _, row in df.iterrows():
        name   = str(row.get("name",   "") or "").strip()
        email  = str(row.get("email",  "") or "").strip()
        mobile = str(row.get("mobile", "") or "").strip()
        if name or email or mobile:
            result.append({"name": name, "email": email, "mobile": mobile})
    return result


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Customers</div>
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

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers from Supabase: {exc}")
            return []

    customers   = fetch_customers()
    state_names = load_state_names() or ["Maharashtra", "Tamil Nadu", "Karnataka"]

    # ── Edit selector ──────────────────────────────────────────────────────────
    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    customer_ids = [""] + list(customer_map)
    selected_customer_id = st.selectbox(
        "Edit existing customer",
        options=customer_ids,
        format_func=lambda cid: "New customer" if not cid
            else f"{customer_map[cid].get('customer_name', 'Unknown')} ({cid})",
        key="selected_customer_id",
    )
    selected_customer = customer_map.get(selected_customer_id)

    # ── Sync session state when selection changes ──────────────────────────────
    if st.session_state.get("_editing_customer_id") != selected_customer_id:
        st.session_state["_editing_customer_id"] = selected_customer_id
        st.session_state["cust_name"]    = selected_customer.get("customer_name", "")             if selected_customer else ""
        st.session_state["cust_gst"]     = selected_customer.get("gst_number", "")                if selected_customer else ""
        st.session_state["cust_billing"] = selected_customer.get("billing_address", "")           if selected_customer else ""
        st.session_state["cust_city"]    = selected_customer.get("city", "")                      if selected_customer else ""
        st.session_state["cust_state"]   = selected_customer.get("state", state_names[0])         if selected_customer else state_names[0]

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    # ── Left / Right columns ───────────────────────────────────────────────────
    col_form, col_list = st.columns([2, 3])

    with col_form:
        # ── Contact persons — OUTSIDE form so rows can be added/removed live ──
        st.markdown('<p class="filter-label">Contact Persons</p>', unsafe_allow_html=True)

        existing_contacts = _parse_contacts(
            selected_customer.get("contact_person") if selected_customer else None
        )
        contacts_df = st.data_editor(
            _contacts_to_df(existing_contacts),
            column_config={
                "name":   st.column_config.TextColumn("Contact Name",   width="medium"),
                "email":  st.column_config.TextColumn("Email",          width="medium"),
                "mobile": st.column_config.TextColumn("Mobile Number",  width="medium"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"contacts_editor_{selected_customer_id or 'new'}",
        )

        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

        # ── Customer details form ──────────────────────────────────────────────
        st.markdown('<p class="filter-label">Customer Details</p>', unsafe_allow_html=True)

        with st.form("customer_form"):
            customer_name  = st.text_input("Customer Name *", key="cust_name")
            gst_number     = st.text_input("GST Number",      key="cust_gst")
            billing_address = st.text_area("Billing Address", key="cust_billing", height=80)

            c_city, c_state = st.columns(2)
            with c_city:
                city  = st.text_input("City",  key="cust_city")
            with c_state:
                state = st.selectbox("State", options=state_names, key="cust_state")

            action_label = "Update Customer" if selected_customer else "Create Customer"
            submitted = st.form_submit_button(action_label)

            if submitted:
                if not customer_name.strip():
                    st.error("Customer Name is required.")
                else:
                    contacts_list = _df_to_contacts(contacts_df)
                    first = contacts_list[0] if contacts_list else {}

                    payload = dict(
                        customer_name=customer_name.strip(),
                        contact_person=json.dumps(contacts_list) if contacts_list else None,
                        # back-fill top-level mobile/email from first contact
                        mobile=first.get("mobile") or None,
                        email=first.get("email") or None,
                        gst_number=gst_number.strip() or None,
                        billing_address=billing_address.strip() or None,
                        city=city.strip() or None,
                        state=state or None,
                    )
                    try:
                        if selected_customer:
                            sb.update_customer(selected_customer_id, payload)
                            st.success("Customer updated.")
                        else:
                            created = sb.insert_customer(payload)
                            label = created.get("customer_code") or created.get("id") or customer_name
                            st.success(f"Customer created: {label}")
                        customers = fetch_customers()
                    except Exception as exc:
                        st.error(f"Could not save customer: {exc}")

    # ── Customer list ──────────────────────────────────────────────────────────
    with col_list:
        col_cap, col_btn = st.columns([3, 1])
        with col_cap:
            st.markdown('<p class="filter-label">All Customers</p>', unsafe_allow_html=True)
        with col_btn:
            if st.button("Refresh", key="refresh_customers"):
                customers = fetch_customers()

        if customers:
            rows = []
            for c in customers:
                contacts = _parse_contacts(c.get("contact_person"))
                # Flatten primary contact for display
                primary = contacts[0] if contacts else {}
                rows.append({
                    "Code":           c.get("customer_code", ""),
                    "Customer Name":  c.get("customer_name", ""),
                    "Primary Contact": primary.get("name", ""),
                    "Email":          primary.get("email", ""),
                    "Mobile":         primary.get("mobile", ""),
                    "Contacts":       len(contacts),
                    "City":           c.get("city", ""),
                    "State":          c.get("state", ""),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No customers found.")
