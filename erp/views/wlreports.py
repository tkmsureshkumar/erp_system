"""
erp/views/wlreports.py
Worklog Reports â€” Pending, Completed, Pending for Billing.
"""
from __future__ import annotations

import calendar as _cal
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

/* â”€â”€ Empty state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 72px 40px;
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

/* â”€â”€ Section header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
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


def _billing_month_str(yr: int, mo: int) -> str:
    """Format a year/month as the billing month key used in work_logs.year."""
    return f"{_cal.month_name[mo]} {yr}"


def _months_range(start: date, end: date, max_months: int = 24):
    """Yield (year, month) from start's month through end's month, capped at max_months."""
    cur    = start.replace(day=1)
    end_m  = end.replace(day=1)
    count  = 0
    while cur <= end_m and count < max_months:
        yield (cur.year, cur.month)
        count += 1
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)


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
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Worklog Reports</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # â”€â”€ Load data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        sb             = SupabaseClient()
        machines       = sb.list_machines()
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
        work_logs      = sb.list_all_worklogs()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    today    = date.today()
    cust_map = {c["id"]: c.get("customer_name", "â€”") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "â€”") for s in sites_list     if s.get("id")}
    mach_map = {m["id"]: m for m in machines if m.get("id")}

    # work_log lookup: (wo_id, machine_id, billing_month_str) â†’ worklog dict
    wl_lookup: dict[tuple[str, str, str], dict] = {}
    for wl in work_logs:
        key = (
            wl.get("work_order_id", ""),
            wl.get("machine_id",    ""),
            wl.get("year",          ""),   # "July 2026"
        )
        wl_lookup[key] = wl

    # Active work orders: started and not yet ended
    active_wos = [
        wo for wo in work_orders
        if (sd := _parse_date(wo.get("start_date"))) is not None
        and sd <= today
        and (_parse_date(wo.get("end_date")) is None or _parse_date(wo.get("end_date")) >= today)
    ]

    # â”€â”€ Build per-machine-month records for active WOs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Each entry: WO + machine + month â†’ worklog status
    pending_rows:   list[dict] = []
    completed_rows: list[dict] = []

    for wo in active_wos:
        wo_id    = wo.get("id", "")
        customer = cust_map.get(wo.get("customer_id", ""), "â€”")
        site     = site_map.get(wo.get("site_id",     ""), "â€”")
        wo_start = _parse_date(wo.get("start_date")) or today

        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            mc_list = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        except Exception:
            continue
        if not isinstance(mc_list, list):
            continue

        for mc_row in mc_list:
            mid    = mc_row.get("machine_id", "")
            mach   = mach_map.get(mid, {})
            code   = mach.get("asset_code", "") or mc_row.get("machine_label", "") or "â€”"
            make   = mach.get("make",  "") or ""
            model  = mach.get("model", "") or ""
            label  = code
            if make or model:
                label += f" â€” {' '.join(p for p in [make, model] if p)}"

            # Check every month from WO start through today
            for yr, mo in _months_range(wo_start, today):
                bm_str = _billing_month_str(yr, mo)
                wl     = wl_lookup.get((wo_id, mid, bm_str))

                if wl is None:
                    status   = "Missing"
                    is_draft = None
                elif wl.get("is_draft", True):
                    status   = "Draft"
                    is_draft = True
                else:
                    status   = "Submitted"
                    is_draft = False

                row = {
                    "Customer":      customer,
                    "Site":          site,
                    "Machine":       label,
                    "Worklog Month": bm_str,
                    "Status":        status,
                    "_wo_id":        wo_id,
                    "_machine_id":   mid,
                    "_yr":           yr,
                    "_mo":           mo,
                    "_is_draft":     is_draft,
                }

                if status in ("Missing", "Draft"):
                    pending_rows.append(row)
                else:
                    completed_rows.append(row)

    # Sort pending: oldest month first (most overdue at top)
    pending_rows.sort(key=lambda r: (r["_yr"], r["_mo"]))
    # Sort completed: most recent first
    completed_rows.sort(key=lambda r: (r["_yr"], r["_mo"]), reverse=True)

    _PENDING_COLS   = ["Customer", "Site", "Machine", "Worklog Month", "Status"]
    _COMPLETED_COLS = ["Customer", "Site", "Machine", "Worklog Month", "Status"]

    # â”€â”€ KPI strip â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    n_missing   = sum(1 for r in pending_rows   if r["Status"] == "Missing")
    n_draft     = sum(1 for r in pending_rows   if r["Status"] == "Draft")
    n_completed = len(completed_rows)
    n_pending   = len(pending_rows)

    st.markdown(
        f"<div class='kpi-grid'>"
        + _kpi_card("pending",   "Pending",   n_pending,
                    "missing or draft worklogs",  "#EF4444")
        + _kpi_card("warning",   "Missing",   n_missing,
                    "no worklog submitted",        "#F59E0B")
        + _kpi_card("edit_note", "Draft",     n_draft,
                    "saved but not submitted",     "#E87722")
        + _kpi_card("task_alt",  "Completed", n_completed,
                    "submitted worklogs",           "#10B981")
        + "</div>",
        unsafe_allow_html=True,
    )

    # â”€â”€ Tabs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    tab_pending, tab_completed, tab_billing = st.tabs([
        f"Pending ({len(pending_rows)})",
        f"Completed ({len(completed_rows)})",
        f"Pending for Billing ({len(completed_rows)})",
    ])

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # TAB 1 â€” PENDING WORKLOGS
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with tab_pending:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        if not pending_rows:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:36px;color:#2563EB;'>task_alt</span>"
                "</div>"
                "<h3>All worklogs up to date</h3>"
                "<p>All worklogs for active work orders are submitted.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            with st.container(border=True):
                _section_hdr("tune", "Filter")
                show_all = st.checkbox(
                    "Show all pending months (including prior months)",
                    value=False,
                    key="wlr_show_all_pending",
                )

            cur_bm  = _billing_month_str(today.year, today.month)
            display = (
                pending_rows if show_all
                else [r for r in pending_rows if r["Worklog Month"] == cur_bm]
            )

            if not display and not show_all:
                st.markdown(
                    f"<div class='empty-state-v2'>"
                    f"<div class='empty-icon-ring'>"
                    f"<span class='msr' style='font-size:36px;color:#2563EB;'>event_available</span>"
                    f"</div>"
                    f"<h3>No pending worklogs for {cur_bm}</h3>"
                    f"<p>Check 'Show all pending months' to see prior months.</p>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                pdf = pd.DataFrame(
                    [{k: r[k] for k in _PENDING_COLS} for r in display],
                    columns=_PENDING_COLS,
                )

                def _pstyle(val: str) -> str:
                    if val == "Missing":
                        return "color:#ef4444;font-weight:700;"
                    if val == "Draft":
                        return "color:#E87722;font-weight:700;"
                    return ""

                with st.container(border=True):
                    _section_hdr("pending", "Pending Worklogs")
                    st.dataframe(
                        pdf.style.map(_pstyle, subset=["Status"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                c1, c2, c3 = st.columns(3)
                c1.metric("Missing",  sum(1 for r in display if r["Status"] == "Missing"))
                c2.metric("Draft",    sum(1 for r in display if r["Status"] == "Draft"))
                c3.metric("Machines", len({(r["_wo_id"], r["_machine_id"]) for r in display}))

                st.download_button(
                    "Export CSV",
                    data=pdf.to_csv(index=False).encode("utf-8"),
                    file_name=f"pending_worklogs_{today.isoformat()}.csv",
                    mime="text/csv",
                    key="wlr_pend_csv",
                )

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # TAB 2 â€” COMPLETED WORKLOGS
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with tab_completed:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        if not completed_rows:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:36px;color:#2563EB;'>assignment</span>"
                "</div>"
                "<h3>No completed worklogs</h3>"
                "<p>No submitted worklogs found for active work orders.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            # Month filter
            available_months = sorted(
                {r["Worklog Month"] for r in completed_rows},
                key=lambda s: datetime.strptime(s, "%B %Y"),
                reverse=True,
            )
            with st.container(border=True):
                _section_hdr("tune", "Filter")
                fp1, _ = st.columns([2, 6])
                with fp1:
                    st.markdown('<p class="filter-label">Month</p>', unsafe_allow_html=True)
                    sel_month = st.selectbox(
                        "Month", ["All"] + available_months,
                        label_visibility="collapsed",
                        key="wlr_comp_month",
                    )

            display = (
                completed_rows if sel_month == "All"
                else [r for r in completed_rows if r["Worklog Month"] == sel_month]
            )

            cdf = pd.DataFrame(
                [{k: r[k] for k in _COMPLETED_COLS} for r in display],
                columns=_COMPLETED_COLS,
            )

            with st.container(border=True):
                _section_hdr("task_alt", "Completed Worklogs")
                st.dataframe(
                    cdf.style.map(
                        lambda v: "color:#16a34a;font-weight:700;",
                        subset=["Status"],
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            st.download_button(
                "Export CSV",
                data=cdf.to_csv(index=False).encode("utf-8"),
                file_name=f"completed_worklogs_{today.isoformat()}.csv",
                mime="text/csv",
                key="wlr_comp_csv",
            )

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    # TAB 3 â€” PENDING FOR BILLING
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    with tab_billing:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;"
            "padding:12px 16px;margin-bottom:14px;font-size:13px;color:#1E40AF;"
            "display:flex;align-items:center;gap:8px;'>"
            "<span class='msr' style='font-size:18px;'>info</span>"
            "Showing all submitted worklogs â€” these are pending invoice generation. "
            "Once invoice tracking is added, billed worklogs will be excluded automatically."
            "</div>",
            unsafe_allow_html=True,
        )

        if not completed_rows:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:36px;color:#2563EB;'>receipt_long</span>"
                "</div>"
                "<h3>No worklogs pending billing</h3>"
                "<p>No submitted worklogs pending billing found.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            avail_b = sorted(
                {r["Worklog Month"] for r in completed_rows},
                key=lambda s: datetime.strptime(s, "%B %Y"),
                reverse=True,
            )
            with st.container(border=True):
                _section_hdr("tune", "Filter")
                fp2, _ = st.columns([2, 6])
                with fp2:
                    st.markdown('<p class="filter-label">Month</p>', unsafe_allow_html=True)
                    sel_b = st.selectbox(
                        "Month", ["All"] + avail_b,
                        label_visibility="collapsed",
                        key="wlr_bill_month",
                    )

            billing_display = (
                completed_rows if sel_b == "All"
                else [r for r in completed_rows if r["Worklog Month"] == sel_b]
            )

            _BILL_COLS = ["Customer", "Site", "Machine", "Worklog Month", "Status"]
            bdf = pd.DataFrame(
                [{k: r[k] for k in _BILL_COLS} for r in billing_display],
                columns=_BILL_COLS,
            )
            bdf["Status"] = "Pending Billing"

            with st.container(border=True):
                _section_hdr("receipt_long", "Pending for Billing")
                st.dataframe(
                    bdf.style.map(
                        lambda v: "color:#E87722;font-weight:700;",
                        subset=["Status"],
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            b1, b2 = st.columns(2)
            b1.metric("Worklogs Pending Billing", len(billing_display))
            b2.metric("Machines Affected", len({(r["_wo_id"], r["_machine_id"]) for r in billing_display}))

            st.download_button(
                "Export CSV",
                data=bdf.to_csv(index=False).encode("utf-8"),
                file_name=f"pending_billing_{today.isoformat()}.csv",
                mime="text/csv",
                key="wlr_bill_csv",
            )
