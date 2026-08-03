"""
erp/views/fleetstatus.py
Fleet Status Report — real-time snapshot of the entire fleet.
One row per machine: Machine ID · Make · Model · Serial No · Status ·
Customer · Site · Monthly Rental · Deployment Date.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient

# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin: 0 0 28px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 16px 20px 12px;
    position: relative; overflow: hidden;
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
    font-size: 9px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 30px; font-weight: 800; color: #111827;
    line-height: 1; margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 10px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 14px; right: 16px;
    font-size: 20px; opacity: .10;
}

/* ── Section header ─────────────────────────────────────────────────── */
.sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Fleet table ─────────────────────────────────────────────────────── */
.fleet-wrap {
    overflow-x: auto;
    border-radius: 12px;
    border: 1px solid #E2EBF0;
    margin-top: 6px;
}
.fleet-table {
    width: 100%; border-collapse: collapse;
    font-size: 12px; font-family: inherit;
}
.fleet-table thead tr {
    background: #F8FAFC;
    border-bottom: 2px solid #E2EBF0;
}
.fleet-table thead th {
    padding: 11px 14px;
    font-size: 9px; font-weight: 700;
    letter-spacing: .11em; text-transform: uppercase;
    color: #6B7280; text-align: left;
    white-space: nowrap;
}
.fleet-table tbody tr {
    border-bottom: 1px solid #F1F5F9;
    transition: background .12s;
}
.fleet-table tbody tr:last-child { border-bottom: none; }
.fleet-table tbody tr:hover { background: #F8FAFC; }
.fleet-table tbody td {
    padding: 10px 14px;
    color: #111827; font-size: 12px;
    white-space: nowrap;
}
.fleet-table tbody td.muted { color: #9CA3AF; }
.fleet-table tbody td.rental {
    font-weight: 700; color: #059669;
    font-variant-numeric: tabular-nums;
}
.fleet-table tbody td.machine-id {
    font-weight: 700; color: #1D4ED8;
    font-family: monospace; font-size: 11px;
}

/* ── Status badges ───────────────────────────────────────────────────── */
.st-badge {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 10px; font-weight: 700;
    padding: 3px 10px; border-radius: 20px;
    letter-spacing: .04em; white-space: nowrap;
}
.st-on-rent   { background:#D1FAE5; color:#065F46; border:1px solid #6EE7B7; }
.st-available { background:#DBEAFE; color:#1E40AF; border:1px solid #93C5FD; }
.st-reserved  { background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; }
.st-breakdown { background:#FEE2E2; color:#991B1B; border:1px solid #FCA5A5; }
.st-mobilize  { background:#EDE9FE; color:#5B21B6; border:1px solid #C4B5FD; }
.st-other     { background:#F3F4F6; color:#374151; border:1px solid #D1D5DB; }

/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-state {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 64px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px; text-align: center;
    margin-top: 8px;
}
.empty-state h3 { font-size: 16px; font-weight: 700; color: #111827; margin: 12px 0 6px; }
.empty-state p  { font-size: 13px; color: #9CA3AF; max-width: 260px; line-height: 1.6; margin: 0; }
</style>
"""

# ── Status badge helper ───────────────────────────────────────────────────────

_STATUS_DOT = {
    "On Rent":      ("st-on-rent",   "●"),
    "Available":    ("st-available", "●"),
    "Reserved":     ("st-reserved",  "●"),
    "Breakdown":    ("st-breakdown", "●"),
    "Under Repair": ("st-breakdown", "●"),
    "Repair":       ("st-breakdown", "●"),
    "Mobilizing":   ("st-mobilize",  "●"),
}

def _status_badge(status: str) -> str:
    cls, dot = _STATUS_DOT.get(status, ("st-other", "●"))
    return f"<span class='st-badge {cls}'>{dot} {status}</span>"


# ── Data helpers ──────────────────────────────────────────────────────────────

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


def _mc_rental(mc_raw, machine_id: str) -> float | None:
    if not mc_raw or not machine_id:
        return None
    try:
        recs = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        if isinstance(recs, list):
            for r in recs:
                if r.get("machine_id") == machine_id:
                    v = r.get("rental_per_month")
                    return float(v) if v is not None else None
    except Exception:
        pass
    return None


def _deploy_date(dep: dict, machine_id: str) -> str:
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
    return str(d)[:10] if d else "—"


def _kpi_card(icon: str, label: str, value, sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _sec_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Fleet Status Report</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
        deployments    = sb.list_deployments()
    except Exception as exc:
        st.error(f"Could not load fleet data: {exc}")
        return

    today    = date.today()
    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    dep_by_wo = {d["work_order_id"]: d for d in deployments if d.get("work_order_id")}

    # machine_id → first active work order
    wo_by_machine: dict[str, dict] = {}
    for wo in work_orders:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd is None or not (sd <= today and (ed is None or ed >= today)):
            continue
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            if isinstance(mc_list, list):
                for mc_row in mc_list:
                    mid = mc_row.get("machine_id")
                    if mid and mid not in wo_by_machine:
                        wo_by_machine[mid] = wo
        except Exception:
            pass

    # ── Build rows ────────────────────────────────────────────────────────────
    rows: list[dict] = []
    for m in machines:
        mid    = m.get("id", "")
        wo     = wo_by_machine.get(mid)
        status = m.get("operational_status") or "—"
        dep    = dep_by_wo.get((wo or {}).get("id", ""), {}) if wo else {}
        rental = _mc_rental(wo.get("machine_config") if wo else None, mid)

        rows.append({
            "Machine ID":      m.get("asset_code")       or "—",
            "Make":            m.get("make")              or "—",
            "Model":           m.get("model")             or "—",
            "Serial Number":   m.get("serial_number")     or "—",
            "Status":          status,
            "Customer":        cust_map.get((wo or {}).get("customer_id", ""), "—") if wo else "—",
            "Site":            (
                site_map.get((wo or {}).get("site_id", ""), "—")
                if wo else
                site_map.get(m.get("current_location") or "", "—")
            ),
            "Monthly Rental":  rental,
            "Deployment Date": _deploy_date(dep, mid),
            # filter-only
            "_machine_type":   m.get("machine_type", ""),
            "_make":           m.get("make", ""),
        })

    # ── KPI strip ─────────────────────────────────────────────────────────────
    n_total     = len(rows)
    n_on_rent   = sum(1 for r in rows if r["Status"] == "On Rent")
    n_available = sum(1 for r in rows if r["Status"] == "Available")
    n_reserved  = sum(1 for r in rows if r["Status"] == "Reserved")
    n_breakdown = sum(
        1 for r in rows
        if (r["Status"] or "").lower() in ("breakdown", "under repair", "repair")
    )
    util_pct    = round(n_on_rent / n_total * 100) if n_total else 0

    st.markdown(
        "<div class='kpi-grid'>"
        + _kpi_card("precision_manufacturing", "Total Fleet",   n_total,
                    f"{len({r['_machine_type'] for r in rows if r['_machine_type']})} types",
                    "#2563EB")
        + _kpi_card("engineering",  "On Rent",   n_on_rent,
                    f"{util_pct}% utilization", "#10B981")
        + _kpi_card("check_circle", "Available", n_available,
                    "ready to deploy",          "#8B5CF6")
        + _kpi_card("bookmark",     "Reserved",  n_reserved,
                    "pending billing start",    "#F59E0B")
        + _kpi_card("build",        "Breakdown", n_breakdown,
                    "needs attention",          "#EF4444")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.container(border=True):
        _sec_hdr("filter_list", "Filters")
        fc1, fc2, fc3, fc4 = st.columns(4)

        with fc1:
            status_opts = ["All"] + sorted({r["Status"] for r in rows if r["Status"] != "—"})
            sel_status = st.selectbox("Status", status_opts,
                                      label_visibility="collapsed", key="fsr_status")
        with fc2:
            cust_opts = ["All"] + sorted({r["Customer"] for r in rows if r["Customer"] != "—"})
            sel_cust = st.selectbox("Customer", cust_opts,
                                    label_visibility="collapsed", key="fsr_cust")
        with fc3:
            mtype_opts = ["All"] + sorted({r["_machine_type"] for r in rows if r["_machine_type"]})
            sel_mtype = st.selectbox("Machine Type", mtype_opts,
                                     label_visibility="collapsed", key="fsr_mtype")
        with fc4:
            make_opts = ["All"] + sorted({r["_make"] for r in rows if r["_make"]})
            sel_make = st.selectbox("Make", make_opts,
                                    label_visibility="collapsed", key="fsr_make")

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = rows
    if sel_status != "All":
        filtered = [r for r in filtered if r["Status"] == sel_status]
    if sel_cust != "All":
        filtered = [r for r in filtered if r["Customer"] == sel_cust]
    if sel_mtype != "All":
        filtered = [r for r in filtered if r["_machine_type"] == sel_mtype]
    if sel_make != "All":
        filtered = [r for r in filtered if r["_make"] == sel_make]

    # ── Table header row ──────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    lbl_col, btn_col = st.columns([7, 1])
    with lbl_col:
        _sec_hdr(
            "table_view",
            f"Fleet — {len(filtered)} of {n_total} machine{'s' if n_total != 1 else ''}",
        )
    with btn_col:
        if filtered:
            export_df = pd.DataFrame([
                {
                    "Machine ID":      r["Machine ID"],
                    "Make":            r["Make"],
                    "Model":           r["Model"],
                    "Serial Number":   r["Serial Number"],
                    "Status":          r["Status"],
                    "Customer":        r["Customer"],
                    "Site":            r["Site"],
                    "Monthly Rental":  r["Monthly Rental"] if isinstance(r["Monthly Rental"], (int, float)) else "",
                    "Deployment Date": r["Deployment Date"],
                }
                for r in filtered
            ])
            st.download_button(
                "Export CSV",
                data=export_df.to_csv(index=False).encode("utf-8"),
                file_name=f"fleet_status_{today.isoformat()}.csv",
                mime="text/csv",
                key="fsr_export",
                use_container_width=True,
            )

    # ── HTML fleet table ──────────────────────────────────────────────────────
    if not filtered:
        st.markdown(
            "<div class='empty-state'>"
            "<span class='msr' style='font-size:36px;color:#9CA3AF;'>search_off</span>"
            "<h3>No machines match filters</h3>"
            "<p>Adjust your filter selections to see fleet machines.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    thead = (
        "<thead><tr>"
        "<th>#</th>"
        "<th>Machine ID</th>"
        "<th>Make</th>"
        "<th>Model</th>"
        "<th>Serial Number</th>"
        "<th>Status</th>"
        "<th>Customer</th>"
        "<th>Site</th>"
        "<th>Monthly Rental</th>"
        "<th>Deployment Date</th>"
        "</tr></thead>"
    )

    tbody_rows = []
    for i, r in enumerate(filtered, 1):
        rental_raw = r["Monthly Rental"]
        rental_disp = (
            f"<td class='rental'>₹ {rental_raw:,.0f}</td>"
            if isinstance(rental_raw, (int, float))
            else "<td class='muted'>—</td>"
        )
        customer_td = (
            f"<td>{r['Customer']}</td>"
            if r["Customer"] != "—"
            else "<td class='muted'>—</td>"
        )
        site_td = (
            f"<td>{r['Site']}</td>"
            if r["Site"] != "—"
            else "<td class='muted'>—</td>"
        )
        dep_td = (
            f"<td>{r['Deployment Date']}</td>"
            if r["Deployment Date"] != "—"
            else "<td class='muted'>—</td>"
        )
        tbody_rows.append(
            f"<tr>"
            f"<td class='muted'>{i}</td>"
            f"<td class='machine-id'>{r['Machine ID']}</td>"
            f"<td>{r['Make']}</td>"
            f"<td>{r['Model']}</td>"
            f"<td>{r['Serial Number']}</td>"
            f"<td>{_status_badge(r['Status'])}</td>"
            f"{customer_td}"
            f"{site_td}"
            f"{rental_disp}"
            f"{dep_td}"
            f"</tr>"
        )

    table_html = (
        "<div class='fleet-wrap'>"
        "<table class='fleet-table'>"
        f"{thead}"
        f"<tbody>{''.join(tbody_rows)}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)
