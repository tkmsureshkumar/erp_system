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


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
.kpi-grid {
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
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 10px;
    display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 34px; font-weight: 800;
    color: #111827; line-height: 1;
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub {
    font-size: 11px; color: #6B7280;
}
.kpi-icon {
    position: absolute; top: 16px; right: 18px;
    font-size: 22px; opacity: .12;
}
/* ── Section header ─────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}
/* ── Machine hero card ──────────────────────────────────────────────── */
.mach-hero {
    background: linear-gradient(135deg, #1E2938 0%, #1c3461 100%);
    border-radius: 14px;
    padding: 22px 24px;
    margin-bottom: 24px;
    display: flex; align-items: flex-start; gap: 20px;
    position: relative; overflow: hidden;
}
.mach-hero::before {
    content: '';
    position: absolute; top: -40px; right: -40px;
    width: 160px; height: 160px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.mach-hero-icon {
    width: 52px; height: 52px; border-radius: 14px;
    background: rgba(255,255,255,.10);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}
.mach-hero-name {
    font-size: 20px; font-weight: 800; color: #fff; line-height: 1.2;
}
.mach-hero-sub {
    font-size: 11px; color: rgba(255,255,255,.45);
    letter-spacing: .07em; margin-top: 4px;
}
.mach-info-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-top: 16px;
}
.mach-info-field {
    background: #F8FAFC;
    border: 1px solid #E2EBF0;
    border-radius: 8px;
    padding: 10px 13px;
}
.mach-info-label {
    font-size: 9px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 3px;
}
.mach-info-value {
    font-size: 13px; font-weight: 600; color: #111827;
    word-break: break-word;
}
.mach-info-value.muted {
    font-weight: 400; color: #9CA3AF;
}
/* ── Status badge ────────────────────────────────────────────────────── */
.status-pill {
    display: inline-block;
    font-size: 10px; font-weight: 700;
    padding: 2px 10px; border-radius: 20px;
    letter-spacing: .05em;
}
/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 64px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px;
    text-align: center;
}
.empty-icon-ring {
    width: 72px; height: 72px; border-radius: 50%;
    background: linear-gradient(145deg, #FFF7ED, #FFEDD5);
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 18px;
    box-shadow: 0 6px 20px rgba(249,115,22,.14);
}
.empty-state-v2 h3 {
    font-size: 16px; font-weight: 700; color: #111827;
    margin: 0 0 8px;
}
.empty-state-v2 p {
    font-size: 13px; color: #9CA3AF;
    max-width: 260px; line-height: 1.6; margin: 0;
}
</style>
"""


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


def _status_color(status: str) -> str:
    s = (status or "").lower()
    if s == "active":
        return "#16a34a"
    if s in ("closed", "completed"):
        return "#6b7280"
    return "#E87722"


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _kpi_card(icon: str, label: str, value: int | str,
              sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _info_field(label: str, value: str, muted: bool = False) -> str:
    val_cls = "mach-info-value muted" if (muted or not value or value == "—") else "mach-info-value"
    disp    = value if value else "—"
    return (
        f"<div class='mach-info-field'>"
        f"<div class='mach-info-label'>{label}</div>"
        f"<div class='{val_cls}'>{disp}</div>"
        f"</div>"
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

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

    cust_map  = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map  = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    dep_by_wo = {d["work_order_id"]: d for d in deployments if d.get("work_order_id")}

    # ── Machine selector ──────────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("manage_search", "Select Machine")

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

    # ── Machine hero card ─────────────────────────────────────────────────────
    op_status = sel_m.get("operational_status", "—") or "—"
    cn_status = sel_m.get("condition_status",   "—") or "—"
    code_disp = sel_m.get("asset_code", "") or ""
    type_disp = sel_m.get("machine_type", "") or ""
    hero_sub  = " · ".join(p for p in [type_disp, code_disp] if p) or "Machine"

    st.markdown(
        f"<div class='mach-hero'>"
        f"<div class='mach-hero-icon'>"
        f"<span class='msr' style='font-size:28px;color:#fff;'>precision_manufacturing</span>"
        f"</div>"
        f"<div style='flex:1;min-width:0;position:relative;z-index:1;'>"
        f"<div class='mach-hero-name'>{sel_m.get('make', '')} {sel_m.get('model', '') or code_disp}</div>"
        f"<div class='mach-hero-sub'>{hero_sub}</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Machine detail grid (below hero)
    st.markdown(
        "<div class='mach-info-grid'>"
        + _info_field("Asset Code",    sel_m.get("asset_code",       "—"))
        + _info_field("Machine Type",  sel_m.get("machine_type",     "—"))
        + _info_field("Make",          sel_m.get("make",             "—"))
        + _info_field("Model",         sel_m.get("model",            "—"))
        + _info_field("Serial Number", sel_m.get("serial_number",    "—"))
        + _info_field("Capacity",      sel_m.get("working_capacity", "—"))
        + _info_field("Op. Status",    op_status)
        + _info_field("Condition",     cn_status)
        + "</div>",
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

        wo_id      = wo.get("id", "")
        dep        = dep_by_wo.get(wo_id, {})
        rental     = mc_row.get("rental_per_month")
        end_d      = _parse_date(wo.get("end_date"))
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
            "_sort_date":        _parse_date(dep_date_raw) or date.min,
            "_rental_raw":       float(rental) if rental is not None else None,
            "_is_active":        dep_status.lower() == "active",
            "Customer":          cust_map.get(wo.get("customer_id", ""), "—"),
            "Site":              site_map.get(wo.get("site_id",       ""), "—"),
            "Deployment Date":   _dep_date_for_machine(dep, sel_id, wo.get("start_date")),
            "Release Date":      _fmt_date(end_d) if end_d else "Active",
            "Work Order":        wo_display,
            "Monthly Rental":    f"₹ {float(rental):,.0f}" if rental is not None else "—",
            "Deployment Status": dep_status,
        })

    # ── History KPI strip ─────────────────────────────────────────────────────
    if history:
        n_total_dep   = len(history)
        n_active      = sum(1 for r in history if r["_is_active"])
        n_cust_unique = len({r["Customer"] for r in history if r["Customer"] != "—"})
        rentals       = [r["_rental_raw"] for r in history if r["_rental_raw"] is not None]
        avg_rental    = (
            f"₹ {sum(rentals) / len(rentals):,.0f}" if rentals else "—"
        )

        st.markdown(
            "<div class='kpi-grid'>"
            + _kpi_card(
                "history", "Total Deployments", n_total_dep,
                "across all work orders",
                "#2563EB",
            )
            + _kpi_card(
                "check_circle", "Currently Active", n_active,
                "open deployments",
                "#10B981",
            )
            + _kpi_card(
                "groups", "Unique Customers", n_cust_unique,
                "served over lifetime",
                "#8B5CF6",
            )
            + _kpi_card(
                "payments", "Avg Monthly Rental", avg_rental,
                "per deployment",
                "#F59E0B",
            )
            + "</div>",
            unsafe_allow_html=True,
        )

    # ── Display ───────────────────────────────────────────────────────────────
    if not history:
        _section_hdr("history", "Deployment History")
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='color:#F97316;font-size:34px;'>history</span>"
            "</div>"
            "<h3>No deployment history</h3>"
            "<p>This machine has not been assigned to any work orders yet.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    history.sort(key=lambda r: r["_sort_date"], reverse=True)

    _section_hdr(
        "history",
        f"Deployment History — {len(history)} record{'s' if len(history) != 1 else ''}",
    )

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
        column_config={
            "Deployment Date":   st.column_config.TextColumn("Deployed On",  width="medium"),
            "Release Date":      st.column_config.TextColumn("Released On",  width="medium"),
            "Monthly Rental":    st.column_config.TextColumn("Mthly Rental", width="medium"),
            "Deployment Status": st.column_config.TextColumn("Status",       width="medium"),
        },
    )

    st.download_button(
        label="Export CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"machine_history_{sel_m.get('asset_code', sel_id)}.csv",
        mime="text/csv",
        key="mh_export",
    )
