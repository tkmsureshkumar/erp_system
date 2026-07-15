"""
erp/views/workorderreport.py
Work Order Reports â€” Active Work Orders and Expiring Work Orders.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient


# â”€â”€ CSS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_PAGE_CSS = """
<style>
/* â”€â”€ KPI strip â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.kpi-grid {
    display: grid;
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
    animation: cs-fadeup .35s ease;
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
    font-size: 32px; font-weight: 800;
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

/* â”€â”€ Section header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* â”€â”€ Empty state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 60px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px;
    text-align: center;
    animation: cs-fadeup .35s ease;
}
.empty-icon-ring {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px;
    margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 {
    font-size: 17px; font-weight: 700; color: #111827;
    margin: 0 0 8px;
}
.empty-state-v2 p {
    font-size: 13px; color: #9CA3AF;
    max-width: 270px; line-height: 1.6; margin: 0;
}

/* â”€â”€ Animations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    return d.strftime("%d %b %Y") if d else "â€”"


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

    wo_num    = wo.get("wo_number",             "â€”") or "â€”"
    client_wo = wo.get("client_work_ordernumber", "") or ""
    wo_display = wo_num
    if client_wo and client_wo != wo_num:
        wo_display = f"{wo_num} / {client_wo}"

    return {
        "Work Order":       wo_display,
        "Customer":         cust_map.get(wo.get("customer_id", ""), "â€”"),
        "Site":             site_map.get(wo.get("site_id",       ""), "â€”"),
        "Start Date":       _fmt_date(sd),
        "End Date":         _fmt_date(ed) if ed else "Open",
        "Monthly Rental":   f"â‚¹ {rental:,.0f}" if rental else "â€”",
        "No. of Machines":  num_machines,
        "Status":           _wo_status(sd, ed, today),
        # raw values for filtering / sorting
        "_start": sd or date.min,
        "_end":   ed,
    }


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


# â”€â”€ HTML builders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


# â”€â”€ Main render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # â”€â”€ Page header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Work Order Reports</div>",
        unsafe_allow_html=True,
    )

    # â”€â”€ Load data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        sb             = SupabaseClient()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    cust_map = {c["id"]: c.get("customer_name", "â€”") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "â€”") for s in sites_list     if s.get("id")}
    today    = date.today()

    # Build all rows
    all_rows = [_build_wo_row(wo, cust_map, site_map, today) for wo in work_orders]

    # â”€â”€ Derive active and expiring subsets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    active_rows = [
        r for r in all_rows
        if r["_start"] <= today and (r["_end"] is None or r["_end"] >= today)
    ]
    active_rows.sort(key=lambda r: r["_start"], reverse=True)

    expiring_15 = [
        r for r in all_rows
        if r["_end"] is not None
        and today <= r["_end"] <= today + timedelta(days=15)
        and r["_start"] <= today
    ]
    total_machines_active = sum(r["No. of Machines"] for r in active_rows)

    # â”€â”€ KPI strip â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='kpi-grid' style='grid-template-columns:repeat(4,1fr);'>"
        + _kpi_card("assignment",            "Total WOs",        len(all_rows),
                    "all work orders on record",                  "#2563EB")
        + _kpi_card("assignment_turned_in",  "Active",           len(active_rows),
                    "currently running",                          "#10B981")
        + _kpi_card("warning",               "Expiring â‰¤15d",    len(expiring_15),
                    "need attention soon",                        "#EF4444")
        + _kpi_card("precision_manufacturing","Machines Out",    total_machines_active,
                    "deployed across active WOs",                 "#F59E0B")
        + "</div>",
        unsafe_allow_html=True,
    )

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # SECTION 1 â€” ACTIVE WORK ORDERS
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with st.container(border=True):
        hdr_l, hdr_r = st.columns([5, 1])
        with hdr_l:
            _section_hdr("assignment_turned_in", f"Active Work Orders â€” {len(active_rows)}")
        with hdr_r:
            if active_rows:
                adf_exp = pd.DataFrame(
                    [{k: r[k] for k in _DISPLAY_COLS} for r in active_rows],
                    columns=_DISPLAY_COLS,
                )
                st.download_button(
                    "Export CSV",
                    data=adf_exp.to_csv(index=False).encode("utf-8"),
                    file_name=f"active_work_orders_{today.isoformat()}.csv",
                    mime="text/csv",
                    key="wor_active_csv",
                )

        if active_rows:
            adf = pd.DataFrame(
                [{k: r[k] for k in _DISPLAY_COLS} for r in active_rows],
                columns=_DISPLAY_COLS,
            )
            st.dataframe(
                adf.style.map(_status_style, subset=["Status"]),
                use_container_width=True,
                hide_index=True,
            )

            open_ended = sum(1 for r in active_rows if r["_end"] is None)
            st.markdown(
                f"<div style='margin-top:8px;font-size:11px;color:#9ca3af;'>"
                f"{len(active_rows)} active WOs Â· "
                f"{total_machines_active} machines deployed Â· "
                f"{open_ended} open-ended (no end date)</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#9CA3AF;'>assignment_late</span>"
                "</div>"
                "<h3>No active work orders</h3>"
                "<p>No work orders are currently active. Check the Work Orders page to create one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # SECTION 2 â€” EXPIRING WORK ORDERS
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with st.container(border=True):
        _section_hdr("warning", "Expiring Work Orders")

        with st.container(border=True):
            _section_hdr("tune", "Window")
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
            and r["_start"] <= today
        ]
        expiring_rows.sort(key=lambda r: r["_end"])

        def _days_left(r: dict) -> str:
            diff = (r["_end"] - today).days
            if diff == 0:
                return "Today"
            if diff == 1:
                return "1 day"
            return f"{diff} days"

        st.markdown(
            f"<div style='font-size:13px;color:#6b7280;margin-bottom:16px;'>"
            f"Showing <strong>{len(expiring_rows)}</strong> work order"
            f"{'s' if len(expiring_rows) != 1 else ''} expiring between today and "
            f"<strong>{cutoff.strftime('%d %b %Y')}</strong>.</div>",
            unsafe_allow_html=True,
        )

        if expiring_rows:
            exp_display = []
            for r in expiring_rows:
                row = {k: r[k] for k in _DISPLAY_COLS}
                row["Days Left"] = _days_left(r)
                exp_display.append(row)

            exp_cols = [
                "Work Order", "Customer", "Site", "End Date", "Days Left",
                "Monthly Rental", "No. of Machines", "Status",
            ]
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
                   .map(_status_style,    subset=["Status"])
                   .map(_days_left_style, subset=["Days Left"]),
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
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#10B981;'>check_circle</span>"
                "</div>"
                f"<h3>All clear for {days_window} days</h3>"
                "<p>No work orders are expiring in this window. You're in good shape.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
