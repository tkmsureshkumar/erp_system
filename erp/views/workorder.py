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

# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ──────────────────────────────────────────────────────── */
.wo-kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin: 0 0 28px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 18px 22px 14px;
    position: relative;
    overflow: hidden;
    transition: box-shadow .18s, transform .18s;
}
.kpi-card:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,.08);
    transform: translateY(-2px);
}
.kpi-accent-bar {
    position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 10px; display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 34px; font-weight: 800;
    color: #111827; line-height: 1; margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 11px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 16px; right: 18px;
    font-size: 22px; opacity: .12;
}

/* ── Search wrapper ─────────────────────────────────────────────────── */
.search-wrap { position: relative; margin-bottom: 8px; }
.search-icon-abs {
    position: absolute; left: 11px; top: 50%;
    transform: translateY(-50%);
    font-size: 16px; color: #9CA3AF;
    z-index: 10; pointer-events: none;
}
.search-wrap .stTextInput input {
    padding-left: 34px !important;
    border-radius: 8px !important;
}

/* ── WO list cards ──────────────────────────────────────────────────── */
.wo-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 10px;
    padding: 10px 13px 9px;
    pointer-events: none;
    transition: box-shadow .16s, border-color .16s, transform .16s;
}
.wo-card:hover {
    box-shadow: 0 4px 16px rgba(232,119,34,.10);
    border-color: #FBD4B4; transform: translateY(-1px);
}
.wo-card.wo-sel {
    border-color: #E87722 !important;
    background: #FFF8F4; border-left-width: 3px;
}
.wo-card-top {
    display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}
.wo-num {
    font-size: 13px; font-weight: 700; color: #111827;
    flex: 1; min-width: 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.wo-card-sub {
    font-size: 11px; color: #6B7280;
    display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
    margin-bottom: 3px;
}
.wo-date-range {
    font-size: 10px; color: #9CA3AF;
    display: flex; align-items: center; gap: 4px; margin-top: 3px;
}
.wo-rental-badge {
    font-size: 10px; font-weight: 700;
    background: #FFF4ED; color: #C2410C;
    border: 1px solid #FDDCBA;
    padding: 1px 7px; border-radius: 20px;
    white-space: nowrap; flex-shrink: 0; margin-left: auto;
}
.wo-cl-dot {
    width: 3px; height: 3px; border-radius: 50%;
    background: #D1D5DB; flex-shrink: 0; display: inline-block;
}

/* ── Empty state ─────────────────────────────────────────────────────── */
.wo-empty {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 72px 40px;
    background: #FAFBFC; border: 2px dashed #E2EBF0;
    border-radius: 16px; text-align: center;
    animation: wo-fadeup .35s ease;
}
.wo-empty-ring {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(145deg, #FFF4ED, #FDE8D4);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px; margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(232,119,34,.14);
}
.wo-empty h3 {
    font-size: 17px; font-weight: 700; color: #111827; margin: 0 0 8px;
}
.wo-empty p {
    font-size: 13px; color: #9CA3AF;
    max-width: 270px; line-height: 1.6; margin: 0;
}

/* ── WO hero banner ─────────────────────────────────────────────────── */
.wo-hero {
    background: linear-gradient(135deg, #1A1F2E 0%, #2D1A0E 55%, #3D2410 100%);
    border-radius: 14px; padding: 22px 24px; margin-bottom: 18px;
    display: flex; align-items: flex-start; gap: 16px;
    position: relative; overflow: hidden;
    animation: wo-fadeup .3s ease;
}
.wo-hero::before {
    content: ''; position: absolute; top: -40px; right: -40px;
    width: 160px; height: 160px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.wo-hero-icon {
    width: 52px; height: 52px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 24px; background: rgba(232,119,34,.25);
    border: 1px solid rgba(232,119,34,.35); flex-shrink: 0;
}
.wo-hero-num {
    font-size: 20px; font-weight: 800; color: #fff; line-height: 1.2;
}
.wo-hero-meta {
    font-size: 11px; color: rgba(255,255,255,.45);
    letter-spacing: .06em; margin-top: 4px;
}
.wo-hero-value {
    margin-left: auto; text-align: right;
    position: relative; z-index: 1; flex-shrink: 0;
}
.wo-hero-value-label {
    font-size: 9px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: rgba(255,255,255,.40); margin-bottom: 3px;
}
.wo-hero-value-num {
    font-size: 22px; font-weight: 800; color: #FBD4B4;
    font-variant-numeric: tabular-nums;
}
.hero-badge {
    font-size: 10px; font-weight: 700;
    padding: 2px 10px; border-radius: 20px;
    letter-spacing: .05em; text-transform: uppercase;
    display: inline-block; margin-right: 4px;
}
.hero-badge-new {
    background: rgba(16,185,129,.20); color: #6EE7B7;
    border: 1px solid rgba(16,185,129,.30);
}
.hero-badge-edit {
    background: rgba(245,158,11,.18); color: #FCD34D;
    border: 1px solid rgba(245,158,11,.28);
}

/* ── Form sections ───────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722; margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Info grid (overview) ────────────────────────────────────────────── */
.info-grid {
    display: grid; grid-template-columns: repeat(2, 1fr);
    gap: 10px; margin-bottom: 14px;
}
.info-field {
    background: #F8FAFC; border: 1px solid #E2EBF0;
    border-radius: 8px; padding: 11px 14px;
}
.info-field-label {
    font-size: 9px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 4px;
}
.info-field-value {
    font-size: 13px; font-weight: 600; color: #111827; word-break: break-word;
}
.info-field-value.muted { font-weight: 400; color: #9CA3AF; }

/* ── Machine summary bar ─────────────────────────────────────────────── */
.mc-summary-bar {
    display: flex; gap: 24px; padding: 8px 12px;
    background: #FFF8F4; border: 1px solid #FDDCBA;
    border-radius: 8px; margin-top: 8px; font-size: 12px;
}

/* ── Billing cards ───────────────────────────────────────────────────── */
.billing-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 10px; padding: 14px 16px; margin-bottom: 8px;
}
.billing-card-top {
    display: flex; align-items: center;
    justify-content: space-between; margin-bottom: 8px;
}
.billing-machine-name { font-size: 13px; font-weight: 700; color: #111827; }
.billing-amount { font-size: 15px; font-weight: 800; color: #E87722; }
.billing-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.billing-meta-item { font-size: 11px; color: #6B7280; }
.billing-meta-item strong { color: #374151; font-weight: 600; }

/* ── Tabs polish ─────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important; background: transparent !important;
    border-bottom: 2px solid #E2EBF0 !important; padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 12px !important; font-weight: 600 !important;
    color: #6B7280 !important; padding: 8px 18px !important;
    border-radius: 0 !important; background: transparent !important;
    border: none !important; margin: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: color .14s !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #374151 !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #E87722 !important;
    border-bottom: 2px solid #E87722 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-panel"]     { padding: 18px 0 0 !important; }

/* ── No-results ──────────────────────────────────────────────────────── */
.no-results {
    text-align: center; padding: 36px 12px;
    color: #9CA3AF; font-size: 13px;
}
.no-results .nr-icon { font-size: 32px; margin-bottom: 8px; display: block; }

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes wo-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""

# ── Parse helpers ─────────────────────────────────────────────────────────────

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
                "Cycle Start":    (_parse_date(r.get("billing_cycle_start_date")) or date.today()).day,
                "Cycle End":      (_parse_date(r.get("billing_cycle_end_date"))   or date.today()).day,
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
    cs_day = cs.day if isinstance(cs, date) else 1
    ce_day = ce.day if isinstance(ce, date) else 31
    st.session_state.update({
        p + "machine":      label,
        p + "prev_m":       label,
        p + "make":         details.get("make")          or row.get("make", ""),
        p + "model":        details.get("model")         or row.get("model", ""),
        p + "serial":       details.get("serial_number") or row.get("serial_number", ""),
        p + "bt":           row.get("billing_type")  or BILLING_TYPES[0],
        p + "bc":           row.get("billing_cycle") or BILLING_CYCLES[0],
        p + "rental":       float(row.get("rental_per_month") or 0),
        p + "cs":           cs_day,
        p + "ce":           ce_day,
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

    # Cycle day dropdowns — Calendar Month auto-fills to day 1 → 31
    if billing_cycle == "Calendar Month":
        st.session_state[p + "cs"] = 1
        st.session_state[p + "ce"] = 31

    _day_opts = list(range(1, 32))
    d1, d2 = st.columns(2)
    with d1:
        cycle_start_day = st.selectbox(
            "Cycle Start (Day)", options=_day_opts, key=p + "cs",
            disabled=(billing_cycle == "Calendar Month"),
        )
    with d2:
        cycle_end_day = st.selectbox(
            "Cycle End (Day)", options=_day_opts, key=p + "ce",
            disabled=(billing_cycle == "Calendar Month"),
        )

    # ── Shift & Hours ──────────────────────────────────────────────────────────
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
                    "billing_cycle_start_date": date(2000, 1, int(cycle_start_day)).isoformat() if cycle_start_day else None,
                    "billing_cycle_end_date":   date(2000, 1, int(cycle_end_day)).isoformat() if cycle_end_day else None,
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


# ── UI helpers ────────────────────────────────────────────────────────────────

def _kpi_card(icon: str, label: str, value, sub: str = "", accent: str = "#E87722") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _info_field(label: str, value, wide: bool = False, muted: bool = False) -> str:
    v = str(value) if value not in (None, "", 0) else ""
    val_cls = "info-field-value muted" if (muted or not v) else "info-field-value"
    disp    = v if v else "—"
    span    = "span 2" if wide else "span 1"
    return (
        f"<div class='info-field' style='grid-column:{span};'>"
        f"<div class='info-field-label'>{label}</div>"
        f"<div class='{val_cls}'>{disp}</div>"
        f"</div>"
    )


def _placeholder_tab(icon: str, title: str, description: str) -> None:
    st.markdown(
        f"<div style='display:flex;flex-direction:column;align-items:center;"
        f"padding:52px 24px;text-align:center;'>"
        f"<div style='width:58px;height:58px;border-radius:14px;"
        f"background:#F8FAFC;border:1px solid #E2EBF0;"
        f"display:flex;align-items:center;justify-content:center;"
        f"font-size:26px;margin-bottom:14px;'>"
        f"<span class='msr' style='color:#9CA3AF;'>{icon}</span></div>"
        f"<div style='font-size:15px;font-weight:700;color:#374151;margin-bottom:6px;'>{title}</div>"
        f"<div style='font-size:12px;color:#9CA3AF;max-width:240px;line-height:1.6;'>{description}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


_STATUS_BADGE_MAP = {
    "Active":    "badge-active",
    "Draft":     "badge-draft",
    "Completed": "badge-completed",
    "Closed":    "badge-closed",
    "Running":   "badge-running",
    "Approved":  "badge-approved",
}


def _wo_total_rental(wo: dict) -> float:
    mc_raw = wo.get("machine_config")
    if not mc_raw:
        return 0.0
    try:
        recs = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        return sum(float(r.get("rental_per_month") or 0) for r in (recs if isinstance(recs, list) else []))
    except Exception:
        return 0.0


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        st.markdown(
            "<div class='page-eyebrow'>// Fleet Operations</div>"
            "<div class='page-title'>Work Orders</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed.")
        st.write(str(exc))
        return

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
    id_to_label = {
        m.get("id"): f"{m.get('asset_code', '')} — {m.get('machine_type', '')}".strip("— ")
        for m in machines if m.get("id")
    }
    label_to_id = {v: k for k, v in id_to_label.items()}

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

    # ── New WO button ──────────────────────────────────────────────────────────
    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New WO", use_container_width=True, type="primary", key="hdr_new_wo"):
            st.session_state["_wo_mode"]        = "new"
            st.session_state["_wo_sel_id"]      = ""
            st.session_state["_editing_wo_id"]  = None   # force field sync
            st.rerun()

    # ── KPI strip ──────────────────────────────────────────────────────────────
    n_total  = len(work_orders)
    n_active = sum(
        1 for w in work_orders
        if (w.get("status") or "").lower() in ("active", "running", "approved")
    )
    n_draft  = sum(
        1 for w in work_orders
        if (w.get("status") or "draft").lower() == "draft"
    )
    n_closed = sum(
        1 for w in work_orders
        if (w.get("status") or "").lower() in ("closed", "completed")
    )
    portfolio_rental = sum(_wo_total_rental(w) for w in work_orders)

    st.markdown(
        f"<div class='wo-kpi-grid'>"
        + _kpi_card("assignment",    "Total WOs",          n_total,
                    f"₹{portfolio_rental:,.0f} / mo portfolio", "#E87722")
        + _kpi_card("play_circle",   "Active",             n_active,
                    "currently running", "#10B981")
        + _kpi_card("edit_document", "Draft",              n_draft,
                    "pending confirmation", "#F59E0B")
        + _kpi_card("check_circle",  "Closed / Completed", n_closed,
                    "concluded work orders", "#6B7280")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_wo_mode"   not in st.session_state:
        st.session_state["_wo_mode"]   = "none"
    if "_wo_sel_id" not in st.session_state:
        st.session_state["_wo_sel_id"] = ""

    mode           = st.session_state["_wo_mode"]
    selected_wo_id = st.session_state["_wo_sel_id"]
    selected_wo    = wo_map.get(selected_wo_id) if selected_wo_id else None
    wo_key         = selected_wo_id or "new"

    # Machine dropdown options: exclude Reserved, keep already-allocated
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

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — WO directory
    # ══════════════════════════════════════════════════════════════════════════
    with left_col:

        # Search with icon overlay
        st.markdown(
            "<div class='search-wrap'>"
            "<span class='search-icon-abs msr'>search</span>",
            unsafe_allow_html=True,
        )
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search WOs, customers…",
            key="wo_search_q",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        q = search_q.strip().lower()
        filtered_wos = sorted(
            [
                w for w in work_orders
                if not q
                or q in (w.get("wo_number") or "").lower()
                or q in customer_map.get(w.get("customer_id", ""), {}).get("customer_name", "").lower()
                or q in site_map.get(w.get("site_id", ""), {}).get("site_name", "").lower()
            ],
            key=lambda w: w.get("wo_number") or "",
        )

        count_txt = (
            f"<span style='color:#E87722;font-weight:700;'>{len(filtered_wos)}</span>"
            f" of {n_total} work orders"
            if q else
            f"<span style='font-weight:700;color:#111827;'>{n_total}</span> work orders"
        )
        st.markdown(
            f"<div style='font-size:11px;color:#6B7280;margin:4px 0 10px;'>{count_txt}</div>",
            unsafe_allow_html=True,
        )

        with st.container(height=530):
            if not filtered_wos:
                st.markdown(
                    "<div class='no-results'>"
                    "<span class='nr-icon msr'>search_off</span>"
                    "No work orders match your search."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                for w in filtered_wos:
                    wid        = w.get("id", "")
                    wo_num     = w.get("wo_number") or "—"
                    cust_name  = customer_map.get(w.get("customer_id", ""), {}).get("customer_name", "")
                    site_name  = site_map.get(w.get("site_id", ""), {}).get("site_name", "")
                    status     = w.get("status") or "Draft"
                    start_d    = w.get("start_date") or ""
                    end_d      = w.get("end_date") or ""
                    date_range = f"{start_d} → {end_d}" if start_d else "No dates set"
                    t_rent     = _wo_total_rental(w)
                    rental_html = (
                        f"<span class='wo-rental-badge'>₹{t_rent:,.0f}</span>"
                        if t_rent else ""
                    )
                    is_sel  = (wid == selected_wo_id and mode == "edit")
                    sel_cls = " wo-sel" if is_sel else ""
                    b_cls   = _STATUS_BADGE_MAP.get(status, "badge-draft")
                    site_html = (
                        f"<span class='wo-cl-dot'></span>{site_name}"
                        if site_name else ""
                    )

                    st.markdown(
                        f"<div class='wo-card{sel_cls}'>"
                        f"<div class='wo-card-top'>"
                        f"<span class='wo-num'>{wo_num}</span>"
                        f"<span class='{b_cls}'>{status}</span>"
                        f"{rental_html}"
                        f"</div>"
                        f"<div class='wo-card-sub'>"
                        f"<span class='msr' style='font-size:12px;opacity:.6;'>business</span>"
                        f"{cust_name or '—'}{site_html}"
                        f"</div>"
                        f"<div class='wo-date-range'>"
                        f"<span class='msr' style='font-size:11px;'>calendar_month</span>"
                        f"{date_range}"
                        f"</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "✓ Selected" if is_sel else "Open →",
                        key=f"wosel_{wid}",
                        use_container_width=True,
                        help=wo_num,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state["_wo_mode"]       = "edit"
                        st.session_state["_wo_sel_id"]     = wid
                        st.session_state["_editing_wo_id"] = None   # force sync
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL
    # ══════════════════════════════════════════════════════════════════════════
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='wo-empty'>"
                "<div class='wo-empty-ring'>"
                "<span class='msr' style='font-size:36px;color:#E87722;'>assignment</span>"
                "</div>"
                "<h3>No work order selected</h3>"
                "<p>Select a work order from the list on the left, "
                "or click <strong>+ New WO</strong> to create one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT PANEL ──────────────────────────────────────────────────
        else:
            wo_num_disp   = (selected_wo.get("wo_number") if selected_wo else None) or "New Work Order"
            cust_name_disp = customer_map.get(
                (selected_wo.get("customer_id") if selected_wo else None) or "", {}
            ).get("customer_name", "")
            status_disp   = (selected_wo.get("status") if selected_wo else None) or "Draft"
            b_cls_hero    = _STATUS_BADGE_MAP.get(status_disp, "badge-draft")
            badge_cls     = "hero-badge-edit" if mode == "edit" else "hero-badge-new"
            badge_lbl     = "Editing" if mode == "edit" else "New Work Order"
            meta_line     = f"Customer: {cust_name_disp}" if cust_name_disp else "Unsaved — fill in details below"
            contract_val  = _wo_total_rental(selected_wo) if selected_wo else 0.0

            contract_html = (
                f"<div class='wo-hero-value'>"
                f"<div class='wo-hero-value-label'>Contract / Month</div>"
                f"<div class='wo-hero-value-num'>₹{contract_val:,.0f}</div>"
                f"</div>"
            ) if contract_val else ""

            # Hero banner
            st.markdown(
                f"<div class='wo-hero'>"
                f"<div class='wo-hero-icon'>"
                f"<span class='msr' style='color:#FBD4B4;'>assignment</span>"
                f"</div>"
                f"<div style='flex:1;min-width:0;position:relative;z-index:1;'>"
                f"<div class='wo-hero-num'>{wo_num_disp}</div>"
                f"<div class='wo-hero-meta'>{meta_line}</div>"
                f"<div style='margin-top:7px;display:flex;gap:6px;flex-wrap:wrap;'>"
                f"<span class='{b_cls_hero}'>{status_disp}</span>"
                f"<span class='hero-badge {badge_cls}'>{badge_lbl}</span>"
                f"</div></div>"
                f"{contract_html}"
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── TABS ──────────────────────────────────────────────────────────
            tab_overview, tab_mc, tab_billing, tab_docs = st.tabs([
                "📋 Overview",
                "⚙️ Machine Config",
                "💰 Billing",
                "📄 Documents",
            ])

            # ── Tab 1: Overview ───────────────────────────────────────────────
            with tab_overview:
                # Read-only summary for existing WOs
                if mode == "edit" and selected_wo:
                    sw = selected_wo
                    cust_nm  = customer_map.get(sw.get("customer_id", ""), {}).get("customer_name", "")
                    site_nm  = site_map.get(sw.get("site_id", ""), {}).get("site_name", "")
                    mc_count = 0
                    if sw.get("machine_config"):
                        try:
                            mc_r = json.loads(sw["machine_config"]) if isinstance(sw["machine_config"], str) else sw["machine_config"]
                            mc_count = len([
                                r for r in (mc_r if isinstance(mc_r, list) else [])
                                if r.get("machine_label") or r.get("machine_id")
                            ])
                        except Exception:
                            pass
                    _section_hdr("info", "Work Order Summary")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("WO Number",    sw.get("wo_number"))
                        + _info_field("Status",       sw.get("status") or "Draft")
                        + _info_field("Customer",     cust_nm)
                        + _info_field("Site",         site_nm)
                        + _info_field("Start Date",   sw.get("start_date"))
                        + _info_field("End Date",     sw.get("end_date"))
                        + _info_field("Client WO #",  sw.get("client_work_ordernumber"))
                        + _info_field("Machines",     str(mc_count) if mc_count else None)
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)

                # Editable form fields (both new and edit)
                _section_hdr("edit", "Edit Details" if mode == "edit" else "Work Order Details")

                with st.container(border=True):
                    _section_hdr("business", "Customer & Site")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.selectbox(
                            "Customer *",
                            options=[""] + list(customer_map),
                            format_func=lambda cid: "Select customer" if not cid
                                else customer_map[cid].get("customer_name", "Unknown"),
                            key="wo_customer_id",
                        )
                    with col2:
                        selected_site_id = st.selectbox(
                            "Site *",
                            options=[""] + list(site_map),
                            format_func=lambda sid: "Select site" if not sid
                                else site_map[sid].get("site_name", "Unknown"),
                            key="wo_site_id",
                        )

                with st.container(border=True):
                    _section_hdr("calendar_month", "Schedule")
                    d1, d2 = st.columns(2)
                    with d1:
                        selected_start_date = st.date_input("Start Date *", key="wo_start_date")
                    with d2:
                        selected_end_date = st.date_input("End Date", key="wo_end_date")
                    cwo1, _ = st.columns([2, 2])
                    with cwo1:
                        selected_client_wo = st.text_input(
                            "Client Work Order Number", placeholder="Client WO#",
                            key="wo_client_wo",
                        )

            # ── Tab 2: Machine Config ─────────────────────────────────────────
            with tab_mc:
                ref_date_for_dialog = st.session_state.get("wo_start_date")
                if not isinstance(ref_date_for_dialog, date):
                    ref_date_for_dialog = None

                st.markdown(
                    "<p style='font-size:12px;color:#6b7280;margin:0 0 12px;'>"
                    "Add one or more machines. <strong>Calendar Month</strong> cycle dates "
                    "auto-fill from the WO Start Date.</p>",
                    unsafe_allow_html=True,
                )

                # Initialize mc_rows from WO data or empty
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

                # Machine rows table
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
                        c1, c2, c3, c4, c5, c6, c7 = st.columns([4, 2, 3, 3, 2, 1, 1])
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
                            if st.button("Edit", key=f"mc_edit_{idx}_{wo_key}", use_container_width=True):
                                _init_dialog_state(row, label_to_details, ref_date_for_dialog)
                                _machine_row_dialog(
                                    row_idx=idx, mc_rows=mc_rows, wo_key=wo_key,
                                    machine_opts=machine_opts, label_to_id=label_to_id,
                                    label_to_details=label_to_details, ref_date=ref_date_for_dialog,
                                )
                        with c7:
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

                # Add Machine button
                if st.button("+ Add Machine", key=f"mc_add_{wo_key}"):
                    _init_dialog_state({}, label_to_details, ref_date_for_dialog)
                    _machine_row_dialog(
                        row_idx=-1, mc_rows=mc_rows, wo_key=wo_key,
                        machine_opts=machine_opts, label_to_id=label_to_id,
                        label_to_details=label_to_details, ref_date=ref_date_for_dialog,
                    )

                # Summary bar
                valid_mc = [r for r in mc_rows if r.get("machine_label") or r.get("machine_id")]
                if valid_mc:
                    total_mc_rental = sum(float(r.get("rental_per_month") or 0) for r in valid_mc)
                    st.markdown(
                        f"<div class='mc-summary-bar'>"
                        f"<span style='color:#6b7280;'>Machines: "
                        f"<strong style='color:#111827;'>{len(valid_mc)}</strong></span>"
                        f"<span style='color:#6b7280;'>Total Rental / Month: "
                        f"<strong style='color:#E87722;'>₹{total_mc_rental:,.0f}</strong></span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            # ── Tab 3: Billing ────────────────────────────────────────────────
            with tab_billing:
                billing_rows = [
                    r for r in st.session_state.get(f"mc_rows_{wo_key}", [])
                    if r.get("machine_label") or r.get("machine_id")
                ]
                if billing_rows:
                    _section_hdr("receipt_long", "Billing Summary")
                    total_billed = 0.0
                    for r in billing_rows:
                        rent = float(r.get("rental_per_month") or 0)
                        total_billed += rent
                        cs = r.get("billing_cycle_start_date") or "—"
                        ce = r.get("billing_cycle_end_date") or "—"
                        cycle_range = f"{cs} → {ce}" if cs != "—" else "—"
                        make_model  = " / ".join(filter(None, [r.get("make", ""), r.get("model", "")])) or "—"
                        st.markdown(
                            f"<div class='billing-card'>"
                            f"<div class='billing-card-top'>"
                            f"<span class='billing-machine-name'>"
                            f"<span class='msr' style='font-size:13px;vertical-align:-2px;"
                            f"margin-right:4px;color:#9CA3AF;'>precision_manufacturing</span>"
                            f"{r.get('machine_label') or '—'}</span>"
                            f"<span class='billing-amount'>₹{rent:,.0f}</span>"
                            f"</div>"
                            f"<div class='billing-meta'>"
                            f"<div class='billing-meta-item'>Type: <strong>{r.get('billing_type') or '—'}</strong></div>"
                            f"<div class='billing-meta-item'>Cycle: <strong>{r.get('billing_cycle') or '—'}</strong></div>"
                            f"<div class='billing-meta-item'>Cycle Dates: <strong>{cycle_range}</strong></div>"
                            f"<div class='billing-meta-item'>Make / Model: <strong>{make_model}</strong></div>"
                            f"</div></div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        f"<div style='display:flex;justify-content:flex-end;"
                        f"padding:10px 16px;background:#FFF8F4;border:1px solid #FDDCBA;"
                        f"border-radius:8px;margin-top:4px;'>"
                        f"<span style='font-size:13px;color:#6b7280;'>Total / Month:&nbsp;</span>"
                        f"<span style='font-size:16px;font-weight:800;color:#E87722;'>₹{total_billed:,.0f}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    _placeholder_tab(
                        "receipt_long",
                        "No billing data yet",
                        "Add machines in the Machine Config tab to see billing details here.",
                    )

            # ── Tab 4: Documents ──────────────────────────────────────────────
            with tab_docs:
                _placeholder_tab(
                    "folder_open",
                    "Documents coming soon",
                    "WO attachments, PO copies, and site reports will be managed here.",
                )

            # ── Action buttons ─────────────────────────────────────────────────
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            sv1, sv2, sv3, _ = st.columns([3, 1, 1, 2])
            with sv1:
                save_clicked = st.button(
                    "💾  Update Work Order" if mode == "edit" else "💾  Create Work Order",
                    type="primary",
                    use_container_width=True,
                    key="wo_save_btn",
                )
            with sv2:
                if st.button("Cancel", use_container_width=True, key="wo_cancel_btn"):
                    st.session_state["_wo_mode"]   = "none"
                    st.session_state["_wo_sel_id"] = ""
                    st.rerun()
            with sv3:
                if st.button("↻ Refresh", use_container_width=True, key="wo_refresh_btn"):
                    st.session_state["_editing_wo_id"] = None
                    st.rerun()

            # ── Save logic ─────────────────────────────────────────────────────
            if save_clicked:
                _cust_id   = st.session_state.get("wo_customer_id", "")
                _site_id   = st.session_state.get("wo_site_id", "")
                _start     = st.session_state.get("wo_start_date")
                _end       = st.session_state.get("wo_end_date")
                _client_wo = st.session_state.get("wo_client_wo", "")

                if not _cust_id:
                    st.error("Customer is required.")
                elif not _site_id:
                    st.error("Site is required.")
                elif not _start:
                    st.error("Start Date is required.")
                else:
                    mc_rows_save = st.session_state.get(f"mc_rows_{wo_key}", [])
                    valid_rows   = [r for r in mc_rows_save if r.get("machine_label") or r.get("machine_id")]
                    if not valid_rows:
                        st.error("Add at least one machine.")
                    else:
                        machine_config_json = json.dumps(valid_rows)
                        payload = dict(
                            customer_id=_cust_id,
                            site_id=_site_id,
                            start_date=_start.isoformat() if isinstance(_start, date) else None,
                            end_date=_end.isoformat()     if isinstance(_end,   date) else None,
                            client_work_ordernumber=_client_wo or None,
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
                                new_id = created.get("id", "")
                                if new_id:
                                    st.session_state["_wo_mode"]       = "edit"
                                    st.session_state["_wo_sel_id"]     = new_id
                                    st.session_state["_editing_wo_id"] = None
                            # Mark every allocated machine as Reserved
                            for row in valid_rows:
                                mid = row.get("machine_id") or label_to_id.get(row.get("machine_label", ""))
                                if mid:
                                    try:
                                        sb.update_machine(mid, {"operational_status": "Reserved"})
                                    except Exception:
                                        pass
                            work_orders = fetch_work_orders()
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not save work order: {exc}")
