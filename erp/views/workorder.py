"""
erp/views/workorder.py
Work Order — one WO can contain multiple machines, each with its own
billing configuration. Start Date and End Date are at the WO level.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient

# ── Constants ─────────────────────────────────────────────────────────────────

BILLING_TYPES  = ["Monthly Fixed Rental", "Daily Rental"]
BILLING_CYCLES = ["Calendar Month", "Custom"]
_HOUR_OPTS     = [""] + [str(h) for h in range(1, 25)]   # 1–24 hrs, blank = not set
_DAYS_OPTS     = [""] + [str(d) for d in range(1, 31)]   # 1–30 days, blank = not set
_YES_NO_OPTS   = ["No", "Yes"]

_MC_COLS = [
    "Machine", "Make", "Model", "Serial Number",
    "Billing Type", "Billing Cycle",
    "Rental / Month",
    "Cycle Start", "Cycle End",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _default_cycle_dates(ref: date | None) -> tuple[date, date]:
    d = ref or date.today()
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _parse_machine_config(raw, id_to_label: dict) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=_MC_COLS)
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(records, list):
            return pd.DataFrame(columns=_MC_COLS)
        rows = []
        for r in records:
            rows.append({
                "Machine":        id_to_label.get(r.get("machine_id", ""), r.get("machine_label", "")),
                "Make":           r.get("make", ""),
                "Model":          r.get("model", ""),
                "Serial Number":  r.get("serial_number", ""),
                "Billing Type":   r.get("billing_type", BILLING_TYPES[0]),
                "Billing Cycle":  r.get("billing_cycle", BILLING_CYCLES[0]),
                "Rental / Month": float(r.get("rental_per_month") or 0.0),
                "Cycle Start":    _parse_date(r.get("billing_cycle_start_date")),
                "Cycle End":      _parse_date(r.get("billing_cycle_end_date")),
            })
        return pd.DataFrame(rows, columns=_MC_COLS)
    except Exception:
        return pd.DataFrame(columns=_MC_COLS)


def _machine_config_to_json(df: pd.DataFrame, label_to_id: dict) -> str:
    records = []
    for _, row in df.iterrows():
        label = str(row.get("Machine") or "").strip()
        if not label:
            continue
        cs = row.get("Cycle Start")
        ce = row.get("Cycle End")
        records.append({
            "machine_id":               label_to_id.get(label),
            "machine_label":            label,
            "make":                     str(row.get("Make") or ""),
            "model":                    str(row.get("Model") or ""),
            "serial_number":            str(row.get("Serial Number") or ""),
            "billing_type":             str(row.get("Billing Type") or ""),
            "billing_cycle":            str(row.get("Billing Cycle") or ""),
            "rental_per_month":         float(row.get("Rental / Month") or 0),
            "billing_cycle_start_date": cs.isoformat() if isinstance(cs, date) else None,
            "billing_cycle_end_date":   ce.isoformat() if isinstance(ce, date) else None,
        })
    return json.dumps(records)


# ── Dialog helpers ────────────────────────────────────────────────────────────

def _init_dialog_state(row: dict, label_to_details: dict, ref_date) -> None:
    """Populate session-state keys that the dialog widgets read via key=.

    Increments _dlg_ver so every dialog open gets a unique key prefix —
    Streamlit has no prior widget state for a key it has never seen, which
    guarantees blank fields for new entries and correct values for edits.
    """
    ver = st.session_state.get("_dlg_ver", 0) + 1
    st.session_state["_dlg_ver"] = ver
    p = f"_dlg_{ver}_"   # key prefix

    label   = row.get("machine_label", "") or ""
    details = label_to_details.get(label, {})
    cs = _parse_date(row.get("billing_cycle_start_date"))
    ce = _parse_date(row.get("billing_cycle_end_date"))
    if not cs:
        cs, ce = _default_cycle_dates(ref_date if isinstance(ref_date, date) else None)
    st.session_state.update({
        p + "machine":      label,
        p + "prev_m":       label,
        p + "make":         details.get("make")          or row.get("make", ""),
        p + "model":        details.get("model")         or row.get("model", ""),
        p + "serial":       details.get("serial_number") or row.get("serial_number", ""),
        p + "bt":           row.get("billing_type")  or BILLING_TYPES[0],
        p + "bc":           row.get("billing_cycle") or BILLING_CYCLES[0],
        p + "rental":       float(row.get("rental_per_month") or 0),
        p + "cs":           cs or date.today(),
        p + "ce":           ce or date.today(),
        p + "no_of_days":   row.get("no_of_days")            or "",
        p + "shift_hour":   row.get("machine_shift_hour")   or "",
        p + "mob_cost":     float(row.get("mobilization_cost")   or 0),
        p + "demob_cost":   float(row.get("demobilization_cost") or 0),
        p + "cross_rental": row.get("cross_rental") or _YES_NO_OPTS[0],
        p + "vendor_name":    row.get("vendor_name")          or "",
        p + "vendor_gst":     row.get("vendor_gst")           or "",
        p + "vendor_contact": row.get("vendor_contact")       or "",
        p + "vendor_rental":  float(row.get("vendor_rental_amount") or 0),
        p + "vendor_mobile":  row.get("vendor_mobile_no")     or "",
        p + "vendor_demob":   row.get("vendor_demob")         or "",
    })


@st.dialog("Machine Configuration", width="large")
def _machine_row_dialog(
    row_idx: int,
    mc_rows: list,
    wo_key: str,
    machine_opts: list,
    label_to_id: dict,
    label_to_details: dict,
    ref_date,
) -> None:
    """Popup form for adding / editing a machine config row."""
    is_new = row_idx < 0
    ver = st.session_state.get("_dlg_ver", 0)
    p = f"_dlg_{ver}_"   # must match prefix set by _init_dialog_state

    st.markdown(
        f"<div style='font-size:11px;font-weight:700;letter-spacing:.1em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:12px;'>"
        f"{'New Machine' if is_new else 'Edit Machine'}</div>",
        unsafe_allow_html=True,
    )

    machine_label = st.selectbox(
        "Machine *",
        machine_opts,
        format_func=lambda x: "— Select Machine —" if x == "" else x,
        key=p + "machine",
    )

    # Cascade: auto-fill Make/Model/Serial when Machine changes
    if machine_label and machine_label != st.session_state.get(p + "prev_m"):
        details = label_to_details.get(machine_label, {})
        st.session_state[p + "make"]   = details.get("make", "")
        st.session_state[p + "model"]  = details.get("model", "")
        st.session_state[p + "serial"] = details.get("serial_number", "")
        st.session_state[p + "prev_m"] = machine_label

    sp1, sp2, sp3 = st.columns(3)
    with sp1:
        make = st.text_input("Make", key=p + "make")
    with sp2:
        model = st.text_input("Model", key=p + "model")
    with sp3:
        serial = st.text_input("Serial Number", key=p + "serial")

    b1, b2 = st.columns(2)
    with b1:
        billing_type = st.selectbox("Billing Type", BILLING_TYPES, key=p + "bt")
    with b2:
        billing_cycle = st.selectbox("Billing Cycle", BILLING_CYCLES, key=p + "bc")

    rental = st.number_input(
        "Rental / Month", min_value=0.0, step=1000.0, format="%.0f", key=p + "rental",
    )

    # Cycle dates — Calendar Month auto-fills from WO start date
    auto_cs, auto_ce = _default_cycle_dates(ref_date if isinstance(ref_date, date) else None)
    if billing_cycle == "Calendar Month":
        st.session_state[p + "cs"] = auto_cs
        st.session_state[p + "ce"] = auto_ce

    d1, d2 = st.columns(2)
    with d1:
        cycle_start = st.date_input(
            "Cycle Start", key=p + "cs",
            disabled=(billing_cycle == "Calendar Month"),
        )
    with d2:
        cycle_end = st.date_input(
            "Cycle End", key=p + "ce",
            disabled=(billing_cycle == "Calendar Month"),
        )
    # ── Shift & Hours ─────────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#E87722;margin:14px 0 8px;'>"
        "Shift &amp; Hours</div>",
        unsafe_allow_html=True,
    )
    h1, h2 = st.columns(2)
    with h1:
        no_of_days = st.selectbox(
            "No of Days",
            _DAYS_OPTS,
            format_func=lambda x: "— Select —" if x == "" else f"{x} day{'s' if x != '1' else ''}",
            key=p + "no_of_days",
        )
    with h2:
        shift_hour = st.selectbox(
            "Shift Hour",
            _HOUR_OPTS,
            format_func=lambda x: "— Select —" if x == "" else f"{x} hr",
            key=p + "shift_hour",
        )

    vm1, vm2 = st.columns(2)
    with vm1:
        mob_cost = st.number_input(
            "Mobilisation Cost", min_value=0.0, step=500.0, format="%.0f",
            key=p + "mob_cost",
        )
    with vm2:
        demob_cost = st.number_input(
            "Demobilisation Cost", min_value=0.0, step=500.0, format="%.0f",
            key=p + "demob_cost",
        )

    # ── Operational Details ────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#E87722;margin:14px 0 8px;'>"
        "Operational Details</div>",
        unsafe_allow_html=True,
    )
    od1, _ = st.columns(2)
    with od1:
        cross_rental = st.selectbox(
            "Cross Rental", _YES_NO_OPTS, key=p + "cross_rental",
        )

    # ── Vendor Details ─────────────────────────────────────────────────────────
    _vendor_locked = (cross_rental != "Yes")
    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#E87722;margin:14px 0 8px;'>"
        f"Vendor Details"
        f"{'<span style=\"font-weight:400;font-size:10px;color:#9ca3af;margin-left:8px;\">'
           '— set Cross Rental to Yes to enable</span>' if _vendor_locked else ''}"
        "</div>",
        unsafe_allow_html=True,
    )
    vd1, vd2 = st.columns(2)
    with vd1:
        vendor_name = st.text_input(
            "Vendor Name", placeholder="Vendor / supplier name",
            key=p + "vendor_name", disabled=_vendor_locked,
        )
    with vd2:
        vendor_gst = st.text_input(
            "Vendor GST", placeholder="GST number",
            key=p + "vendor_gst", disabled=_vendor_locked,
        )
    vd3, vd4, vd5 = st.columns(3)
    with vd3:
        vendor_contact = st.text_input(
            "Vendor Contact", placeholder="Contact person",
            key=p + "vendor_contact", disabled=_vendor_locked,
        )
    with vd4:
        vendor_mobile = st.text_input(
            "Vendor Mobile No.", placeholder="+91 XXXXX XXXXX",
            key=p + "vendor_mobile", disabled=_vendor_locked,
        )
    with vd5:
        vendor_demob = st.text_input(
            "Vendor Demob No.", placeholder="+91 XXXXX XXXXX",
            key=p + "vendor_demob", disabled=_vendor_locked,
        )
    vendor_rental = st.number_input(
        "Vendor Rental Amount", min_value=0.0, step=1000.0, format="%.0f",
        key=p + "vendor_rental", disabled=_vendor_locked,
    )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    a1, a2 = st.columns(2)
    with a1:
        if st.button("Save", type="primary", use_container_width=True, key=f"dlg_{ver}_save"):
            if not machine_label:
                st.error("Please select a machine.")
            else:
                new_row = {
                    "machine_id":               label_to_id.get(machine_label),
                    "machine_label":            machine_label,
                    "make":                     make or "",
                    "model":                    model or "",
                    "serial_number":            serial or "",
                    "billing_type":             billing_type or BILLING_TYPES[0],
                    "billing_cycle":            billing_cycle or BILLING_CYCLES[0],
                    "rental_per_month":         float(rental or 0),
                    "billing_cycle_start_date": cycle_start.isoformat() if isinstance(cycle_start, date) else None,
                    "billing_cycle_end_date":   cycle_end.isoformat() if isinstance(cycle_end, date) else None,
                    "no_of_days":               no_of_days   or None,
                    "machine_shift_hour":       shift_hour   or None,
                    "mobilization_cost":        float(mob_cost   or 0),
                    "demobilization_cost":      float(demob_cost or 0),
                    "cross_rental":             cross_rental,
                    "vendor_name":              vendor_name    or None,
                    "vendor_gst":               vendor_gst     or None,
                    "vendor_contact":           vendor_contact or None,
                    "vendor_rental_amount":     float(vendor_rental or 0),
                    "vendor_mobile_no":         vendor_mobile  or None,
                    "vendor_demob":             vendor_demob   or None,
                }
                rows = list(mc_rows)
                if is_new:
                    rows.append(new_row)
                else:
                    rows[row_idx] = new_row
                st.session_state[f"mc_rows_{wo_key}"] = rows
                st.rerun()
    with a2:
        if st.button("Cancel", use_container_width=True, key=f"dlg_{ver}_cancel"):
            st.rerun()


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Work Orders</div>
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

    # ── Fetchers ───────────────────────────────────────────────────────────────
    def fetch_work_orders() -> list[dict]:
        try:
            return sb.list_work_orders()
        except Exception as exc:
            st.error(f"Failed to load work orders: {exc}")
            return []

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception:
            return []

    def fetch_sites() -> list[dict]:
        try:
            return sb.list_sites()
        except Exception:
            return []

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception:
            return []

    work_orders = fetch_work_orders()
    customers   = fetch_customers()
    sites       = fetch_sites()
    machines    = fetch_machines()

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}
    wo_map       = {w.get("id"): w for w in work_orders if w.get("id")}

    # Machine label ↔ ID lookups (use ALL machines so existing WO rows parse correctly)
    machines_by_id: dict[str, dict] = {m["id"]: m for m in machines if m.get("id")}
    id_to_label  = {
        m.get("id"): f"{m.get('asset_code', '')} — {m.get('machine_type', '')}".strip("— ")
        for m in machines if m.get("id")
    }
    label_to_id  = {v: k for k, v in id_to_label.items()}
    # machine_opts built below after selected_wo is known (excludes Reserved machines)

    # Per-machine detail lookup for cascade auto-fill (label → specs)
    label_to_details: dict[str, dict] = {
        label: {
            "make":          m.get("make", "") or "",
            "model":         m.get("model", "") or "",
            "serial_number": m.get("serial_number", "") or "",
        }
        for m in machines
        for label in [id_to_label.get(m.get("id"), "")]
        if label
    }

    # ── Edit selector ──────────────────────────────────────────────────────────
    # Optional customer filter — narrows the WO list; blank = show all + allow new.
    _cids_with_wo = sorted(
        {wo.get("customer_id") for wo in work_orders if wo.get("customer_id")},
        key=lambda cid: customer_map.get(cid, {}).get("customer_name", ""),
    )
    _filter_customer_id = st.selectbox(
        "Filter by Customer",
        options=[""] + _cids_with_wo,
        format_func=lambda cid: "All customers" if not cid
            else customer_map.get(cid, {}).get("customer_name", cid),
        key="wo_filter_customer_id",
    )

    # Reset WO selection when the customer filter changes.
    if st.session_state.get("_wo_prev_filter_customer") != _filter_customer_id:
        st.session_state["_wo_prev_filter_customer"] = _filter_customer_id
        st.session_state["selected_wo_id"] = ""

    _filtered_wo_ids = sorted(
        [wid for wid, wo in wo_map.items()
         if not _filter_customer_id or wo.get("customer_id") == _filter_customer_id],
        key=lambda wid: wo_map[wid].get("wo_number", ""),
    )
    selected_wo_id = st.selectbox(
        "Edit existing work order",
        options=[""] + _filtered_wo_ids,
        format_func=lambda wid: "New work order" if not wid
            else f"{wo_map[wid].get('wo_number', 'Unknown')} — "
                 f"{customer_map.get(wo_map[wid].get('customer_id', ''), {}).get('customer_name', '')}",
        key="selected_wo_id",
    )
    selected_wo = wo_map.get(selected_wo_id)
    wo_key = selected_wo_id or "new"

    # Machine dropdown options: exclude Reserved machines, but keep any machine
    # already allocated to the currently-selected WO (so edits display correctly).
    current_wo_machine_ids: set[str] = set()
    if selected_wo:
        raw_mc = selected_wo.get("machine_config")
        try:
            records = json.loads(raw_mc) if isinstance(raw_mc, str) else (raw_mc or [])
            for r in (records if isinstance(records, list) else []):
                mid = r.get("machine_id")
                if mid:
                    current_wo_machine_ids.add(mid)
        except Exception:
            pass
    machine_opts = [""] + sorted([
        lbl for mid, lbl in id_to_label.items()
        if machines_by_id.get(mid, {}).get("operational_status") != "Reserved"
        or mid in current_wo_machine_ids
    ])

    # ── Sync session state on selection change ─────────────────────────────────
    if st.session_state.get("_editing_wo_id") != selected_wo_id:
        st.session_state["_editing_wo_id"] = selected_wo_id
        wo = selected_wo or {}
        st.session_state["wo_customer_id"] = wo.get("customer_id", "")
        st.session_state["wo_site_id"]     = wo.get("site_id", "")
        st.session_state["wo_start_date"]  = _parse_date(wo.get("start_date"))
        st.session_state["wo_end_date"]    = _parse_date(wo.get("end_date"))
        st.session_state["wo_client_wo"]   = wo.get("client_work_ordernumber", "") or ""
        for k in [f"mc_data_{wo_key}", f"mc_recalc_{wo_key}", f"mc_rows_{wo_key}"]:
            st.session_state.pop(k, None)

    # ── A. Basic Selection ─────────────────────────────────────────────────────
    st.markdown(
        "<div style='margin-bottom:6px;border-top:2px solid #E87722;padding-top:10px;"
        "font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        "text-transform:uppercase;'>A — Basic Selection</div>",
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        selected_customer_id = st.selectbox(
            "Customer *",
            options=[""] + list(customer_map),
            format_func=lambda cid: "Select customer" if not cid
                else customer_map[cid].get("customer_name", "Unknown"),
            key="wo_customer_id",
        )
    with col2:
        filtered_sites = {
            sid: s for sid, s in site_map.items()
            if str(s.get("customer_id", "")) == str(selected_customer_id)
        }
        if st.session_state.get("wo_site_id") not in filtered_sites:
            st.session_state["wo_site_id"] = ""
        selected_site_id = st.selectbox(
            "Site *",
            options=[""] + list(filtered_sites),
            format_func=lambda sid: "Select site" if not sid
                else filtered_sites[sid].get("site_name", "Unknown"),
            key="wo_site_id",
        )
    with col3:
        selected_start_date = st.date_input("Start Date *", key="wo_start_date")
    with col4:
        selected_end_date = st.date_input("End Date", key="wo_end_date")

    cwo1, _ = st.columns([2, 2])
    with cwo1:
        selected_client_wo = st.text_input(
            "Client Work Order Number", placeholder="Client WO#",
            key="wo_client_wo",
        )

    # ── B. Machine Configuration ───────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='margin-bottom:6px;border-top:2px solid #E87722;padding-top:10px;"
        "font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        "text-transform:uppercase;'>B — Machine Configuration</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='font-size:12px;color:#6b7280;margin:0 0 10px;'>"
        "Add one or more machines. <strong>Calendar Month</strong> cycle dates "
        "auto-fill from the WO Start Date.</p>",
        unsafe_allow_html=True,
    )

    # ── Initialize mc_rows from WO data or empty ──────────────────────────────
    if f"mc_rows_{wo_key}" not in st.session_state:
        if selected_wo and selected_wo.get("machine_config"):
            raw = selected_wo["machine_config"]
            try:
                records = json.loads(raw) if isinstance(raw, str) else raw
                st.session_state[f"mc_rows_{wo_key}"] = records if isinstance(records, list) else []
            except Exception:
                st.session_state[f"mc_rows_{wo_key}"] = []
        else:
            st.session_state[f"mc_rows_{wo_key}"] = []

    mc_rows: list[dict] = st.session_state[f"mc_rows_{wo_key}"]
    ref_date_for_dialog = selected_start_date if isinstance(selected_start_date, date) else None

    # ── Machine rows table ─────────────────────────────────────────────────────
    if mc_rows:
        th1, th2, th3, th4, th5, th6 = st.columns([4, 2, 3, 3, 2, 2])
        for th, lbl in zip(
            [th1, th2, th3, th4, th5, th6],
            ["Machine", "Make / Model", "Billing Type", "Billing Cycle", "Rental / Mo", ""],
        ):
            th.markdown(
                f"<div style='font-size:10px;font-weight:700;color:#6b7280;"
                f"letter-spacing:.08em;text-transform:uppercase;padding-bottom:4px;"
                f"border-bottom:1px solid #e5e7eb;'>{lbl}</div>",
                unsafe_allow_html=True,
            )

        for idx, row in enumerate(mc_rows):
            c1, c2, c3, c4, c5, c6 = st.columns([4, 2, 3, 3, 2, 2])
            c1.write(row.get("machine_label") or "—")
            c2.write(
                " / ".join(filter(None, [
                    row.get("make", ""), row.get("model", ""),
                ])) or "—"
            )
            c3.write(row.get("billing_type") or "—")
            c4.write(row.get("billing_cycle") or "—")
            c5.write(f"{float(row.get('rental_per_month') or 0):,.0f}")
            with c6:
                e1, e2 = st.columns(2)
                with e1:
                    if st.button("Edit", key=f"mc_edit_{idx}_{wo_key}", use_container_width=True):
                        _init_dialog_state(row, label_to_details, ref_date_for_dialog)
                        _machine_row_dialog(
                            row_idx=idx, mc_rows=mc_rows, wo_key=wo_key,
                            machine_opts=machine_opts, label_to_id=label_to_id,
                            label_to_details=label_to_details, ref_date=ref_date_for_dialog,
                        )
                with e2:
                    if st.button("Del", key=f"mc_del_{idx}_{wo_key}", use_container_width=True):
                        updated = list(mc_rows)
                        updated.pop(idx)
                        st.session_state[f"mc_rows_{wo_key}"] = updated
                        st.rerun()
    else:
        st.markdown(
            "<p style='color:#9ca3af;font-size:13px;padding:12px 0;'>"
            "No machines added yet — click <strong>+ Add Machine</strong> below.</p>",
            unsafe_allow_html=True,
        )

    # ── Add Machine button ─────────────────────────────────────────────────────
    if st.button("+ Add Machine", key=f"mc_add_{wo_key}"):
        _init_dialog_state({}, label_to_details, ref_date_for_dialog)
        _machine_row_dialog(
            row_idx=-1, mc_rows=mc_rows, wo_key=wo_key,
            machine_opts=machine_opts, label_to_id=label_to_id,
            label_to_details=label_to_details, ref_date=ref_date_for_dialog,
        )

    # ── Summary bar ───────────────────────────────────────────────────────────
    valid_mc = [r for r in mc_rows if r.get("machine_label") or r.get("machine_id")]
    if valid_mc:
        total_rental = sum(float(r.get("rental_per_month") or 0) for r in valid_mc)
        st.markdown(
            f"<div style='display:flex;gap:32px;padding:8px 12px;"
            f"background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;"
            f"margin-top:8px;font-size:12px;'>"
            f"<span style='color:#6b7280;'>Machines: "
            f"<strong style='color:#111827;'>{len(valid_mc)}</strong></span>"
            f"<span style='color:#6b7280;'>Total Rental / Month: "
            f"<strong style='color:#E87722;'>{total_rental:,.0f}</strong></span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

    # ── Form (submit) ──────────────────────────────────────────────────────────
    with st.form("wo_form"):
        if selected_wo:
            st.markdown(
                f"<span style='font-size:11px;color:#6b7280;'>WO Number: "
                f"<strong>{selected_wo.get('wo_number', '—')}</strong></span>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

        submitted = st.form_submit_button(
            "Update Work Order" if selected_wo else "Create Work Order"
        )

        if submitted:
            if not selected_customer_id:
                st.error("Customer is required.")
            elif not selected_site_id:
                st.error("Site is required.")
            elif not selected_start_date:
                st.error("Start Date is required.")
            else:
                mc_rows_save = st.session_state.get(f"mc_rows_{wo_key}", [])
                valid_rows   = [r for r in mc_rows_save if r.get("machine_label") or r.get("machine_id")]
                if not valid_rows:
                    st.error("Add at least one machine.")
                else:
                    machine_config_json = json.dumps(valid_rows)
                    payload = dict(
                        customer_id=selected_customer_id,
                        site_id=selected_site_id,
                        start_date=selected_start_date.isoformat() if isinstance(selected_start_date, date) else None,
                        end_date=selected_end_date.isoformat()     if isinstance(selected_end_date, date)   else None,
                        client_work_ordernumber=selected_client_wo or None,
                        machine_config=machine_config_json,
                    )
                    try:
                        if selected_wo:
                            sb.update_work_order(selected_wo_id, payload)
                            st.success("Work order updated.")
                        else:
                            created = sb.insert_work_order(payload)
                            wo_num  = created.get("wo_number") or created.get("id", "")
                            st.success(f"Work order created: {wo_num}")
                        # Mark every allocated machine as Reserved
                        for row in valid_rows:
                            mid = row.get("machine_id") or label_to_id.get(row.get("machine_label", ""))
                            if mid:
                                try:
                                    sb.update_machine(mid, {"operational_status": "Reserved"})
                                except Exception:
                                    pass
                        work_orders = fetch_work_orders()
                    except Exception as exc:
                        st.error(f"Could not save work order: {exc}")

    # ── Work order list ────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    col_cap, col_btn = st.columns([5, 1])
    with col_cap:
        st.markdown('<p class="filter-label">All Work Orders</p>', unsafe_allow_html=True)
    with col_btn:
        if st.button("Refresh", key="refresh_wo"):
            work_orders = fetch_work_orders()

    if work_orders:
        rows = []
        for w in work_orders:
            mc_raw    = w.get("machine_config")
            mc_list   = []
            total_rnt = 0.0
            if mc_raw:
                try:
                    mc_records = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
                    mc_list    = [r.get("machine_label", "") for r in mc_records if r.get("machine_label")]
                    total_rnt  = sum(float(r.get("rental_per_month") or 0) for r in mc_records)
                except Exception:
                    pass
            rows.append({
                "WO Number":    w.get("wo_number", ""),
                "Customer":     customer_map.get(w.get("customer_id", ""), {}).get("customer_name", ""),
                "Site":         site_map.get(w.get("site_id", ""), {}).get("site_name", ""),
                "Start Date":   w.get("start_date", ""),
                "End Date":     w.get("end_date", ""),
                "Machines":     len(mc_list),
                "Machine List": ", ".join(mc_list) if mc_list else "—",
                "Total Rental": f"{total_rnt:,.0f}" if total_rnt else "—",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No work orders found.")
