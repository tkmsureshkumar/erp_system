"""
erp/views/workorderreport.py
Work Order Reports — Active Work Orders and Expiring Work Orders.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

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


def _wo_status(start: date | None, end: date | None, today: date) -> str:
    if start and start > today:
        return "Upcoming"
    if end is None:
        return "Active"
    days_left = (end - today).days
    if days_left < 0:
        return "Expired"
    if days_left <= 15:
        return f"Expiring in {days_left}d"
    return "Active"


def _parse_mc(mc_raw) -> tuple[int, float]:
    """Return (num_machines, total_rental) from machine_config JSON."""
    if not mc_raw:
        return 0, 0.0
    try:
        records = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        if isinstance(records, list):
            count  = len([r for r in records if r.get("machine_id") or r.get("machine_label")])
            rental = sum(float(r.get("rental_per_month") or 0) for r in records)
            return count, rental
    except Exception:
        pass
    return 0, 0.0


def _build_wo_row(wo: dict, cust_map: dict, site_map: dict, today: date) -> dict:
    sd  = _parse_date(wo.get("start_date"))
    ed  = _parse_date(wo.get("end_date"))
    num_machines, rental = _parse_mc(wo.get("machine_config"))

    wo_num    = wo.get("wo_number",             "—") or "—"
    client_wo = wo.get("client_work_ordernumber", "") or ""
    wo_display = wo_num
    if client_wo and client_wo != wo_num:
        wo_display = f"{wo_num} / {client_wo}"

    return {
        "Work Order":        wo_display,
        "Customer":          cust_map.get(wo.get("customer_id", ""), "—"),
        "Site":              site_map.get(wo.get("site_id",       ""), "—"),
        "Start Date":        _fmt_date(sd),
        "End Date":          _fmt_date(ed) if ed else "Open",
        "Monthly Rental":    f"₹ {rental:,.0f}" if rental else "—",
        "No. of Machines":   num_machines,
        "Status":            _wo_status(sd, ed, today),
        # raw values for filtering / sorting
        "_start": sd or date.min,
        "_end":   ed,
    }


def _section_header(title: str) -> None:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:14px;'>"
        f"{title}</div>",
        unsafe_allow_html=True,
    )


def _status_style(val: str) -> str:
    v = str(val).lower()
    if v == "active":
        return "color:#16a34a;font-weight:700;"
    if v.startswith("expiring"):
        return "color:#E87722;font-weight:700;"
    if v == "expired":
        return "color:#ef4444;font-weight:700;"
    if v == "upcoming":
        return "color:#2563eb;font-weight:700;"
    return ""


_DISPLAY_COLS = [
    "Work Order", "Customer", "Site",
    "Start Date", "End Date", "Monthly Rental",
    "No. of Machines", "Status",
]


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Work Order Reports</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        sb             = SupabaseClient()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    today    = date.today()

    # Build all rows
    all_rows = [_build_wo_row(wo, cust_map, site_map, today) for wo in work_orders]

    # ════════════════════════════════════════════════════════════════════
    # SECTION 1 — ACTIVE WORK ORDERS
    # ════════════════════════════════════════════════════════════════════
    active_rows = [
        r for r in all_rows
        if r["_start"] <= today and (r["_end"] is None or r["_end"] >= today)
    ]
    active_rows.sort(key=lambda r: r["_start"], reverse=True)

    _section_header(f"Active Work Orders — {len(active_rows)}")

    if active_rows:
        adf = pd.DataFrame(
            [{k: r[k] for k in _DISPLAY_COLS} for r in active_rows],
            columns=_DISPLAY_COLS,
        )
        st.dataframe(
            adf.style.applymap(_status_style, subset=["Status"]),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Export CSV",
            data=adf.to_csv(index=False).encode("utf-8"),
            file_name=f"active_work_orders_{today.isoformat()}.csv",
            mime="text/csv",
            key="wor_active_csv",
        )

        # Summary metrics
        total_machines = sum(r["No. of Machines"] for r in active_rows)
        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Active Work Orders", len(active_rows))
        with m2:
            st.metric("Total Machines Deployed", total_machines)
        with m3:
            open_ended = sum(1 for r in active_rows if r["_end"] is None)
            st.metric("Open-ended (No End Date)", open_ended)
    else:
        st.info("No active work orders found.")

    st.markdown("<div style='margin-top:40px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 2 — EXPIRING WORK ORDERS
    # ════════════════════════════════════════════════════════════════════
    _section_header("Expiring Work Orders")

    window_opts = {"Next 15 Days": 15, "Next 30 Days": 30, "Next 60 Days": 60}
    sel_window  = st.radio(
        "Show expiring within",
        list(window_opts.keys()),
        horizontal=True,
        key="wor_window",
        label_visibility="collapsed",
    )
    days_window = window_opts[sel_window]
    cutoff      = today + timedelta(days=days_window)

    expiring_rows = [
        r for r in all_rows
        if r["_end"] is not None
        and today <= r["_end"] <= cutoff
        and r["_start"] <= today          # already started (active, not upcoming)
    ]
    expiring_rows.sort(key=lambda r: r["_end"])   # soonest first

    # Add days-remaining helper column for this view
    def _days_left(r: dict) -> str:
        diff = (r["_end"] - today).days
        if diff == 0:
            return "Today"
        if diff == 1:
            return "1 day"
        return f"{diff} days"

    st.markdown(
        f"<div style='font-size:13px;color:#6b7280;margin-bottom:16px;'>"
        f"Showing {len(expiring_rows)} work order{'s' if len(expiring_rows) != 1 else ''} "
        f"expiring between today and <strong>{cutoff.strftime('%d %b %Y')}</strong>.</div>",
        unsafe_allow_html=True,
    )

    if expiring_rows:
        exp_display = []
        for r in expiring_rows:
            row = {k: r[k] for k in _DISPLAY_COLS}
            row["Days Left"] = _days_left(r)
            exp_display.append(row)

        exp_cols = ["Work Order", "Customer", "Site", "End Date", "Days Left",
                    "Monthly Rental", "No. of Machines", "Status"]
        edf = pd.DataFrame(exp_display, columns=exp_cols)

        def _days_left_style(val: str) -> str:
            if val == "Today":
                return "color:#ef4444;font-weight:800;"
            try:
                d = int(str(val).replace(" day", "").replace("s", "").strip())
                if d <= 7:
                    return "color:#ef4444;font-weight:700;"
                if d <= 15:
                    return "color:#E87722;font-weight:700;"
            except ValueError:
                pass
            return "color:#16a34a;font-weight:600;"

        st.dataframe(
            edf.style
               .applymap(_status_style,    subset=["Status"])
               .applymap(_days_left_style, subset=["Days Left"]),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Export CSV",
            data=edf.to_csv(index=False).encode("utf-8"),
            file_name=f"expiring_wo_{days_window}days_{today.isoformat()}.csv",
            mime="text/csv",
            key="wor_exp_csv",
        )
    else:
        st.success(f"No work orders expiring in the next {days_window} days.")
