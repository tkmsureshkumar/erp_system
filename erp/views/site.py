"""
erp/views/site.py
Manage sites with multiple contact persons and payment terms.
site_contact column stores a JSON array:
  [{"name": "...", "email": "...", "mobile": "..."}, ...]
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ..state_config import load_state_names
from ..supabase_client import SupabaseClient

# ── Contact helpers (same pattern as customers.py) ────────────────────────────

def _parse_contacts(raw) -> list[dict]:
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
            # Legacy plain string — treat as single contact name
            return [{"name": raw, "email": "", "mobile": ""}]
    return []


def _contacts_to_df(contacts: list[dict]) -> pd.DataFrame:
    rows = contacts or [{"name": "", "email": "", "mobile": ""}]
    return pd.DataFrame(rows, columns=["name", "email", "mobile"])


def _df_to_contacts(df: pd.DataFrame) -> list[dict]:
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
        <div class="page-title">Sites</div>
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

    def fetch_sites() -> list[dict]:
        try:
            return sb.list_sites()
        except Exception as exc:
            st.error(f"Failed to load sites from Supabase: {exc}")
            return []

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers from Supabase: {exc}")
            return []

    sites       = fetch_sites()
    customers   = fetch_customers()
    state_names = load_state_names() or ["Maharashtra", "Tamil Nadu", "Karnataka"]

    # ── Edit selector ──────────────────────────────────────────────────────────
    site_map = {s.get("id"): s for s in sites if s.get("id")}
    site_ids = [""] + list(site_map)
    selected_site_id = st.selectbox(
        "Edit existing site",
        options=site_ids,
        format_func=lambda sid: "New site" if not sid
            else f"{site_map[sid].get('site_name', 'Unknown')} ({sid})",
        key="selected_site_id",
    )
    selected_site = site_map.get(selected_site_id)

    # ── Sync session state when selection changes ──────────────────────────────
    if st.session_state.get("_editing_site_id") != selected_site_id:
        st.session_state["_editing_site_id"]      = selected_site_id
        st.session_state["site_name"]             = selected_site.get("site_name", "")             if selected_site else ""
        st.session_state["site_customer_id"]      = selected_site.get("customer_id", "")           if selected_site else ""
        st.session_state["site_address"]          = selected_site.get("address", "")               if selected_site else ""
        st.session_state["site_city"]             = selected_site.get("city", "")                  if selected_site else ""
        st.session_state["site_state"]            = selected_site.get("state", state_names[0])     if selected_site else state_names[0]
        st.session_state["site_pincode"]          = selected_site.get("pincode", "")               if selected_site else ""
        st.session_state["site_payment_terms"]    = selected_site.get("payment_terms") or 0        if selected_site else 0

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    # ── Left / Right columns ───────────────────────────────────────────────────
    col_form, col_list = st.columns([2, 3])

    with col_form:
        # ── Site contact persons — OUTSIDE form so rows can be added/removed ──
        st.markdown('<p class="filter-label">Site Contact Persons</p>', unsafe_allow_html=True)

        existing_contacts = _parse_contacts(
            selected_site.get("site_contact") if selected_site else None
        )
        contacts_df = st.data_editor(
            _contacts_to_df(existing_contacts),
            column_config={
                "name":   st.column_config.TextColumn("Contact Name",  width="medium"),
                "email":  st.column_config.TextColumn("Email",         width="medium"),
                "mobile": st.column_config.TextColumn("Mobile Number", width="medium"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"site_contacts_editor_{selected_site_id or 'new'}",
        )

        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

        # ── Site details form ──────────────────────────────────────────────────
        st.markdown('<p class="filter-label">Site Details</p>', unsafe_allow_html=True)

        with st.form("site_form"):
            site_name = st.text_input("Site Name *", key="site_name")

            customer_options = {
                c.get("id"): c.get("customer_name", "Unknown")
                for c in customers if c.get("id")
            }
            customer_id = st.selectbox(
                "Customer *",
                options=[""] + list(customer_options),
                format_func=lambda cid: "Select customer" if not cid
                    else customer_options.get(cid, "Unknown"),
                key="site_customer_id",
            )

            address = st.text_input("Address", key="site_address")

            c_city, c_state = st.columns(2)
            with c_city:
                city    = st.text_input("City",    key="site_city")
            with c_state:
                state   = st.selectbox("State", options=state_names, key="site_state")

            pincode = st.text_input("Pincode", key="site_pincode")

            payment_terms = st.number_input(
                "Payment Terms (days)",
                value=int(st.session_state.get("site_payment_terms", 0)),
                step=1,
                min_value=0,
                key="site_payment_terms",
            )

            action_label = "Update Site" if selected_site else "Create Site"
            submitted = st.form_submit_button(action_label)

            if submitted:
                if not site_name.strip():
                    st.error("Site Name is required.")
                elif not customer_id:
                    st.error("Customer is required.")
                else:
                    contacts_list = _df_to_contacts(contacts_df)
                    first = contacts_list[0] if contacts_list else {}

                    payload = dict(
                        site_name=site_name.strip(),
                        customer_id=customer_id,
                        address=address.strip() or None,
                        city=city.strip() or None,
                        state=state or None,
                        pincode=pincode.strip() or None,
                        # contacts stored as JSON; back-fill legacy columns from first contact
                        site_contact=json.dumps(contacts_list) if contacts_list else None,
                        site_contact_number=first.get("mobile") or None,
                        payment_terms=int(payment_terms) if payment_terms else None,
                    )
                    try:
                        if selected_site:
                            sb.update_site(selected_site_id, payload)
                            st.success("Site updated.")
                        else:
                            created = sb.insert_site(payload)
                            label = created.get("site_code") or created.get("id") or site_name
                            st.success(f"Site created: {label}")
                        sites = fetch_sites()
                    except Exception as exc:
                        st.error(f"Could not save site: {exc}")

    # ── Site list ──────────────────────────────────────────────────────────────
    with col_list:
        col_cap, col_btn = st.columns([3, 1])
        with col_cap:
            st.markdown('<p class="filter-label">All Sites</p>', unsafe_allow_html=True)
        with col_btn:
            if st.button("Refresh", key="refresh_sites"):
                sites = fetch_sites()

        if sites:
            rows = []
            for s in sites:
                contacts = _parse_contacts(s.get("site_contact"))
                primary  = contacts[0] if contacts else {}
                rows.append({
                    "Code":            s.get("site_code", ""),
                    "Site Name":       s.get("site_name", ""),
                    "Customer":        next(
                        (c.get("customer_name", "") for c in customers if c.get("id") == s.get("customer_id")),
                        "",
                    ),
                    "Primary Contact": primary.get("name", ""),
                    "Mobile":          primary.get("mobile", ""),
                    "Contacts":        len(contacts),
                    "City":            s.get("city", ""),
                    "Payment Terms":   s.get("payment_terms", ""),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No sites found.")
