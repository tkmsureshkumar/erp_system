"""
erp/views/deployment.py
Deployment tracking — links a Work Order to logistics: machine dates and truck driver.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import streamlit as st

from ..supabase_client import SupabaseClient
from ..models import DeploymentStatus

_DEP_STATUS_OPTS = [s.value for s in DeploymentStatus]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_date(value) -> date | None:
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


_STATUS_COLOURS: dict[str, tuple[str, str]] = {
    "Available":    ("#dcfce7", "#166534"),
    "On Rent":      ("#dbeafe", "#1e40af"),
    "Reserved":     ("#fef3c7", "#92400e"),
    "Mobilizing":   ("#ffedd5", "#c2410c"),
    "Demobilizing": ("#ede9fe", "#6d28d9"),
    "Breakdown":    ("#fee2e2", "#991b1b"),
    "Sold":         ("#f3f4f6", "#6b7280"),
}

def _status_badge(status: str) -> str:
    bg, fg = _STATUS_COLOURS.get(status, ("#f3f4f6", "#6b7280"))
    return (
        f"<span style='display:inline-block;padding:2px 9px;border-radius:20px;"
        f"font-size:10px;font-weight:700;letter-spacing:.04em;"
        f"background:{bg};color:{fg};white-space:nowrap;'>{status or '—'}</span>"
    )


def _info_card(label: str, value: str) -> str:
    return (
        f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;"
        f"padding:12px 16px;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.1em;color:#9ca3af;"
        f"text-transform:uppercase;margin-bottom:4px;'>{label}</div>"
        f"<div style='font-size:15px;font-weight:600;color:#111827;'>{value}</div>"
        f"</div>"
    )


def _section_header(label: str, subtitle: str = "") -> None:
    sub = (
        f"<div style='font-size:12px;color:#6b7280;margin-top:4px;font-weight:400;"
        f"letter-spacing:0;text-transform:none;'>{subtitle}</div>"
        if subtitle else ""
    )
    st.markdown(
        f"<div style='margin-bottom:14px;border-left:3px solid #E87722;padding:6px 0 6px 14px;'>"
        f"<div style='font-size:11px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        f"text-transform:uppercase;'>{label}</div>"
        f"{sub}</div>",
        unsafe_allow_html=True,
    )


# ── View ───────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Deployment</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed.")
        st.write(str(exc))
        return

    # ── Fetch ──────────────────────────────────────────────────────────────────
    try:
        work_orders = sb.list_work_orders()
    except Exception as exc:
        st.error(f"Failed to load work orders: {exc}")
        return

    try:
        customers = sb.list_customers()
    except Exception:
        customers = []

    try:
        sites = sb.list_sites()
    except Exception:
        sites = []

    try:
        machines = sb.list_machines()
    except Exception:
        machines = []

    customer_map: dict[str, dict] = {c["id"]: c for c in customers if c.get("id")}
    site_map: dict[str, dict]     = {s["id"]: s for s in sites     if s.get("id")}
    wo_map: dict[str, dict]       = {w["id"]: w for w in work_orders if w.get("id")}
    machine_status_map: dict[str, str] = {
        m["id"]: m.get("operational_status", "") for m in machines if m.get("id")
    }
    machine_full_map: dict[str, dict] = {
        m["id"]: m for m in machines if m.get("id")
    }

    # ── Work Order selector ────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:11px;font-weight:700;color:#374151;"
        "letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px;'>"
        "Select Work Order</div>",
        unsafe_allow_html=True,
    )
    selected_wo_id: str = st.selectbox(
        "Select Work Order",
        options=[""] + list(wo_map),
        format_func=lambda wid: "— Choose a work order —" if not wid
            else (
                f"{wo_map[wid].get('wo_number', 'Unknown')}  ·  "
                f"{customer_map.get(wo_map[wid].get('customer_id', ''), {}).get('customer_name', '')}"
            ),
        key="dep_selected_wo_id",
        label_visibility="collapsed",
    )

    if not selected_wo_id:
        st.markdown(
            "<div style='margin-top:32px;padding:28px 24px;background:#f8fafc;"
            "border:1px dashed #d1d5db;border-radius:10px;text-align:center;'>"
            "<div style='font-size:28px;margin-bottom:8px;'>📋</div>"
            "<div style='font-size:14px;font-weight:600;color:#374151;'>No work order selected</div>"
            "<div style='font-size:12px;color:#9ca3af;margin-top:4px;'>"
            "Pick a work order above to manage its deployment details.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    selected_wo = wo_map[selected_wo_id]
    dep_key     = selected_wo_id

    # Fetch the deployment record for this WO directly (avoids silent failures from bulk fetch)
    try:
        existing_dep: dict = sb.get_deployment_by_wo(selected_wo_id)
    except Exception:
        existing_dep = {}

    _dep_exists = bool(existing_dep.get("id"))

    # Status badge
    if _dep_exists:
        st.markdown(
            "<div style='display:inline-flex;align-items:center;gap:6px;margin:6px 0 18px;"
            "background:#dcfce7;border:1px solid #bbf7d0;border-radius:20px;"
            "padding:4px 12px;font-size:11px;font-weight:600;color:#166534;'>"
            "&#10003; Deployment record exists — editing</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='display:inline-flex;align-items:center;gap:6px;margin:6px 0 18px;"
            "background:#fef3c7;border:1px solid #fde68a;border-radius:20px;"
            "padding:4px 12px;font-size:11px;font-weight:600;color:#92400e;'>"
            "&#9711; New deployment — not yet saved</div>",
            unsafe_allow_html=True,
        )

    # Reset session state when the selected WO changes
    if st.session_state.get("_dep_editing_wo_id") != selected_wo_id:
        st.session_state["_dep_editing_wo_id"] = selected_wo_id

        ed = existing_dep
        st.session_state[f"dep_{dep_key}_dep_status"]     = ed.get("deployment_status") or DeploymentStatus.ACTIVE.value
        st.session_state[f"dep_{dep_key}_lorry_reg"]      = ed.get("lorry_registration_number") or ""
        st.session_state[f"dep_{dep_key}_driver_name"]    = ed.get("lorry_driver_name")          or ""
        st.session_state[f"dep_{dep_key}_driver_mobile"]  = ed.get("driver_mobile_number")       or ""
        st.session_state[f"dep_{dep_key}_tracking_notes"] = ed.get("tracking_notes")             or ""

        existing_mc_dates: dict[str, dict] = {}
        raw_mcd = ed.get("machine_deployments")
        if raw_mcd:
            try:
                mcd_list = json.loads(raw_mcd) if isinstance(raw_mcd, str) else raw_mcd
                for entry in (mcd_list if isinstance(mcd_list, list) else []):
                    key_id = entry.get("machine_id") or entry.get("machine_label")
                    if key_id:
                        existing_mc_dates[key_id] = entry
            except Exception:
                pass

        raw_mc = selected_wo.get("machine_config")
        mc_rows_init: list[dict] = []
        if raw_mc:
            try:
                records = json.loads(raw_mc) if isinstance(raw_mc, str) else raw_mc
                mc_rows_init = [r for r in (records if isinstance(records, list) else []) if r.get("machine_label")]
            except Exception:
                pass

        for mr in mc_rows_init:
            mid   = mr.get("machine_id") or mr.get("machine_label", "")
            saved = existing_mc_dates.get(mid) or existing_mc_dates.get(mr.get("machine_label", "")) or {}
            _raw_dtype = saved.get("deployment_type") or "Mob"
            _DTYPE_NORM_SEED = {"Mobilisation": "Mob", "Demobilisation": "Demob"}
            st.session_state[f"dep_{dep_key}_dtype_{mid}"] = _DTYPE_NORM_SEED.get(_raw_dtype, _raw_dtype) if _DTYPE_NORM_SEED.get(_raw_dtype, _raw_dtype) in ["Mob", "Demob", "Other"] else "Mob"
            st.session_state[f"dep_{dep_key}_location_{mid}"] = saved.get("machine_current_location") or ""
            st.session_state[f"dep_{dep_key}_ts_{mid}"]       = _parse_date(saved.get("transaction_start_date"))
            st.session_state[f"dep_{dep_key}_sr_{mid}"]       = _parse_date(saved.get("site_reached_date"))
            st.session_state[f"dep_{dep_key}_bs_{mid}"]       = _parse_date(saved.get("billing_start_date"))

    # ── Derive machine list ────────────────────────────────────────────────────
    raw_mc = selected_wo.get("machine_config")
    mc_rows: list[dict] = []
    if raw_mc:
        try:
            records = json.loads(raw_mc) if isinstance(raw_mc, str) else raw_mc
            mc_rows = [r for r in (records if isinstance(records, list) else []) if r.get("machine_label")]
        except Exception:
            mc_rows = []

    # ── Section A — Work Order Details ────────────────────────────────────────
    _section_header("A — Work Order Details", "Read-only reference fields from the selected work order")

    customer_name = customer_map.get(selected_wo.get("customer_id", ""), {}).get("customer_name") or "—"
    site_name     = site_map.get(selected_wo.get("site_id", ""), {}).get("site_name") or "—"
    client_wo_num = selected_wo.get("client_work_ordernumber") or "—"
    wo_number     = selected_wo.get("wo_number") or "—"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_info_card("WO Number", wo_number), unsafe_allow_html=True)
    with c2:
        st.markdown(_info_card("Customer", customer_name), unsafe_allow_html=True)
    with c3:
        st.markdown(_info_card("Site", site_name), unsafe_allow_html=True)
    with c4:
        st.markdown(_info_card("Client WO Number", client_wo_num), unsafe_allow_html=True)

    # ── Machine tags ──────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.1em;color:#6b7280;"
        "text-transform:uppercase;margin-bottom:8px;'>Machines on this Work Order</div>",
        unsafe_allow_html=True,
    )
    if mc_rows:
        tags_html = "".join(
            f"<span style='display:inline-flex;align-items:center;gap:6px;"
            f"background:#fff;border:1px solid #e2e8f0;border-radius:6px;"
            f"padding:6px 12px;font-size:12px;font-weight:600;color:#111827;"
            f"margin:0 6px 6px 0;'>"
            f"<span style='width:7px;height:7px;border-radius:50%;background:#E87722;"
            f"display:inline-block;flex-shrink:0;'></span>"
            f"{mr.get('machine_label', '—')}"
            + (
                f"<span style='font-weight:400;color:#9ca3af;font-size:11px;'>"
                f"&nbsp;{mr.get('make','')} {mr.get('model','')}</span>".strip()
                if mr.get("make") or mr.get("model") else ""
            )
            + _status_badge(machine_status_map.get(mr.get("machine_id", ""), ""))
            + "</span>"
            for mr in mc_rows
        )
        st.markdown(
            f"<div style='display:flex;flex-wrap:wrap;padding:10px 12px;"
            f"background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'>"
            f"{tags_html}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='padding:14px 16px;background:#fff7ed;border:1px solid #fed7aa;"
            "border-radius:8px;font-size:13px;color:#92400e;'>"
            "&#9888; No machines configured on this work order. "
            "Add machines via the Work Orders page first.</div>",
            unsafe_allow_html=True,
        )

    # ── Machine selector + detail card ───────────────────────────────────────
    if mc_rows:
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
        machine_labels = [mr.get("machine_label", f"Machine {i+1}") for i, mr in enumerate(mc_rows)]

        sel_machine_label = st.selectbox(
            "Select Machine",
            options=machine_labels,
            key=f"dep_machine_sel_{selected_wo_id}",
        )

        sel_mr = next(
            (mr for mr in mc_rows if mr.get("machine_label") == sel_machine_label),
            mc_rows[0],
        )

        op_status   = machine_status_map.get(sel_mr.get("machine_id", ""), "")
        mach_master = machine_full_map.get(sel_mr.get("machine_id", ""), {})
        make  = sel_mr.get("make")  or mach_master.get("make",  "")
        model = sel_mr.get("model") or mach_master.get("model", "")
        make_model = " · ".join(filter(None, [make, model])) or "—"

        rental = sel_mr.get("rental_per_month")
        mob    = sel_mr.get("mobilization_cost")
        demob  = sel_mr.get("demobilization_cost")
        cycle_period = (
            f"{sel_mr.get('billing_cycle_start_date', '—')}  →  "
            f"{sel_mr.get('billing_cycle_end_date', '—')}"
        )
        shift_hr  = sel_mr.get("machine_shift_hour")
        no_days   = sel_mr.get("no_of_days")

        detail_fields = [
            ("Make / Model",       make_model),
            ("Billing Type",       sel_mr.get("billing_type")  or "—"),
            ("Billing Cycle",      sel_mr.get("billing_cycle") or "—"),
            ("Rental / Month",     f"{float(rental):,.0f}" if rental else "—"),
            ("Cycle Period",       cycle_period),
            ("Shift Hour",         f"{shift_hr} hr" if shift_hr else "—"),
            ("No of Days",         str(no_days) if no_days else "—"),
            ("Mobilisation Cost",  f"{float(mob):,.0f}"  if mob  else "—"),
            ("Demobilisation Cost",f"{float(demob):,.0f}" if demob else "—"),
        ]

        st.markdown(
            "<div style='background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;"
            "padding:16px 20px 8px;margin-top:8px;'>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:14px;'>"
            f"<div style='font-size:17px;font-weight:800;color:#111827;'>{sel_machine_label}</div>"
            f"{_status_badge(op_status)}"
            f"</div>",
            unsafe_allow_html=True,
        )

        cols = st.columns(4)
        for i, (lbl, val) in enumerate(detail_fields):
            with cols[i % 4]:
                st.markdown(_info_card(lbl, val), unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Section B — Machine Deployment ────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    _section_header(
        "B — Machine Deployment",
        "Set the deployment type and dates for each machine",
    )

    _DEPLOY_TYPES = ["Mob", "Demob", "Other"]

    if mc_rows:
        _section_b_machines = [sel_mr] if sel_mr else mc_rows
        for idx, mr in enumerate(_section_b_machines):
            mlabel    = mr.get("machine_label", "")
            mid       = mr.get("machine_id") or mlabel
            op_status = machine_status_map.get(mr.get("machine_id", ""), "")
            make_model = " · ".join(filter(None, [mr.get("make", ""), mr.get("model", "")])).strip()

            st.markdown(
                f"<div style='background:{'#ffffff' if idx % 2 == 0 else '#fafafa'};"
                f"border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px 4px;"
                f"margin-bottom:10px;'>",
                unsafe_allow_html=True,
            )

            # Normalize stale dtype values from old option labels
            _dtype_key = f"dep_{dep_key}_dtype_{mid}"
            _DTYPE_NORM = {"Mobilisation": "Mob", "Demobilisation": "Demob"}
            if st.session_state.get(_dtype_key) not in _DEPLOY_TYPES:
                st.session_state[_dtype_key] = _DTYPE_NORM.get(
                    st.session_state.get(_dtype_key, ""), "Mob"
                )

            # Row 1: machine name | status | Deployment Type
            r1c1, r1c2, r1c3 = st.columns([2, 1, 2])
            with r1c1:
                st.markdown(
                    f"<div style='padding:6px 0 2px;'>"
                    f"<div style='font-size:14px;font-weight:700;color:#111827;'>{mlabel}</div>"
                    + (f"<div style='font-size:11px;color:#9ca3af;'>{make_model}</div>" if make_model else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
            with r1c2:
                st.markdown(
                    f"<div style='padding:10px 0 2px;'>{_status_badge(op_status)}</div>",
                    unsafe_allow_html=True,
                )
            with r1c3:
                dtype = st.selectbox(
                    "Deployment Type",
                    options=_DEPLOY_TYPES,
                    key=f"dep_{dep_key}_dtype_{mid}",
                )

            # Row 2: conditional fields based on Deployment Type
            if dtype == "Mob":
                # Default Loading Date to today when Reserved and not yet set
                ts_key_mob = f"dep_{dep_key}_ts_{mid}"
                if op_status == "Reserved" and not isinstance(
                    st.session_state.get(ts_key_mob), date
                ):
                    st.session_state[ts_key_mob] = date.today()

                # Read Site Reach Date from session state to decide if Billing Start Date unlocks
                sr_filled = isinstance(
                    st.session_state.get(f"dep_{dep_key}_sr_{mid}"), date
                )

                loading_disabled      = op_status not in ("Reserved", "Mobilizing")
                site_reach_disabled   = op_status != "Mobilizing"
                billing_disabled      = not (op_status == "Mobilizing" and sr_filled)

                r2c1, r2c2, r2c3, r2c4 = st.columns(4)
                with r2c1:
                    st.text_input(
                        "Machine Current Location",
                        placeholder="e.g. Chennai Yard",
                        key=f"dep_{dep_key}_location_{mid}",
                    )
                with r2c2:
                    st.date_input(
                        "Loading Date",
                        key=f"dep_{dep_key}_ts_{mid}",
                        disabled=loading_disabled,
                    )
                with r2c3:
                    st.date_input(
                        "Site Reach Date",
                        key=f"dep_{dep_key}_sr_{mid}",
                        disabled=site_reach_disabled,
                    )
                with r2c4:
                    st.date_input(
                        "Billing Start Date",
                        key=f"dep_{dep_key}_bs_{mid}",
                        disabled=billing_disabled,
                    )
            elif dtype == "Demob":
                r2c1, r2c2, r2c3 = st.columns(3)
                with r2c1:
                    st.text_input(
                        "Machine Current Location",
                        placeholder="e.g. Chennai Yard",
                        key=f"dep_{dep_key}_location_{mid}",
                    )
                with r2c2:
                    st.date_input("Loading Date", key=f"dep_{dep_key}_ts_{mid}")
                with r2c3:
                    st.date_input("Site Reach Date", key=f"dep_{dep_key}_sr_{mid}")
            else:
                r2c1, r2c2 = st.columns(2)
                with r2c1:
                    st.date_input("Transaction Start Date", key=f"dep_{dep_key}_ts_{mid}")
                with r2c2:
                    st.date_input("Site Reached Date", key=f"dep_{dep_key}_sr_{mid}")

            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='padding:20px 16px;background:#f8fafc;border:1px solid #e2e8f0;"
            "border-radius:8px;text-align:center;font-size:13px;color:#9ca3af;'>"
            "No machines to configure.</div>",
            unsafe_allow_html=True,
        )

    # ── Section C — Truck Driver Details ──────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    _section_header("C — Truck Driver Details", "Logistics and transport information for this deployment")

    st.markdown(
        "<div style='background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;"
        "padding:20px 20px 8px;'>",
        unsafe_allow_html=True,
    )

    ds1, _ = st.columns([1, 3])
    with ds1:
        st.selectbox(
            "Deployment Status",
            options=_DEP_STATUS_OPTS,
            key=f"dep_{dep_key}_dep_status",
        )

    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)

    td1, td2, td3 = st.columns(3)
    with td1:
        st.text_input(
            "Lorry Registration Number",
            placeholder="e.g. TN 01 AB 1234",
            key=f"dep_{dep_key}_lorry_reg",
        )
    with td2:
        st.text_input(
            "Lorry Driver Name",
            placeholder="Driver full name",
            key=f"dep_{dep_key}_driver_name",
        )
    with td3:
        st.text_input(
            "Driver Mobile Number",
            placeholder="+91 XXXXX XXXXX",
            key=f"dep_{dep_key}_driver_mobile",
        )

    st.text_area(
        "Notes for Tracking",
        placeholder="Route details, special instructions, or any other tracking notes…",
        height=110,
        key=f"dep_{dep_key}_tracking_notes",
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Save ──────────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    with st.form("dep_form"):
        submitted = st.form_submit_button(
            "✔  Update Deployment" if existing_dep else "Save Deployment",
            type="primary",
            use_container_width=False,
        )

        if submitted:
            mc_dates_payload = []
            for mr in mc_rows:
                mlabel   = mr.get("machine_label", "")
                mid      = mr.get("machine_id") or mlabel
                dtype    = st.session_state.get(f"dep_{dep_key}_dtype_{mid}") or "Mobilisation"
                ts       = st.session_state.get(f"dep_{dep_key}_ts_{mid}")
                sr       = st.session_state.get(f"dep_{dep_key}_sr_{mid}")
                location = st.session_state.get(f"dep_{dep_key}_location_{mid}") or None
                bs       = st.session_state.get(f"dep_{dep_key}_bs_{mid}")
                mc_dates_payload.append({
                    "machine_id":               mr.get("machine_id"),
                    "machine_label":            mlabel,
                    "deployment_type":          dtype,
                    "machine_current_location": location,
                    "transaction_start_date":   ts.isoformat() if isinstance(ts, date) else None,
                    "site_reached_date":        sr.isoformat() if isinstance(sr, date) else None,
                    "billing_start_date":       bs.isoformat() if isinstance(bs, date) else None,
                })

            payload = dict(
                work_order_id=selected_wo_id,
                customer_id=selected_wo.get("customer_id"),
                site_id=selected_wo.get("site_id"),
                deployment_date=date.today().isoformat(),
                client_work_ordernumber=selected_wo.get("client_work_ordernumber"),
                machine_deployments=json.dumps(mc_dates_payload),
                deployment_status=        st.session_state.get(f"dep_{dep_key}_dep_status")     or DeploymentStatus.ACTIVE.value,
                lorry_registration_number=st.session_state.get(f"dep_{dep_key}_lorry_reg")      or None,
                lorry_driver_name=        st.session_state.get(f"dep_{dep_key}_driver_name")    or None,
                driver_mobile_number=     st.session_state.get(f"dep_{dep_key}_driver_mobile")  or None,
                tracking_notes=           st.session_state.get(f"dep_{dep_key}_tracking_notes") or None,
            )

            try:
                if _dep_exists:
                    sb.update_deployment(existing_dep["id"], payload)
                    st.success("Deployment updated successfully.")
                else:
                    sb.insert_deployment(payload)
                    st.success("Deployment saved successfully.")

                # Update machine operational_status based on deployment type
                for mr in mc_rows:
                    machine_id_val = mr.get("machine_id")
                    mid_val        = machine_id_val or mr.get("machine_label", "")
                    dtype_val      = st.session_state.get(f"dep_{dep_key}_dtype_{mid_val}") or "Mob"
                    new_status     = None
                    if dtype_val == "Mob":
                        bs_val = st.session_state.get(f"dep_{dep_key}_bs_{mid_val}")
                        ts_val = st.session_state.get(f"dep_{dep_key}_ts_{mid_val}")
                        if isinstance(bs_val, date):
                            new_status = "On Rent"
                        elif isinstance(ts_val, date):
                            new_status = "Mobilizing"
                    elif dtype_val == "Demob":
                        sr_val = st.session_state.get(f"dep_{dep_key}_sr_{mid_val}")
                        ts_val = st.session_state.get(f"dep_{dep_key}_ts_{mid_val}")
                        if isinstance(sr_val, date):
                            new_status = "Available"
                        elif isinstance(ts_val, date):
                            new_status = "Demobilizing"
                    if new_status:
                        if not machine_id_val:
                            st.warning(
                                f"Machine '{mr.get('machine_label', '')}' has no ID linked — "
                                "operational status not updated. Re-save the Work Order to fix this."
                            )
                        else:
                            try:
                                sb.update_machine(machine_id_val, {"operational_status": new_status})
                            except Exception as me:
                                st.warning(f"Could not update machine status for '{mr.get('machine_label', '')}': {me}")

                # Force re-fetch on next render so fields reload from DB
                st.session_state.pop("_dep_editing_wo_id", None)
            except Exception as exc:
                st.error(f"Could not save deployment: {exc}")
