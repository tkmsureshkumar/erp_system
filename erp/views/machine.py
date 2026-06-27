"""
erp/views/machine.py
Machine management — modern enterprise UI.
Left:  searchable machine directory.
Right: multi-section form (Basic Details / Serial Numbers / Ownership / Compliance / Status).

Mode state  _mach_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from ..models import ConditionStatus, OperationalStatus
from ..supabase_client import SupabaseClient

OWNERSHIP_OPTIONS = ["Owned", "Leased"]


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


def _section(title: str) -> None:
    st.markdown(
        f"<div style='margin:18px 0 8px;border-top:1px solid #e5e7eb;padding-top:12px;'>"
        f"<span style='font-size:10px;font-weight:700;letter-spacing:.12em;"
        f"color:#E87722;text-transform:uppercase;'>{title}</span></div>",
        unsafe_allow_html=True,
    )


def _avatar_color(name: str) -> str:
    palette = ["#0ea5e9", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444",
               "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16"]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


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
            "<div class='page-title'>Machines</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed. Check your Supabase settings.")
        st.write(str(exc))
        return

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception as exc:
            st.error(f"Failed to load machines from Supabase: {exc}")
            return []

    def fetch_assets() -> list[dict]:
        try:
            return sb.list_assets()
        except Exception as exc:
            st.warning(f"Could not load asset types: {exc}")
            return []

    machines = fetch_machines()
    assets   = fetch_assets()
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

    # ── Stats bar ──────────────────────────────────────────────────────────────
    n_total     = len(machines)
    n_available = sum(1 for m in machines if m.get("operational_status") == "Available")
    n_owned     = sum(1 for m in machines if m.get("ownership") == "Owned")
    st.markdown(
        f"<div class='cust-stat-row'>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_total}</span>"
        f"<span class='cust-stat-lbl'>Total Machines</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_available}</span>"
        f"<span class='cust-stat-lbl'>Available</span></div>"
        f"<div class='cust-stat-pill'><span class='cust-stat-val'>{n_owned}</span>"
        f"<span class='cust-stat-lbl'>Owned</span></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_mach_mode" not in st.session_state:
        st.session_state["_mach_mode"] = "none"
    if "_mach_sel_id" not in st.session_state:
        st.session_state["_mach_sel_id"] = ""

    mode               = st.session_state["_mach_mode"]       # "none" | "new" | "edit"
    selected_machine_id = st.session_state["_mach_sel_id"]
    selected_machine    = machine_map.get(selected_machine_id) if selected_machine_id else None

    # ── Sync form fields when selection or mode changes ────────────────────────
    sync_key = f"{mode}__{selected_machine_id}"
    if st.session_state.get("_mach_sync_key") != sync_key:
        st.session_state["_mach_sync_key"] = sync_key
        m = selected_machine or {}

        current_type = m.get("machine_type", "")
        st.session_state["m_machine_type"]               = current_type if current_type in asset_type_options else ""
        st.session_state["m_make"]                       = m.get("make", "")
        st.session_state["m_model"]                      = m.get("model", "")
        st.session_state["m_serial_number"]              = m.get("serial_number", "")
        st.session_state["m_original_serial_number"]     = m.get("original_serial_number", "")
        st.session_state["m_operational_serial_number"]  = m.get("operational_serial_number", "")
        st.session_state["m_original_yom"]               = m.get("original_yom") or 0
        st.session_state["m_operational_yom"]            = str(m.get("operational_yom", "") or "")
        st.session_state["m_working_capacity"]           = str(m.get("working_capacity", "") or "")
        st.session_state["m_current_location"]           = m.get("current_location", "")
        st.session_state["m_purchase_date"]              = _parse_date(m.get("purchase_date"))
        st.session_state["m_purchase_cost"]              = float(m.get("purchase_cost") or 0.0)
        st.session_state["m_ownership"]                  = m.get("ownership", OWNERSHIP_OPTIONS[0])
        st.session_state["m_tpi_expiry"]                 = _parse_date(m.get("TPI_expiry"))
        st.session_state["m_puc_expiry"]                 = _parse_date(m.get("PUC_expiry"))
        st.session_state["m_form11_expiry"]              = _parse_date(m.get("Form_11_expiry"))
        st.session_state["m_insurance_expiry"]           = _parse_date(m.get("insurance_expiry"))
        st.session_state["m_operational_status"]         = m.get("operational_status", OperationalStatus.AVAILABLE.value)
        st.session_state["m_condition_status"]           = m.get("condition_status", ConditionStatus.RUNNING.value)

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ──────────────────────────────────────────────────────────────────────────
    # LEFT — Machine directory
    # ──────────────────────────────────────────────────────────────────────────
    with left_col:
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search by type or make…",
            key="mach_search_q",
        )
        q = search_q.strip().lower()
        filtered_map = {
            mid: m for mid, m in machine_map.items()
            if not q
            or q in m.get("machine_type", "").lower()
            or q in m.get("make", "").lower()
        }

        count_txt = (
            f"{len(filtered_map)} of {n_total}" if q
            else f"{n_total} machine{'s' if n_total != 1 else ''}"
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
            for mid, m in filtered_map.items():
                is_sel          = (mid == selected_machine_id and mode == "edit")
                machine_type_v  = m.get("machine_type", "Unknown")
                make_v          = m.get("make", "")
                op_status_v     = m.get("operational_status", "")
                asset_code_v    = m.get("asset_code", "")
                color           = _avatar_color(machine_type_v)
                initials_v      = machine_type_v[:2].upper() if machine_type_v else "??"

                sel_border = "border-left:3px solid #E87722;" if is_sel else "border-left:3px solid transparent;"
                sel_bg     = "background:#fff7ed;" if is_sel else "background:#ffffff;"
                code_color = "color:#E87722;font-weight:800;" if is_sel else "color:#E87722;font-weight:700;"
                line1      = asset_code_v or machine_type_v
                line2      = " · ".join(filter(None, [make_v, op_status_v])) or "—"

                st.markdown(
                    f"<div style='{sel_bg}{sel_border}border:1px solid #e5e7eb;"
                    f"padding:9px 12px;display:flex;align-items:center;gap:10px;"
                    f"pointer-events:none;'>"
                    f"<div style='width:34px;height:34px;border-radius:50%;"
                    f"background:{color};display:flex;align-items:center;"
                    f"justify-content:center;font-size:12px;font-weight:800;"
                    f"color:#fff;flex-shrink:0;'>{initials_v}</div>"
                    f"<div style='min-width:0;flex:1;'>"
                    f"<div style='font-size:13px;{code_color}"
                    f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{line1}</div>"
                    f"<div style='font-size:11px;color:#6b7280;margin-top:1px;'>{line2}</div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Selected ✓" if is_sel else "Open",
                    key=f"msel_{mid}",
                    use_container_width=True,
                    help=machine_type_v,
                ):
                    st.session_state["_mach_mode"]     = "edit"
                    st.session_state["_mach_sel_id"]   = mid
                    st.session_state["_mach_sync_key"] = None   # force sync
                    st.rerun()

    # ──────────────────────────────────────────────────────────────────────────
    # RIGHT — Detail / form panel
    # ──────────────────────────────────────────────────────────────────────────
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='cust-empty'>"
                "<div class='cust-empty-icon'>🏗️</div>"
                "<div class='cust-empty-title'>No machine selected</div>"
                "<p class='cust-empty-sub'>Pick a machine from the directory "
                "or click <strong>+ New Machine</strong> above to add one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT FORM ───────────────────────────────────────────────────
        else:
            # Header banner
            asset_code_disp = (
                selected_machine.get("asset_code", "") if selected_machine else ""
            )
            machine_type_disp = (
                st.session_state.get("m_machine_type")
                or (selected_machine.get("machine_type", "") if selected_machine else "")
                or "New Machine"
            )
            col_val = _avatar_color(machine_type_disp)
            initials_banner = machine_type_disp[:2].upper() if machine_type_disp else "??"
            badge = (
                "<span class='badge-edit'>Editing</span>"
                if mode == "edit" else "<span class='badge-new'>New</span>"
            )
            code_row = (
                f"<div class='cust-banner-code'>ASSET: {asset_code_disp}</div>"
                if asset_code_disp else ""
            )
            st.markdown(
                f"<div class='cust-banner'>"
                f"<div class='cust-banner-avatar' style='background:{col_val};'>"
                f"{initials_banner}</div>"
                f"<div style='flex:1;min-width:0;'>"
                f"<div class='cust-banner-name'>"
                f"{asset_code_disp or machine_type_disp}</div>"
                f"<div class='cust-banner-code'>{machine_type_disp}</div>"
                f"{code_row}</div>"
                f"{badge}</div>",
                unsafe_allow_html=True,
            )

            # ── Machine Type DDL — outside the form so preview updates immediately ──
            machine_type = st.selectbox(
                "Machine Type *",
                options=asset_type_options,
                format_func=lambda v: "Select machine type" if not v
                    else (f"{v}  ({asset_prefix_map[v]})" if asset_prefix_map.get(v) else v),
                key="m_machine_type",
            )

            # ── Asset Code preview ─────────────────────────────────────────────
            if selected_machine:
                existing_code = selected_machine.get("asset_code", "—")
                st.markdown(
                    f"<div style='display:inline-flex;align-items:center;gap:10px;"
                    f"background:#f8fafc;border:1px solid #e2e8f0;"
                    f"border-radius:6px;padding:8px 16px;margin-bottom:8px;'>"
                    f"<span style='font-size:11px;font-weight:700;letter-spacing:.1em;"
                    f"color:#6b7280;text-transform:uppercase;'>Asset Code</span>"
                    f"<span style='font-size:18px;font-weight:800;color:#E87722;"
                    f"letter-spacing:.05em;'>{existing_code}</span></div>",
                    unsafe_allow_html=True,
                )
            elif machine_type:
                prefix  = asset_prefix_map.get(machine_type, machine_type[:3]).strip().upper()
                preview = _generate_asset_code(prefix, machines)
                st.markdown(
                    f"<div style='display:inline-flex;align-items:center;gap:10px;"
                    f"background:#fff7ed;border:1px solid #fed7aa;"
                    f"border-radius:6px;padding:8px 16px;margin-bottom:8px;'>"
                    f"<span style='font-size:11px;font-weight:700;letter-spacing:.1em;"
                    f"color:#9a3412;text-transform:uppercase;'>Asset Code (auto)</span>"
                    f"<span style='font-size:18px;font-weight:800;color:#E87722;"
                    f"letter-spacing:.05em;'>{preview}</span></div>",
                    unsafe_allow_html=True,
                )

            # ── Form ───────────────────────────────────────────────────────────
            with st.form("machine_form"):

                # ── Basic Details ──────────────────────────────────────────────
                _section("Basic Details")
                b1, b2 = st.columns(2)
                with b1:
                    make             = st.text_input("Make",  key="m_make")
                    original_yom     = st.number_input(
                        "Original Year of Manufacture",
                        step=1,
                        key="m_original_yom",
                    )
                    working_capacity = st.text_input(
                        "Working Capacity", key="m_working_capacity",
                        placeholder="e.g. 12m / 500kg",
                    )
                    purchase_cost    = st.number_input(
                        "Purchase Cost",
                        step=0.01,
                        key="m_purchase_cost",
                    )
                with b2:
                    model            = st.text_input("Model", key="m_model")
                    operational_yom  = st.text_input(
                        "Operational Year of Manufacture",
                        key="m_operational_yom", placeholder="e.g. 2020",
                    )
                    purchase_date    = st.date_input("Purchase Date", key="m_purchase_date")
                    current_location = st.text_input(
                        "Current Location", key="m_current_location",
                        placeholder="e.g. Mumbai Yard",
                    )

                # ── Serial Numbers ─────────────────────────────────────────────
                _section("Serial Numbers")
                s1, s2, s3 = st.columns(3)
                with s1:
                    serial_number = st.text_input(
                        "Serial Number", key="m_serial_number",
                    )
                with s2:
                    original_serial_number = st.text_input(
                        "Original Serial Number", key="m_original_serial_number",
                    )
                with s3:
                    operational_serial_number = st.text_input(
                        "Operational Serial Number", key="m_operational_serial_number",
                    )

                # ── Ownership ──────────────────────────────────────────────────
                _section("Ownership")
                o1, _ = st.columns([1, 3])
                with o1:
                    ownership = st.selectbox(
                        "Ownership *",
                        options=OWNERSHIP_OPTIONS,
                        key="m_ownership",
                    )

                # ── Compliance & Expiry Dates ──────────────────────────────────
                _section("Compliance & Expiry Dates")
                e1, e2, e3, e4 = st.columns(4)
                with e1:
                    tpi_expiry = st.date_input("TPI Expiry",      key="m_tpi_expiry")
                with e2:
                    puc_expiry = st.date_input("PUC Expiry",      key="m_puc_expiry")
                with e3:
                    form11_expiry = st.date_input("Form 11 Expiry", key="m_form11_expiry")
                with e4:
                    insurance_expiry = st.date_input("Insurance Expiry", key="m_insurance_expiry")

                # ── Status ─────────────────────────────────────────────────────
                _section("Status")
                st1, st2 = st.columns(2)
                with st1:
                    operational_status = st.selectbox(
                        "Operational Status *",
                        options=operational_status_values,
                        key="m_operational_status",
                    )
                with st2:
                    condition_status = st.selectbox(
                        "Condition Status *",
                        options=condition_status_values,
                        key="m_condition_status",
                    )

                # ── Action row ─────────────────────────────────────────────────
                act1, act2, act3 = st.columns([4, 1, 1])
                with act1:
                    submitted = st.form_submit_button(
                        "Update Machine" if mode == "edit" else "Create Machine",
                        type="primary",
                        use_container_width=True,
                    )
                with act2:
                    cancel_clicked = st.form_submit_button(
                        "Cancel",
                        use_container_width=True,
                    )
                with act3:
                    refresh_clicked = st.form_submit_button(
                        "Refresh",
                        use_container_width=True,
                    )

                if cancel_clicked:
                    st.session_state["_mach_mode"]     = "none"
                    st.session_state["_mach_sel_id"]   = ""
                    st.session_state["_mach_sync_key"] = None
                    st.rerun()

                if refresh_clicked:
                    st.session_state["_mach_sync_key"] = None
                    st.rerun()

                if submitted:
                    if not machine_type:
                        st.error("Machine Type is required.")
                    elif not operational_status:
                        st.error("Operational Status is required.")
                    elif not condition_status:
                        st.error("Condition Status is required.")
                    else:
                        payload: dict = dict(
                            machine_type=machine_type,
                            make=make.strip() or None,
                            model=model.strip() or None,
                            serial_number=serial_number.strip() or None,
                            original_serial_number=original_serial_number.strip() or None,
                            operational_serial_number=operational_serial_number.strip() or None,
                            original_yom=int(original_yom) if original_yom else None,
                            operational_yom=operational_yom.strip() or None,
                            working_capacity=working_capacity.strip() or None,
                            current_location=current_location.strip() or None,
                            purchase_date=purchase_date.isoformat() if purchase_date else None,
                            purchase_cost=float(purchase_cost) if purchase_cost else None,
                            ownership=ownership,
                            TPI_expiry=tpi_expiry.isoformat() if tpi_expiry else None,
                            PUC_expiry=puc_expiry.isoformat() if puc_expiry else None,
                            Form_11_expiry=form11_expiry.isoformat() if form11_expiry else None,
                            insurance_expiry=insurance_expiry.isoformat() if insurance_expiry else None,
                            operational_status=operational_status,
                            condition_status=condition_status,
                        )

                        if mode == "new":
                            prefix = asset_prefix_map.get(machine_type, machine_type[:3]).strip().upper()
                            payload["asset_code"] = _generate_asset_code(prefix, machines)

                        _err       = None
                        _toast_msg = None
                        _new_id    = None
                        try:
                            if mode == "edit" and selected_machine:
                                sb.update_machine(selected_machine_id, payload)
                                _toast_msg = f"Machine updated — {asset_code_disp or machine_type}"
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
                                st.error("Serial Number already exists. Each machine must have a unique serial number.")
                            elif "23505" in msg and "asset_code" in msg:
                                st.error("Asset Code conflict detected — please refresh and try again.")
                            elif "23505" in msg:
                                st.error("A duplicate value was detected. Please check your input for fields that must be unique.")
                            else:
                                st.error(f"Could not save machine: {_err}")
                        else:
                            if _new_id:
                                st.session_state["_mach_mode"]     = "edit"
                                st.session_state["_mach_sel_id"]   = _new_id
                                st.session_state["_mach_sync_key"] = None
                            st.toast(_toast_msg, icon="✅")
                            st.rerun()
