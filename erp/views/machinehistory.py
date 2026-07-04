"""
erp/views/machinehistory.py
Machine History Report — complete deployment history for a selected machine.
"""
from __future__ import annotations

import json
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


def _fmt_date(value) -> str:
    d = _parse_date(value)
    return d.strftime("%d %b %Y") if d else "—"


def _mc_rental_for_machine(mc_raw, machine_id: str) -> float | None:
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


def _dep_date_for_machine(dep: dict, machine_id: str, wo_start: str | None) -> str:
    """
    Return the deployment date for a specific machine within a deployment record.
    Priority: billing_start_date → transaction_start_date → WO start_date.
    """
    md_raw = dep.get("machine_deployments") if dep else None
    if md_raw:
        try:
            mds = json.loads(md_raw) if isinstance(md_raw, str) else md_raw
            if isinstance(mds, list):
                for md in mds:
                    if md.get("machine_id") == machine_id:
                        d = (
                            md.get("billing_start_date")
                            or md.get("transaction_start_date")
                            or md.get("site_reached_date")
                        )
                        if d:
                            return _fmt_date(d)
        except Exception:
            pass
    if dep and dep.get("deployment_date"):
        return _fmt_date(dep["deployment_date"])
    return _fmt_date(wo_start)


def _section_header(title: str) -> None:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:14px;'>"
        f"{title}</div>",
        unsafe_allow_html=True,
    )


def _info_chip(label: str, value: str, color: str = "#111827") -> str:
    return (
        f"<div style='display:inline-flex;flex-direction:column;margin-right:32px;"
        f"margin-bottom:8px;'>"
        f"<span style='font-size:9px;font-weight:700;letter-spacing:.12em;"
        f"text-transform:uppercase;color:#9ca3af;'>{label}</span>"
        f"<span style='font-size:15px;font-weight:700;color:{color};margin-top:2px;'>"
        f"{value}</span></div>"
    )


def _status_color(status: str) -> str:
    s = (status or "").lower()
    if s == "active":
        return "#16a34a"
    if s in ("closed", "completed"):
        return "#6b7280"
    return "#E87722"


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Machine History Report</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
        deployments    = sb.list_deployments()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    if not machines:
        st.info("No machines found.")
        return

    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    dep_by_wo = {d["work_order_id"]: d for d in deployments if d.get("work_order_id")}

    # ── Machine selector ──────────────────────────────────────────────────────
    _section_header("Select Machine")

    def _machine_label(m: dict) -> str:
        code  = m.get("asset_code", "")
        make  = m.get("make", "")
        model = m.get("model", "")
        sn    = m.get("serial_number", "")
        parts = [p for p in [make, model] if p]
        desc  = " ".join(parts)
        label = f"{code}" if code else m.get("machine_type", "Unknown")
        if desc:
            label += f" — {desc}"
        if sn:
            label += f"  (S/N: {sn})"
        return label

    machine_options = sorted(machines, key=lambda m: m.get("asset_code") or "")
    machine_labels  = [_machine_label(m) for m in machine_options]
    machine_ids     = [m.get("id", "") for m in machine_options]

    sel_label = st.selectbox(
        "Machine",
        machine_labels,
        label_visibility="collapsed",
        key="mh_machine",
    )
    sel_idx = machine_labels.index(sel_label)
    sel_id  = machine_ids[sel_idx]
    sel_m   = machine_options[sel_idx]

    # ── Machine info card ─────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    _section_header("Machine Details")

    op_status = sel_m.get("operational_status", "—")
    cn_status = sel_m.get("condition_status",   "—")
    op_color  = "#2563eb" if op_status == "On Rent" else (
                "#16a34a" if op_status == "Available" else (
                "#ef4444" if cn_status == "Breakdown" else "#E87722"))

    chips = "".join([
        _info_chip("Asset Code",    sel_m.get("asset_code",    "—")),
        _info_chip("Type",          sel_m.get("machine_type",  "—")),
        _info_chip("Make",          sel_m.get("make",          "—")),
        _info_chip("Model",         sel_m.get("model",         "—")),
        _info_chip("Serial Number", sel_m.get("serial_number", "—")),
        _info_chip("Capacity",      sel_m.get("working_capacity", "—")),
        _info_chip("Status",        op_status, op_color),
        _info_chip("Condition",     cn_status),
        _info_chip("Location",      sel_m.get("current_location", "—")),
    ])
    st.markdown(
        f"<div style='background:#fff;border:1px solid #e5e7eb;border-radius:6px;"
        f"padding:20px 24px;box-shadow:0 1px 4px rgba(0,0,0,.06);'>"
        f"{chips}</div>",
        unsafe_allow_html=True,
    )

    # ── Build deployment history ───────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    history: list[dict] = []
    for wo in work_orders:
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        except Exception:
            continue
        if not isinstance(mc_list, list):
            continue

        mc_row = next((r for r in mc_list if r.get("machine_id") == sel_id), None)
        if mc_row is None:
            continue

        wo_id   = wo.get("id", "")
        dep     = dep_by_wo.get(wo_id, {})
        rental  = mc_row.get("rental_per_month")
        end_d   = _parse_date(wo.get("end_date"))
        dep_status = (dep.get("deployment_status") or "—") if dep else "—"

        # Compute a sortable date for ordering
        dep_date_raw = None
        md_raw = dep.get("machine_deployments") if dep else None
        if md_raw:
            try:
                mds = json.loads(md_raw) if isinstance(md_raw, str) else md_raw
                if isinstance(mds, list):
                    for md in mds:
                        if md.get("machine_id") == sel_id:
                            dep_date_raw = (
                                md.get("billing_start_date")
                                or md.get("transaction_start_date")
                                or md.get("site_reached_date")
                            )
                            break
            except Exception:
                pass
        if not dep_date_raw and dep:
            dep_date_raw = dep.get("deployment_date")
        if not dep_date_raw:
            dep_date_raw = wo.get("start_date")

        wo_num    = wo.get("wo_number",             "—") or "—"
        client_wo = wo.get("client_work_ordernumber", "") or ""
        wo_display = wo_num
        if client_wo and client_wo != wo_num:
            wo_display = f"{wo_num} / {client_wo}"

        history.append({
            "_sort_date": _parse_date(dep_date_raw) or date.min,
            "Customer":          cust_map.get(wo.get("customer_id", ""), "—"),
            "Site":              site_map.get(wo.get("site_id",       ""), "—"),
            "Deployment Date":   _dep_date_for_machine(dep, sel_id, wo.get("start_date")),
            "Release Date":      _fmt_date(end_d) if end_d else "Active",
            "Work Order":        wo_display,
            "Monthly Rental":    f"₹ {float(rental):,.0f}" if rental is not None else "—",
            "Deployment Status": dep_status,
        })

    # ── Display ───────────────────────────────────────────────────────────────
    if not history:
        _section_header("Deployment History")
        st.info("No deployment history found for this machine.")
        return

    history.sort(key=lambda r: r["_sort_date"], reverse=True)

    _section_header(f"Deployment History — {len(history)} record{'s' if len(history) != 1 else ''}")

    _COLS = [
        "Customer", "Site", "Deployment Date", "Release Date",
        "Work Order", "Monthly Rental", "Deployment Status",
    ]
    df = pd.DataFrame([{k: r[k] for k in _COLS} for r in history], columns=_COLS)

    # Color-code Deployment Status column
    def _style_status(val):
        clr = _status_color(str(val))
        return f"color:{clr};font-weight:700;"

    st.dataframe(
        df.style.applymap(_style_status, subset=["Deployment Status"]),
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        label="Export CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"machine_history_{sel_m.get('asset_code', sel_id)}.csv",
        mime="text/csv",
        key="mh_export",
    )
