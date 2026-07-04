"""
erp/views/wlreports.py
Worklog Reports — Pending, Completed, Pending for Billing.
"""
from __future__ import annotations

import calendar as _cal
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


def _section_header(title: str) -> None:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
        f"text-transform:uppercase;color:#E87722;margin-bottom:14px;'>"
        f"{title}</div>",
        unsafe_allow_html=True,
    )


def _badge(text: str, bg: str, fg: str = "#fff") -> str:
    return (
        f"<span style='background:{bg};color:{fg};font-size:10px;font-weight:700;"
        f"letter-spacing:.06em;padding:2px 8px;border-radius:4px;'>{text}</span>"
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Worklog Reports</div>",
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
        work_logs      = sb.list_all_worklogs()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    today    = date.today()
    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    mach_map = {m["id"]: m for m in machines if m.get("id")}

    # work_log lookup: (wo_id, machine_id, billing_month_str) → worklog dict
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

    # ── Build per-machine-month records for active WOs ────────────────────────
    # Each entry: WO + machine + month → worklog status
    pending_rows:  list[dict] = []
    completed_rows: list[dict] = []

    for wo in active_wos:
        wo_id    = wo.get("id", "")
        customer = cust_map.get(wo.get("customer_id", ""), "—")
        site     = site_map.get(wo.get("site_id",     ""), "—")
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
            code   = mach.get("asset_code", "") or mc_row.get("machine_label", "") or "—"
            make   = mach.get("make",  "") or ""
            model  = mach.get("model", "") or ""
            label  = code
            if make or model:
                label += f" — {' '.join(p for p in [make, model] if p)}"

            # Check every month from WO start through today
            for yr, mo in _months_range(wo_start, today):
                bm_str = _billing_month_str(yr, mo)
                wl     = wl_lookup.get((wo_id, mid, bm_str))

                if wl is None:
                    status    = "Missing"
                    is_draft  = None
                elif wl.get("is_draft", True):
                    status    = "Draft"
                    is_draft  = True
                else:
                    status    = "Submitted"
                    is_draft  = False

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

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_pending, tab_completed, tab_billing = st.tabs([
        f"Pending ({len(pending_rows)})",
        f"Completed ({len(completed_rows)})",
        f"Pending for Billing ({len(completed_rows)})",
    ])

    # ════════════════════════════════════════════════════════════════════
    # TAB 1 — PENDING WORKLOGS
    # ════════════════════════════════════════════════════════════════════
    with tab_pending:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        if not pending_rows:
            st.success("All worklogs for active work orders are up to date.")
        else:
            # Quick filter: show current month only vs all pending
            show_all = st.checkbox(
                "Show all pending months (including prior months)",
                value=False,
                key="wlr_show_all_pending",
            )
            cur_bm = _billing_month_str(today.year, today.month)
            display = (
                pending_rows if show_all
                else [r for r in pending_rows if r["Worklog Month"] == cur_bm]
            )

            if not display and not show_all:
                st.success(
                    f"No pending worklogs for {cur_bm}. "
                    "Check 'Show all pending months' to see prior months."
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

                st.dataframe(
                    pdf.style.applymap(_pstyle, subset=["Status"]),
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

    # ════════════════════════════════════════════════════════════════════
    # TAB 2 — COMPLETED WORKLOGS
    # ════════════════════════════════════════════════════════════════════
    with tab_completed:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        if not completed_rows:
            st.info("No submitted worklogs found for active work orders.")
        else:
            # Month filter
            available_months = sorted(
                {r["Worklog Month"] for r in completed_rows},
                key=lambda s: datetime.strptime(s, "%B %Y"),
                reverse=True,
            )
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
            st.dataframe(
                cdf.style.applymap(
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

    # ════════════════════════════════════════════════════════════════════
    # TAB 3 — PENDING FOR BILLING
    # ════════════════════════════════════════════════════════════════════
    with tab_billing:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        st.info(
            "Showing all submitted worklogs — these are pending invoice generation. "
            "Once invoice tracking is added, billed worklogs will be excluded automatically.",
            icon="ℹ️",
        )

        if not completed_rows:
            st.success("No submitted worklogs pending billing.")
        else:
            fp2, _ = st.columns([2, 6])
            with fp2:
                st.markdown('<p class="filter-label">Month</p>', unsafe_allow_html=True)
                avail_b = sorted(
                    {r["Worklog Month"] for r in completed_rows},
                    key=lambda s: datetime.strptime(s, "%B %Y"),
                    reverse=True,
                )
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

            st.dataframe(
                bdf.style.applymap(
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
