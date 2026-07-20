"""
erp/views/deployment.py
Deployment tracking — links a Work Order to logistics: machine dates and truck driver.

Auto-closes the work order when every machine on the WO returns to "Available".
Shows the entire form in read-only mode once the WO is Closed.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import streamlit as st

from ..supabase_client import SupabaseClient
from ..models import DeploymentStatus

# WO statuses that mean "no more editing"
_CLOSED_STATUSES = {"Closed", "Completed", "Cancelled"}


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


_STATUS_CLASS: dict[str, str] = {
    "Available":    "badge-available",
    "On Rent":      "badge-on-rent",
    "Reserved":     "badge-reserved",
    "Mobilizing":   "badge-mobilizing",
    "Demobilizing": "badge-demobilizing",
    "Breakdown":    "badge-breakdown",
    "Sold":         "badge-sold",
}


def _status_badge(status: str) -> str:
    cls = _STATUS_CLASS.get(status, "badge-draft")
    return f"<span class='badge {cls}'>{status or '—'}</span>"


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

    # ── Customer → Work Order selectors ───────────────────────────────────────
    _cids_with_wo = sorted(
        {wo.get("customer_id") for wo in work_orders if wo.get("customer_id")},
        key=lambda cid: customer_map.get(cid, {}).get("customer_name", ""),
    )
    selected_customer_id: str = st.selectbox(
        "Select Customer",
        options=[""] + _cids_with_wo,
        format_func=lambda cid: "Select a customer" if not cid
            else customer_map.get(cid, {}).get("customer_name", cid),
        key="dep_selected_customer_id",
    )

    if st.session_state.get("_dep_prev_customer") != selected_customer_id:
        st.session_state["_dep_prev_customer"] = selected_customer_id
        st.session_state["dep_selected_wo_id"] = ""

    if not selected_customer_id:
        st.markdown(
            "<div style='margin-top:32px;padding:28px 24px;background:#f8fafc;"
            "border:1px dashed #d1d5db;border-radius:10px;text-align:center;'>"
            "<div style='font-size:28px;margin-bottom:8px;'>📋</div>"
            "<div style='font-size:14px;font-weight:600;color:#374151;'>No customer selected</div>"
            "<div style='font-size:12px;color:#9ca3af;margin-top:4px;'>"
            "Pick a customer above to continue.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    _filtered_wo_ids = sorted(
        [wid for wid, wo in wo_map.items()
         if wo.get("customer_id") == selected_customer_id],
        key=lambda wid: wo_map[wid].get("wo_number", ""),
    )
    selected_wo_id: str = st.selectbox(
        "Select Work Order",
        options=[""] + _filtered_wo_ids,
        format_func=lambda wid: "— Choose a work order —" if not wid
            else wo_map[wid].get("wo_number", "Unknown"),
        key="dep_selected_wo_id",
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

    selected_wo  = wo_map[selected_wo_id]
    dep_key      = selected_wo_id
    _wo_status   = selected_wo.get("status", "")
    _wo_is_closed = _wo_status in _CLOSED_STATUSES

    # Fetch the deployment record for this WO
    try:
        existing_dep: dict = sb.get_deployment_by_wo(selected_wo_id)
    except Exception:
        existing_dep = {}

    _dep_exists = bool(existing_dep.get("id"))

    # ── Status banner ─────────────────────────────────────────────────────────
    if _wo_is_closed:
        st.markdown(
            f"<div style='display:inline-flex;align-items:center;gap:8px;margin:6px 0 18px;"
            f"background:#F1F5F9;border:1px solid #CBD5E1;border-radius:20px;"
            f"padding:6px 16px;font-size:12px;font-weight:700;color:#475569;'>"
            f"<span class='msr' style='font-size:15px;'>lock</span>"
            f"Work Order is {_wo_status} — view only</div>",
            unsafe_allow_html=True,
        )
    elif _dep_exists:
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

    # ── Session state init (editable mode only) ───────────────────────────────
    if not _wo_is_closed:
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
    raw_mc  = selected_wo.get("machine_config")
    mc_rows: list[dict] = []
    if raw_mc:
        try:
            records = json.loads(raw_mc) if isinstance(raw_mc, str) else raw_mc
            mc_rows = [r for r in (records if isinstance(records, list) else []) if r.get("machine_label")]
        except Exception:
            mc_rows = []

    # ── Location filter: only show machines whose current_site_id matches the WO site_id ──
    _wo_site     = site_map.get(selected_wo.get("site_id", ""), {})
    _wo_site_id  = selected_wo.get("site_id", "")

    def _location_matches_site(machine_id: str) -> bool:
        m = machine_full_map.get(machine_id, {})
        machine_site_id = m.get("current_site_id") or ""
        if not machine_site_id:
            return True   # current_site_id not set — include by default
        return machine_site_id == _wo_site_id

    filtered_mc_rows = [mr for mr in mc_rows if _location_matches_site(mr.get("machine_id", ""))]
    excluded_mc_rows = [mr for mr in mc_rows if not _location_matches_site(mr.get("machine_id", ""))]

    # Parse saved deployment machine rows (used by both modes)
    _ro_mc_dates: dict[str, dict] = {}
    _raw_mcd_ro = existing_dep.get("machine_deployments")
    if _raw_mcd_ro:
        try:
            _mcd_list_ro = json.loads(_raw_mcd_ro) if isinstance(_raw_mcd_ro, str) else _raw_mcd_ro
            for _entry in (_mcd_list_ro if isinstance(_mcd_list_ro, list) else []):
                _kid = _entry.get("machine_id") or _entry.get("machine_label")
                if _kid:
                    _ro_mc_dates[_kid] = _entry
        except Exception:
            pass

    # ── Section A — Work Order Details (always read-only) ─────────────────────
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

    # Machine tags
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

    # Machine detail card (show for both modes, but only with selectbox in editable)
    if excluded_mc_rows:
        excl_names = ", ".join(mr.get("machine_label", "—") for mr in excluded_mc_rows)
        _excl_site_label = _wo_site.get("site_name") or _wo_site.get("city") or "the work order site"
        st.markdown(
            f"<div style='margin-top:12px;padding:10px 14px;background:#FFF7ED;"
            f"border:1px solid #FED7AA;border-radius:8px;font-size:12px;color:#92400E;"
            f"display:flex;align-items:flex-start;gap:8px;'>"
            f"<span class='msr' style='font-size:15px;flex-shrink:0;'>location_off</span>"
            f"<div><strong>Location mismatch — hidden from selector:</strong> {excl_names}. "
            f"These machines are not currently located at <strong>{_excl_site_label}</strong>. "
            f"Move them to the site first via the Machine Movement page.</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    if filtered_mc_rows:
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
        machine_labels = [mr.get("machine_label", f"Machine {i+1}") for i, mr in enumerate(filtered_mc_rows)]

        sel_machine_label = st.selectbox(
            "Select Machine",
            options=machine_labels,
            key=f"dep_machine_sel_{selected_wo_id}",
            disabled=_wo_is_closed,
        )

        sel_mr = next(
            (mr for mr in filtered_mc_rows if mr.get("machine_label") == sel_machine_label),
            filtered_mc_rows[0],
        )

        op_status   = machine_status_map.get(sel_mr.get("machine_id", ""), "")
        mach_master = machine_full_map.get(sel_mr.get("machine_id", ""), {})
        make  = sel_mr.get("make")  or mach_master.get("make",  "")
        model = sel_mr.get("model") or mach_master.get("model", "")
        make_model  = " · ".join(filter(None, [make, model])) or "—"

        rental = sel_mr.get("rental_per_month")
        mob    = sel_mr.get("mobilization_cost")
        demob  = sel_mr.get("demobilization_cost")
        cycle_period = (
            f"{sel_mr.get('billing_cycle_start_date', '—')}  →  "
            f"{sel_mr.get('billing_cycle_end_date', '—')}"
        )
        shift_hr = sel_mr.get("machine_shift_hour")
        no_days  = sel_mr.get("no_of_days")

        detail_fields = [
            ("Make / Model",        make_model),
            ("Billing Type",        sel_mr.get("billing_type")  or "—"),
            ("Billing Cycle",       sel_mr.get("billing_cycle") or "—"),
            ("Rental / Month",      f"{float(rental):,.0f}" if rental else "—"),
            ("Cycle Period",        cycle_period),
            ("Shift Hour",          f"{shift_hr} hr" if shift_hr else "—"),
            ("No of Days",          str(no_days) if no_days else "—"),
            ("Mobilisation Cost",   f"{float(mob):,.0f}"   if mob   else "—"),
            ("Demobilisation Cost", f"{float(demob):,.0f}" if demob else "—"),
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

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSED MODE — read-only Sections B & C
    # ══════════════════════════════════════════════════════════════════════════
    if _wo_is_closed:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

        # Closed info banner
        st.markdown(
            f"<div style='background:#F8FAFC;border:1px solid #CBD5E1;border-radius:10px;"
            f"padding:16px 20px;margin-bottom:24px;display:flex;align-items:center;gap:12px;'>"
            f"<span class='msr' style='font-size:24px;color:#64748B;'>lock</span>"
            f"<div>"
            f"<div style='font-size:13px;font-weight:700;color:#374151;'>"
            f"Work Order is {_wo_status}</div>"
            f"<div style='font-size:12px;color:#94A3B8;margin-top:2px;'>"
            f"All machines have returned to Available. This record is locked for viewing only.</div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        # No save button for closed WOs — done.
        return

    # ── Billing Start Date — pre-sync session state from saved deployment ─────
    _bsd_sync_key = f"_bsd_sync_{dep_key}"
    if st.session_state.get(_bsd_sync_key) != dep_key:
        st.session_state[_bsd_sync_key] = dep_key
        for _mr in filtered_mc_rows:
            _mid = _mr.get("machine_id") or _mr.get("machine_label", "")
            _saved_entry = _ro_mc_dates.get(_mid) or _ro_mc_dates.get(_mr.get("machine_label", "")) or {}
            _saved_bsd = _saved_entry.get("billing_start_date")
            _bsd_key = f"dep_{dep_key}_bsd_{_mid}"
            if _saved_bsd and _bsd_key not in st.session_state:
                try:
                    st.session_state[_bsd_key] = date.fromisoformat(str(_saved_bsd))
                except Exception:
                    pass

    # ── Save ──────────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    _section_header("Billing Start Date", "Set the billing start date for each machine on this deployment")

    with st.form("dep_form"):
        for _mr in filtered_mc_rows:
            _mid   = _mr.get("machine_id") or _mr.get("machine_label", "")
            _mlbl  = _mr.get("machine_label", _mid)
            _bcol1, _bcol2 = st.columns([3, 2])
            with _bcol1:
                st.markdown(
                    f"<div style='font-size:13px;font-weight:600;color:#111827;"
                    f"padding:6px 0 2px;'>{_mlbl}</div>",
                    unsafe_allow_html=True,
                )
            with _bcol2:
                st.date_input("Billing Start Date", key=f"dep_{dep_key}_bsd_{_mid}",
                              label_visibility="collapsed")

        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "✔  Update Deployment" if _dep_exists else "Save Deployment",
            type="primary",
            use_container_width=False,
        )

        if submitted:
            mc_dates_payload = []
            for mr in filtered_mc_rows:
                mid  = mr.get("machine_id") or mr.get("machine_label", "")
                mlbl = mr.get("machine_label", mid)
                bsd  = st.session_state.get(f"dep_{dep_key}_bsd_{mid}")
                mc_dates_payload.append({
                    "machine_id":        mr.get("machine_id"),
                    "machine_label":     mlbl,
                    "billing_start_date": bsd.isoformat() if isinstance(bsd, date) else None,
                })

            payload = dict(
                work_order_id=selected_wo_id,
                customer_id=selected_wo.get("customer_id"),
                site_id=selected_wo.get("site_id"),
                deployment_date=date.today().isoformat(),
                client_work_ordernumber=selected_wo.get("client_work_ordernumber"),
                machine_deployments=json.dumps(mc_dates_payload),
            )

            try:
                if _dep_exists:
                    sb.update_deployment(existing_dep["id"], payload)
                else:
                    sb.insert_deployment(payload)

                for mr in filtered_mc_rows:
                    _mid_val = mr.get("machine_id")
                    if _mid_val:
                        _bsd_val = st.session_state.get(f"dep_{dep_key}_bsd_{_mid_val or mr.get('machine_label', '')}")
                        _new_status = "On Rent" if isinstance(_bsd_val, date) else "Reserved"
                        try:
                            sb.update_machine(_mid_val, {"operational_status": _new_status})
                        except Exception:
                            pass

                st.success("✔ Deployment updated." if _dep_exists else "Deployment saved successfully.")
                st.session_state.pop("_dep_editing_wo_id", None)
                st.session_state.pop(_bsd_sync_key, None)

            except Exception as exc:
                st.error(f"Could not save deployment: {exc}")
