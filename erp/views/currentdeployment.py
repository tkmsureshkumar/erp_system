"""
erp/views/currentdeployment.py
Current Deployment Report — all actively deployed machines.
"""
from __future__ import annotations

import json
from collections import Counter
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
    background: linear-gradient(145deg, #F0FDF4, #DCFCE7);
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 18px;
    box-shadow: 0 6px 20px rgba(16,185,129,.14);
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


def _dep_date(md: dict) -> str:
    """Deployment date for one machine_deployments entry."""
    d = (
        md.get("billing_start_date")
        or md.get("transaction_start_date")
        or md.get("site_reached_date")
    )
    return _fmt_date(d) if d else "—"


def _mc_rental(mc_raw, machine_id: str) -> str:
    if not mc_raw or not machine_id:
        return "—"
    try:
        records = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        if isinstance(records, list):
            for r in records:
                if r.get("machine_id") == machine_id:
                    v = r.get("rental_per_month")
                    if v is not None:
                        return f"₹ {float(v):,.0f}"
    except Exception:
        pass
    return "—"


def _mc_rental_float(mc_raw, machine_id: str) -> float | None:
    """Return raw float rental for KPI aggregation."""
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


def _operator_from_schedule(schedule_raw) -> str:
    if not schedule_raw:
        return "—"
    try:
        rows = json.loads(schedule_raw) if isinstance(schedule_raw, str) else schedule_raw
        if isinstance(rows, list):
            ops = [r.get("operator", "").strip() for r in rows if r.get("operator", "").strip()]
            if ops:
                return Counter(ops).most_common(1)[0][0]
    except Exception:
        pass
    return "—"


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


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Current Deployment Report</div>",
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
        work_logs      = sb.list_all_worklogs()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    # ── Lookup maps ──────────────────────────────────────────────────────────
    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    mach_map = {m["id"]: m for m in machines if m.get("id")}
    wo_map   = {w["id"]: w for w in work_orders if w.get("id")}

    # (wo_id, machine_id) → operator from most recent work log
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
        mid   = wl.get("machine_id",   "")
        sk    = _log_sort_key(wl)
        op    = _operator_from_schedule(wl.get("schedule_data"))
        key   = (wo_id, mid)
        prev  = log_latest.get(key)
        if prev is None or sk > prev[0]:
            log_latest[key] = (sk, op)
    log_op_map = {k: v[1] for k, v in log_latest.items()}

    # ── Build rows — one per machine in each active deployment ────────────────
    rows: list[dict] = []
    for dep in deployments:
        if (dep.get("deployment_status") or "").lower() != "active":
            continue

        wo_id  = dep.get("work_order_id", "")
        wo     = wo_map.get(wo_id, {})
        cid    = dep.get("customer_id") or wo.get("customer_id", "")
        sid    = dep.get("site_id")     or wo.get("site_id",     "")
        mc_raw = wo.get("machine_config")

        md_raw = dep.get("machine_deployments")
        if not md_raw:
            continue
        try:
            md_list = json.loads(md_raw) if isinstance(md_raw, str) else md_raw
        except Exception:
            continue
        if not isinstance(md_list, list):
            continue

        for md in md_list:
            mid  = md.get("machine_id", "")
            mach = mach_map.get(mid, {})

            serial = mach.get("serial_number") or "—"
            code   = mach.get("asset_code",   "") or ""
            make   = mach.get("make",         "") or ""
            model  = mach.get("model",        "") or ""
            machine_label = code
            if make or model:
                machine_label += f" — {' '.join(p for p in [make, model] if p)}"

            rows.append({
                "Serial Number":   serial,
                "Machine":         machine_label or md.get("machine_label", "—"),
                "Customer":        cust_map.get(cid, "—"),
                "Site":            site_map.get(sid, "—"),
                "Operator":        log_op_map.get((wo_id, mid), "—"),
                "Deployment Date": _dep_date(md),
                "Monthly Rental":  _mc_rental(mc_raw, mid),
                # internal keys
                "_rental_raw": _mc_rental_float(mc_raw, mid),
                "_dep_sort": _parse_date(
                    md.get("billing_start_date")
                    or md.get("transaction_start_date")
                    or md.get("site_reached_date")
                    or dep.get("deployment_date")
                ) or date.min,
            })

    # ── KPI strip (from full dataset before filtering) ────────────────────────
    n_deployed  = len(rows)
    n_customers = len({r["Customer"] for r in rows if r["Customer"] != "—"})
    n_sites     = len({r["Site"]     for r in rows if r["Site"]     != "—"})
    revenue_raw = sum(r["_rental_raw"] for r in rows if r["_rental_raw"] is not None)
    revenue_fmt = (
        f"₹ {revenue_raw / 100_000:.1f}L"
        if revenue_raw >= 100_000
        else f"₹ {revenue_raw:,.0f}"
    )

    st.markdown(
        "<div class='kpi-grid'>"
        + _kpi_card(
            "precision_manufacturing", "Deployed Machines", n_deployed,
            "machines currently on site",
            "#2563EB",
        )
        + _kpi_card(
            "groups", "Active Customers", n_customers,
            "with machines deployed",
            "#8B5CF6",
        )
        + _kpi_card(
            "location_on", "Active Sites", n_sites,
            "unique project sites",
            "#10B981",
        )
        + _kpi_card(
            "payments", "Monthly Revenue", revenue_fmt,
            "est. total rental revenue",
            "#F59E0B",
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("filter_list", "Filters")

        ff1, ff2 = st.columns(2)

        with ff1:
            st.markdown('<p class="filter-label">Customer</p>', unsafe_allow_html=True)
            cust_opts = ["All"] + sorted(
                {r["Customer"] for r in rows if r["Customer"] != "—"}
            )
            sel_cust = st.selectbox(
                "Customer", cust_opts, label_visibility="collapsed", key="cd_customer"
            )

        with ff2:
            st.markdown('<p class="filter-label">Site</p>', unsafe_allow_html=True)
            site_opts = ["All"] + sorted(
                {r["Site"] for r in rows if r["Site"] != "—"}
            )
            sel_site = st.selectbox(
                "Site", site_opts, label_visibility="collapsed", key="cd_site"
            )

    # ── Apply filters & sort ──────────────────────────────────────────────────
    filtered = rows
    if sel_cust != "All":
        filtered = [r for r in filtered if r["Customer"] == sel_cust]
    if sel_site != "All":
        filtered = [r for r in filtered if r["Site"] == sel_site]

    # ── Display ───────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    _section_hdr(
        "table_view",
        f"Active Deployments — {len(filtered)} machine{'s' if len(filtered) != 1 else ''}",
    )

    if not filtered:
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='color:#10B981;font-size:34px;'>deployed_code</span>"
            "</div>"
            "<h3>No active deployments</h3>"
            "<p>No machines are currently deployed, or none match the selected filters.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    filtered.sort(key=lambda r: r["_dep_sort"], reverse=True)

    _COLS = [
        "Serial Number", "Machine", "Customer", "Site",
        "Operator", "Deployment Date", "Monthly Rental",
    ]
    df = pd.DataFrame([{k: r[k] for k in _COLS} for r in filtered], columns=_COLS)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Serial Number":   st.column_config.TextColumn("Serial No.",    width="medium"),
            "Monthly Rental":  st.column_config.TextColumn("Mthly Rental",  width="medium"),
            "Deployment Date": st.column_config.TextColumn("Deployed On",   width="medium"),
        },
    )

    st.download_button(
        label="Export CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"current_deployments_{date.today().isoformat()}.csv",
        mime="text/csv",
        key="cd_export",
    )
