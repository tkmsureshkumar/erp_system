"""
erp/views/wlreports.py
Pending Worklogs — monthly worklogs, mobilization & de-mobilization.
"""
from __future__ import annotations

import calendar as _cal
import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient
from ._report_utils import render_export_buttons


# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
.kpi-grid-6 {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 12px;
    margin: 0 0 26px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 16px 18px 12px;
    position: relative;
    overflow: hidden;
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
    margin-bottom: 8px; display: flex; align-items: center; gap: 5px;
}
.kpi-value {
    font-size: 28px; font-weight: 800; color: #111827; line-height: 1;
    margin-bottom: 4px; font-variant-numeric: tabular-nums;
}
.kpi-sub { font-size: 10px; color: #6B7280; }
.kpi-icon {
    position: absolute; top: 14px; right: 14px;
    font-size: 20px; opacity: .12;
}

.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 64px 40px;
    background: #FAFBFC; border: 2px dashed #E2EBF0;
    border-radius: 16px; text-align: center;
    animation: cs-fadeup .35s ease;
}
.empty-icon-ring {
    width: 72px; height: 72px; border-radius: 50%;
    background: linear-gradient(145deg,#EFF6FF,#DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 34px; margin-bottom: 18px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 { font-size:16px; font-weight:700; color:#111827; margin:0 0 6px; }
.empty-state-v2 p  { font-size:13px; color:#9CA3AF; max-width:270px; line-height:1.6; margin:0; }

.form-sec-hdr {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* pending section title */
.pending-section-title {
    font-size: 16px; font-weight: 800; color: #1E2938;
    margin: 18px 0 10px; letter-spacing: -.2px;
}

@keyframes cs-fadeup {
    from { opacity:0; transform:translateY(10px); }
    to   { opacity:1; transform:translateY(0); }
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


def _billing_month_str(yr: int, mo: int) -> str:
    return f"{_cal.month_name[mo]} {yr}"


def _months_range(start: date, end: date, max_months: int = 24):
    cur   = start.replace(day=1)
    end_m = end.replace(day=1)
    count = 0
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


def _status_chip(label: str, color: str) -> str:
    palettes = {
        "Missing":         ("#FEE2E2", "#991B1B"),
        "Draft":           ("#FEF3C7", "#92400E"),
        "Submitted":       ("#DCFCE7", "#166534"),
        "Pending Billing": ("#FEF3C7", "#92400E"),
        "Pending":         ("#FEE2E2", "#991B1B"),
    }
    bg, fg = palettes.get(label, ("#F1F5F9", "#374151"))
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;"
        f"border-radius:12px;font-size:11px;font-weight:700;'>{label}</span>"
    )


def _month_to_date(bm_str: str) -> date | None:
    try:
        return datetime.strptime(bm_str, "%B %Y").date()
    except Exception:
        return None


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Pending Worklogs</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    # ── Load data ──────────────────────────────────────────────────────────────
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
            wl.get("year",          ""),
        )
        wl_lookup[key] = wl

    # ── Build all rows ─────────────────────────────────────────────────────────
    pending_rows:   list[dict] = []
    completed_rows: list[dict] = []
    mob_rows:       list[dict] = []
    demob_rows:     list[dict] = []

    for wo in work_orders:
        wo_id      = wo.get("id", "")
        customer   = cust_map.get(wo.get("customer_id", ""), "—")
        site       = site_map.get(wo.get("site_id",     ""), "—")
        wo_start   = _parse_date(wo.get("start_date"))
        wo_end     = _parse_date(wo.get("end_date"))

        if not wo_start:
            continue

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
            mid       = mc_row.get("machine_id", "")
            mach      = mach_map.get(mid, {})
            asset_code = mach.get("asset_code") or mc_row.get("machine_label") or "—"
            make      = mach.get("make",  "") or mc_row.get("make",  "") or ""
            model     = mach.get("model", "") or mc_row.get("model", "") or ""
            serial_no = mach.get("serial_number") or mc_row.get("serial_number") or "—"
            suffix    = " ".join(p for p in [make, model] if p)
            machine_label = f"{asset_code} — {suffix}" if suffix else asset_code

            mob_cost   = float(mc_row.get("mobilization_cost")   or 0)
            demob_cost = float(mc_row.get("demobilization_cost")  or 0)

            # ── Monthly worklog rows (active WOs only) ────────────────────────
            wo_is_active = (
                wo_start <= today
                and (wo_end is None or wo_end >= today)
            )
            if wo_is_active:
                for yr, mo in _months_range(wo_start, today):
                    bm_str = _billing_month_str(yr, mo)
                    wl     = wl_lookup.get((wo_id, mid, bm_str))

                    if wl is None:
                        status   = "Missing"
                    elif wl.get("is_draft", True):
                        status   = "Draft"
                    else:
                        status   = "Submitted"

                    row = {
                        "Customer":      customer,
                        "Site":          site,
                        "Asset Code":    asset_code,
                        "Machine":       machine_label,
                        "Serial No.":    serial_no,
                        "Month":         bm_str,
                        "_date":         date(yr, mo, 1),
                        "Status":        status,
                        "_wo_id":        wo_id,
                        "_machine_id":   mid,
                        "_yr":           yr,
                        "_mo":           mo,
                    }

                    if status in ("Missing", "Draft"):
                        pending_rows.append(row)
                    else:
                        completed_rows.append(row)

            # ── Pending Mobilization ──────────────────────────────────────────
            # Pending once WO has started and mob cost > 0
            if mob_cost > 0 and wo_start <= today:
                mob_rows.append({
                    "Customer":   customer,
                    "Site":       site,
                    "Asset Code": asset_code,
                    "Machine":    machine_label,
                    "Serial No.": serial_no,
                    "WO Start":   wo_start.isoformat(),
                    "_date":      wo_start,
                    "Amount (₹)": mob_cost,
                    "Status":     "Pending",
                    "_wo_id":     wo_id,
                    "_machine_id":mid,
                })

            # ── Pending De-Mobilization ───────────────────────────────────────
            # Pending once WO end date has passed and demob cost > 0
            if demob_cost > 0 and wo_end and wo_end <= today:
                demob_rows.append({
                    "Customer":   customer,
                    "Site":       site,
                    "Asset Code": asset_code,
                    "Machine":    machine_label,
                    "Serial No.": serial_no,
                    "WO End":     wo_end.isoformat(),
                    "_date":      wo_end,
                    "Amount (₹)": demob_cost,
                    "Status":     "Pending",
                    "_wo_id":     wo_id,
                    "_machine_id":mid,
                })

    # Sort
    pending_rows.sort(key=lambda r: (r["_yr"], r["_mo"]))
    completed_rows.sort(key=lambda r: (r["_yr"], r["_mo"]), reverse=True)
    mob_rows.sort(key=lambda r: r["_date"])
    demob_rows.sort(key=lambda r: r["_date"])

    # ── Global Filters ─────────────────────────────────────────────────────────
    all_custs  = sorted({r["Customer"]   for r in pending_rows + completed_rows + mob_rows + demob_rows if r["Customer"]   != "—"})
    all_sites  = sorted({r["Site"]       for r in pending_rows + completed_rows + mob_rows + demob_rows if r["Site"]       != "—"})
    all_assets = sorted({r["Asset Code"] for r in pending_rows + completed_rows + mob_rows + demob_rows if r["Asset Code"] != "—"})

    with st.container(border=True):
        _section_hdr("tune", "Filters")
        fc1, fc2, fc3, fc4, fc5, fc6, fc7 = st.columns([2, 2, 2, 2, 2, 2, 1])

        with fc1:
            sel_cust  = st.selectbox("Customer",    ["All"] + all_custs,  key="wlr_cust")
        with fc2:
            sel_site  = st.selectbox("Site",        ["All"] + all_sites,  key="wlr_site")
        with fc3:
            sel_mach  = st.selectbox("Machine",     ["All"] + all_assets, key="wlr_mach")
        with fc4:
            all_dates = [r["_date"] for r in pending_rows + completed_rows + mob_rows + demob_rows if r.get("_date")]
            min_d = min(all_dates) if all_dates else date.today()
            max_d = date.today()
            sel_from = st.date_input("Date From", value=min_d, key="wlr_from")
        with fc5:
            sel_to   = st.date_input("Date To",   value=max_d, key="wlr_to")
        with fc6:
            st.markdown("<div></div>", unsafe_allow_html=True)
        with fc7:
            st.markdown("<div style='margin-top:22px'></div>", unsafe_allow_html=True)
            if st.button("Clear", key="wlr_clear"):
                for k in ["wlr_cust","wlr_site","wlr_mach","wlr_from","wlr_to"]:
                    st.session_state.pop(k, None)
                st.rerun()

    def _apply_filters(rows: list[dict]) -> list[dict]:
        out = rows
        if sel_cust != "All":
            out = [r for r in out if r["Customer"] == sel_cust]
        if sel_site != "All":
            out = [r for r in out if r["Site"] == sel_site]
        if sel_mach != "All":
            out = [r for r in out if r["Asset Code"] == sel_mach]
        if sel_from and sel_to and sel_from <= sel_to:
            out = [r for r in out if r.get("_date") and sel_from <= r["_date"] <= sel_to]
        return out

    f_pending   = _apply_filters(pending_rows)
    f_completed = _apply_filters(completed_rows)
    f_mob       = _apply_filters(mob_rows)
    f_demob     = _apply_filters(demob_rows)

    # ── KPI strip ──────────────────────────────────────────────────────────────
    n_missing   = sum(1 for r in f_pending if r["Status"] == "Missing")
    n_draft     = sum(1 for r in f_pending if r["Status"] == "Draft")

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='kpi-grid-6'>"
        + _kpi_card("pending",      "Pending WL",     len(f_pending),
                    "missing or draft",   "#EF4444")
        + _kpi_card("warning",      "Missing",        n_missing,
                    "no worklog yet",     "#F59E0B")
        + _kpi_card("edit_note",    "Draft",          n_draft,
                    "saved, not submitted","#E87722")
        + _kpi_card("task_alt",     "Submitted",      len(f_completed),
                    "completed worklogs", "#10B981")
        + _kpi_card("local_shipping","Pending Mob",   len(f_mob),
                    "mobilization due",   "#8B5CF6")
        + _kpi_card("local_shipping","Pending Demob", len(f_demob),
                    "de-mobilization due","#6366F1")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Tabs ───────────────────────────────────────────────────────────────────
    n_pending_all = len(f_pending) + len(f_mob) + len(f_demob)
    tab_pending, tab_completed, tab_billing = st.tabs([
        f"Pending ({n_pending_all})",
        f"Completed ({len(f_completed)})",
        f"Pending for Billing ({len(f_completed)})",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — PENDING
    # ══════════════════════════════════════════════════════════════════════════
    with tab_pending:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        # ── Pending Worklogs section ──────────────────────────────────────────
        st.markdown(
            "<div class='pending-section-title'>Pending Monthly Worklogs</div>",
            unsafe_allow_html=True,
        )

        if not f_pending:
            st.markdown(
                "<div class='empty-state-v2' style='padding:36px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:34px;color:#2563EB;'>task_alt</span>"
                "</div>"
                "<h3>All worklogs up to date</h3>"
                "<p>No missing or draft worklogs for the selected filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            # Sub-filter: current month only toggle
            show_all = st.checkbox(
                "Show all months (including prior)",
                value=False,
                key="wlr_show_all",
            )
            cur_bm  = _billing_month_str(today.year, today.month)
            display = f_pending if show_all else [r for r in f_pending if r["Month"] == cur_bm]

            if not display and not show_all:
                st.info(f"No pending worklogs for {cur_bm}. Enable 'Show all months' to see prior months.")
            else:
                _WL_COLS = ["Customer", "Site", "Machine", "Serial No.", "Month", "Status"]
                pdf = pd.DataFrame([{k: r[k] for k in _WL_COLS} for r in display], columns=_WL_COLS)

                def _pstyle(val: str) -> str:
                    if val == "Missing": return "color:#ef4444;font-weight:700;"
                    if val == "Draft":   return "color:#E87722;font-weight:700;"
                    return ""

                with st.container(border=True):
                    st.dataframe(
                        pdf.style.map(_pstyle, subset=["Status"]),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                            "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                            "Month":      st.column_config.TextColumn("Month",      width="small"),
                            "Status":     st.column_config.TextColumn("Status",     width="small"),
                        },
                    )

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Missing",  sum(1 for r in display if r["Status"] == "Missing"))
                m2.metric("Draft",    sum(1 for r in display if r["Status"] == "Draft"))
                m3.metric("Machines", len({r["_machine_id"] for r in display}))
                m4.metric("Customers", len({r["Customer"] for r in display}))

                render_export_buttons(
                    pdf, "pending_worklogs",
                    "wlr_pend_xl", "wlr_pend_pdf", "Pending Worklogs",
                )

        # ── Pending Mobilization section ──────────────────────────────────────
        st.markdown(
            "<div class='pending-section-title'>Pending Mobilization</div>",
            unsafe_allow_html=True,
        )

        if not f_mob:
            st.markdown(
                "<div style='padding:16px;background:#F8FAFC;border:1px solid #E2EBF0;"
                "border-radius:10px;font-size:13px;color:#6B7280;'>"
                "No pending mobilization charges for the selected filters.</div>",
                unsafe_allow_html=True,
            )
        else:
            _MOB_COLS = ["Customer", "Site", "Machine", "Serial No.", "WO Start", "Amount (₹)", "Status"]
            mob_df = pd.DataFrame([{k: r[k] for k in _MOB_COLS} for r in f_mob], columns=_MOB_COLS)

            with st.container(border=True):
                st.dataframe(
                    mob_df.style
                    .map(lambda v: "color:#991B1B;font-weight:700;", subset=["Status"])
                    .format({"Amount (₹)": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "WO Start":   st.column_config.TextColumn("WO Start",   width="small"),
                        "Amount (₹)": st.column_config.NumberColumn("Amount (₹)", format="₹%,.0f"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                )

            ma1, ma2 = st.columns(2)
            ma1.metric("Machines Pending Mob",  len(f_mob))
            ma2.metric("Total Mob Amount (₹)", f"{sum(r['Amount (₹)'] for r in f_mob):,.0f}")

        # ── Pending De-Mobilization section ───────────────────────────────────
        st.markdown(
            "<div class='pending-section-title'>Pending De-Mobilization</div>",
            unsafe_allow_html=True,
        )

        if not f_demob:
            st.markdown(
                "<div style='padding:16px;background:#F8FAFC;border:1px solid #E2EBF0;"
                "border-radius:10px;font-size:13px;color:#6B7280;'>"
                "No pending de-mobilization charges for the selected filters.</div>",
                unsafe_allow_html=True,
            )
        else:
            _DEMOB_COLS = ["Customer", "Site", "Machine", "Serial No.", "WO End", "Amount (₹)", "Status"]
            demob_df = pd.DataFrame([{k: r[k] for k in _DEMOB_COLS} for r in f_demob], columns=_DEMOB_COLS)

            with st.container(border=True):
                st.dataframe(
                    demob_df.style
                    .map(lambda v: "color:#991B1B;font-weight:700;", subset=["Status"])
                    .format({"Amount (₹)": "{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "WO End":     st.column_config.TextColumn("WO End",     width="small"),
                        "Amount (₹)": st.column_config.NumberColumn("Amount (₹)", format="₹%,.0f"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                )

            da1, da2 = st.columns(2)
            da1.metric("Machines Pending Demob",  len(f_demob))
            da2.metric("Total Demob Amount (₹)", f"{sum(r['Amount (₹)'] for r in f_demob):,.0f}")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — COMPLETED WORKLOGS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_completed:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

        if not f_completed:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:34px;color:#2563EB;'>assignment</span>"
                "</div>"
                "<h3>No completed worklogs</h3>"
                "<p>No submitted worklogs match the selected filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            available_months = sorted(
                {r["Month"] for r in f_completed},
                key=lambda s: datetime.strptime(s, "%B %Y"),
                reverse=True,
            )
            with st.container(border=True):
                _section_hdr("tune", "Month Filter")
                fp1, _ = st.columns([2, 6])
                with fp1:
                    sel_month = st.selectbox(
                        "Month", ["All"] + available_months,
                        label_visibility="collapsed",
                        key="wlr_comp_month",
                    )

            display = (
                f_completed if sel_month == "All"
                else [r for r in f_completed if r["Month"] == sel_month]
            )

            _COMP_COLS = ["Customer", "Site", "Machine", "Serial No.", "Month", "Status"]
            cdf = pd.DataFrame([{k: r[k] for k in _COMP_COLS} for r in display], columns=_COMP_COLS)

            with st.container(border=True):
                _section_hdr("task_alt", "Completed Worklogs")
                st.dataframe(
                    cdf.style.map(lambda v: "color:#16a34a;font-weight:700;", subset=["Status"]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "Month":      st.column_config.TextColumn("Month",      width="small"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                )

            render_export_buttons(
                cdf, "completed_worklogs",
                "wlr_comp_xl", "wlr_comp_pdf", "Completed Worklogs",
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — PENDING FOR BILLING
    # ══════════════════════════════════════════════════════════════════════════
    with tab_billing:
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:10px;"
            "padding:12px 16px;margin-bottom:14px;font-size:13px;color:#1E40AF;"
            "display:flex;align-items:center;gap:8px;'>"
            "<span class='msr' style='font-size:18px;'>info</span>"
            "Showing all submitted worklogs — these are pending invoice generation.</div>",
            unsafe_allow_html=True,
        )

        if not f_completed:
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:34px;color:#2563EB;'>receipt_long</span>"
                "</div>"
                "<h3>No worklogs pending billing</h3>"
                "<p>No submitted worklogs match the selected filters.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            avail_b = sorted(
                {r["Month"] for r in f_completed},
                key=lambda s: datetime.strptime(s, "%B %Y"),
                reverse=True,
            )
            with st.container(border=True):
                _section_hdr("tune", "Month Filter")
                fp2, _ = st.columns([2, 6])
                with fp2:
                    sel_b = st.selectbox(
                        "Month", ["All"] + avail_b,
                        label_visibility="collapsed",
                        key="wlr_bill_month",
                    )

            billing_display = (
                f_completed if sel_b == "All"
                else [r for r in f_completed if r["Month"] == sel_b]
            )

            _BILL_COLS = ["Customer", "Site", "Machine", "Serial No.", "Month", "Status"]
            bdf = pd.DataFrame([{k: r[k] for k in _BILL_COLS} for r in billing_display], columns=_BILL_COLS)
            bdf["Status"] = "Pending Billing"

            with st.container(border=True):
                _section_hdr("receipt_long", "Pending for Billing")
                st.dataframe(
                    bdf.style.map(lambda v: "color:#E87722;font-weight:700;", subset=["Status"]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Machine":    st.column_config.TextColumn("Machine",    width="medium"),
                        "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                        "Month":      st.column_config.TextColumn("Month",      width="small"),
                        "Status":     st.column_config.TextColumn("Status",     width="small"),
                    },
                )

            b1, b2 = st.columns(2)
            b1.metric("Worklogs Pending Billing", len(billing_display))
            b2.metric("Machines Affected", len({r["_machine_id"] for r in billing_display}))

            render_export_buttons(
                bdf, "pending_billing",
                "wlr_bill_xl", "wlr_bill_pdf", "Pending for Billing",
            )

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    if st.button("Refresh Data", key="wlr_refresh"):
        st.rerun()
