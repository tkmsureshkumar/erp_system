"""
erp/views/customers.py
Customer management — modern enterprise UI.
Left:  searchable customer directory.
Right: multi-section form (Business Info / Address / Contacts).

Mode state  _cust_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ..state_config import load_state_names
from ..supabase_client import SupabaseClient

# ── Constants ─────────────────────────────────────────────────────────────────

_CONTACT_COLS = ["name", "designation", "email", "mobile", "remarks"]

# ── Data helpers ──────────────────────────────────────────────────────────────

def _parse_contacts(raw) -> list[dict]:
    def _norm(c: dict) -> dict:
        return {
            "name":        c.get("name", ""),
            "designation": c.get("designation", ""),
            "email":       c.get("email", ""),
            "mobile":      c.get("mobile", ""),
            "remarks":     c.get("remarks", ""),
        }
    if not raw:
        return []
    if isinstance(raw, list):
        return [_norm(c) for c in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [_norm(c) for c in parsed]
        except (json.JSONDecodeError, ValueError):
            return [{"name": raw, "designation": "", "email": "",
                     "mobile": "", "remarks": ""}]
    return []


def _contacts_to_df(contacts: list[dict]) -> pd.DataFrame:
    rows = contacts or [{"name": "", "designation": "", "email": "",
                         "mobile": "", "remarks": ""}]
    return pd.DataFrame(rows, columns=_CONTACT_COLS)


def _df_to_contacts(df: pd.DataFrame) -> list[dict]:
    result = []
    for _, row in df.iterrows():
        name        = str(row.get("name",        "") or "").strip()
        designation = str(row.get("designation", "") or "").strip()
        email       = str(row.get("email",       "") or "").strip()
        mobile      = str(row.get("mobile",      "") or "").strip()
        remarks     = str(row.get("remarks",     "") or "").strip()
        if name or email or mobile:
            result.append({"name": name, "designation": designation,
                           "email": email, "mobile": mobile, "remarks": remarks})
    return result


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
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


def _open_new_form(state_names: list[str]) -> None:
    """Switch UI to new-customer mode and reset form fields."""
    st.session_state["_cust_mode"]     = "new"
    st.session_state["_cust_sel_id"]   = ""
    st.session_state["_cust_sync_key"] = "__new__"
    st.session_state["cust_name"]      = ""
    st.session_state["cust_gst"]       = ""
    st.session_state["cust_billing"]   = ""
    st.session_state["cust_city"]      = ""
    st.session_state["cust_state"]     = state_names[0] if state_names else ""


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
            "<div class='page-title'>Customers</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers: {exc}")
            return []

    customers    = fetch_customers()
    state_names  = load_state_names() or ["Maharashtra", "Tamil Nadu", "Karnataka"]
    customer_map = {c["id"]: c for c in customers if c.get("id")}

    # ── Header button (after state_names is available) ─────────────────────────
    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New Customer", use_container_width=True,
                     type="primary", key="hdr_new_cust"):
            _open_new_form(state_names)
            st.rerun()

    # ── Stats bar ──────────────────────────────────────────────────────────────
    n_customers = len(customers)
    n_contacts  = sum(len(_parse_contacts(c.get("contact_person"))) for c in customers)
    n_cities    = len({c.get("city")  for c in customers if c.get("city")})
    n_states    = len({c.get("state") for c in customers if c.get("state")})
    st.markdown(
        f"<div class='cust-stat-row'>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_customers}</span>"
        f"<span class='cust-stat-lbl'>Customers</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_contacts}</span>"
        f"<span class='cust-stat-lbl'>Contacts</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_cities}</span>"
        f"<span class='cust-stat-lbl'>Cities</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_states}</span>"
        f"<span class='cust-stat-lbl'>States</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_cust_mode" not in st.session_state:
        st.session_state["_cust_mode"]   = "none"
    if "_cust_sel_id" not in st.session_state:
        st.session_state["_cust_sel_id"] = ""

    mode        = st.session_state["_cust_mode"]          # "none" | "new" | "edit"
    selected_id = st.session_state["_cust_sel_id"]
    selected_customer = customer_map.get(selected_id) if selected_id else None

    # ── Sync form fields when selection or mode changes ────────────────────────
    sync_key = f"{mode}__{selected_id}"
    if st.session_state.get("_cust_sync_key") != sync_key:
        st.session_state["_cust_sync_key"] = sync_key
        c = selected_customer or {}
        st.session_state["cust_name"]    = c.get("customer_name", "")
        st.session_state["cust_gst"]     = c.get("gst_number", "")
        st.session_state["cust_billing"] = c.get("billing_address", "")
        st.session_state["cust_city"]    = c.get("city", "")
        raw_state = c.get("state", "")
        st.session_state["cust_state"]   = (
            raw_state if raw_state in state_names else (state_names[0] if state_names else "")
        )

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ──────────────────────────────────────────────────────────────────────────
    # LEFT — Customer directory
    # ──────────────────────────────────────────────────────────────────────────
    with left_col:
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search by name or city…",
            key="cust_search_q",
        )
        q = search_q.strip().lower()
        filtered_map = {
            cid: c for cid, c in customer_map.items()
            if not q
            or q in c.get("customer_name", "").lower()
            or q in c.get("city", "").lower()
        }

        count_txt = (
            f"{len(filtered_map)} of {n_customers}" if q
            else f"{n_customers} customers"
        )
        st.markdown(
            f"<p style='font-size:11px;color:#9ca3af;margin:2px 0 8px;'>{count_txt}</p>",
            unsafe_allow_html=True,
        )

        contact_counts = {
            c["id"]: len(_parse_contacts(c.get("contact_person")))
            for c in customers if c.get("id")
        }

        with st.container(height=530):
            if not filtered_map:
                st.markdown(
                    "<p style='color:#9ca3af;font-size:13px;text-align:center;"
                    "padding:40px 0;'>No matches found.</p>",
                    unsafe_allow_html=True,
                )
            for cid, c in filtered_map.items():
                is_sel    = (cid == selected_id and mode == "edit")
                name      = c.get("customer_name", "Unknown")
                city_val  = c.get("city", "")
                state_v   = c.get("state", "")
                code_val  = c.get("customer_code", "")
                n_con     = contact_counts.get(cid, 0)
                location  = ", ".join(filter(None, [city_val, state_v])) or "—"
                color     = _avatar_color(name)

                sel_border = "border-left:3px solid #E87722;" if is_sel else "border-left:3px solid transparent;"
                sel_bg     = "background:#fff7ed;" if is_sel else "background:#ffffff;"
                name_w     = "font-weight:700;" if is_sel else "font-weight:500;"
                code_badge = (
                    f"<span style='font-size:9px;font-weight:700;background:#f3f4f6;"
                    f"color:#6b7280;padding:2px 7px;border-radius:10px;"
                    f"white-space:nowrap;margin-left:auto;'>{code_val}</span>"
                    if code_val else ""
                )
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
                    f"{location}&nbsp;·&nbsp;"
                    f"{n_con} contact{'s' if n_con != 1 else ''}</div>"
                    f"</div>{code_badge}</div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Selected ✓" if is_sel else "Open",
                    key=f"csel_{cid}",
                    use_container_width=True,
                    help=name,
                ):
                    st.session_state["_cust_mode"]     = "edit"
                    st.session_state["_cust_sel_id"]   = cid
                    st.session_state["_cust_sync_key"] = None   # force sync
                    st.rerun()

    # ──────────────────────────────────────────────────────────────────────────
    # RIGHT — Detail / form panel
    # ──────────────────────────────────────────────────────────────────────────
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='cust-empty'>"
                "<div class='cust-empty-icon'>👥</div>"
                "<div class='cust-empty-title'>No customer selected</div>"
                "<p class='cust-empty-sub'>Pick a customer from the directory "
                "or click <strong>+ New Customer</strong> above to add one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT FORM ───────────────────────────────────────────────────
        else:
            # Header banner
            display_name = (
                st.session_state.get("cust_name")
                or (selected_customer.get("customer_name", "") if selected_customer else "")
                or "New Customer"
            )
            code_disp = selected_customer.get("customer_code", "") if selected_customer else ""
            col_val   = _avatar_color(display_name)
            badge     = (
                "<span class='badge-edit'>Editing</span>"
                if mode == "edit" else "<span class='badge-new'>New Customer</span>"
            )
            code_row = (
                f"<div class='cust-banner-code'>CODE: {code_disp}</div>"
                if code_disp else ""
            )
            st.markdown(
                f"<div class='cust-banner'>"
                f"<div class='cust-banner-avatar' style='background:{col_val};'>"
                f"{_initials(display_name)}</div>"
                f"<div style='flex:1;min-width:0;'>"
                f"<div class='cust-banner-name'>{display_name}</div>{code_row}</div>"
                f"{badge}</div>",
                unsafe_allow_html=True,
            )

            # Section 1 — Business Information
            with st.container(border=True):
                _section_hdr("Business Information")
                bi1, bi2 = st.columns([3, 2])
                with bi1:
                    customer_name = st.text_input(
                        "Customer Name *", key="cust_name",
                        placeholder="e.g. Acme Pvt Ltd",
                    )
                with bi2:
                    gst_number = st.text_input(
                        "GST Number", key="cust_gst",
                        placeholder="e.g. 27AAPFU0939F1ZV",
                    )

            # Section 2 — Address
            with st.container(border=True):
                _section_hdr("Address")
                billing_address = st.text_area(
                    "Billing Address", key="cust_billing",
                    placeholder="Street, Area, Landmark…", height=72,
                )
                a1, a2 = st.columns(2)
                with a1:
                    city = st.text_input(
                        "City", key="cust_city", placeholder="e.g. Mumbai"
                    )
                with a2:
                    state_val = st.selectbox(
                        "State", options=state_names, key="cust_state"
                    )

            # Section 3 — Contact Persons
            existing_contacts = _parse_contacts(
                selected_customer.get("contact_person") if selected_customer else None
            )
            with st.container(border=True):
                _section_hdr(
                    "Contact Persons",
                    note=f"{len(existing_contacts)} saved" if existing_contacts else "",
                )
                contacts_df = st.data_editor(
                    _contacts_to_df(existing_contacts),
                    column_config={
                        "name":        st.column_config.TextColumn("Name",        width="medium"),
                        "designation": st.column_config.TextColumn("Designation", width="medium"),
                        "email":       st.column_config.TextColumn("Email",       width="medium"),
                        "mobile":      st.column_config.TextColumn("Mobile",      width="medium"),
                        "remarks":     st.column_config.TextColumn("Remarks",     width="large"),
                    },
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key=f"contacts_editor_{selected_id or 'new'}",
                )

            # Action buttons
            sv1, sv2, sv3 = st.columns([4, 1, 1])
            with sv1:
                save_clicked = st.button(
                    "Update Customer" if mode == "edit" else "Create Customer",
                    type="primary",
                    use_container_width=True,
                    key="cust_save_btn",
                )
            with sv2:
                if st.button("Cancel", use_container_width=True, key="cust_cancel_btn"):
                    st.session_state["_cust_mode"]   = "none"
                    st.session_state["_cust_sel_id"] = ""
                    st.session_state["_cust_sync_key"] = None
                    st.rerun()
            with sv3:
                if st.button("Refresh", use_container_width=True, key="cust_refresh_btn"):
                    st.session_state["_cust_sync_key"] = None
                    st.rerun()

            # ── Save logic ─────────────────────────────────────────────────────
            if save_clicked:
                name_val = customer_name.strip()
                if not name_val:
                    st.error("Customer Name is required.")
                else:
                    contacts_list = _df_to_contacts(contacts_df)
                    first = contacts_list[0] if contacts_list else {}
                    payload = dict(
                        customer_name   = name_val,
                        contact_person  = json.dumps(contacts_list) if contacts_list else None,
                        mobile          = first.get("mobile") or None,
                        email           = first.get("email")  or None,
                        gst_number      = gst_number.strip() or None,
                        billing_address = billing_address.strip() or None,
                        city            = city.strip() or None,
                        state           = state_val or None,
                    )

                    # Keep st.rerun() OUTSIDE try/except —
                    # RerunException(Exception) would otherwise be swallowed.
                    _err        = None
                    _toast_msg  = None
                    _new_id     = None
                    try:
                        if mode == "edit" and selected_customer:
                            sb.update_customer(selected_id, payload)
                            _toast_msg = f"'{name_val}' updated successfully."
                        else:
                            created    = sb.insert_customer(payload)
                            _new_id    = created.get("id", "")
                            new_code   = created.get("customer_code") or _new_id
                            _toast_msg = f"Customer created — Code: {new_code}"
                    except Exception as exc:
                        _err = str(exc)

                    if _err:
                        st.error(f"Could not save customer: {_err}")
                    else:
                        if _new_id:
                            st.session_state["_cust_mode"]     = "edit"
                            st.session_state["_cust_sel_id"]   = _new_id
                            st.session_state["_cust_sync_key"] = None
                        st.toast(_toast_msg, icon="✅")
                        st.rerun()
