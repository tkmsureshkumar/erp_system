"""
erp/views/fleetstatus.py
Fleet Status Report — live status of all fleet machines.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _mc_rental_for_machine(mc_raw, machine_id: str) -> float | None:
    """Return rental_per_month for a specific machine_id in a WO's machine_config JSON."""
    if not mc_raw or not machine_id:
        return None
    try:
        records = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        if isinstance(records, list):
            for r in records:
                if r.get("machine_id") == machine_id:
                    v = r.get("rental_per_month")
                    return float(v) if v is not None else None
    except Exception:
        pass
    return None


def _deployment_date_for_machine(dep: dict, machine_id: str) -> str:
    """Extract billing_start_date (falling back to transaction_start_date) for a machine."""
    if not dep:
        return "—"
    md_raw = dep.get("machine_deployments")
    if md_raw:
        try:
            mds = json.loads(md_raw) if isinstance(md_raw, str) else md_raw
            if isinstance(mds, list):
                for md in mds:
                    if md.get("machine_id") == machine_id:
                        d = md.get("billing_start_date") or md.get("transaction_start_date")
                        if d:
                            return str(d)[:10]
        except Exception:
            pass
    d = dep.get("deployment_date")
    if d:
        return str(d)[:10]
    return "—"


def _operator_from_schedule(schedule_data_raw) -> str:
    """Return the most common non-empty operator name in a schedule_data JSON string."""
    if not schedule_data_raw:
        return "—"
    try:
        rows = json.loads(schedule_data_raw) if isinstance(schedule_data_raw, str) else schedule_data_raw
        if isinstance(rows, list):
            ops = [
                r.get("operator", "").strip()
                for r in rows
                if r.get("operator", "").strip()
            ]
            if ops:
                return Counter(ops).most_common(1)[0][0]
    except Exception:
        pass
    return "—"


def _section_header(title: str) -> None:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:14px;'>"
        f"{title}</div>",
        unsafe_allow_html=True,
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Fleet Status Report</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    machines:       list[dict] = []
    work_orders:    list[dict] = []
    customers_list: list[dict] = []
    sites_list:     list[dict] = []
    deployments:    list[dict] = []
    work_logs:      list[dict] = []
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
        deployments    = sb.list_deployments()
        work_logs      = sb.list_all_worklogs()
    except Exception as exc:
        st.error(f"Could not load fleet data: {exc}")
        return

    # ── Lookup maps ──────────────────────────────────────────────────────────
    today    = date.today()
    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name", "—")     for s in sites_list     if s.get("id")}
    dep_by_wo = {d["work_order_id"]: d for d in deployments if d.get("work_order_id")}

    # machine_id → list of currently active work orders
    wo_by_machine: dict[str, list[dict]] = {}
    for wo in work_orders:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd is None:
            continue
        if not (sd <= today and (ed is None or ed >= today)):
            continue
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            if isinstance(mc_list, list):
                for mc_row in mc_list:
                    mid = mc_row.get("machine_id")
                    if mid:
                        wo_by_machine.setdefault(mid, []).append(wo)
        except Exception:
            pass

    # (wo_id, machine_id) → operator from most recent worklog
    # "year" field stores "Month YYYY" strings e.g. "July 2026"
    def _log_sort_key(wl: dict) -> tuple[int, int]:
        raw = str(wl.get("year") or "")
        try:
            dt = datetime.strptime(raw, "%B %Y")
            return (dt.year, dt.month)
        except (ValueError, TypeError):
            pass
        try:
            return (int(raw), int(wl.get("month") or 0))
        except (ValueError, TypeError):
            return (0, 0)

    log_latest: dict[tuple[str, str], tuple[tuple[int, int], str]] = {}
    for wl in work_logs:
        wo_id = wl.get("work_order_id", "")
        mid   = wl.get("machine_id", "")
        sk    = _log_sort_key(wl)
        op    = _operator_from_schedule(wl.get("schedule_data"))
        key   = (wo_id, mid)
        prev  = log_latest.get(key)
        if prev is None or sk > prev[0]:
            log_latest[key] = (sk, op)
    log_op_map = {k: v[1] for k, v in log_latest.items()}

    # ── Build fleet rows ──────────────────────────────────────────────────────
    rows: list[dict] = []
    for m in machines:
        mid       = m.get("id", "")
        wo        = (wo_by_machine.get(mid) or [None])[0]

        customer  = cust_map.get((wo or {}).get("customer_id", ""), "—") if wo else "—"
        site      = site_map.get((wo or {}).get("site_id", ""),     "—") if wo else "—"
        rental    = _mc_rental_for_machine(wo.get("machine_config") if wo else None, mid)
        dep       = dep_by_wo.get((wo or {}).get("id", ""), {}) if wo else {}
        dep_date  = _deployment_date_for_machine(dep, mid)
        operator  = log_op_map.get((wo.get("id", ""), mid), "—") if wo else "—"

        rows.append({
            "Serial Number":   m.get("serial_number")    or "—",
            "Machine Code":    m.get("asset_code")        or "—",
            "Make":            m.get("make")              or "—",
            "Model":           m.get("model")             or "—",
            "Working Height":  m.get("working_capacity")  or "—",
            "Customer":        customer,
            "Site":            site,
            "Current Status":  m.get("operational_status") or "—",
            "Monthly Rental":  rental,
            "Operator":        operator,
            "Deployment Date": dep_date,
            # internal — filter only, not shown in table
            "_machine_type":   m.get("machine_type", ""),
        })

    # ── Filters ───────────────────────────────────────────────────────────────
    _section_header("Filters")

    fc1, fc2, fc3 = st.columns(3)
    fc4, fc5, fc6 = st.columns(3)

    with fc1:
        st.markdown('<p class="filter-label">Status</p>', unsafe_allow_html=True)
        status_opts = ["All"] + sorted({r["Current Status"] for r in rows if r["Current Status"] != "—"})
        sel_status = st.selectbox("Status", status_opts, label_visibility="collapsed", key="fsr_status")

    with fc2:
        st.markdown('<p class="filter-label">Customer</p>', unsafe_allow_html=True)
        cust_opts = ["All"] + sorted({r["Customer"] for r in rows if r["Customer"] != "—"})
        sel_cust = st.selectbox("Customer", cust_opts, label_visibility="collapsed", key="fsr_customer")

    with fc3:
        st.markdown('<p class="filter-label">Site</p>', unsafe_allow_html=True)
        site_opts = ["All"] + sorted({r["Site"] for r in rows if r["Site"] != "—"})
        sel_site = st.selectbox("Site", site_opts, label_visibility="collapsed", key="fsr_site")

    with fc4:
        st.markdown('<p class="filter-label">Machine Type</p>', unsafe_allow_html=True)
        mtype_opts = ["All"] + sorted({r["_machine_type"] for r in rows if r["_machine_type"]})
        sel_mtype = st.selectbox("Machine Type", mtype_opts, label_visibility="collapsed", key="fsr_mtype")

    with fc5:
        st.markdown('<p class="filter-label">Make</p>', unsafe_allow_html=True)
        make_opts = ["All"] + sorted({r["Make"] for r in rows if r["Make"] != "—"})
        sel_make = st.selectbox("Make", make_opts, label_visibility="collapsed", key="fsr_make")

    with fc6:
        st.markdown('<p class="filter-label">Model</p>', unsafe_allow_html=True)
        model_opts = ["All"] + sorted({r["Model"] for r in rows if r["Model"] != "—"})
        sel_model = st.selectbox("Model", model_opts, label_visibility="collapsed", key="fsr_model")

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = rows
    if sel_status != "All":
        filtered = [r for r in filtered if r["Current Status"] == sel_status]
    if sel_cust != "All":
        filtered = [r for r in filtered if r["Customer"] == sel_cust]
    if sel_site != "All":
        filtered = [r for r in filtered if r["Site"] == sel_site]
    if sel_mtype != "All":
        filtered = [r for r in filtered if r["_machine_type"] == sel_mtype]
    if sel_make != "All":
        filtered = [r for r in filtered if r["Make"] == sel_make]
    if sel_model != "All":
        filtered = [r for r in filtered if r["Model"] == sel_model]

    # ── Table ─────────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    _section_header(f"Fleet Status — {len(filtered)} machine{'s' if len(filtered) != 1 else ''}")

    _DISPLAY_COLS = [
        "Serial Number", "Machine Code", "Make", "Model", "Working Height",
        "Customer", "Site", "Current Status", "Monthly Rental", "Operator",
        "Deployment Date",
    ]

    if filtered:
        df = pd.DataFrame(
            [{k: r[k] for k in _DISPLAY_COLS} for r in filtered],
            columns=_DISPLAY_COLS,
        )
        df["Monthly Rental"] = df["Monthly Rental"].apply(
            lambda v: f"₹ {v:,.0f}" if isinstance(v, (int, float)) else "—"
        )

        st.dataframe(df, use_container_width=True, hide_index=True)

        csv_df = df.copy()
        csv_df["Monthly Rental"] = [
            r["Monthly Rental"] if isinstance(r["Monthly Rental"], (int, float))
            else (
                r["Monthly Rental"].replace("₹ ", "").replace(",", "")
                if isinstance(r["Monthly Rental"], str) else ""
            )
            for r in filtered
        ]
        st.download_button(
            label="Export CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"fleet_status_{today.isoformat()}.csv",
            mime="text/csv",
            key="fsr_export",
        )
    else:
        st.info("No machines match the selected filters.")
