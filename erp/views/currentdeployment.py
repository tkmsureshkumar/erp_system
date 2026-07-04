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


def _section_header(title: str) -> None:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:14px;'>"
        f"{title}</div>",
        unsafe_allow_html=True,
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
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
                # internal sort key
                "_dep_sort": _parse_date(
                    md.get("billing_start_date")
                    or md.get("transaction_start_date")
                    or md.get("site_reached_date")
                    or dep.get("deployment_date")
                ) or date.min,
            })

    # ── Display ───────────────────────────────────────────────────────────────
    _section_header(f"Active Deployments — {len(rows)} machine{'s' if len(rows) != 1 else ''}")

    if not rows:
        st.info("No active deployments found.")
        return

    rows.sort(key=lambda r: r["_dep_sort"], reverse=True)

    _COLS = [
        "Serial Number", "Machine", "Customer", "Site",
        "Operator", "Deployment Date", "Monthly Rental",
    ]
    df = pd.DataFrame([{k: r[k] for k in _COLS} for r in rows], columns=_COLS)

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        label="Export CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"current_deployments_{date.today().isoformat()}.csv",
        mime="text/csv",
        key="cd_export",
    )
