"""
erp/views/customerreport.py
Customer Reports — Revenue Summary and Deployment History per customer.
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

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
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


def _parse_mc(mc_raw) -> list[dict]:
    if not mc_raw:
        return []
    try:
        records = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
        return records if isinstance(records, list) else []
    except Exception:
        return []


def _wo_status(start: date | None, end: date | None, today: date) -> str:
    if start and start > today:
        return "Upcoming"
    if end is None:
        return "Active"
    return "Active" if end >= today else "Closed"


def _status_style(val: str) -> str:
    v = str(val).lower()
    if v == "active":
        return "color:#16a34a;font-weight:700;"
    if v == "closed":
        return "color:#6b7280;font-weight:600;"
    if v == "upcoming":
        return "color:#2563eb;font-weight:700;"
    return ""


# ── HTML builders ─────────────────────────────────────────────────────────────

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


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Customer Reports</div>",
        unsafe_allow_html=True,
    )

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

    today    = date.today()
    site_map = {s["id"]: s.get("site_name", "—") for s in sites_list if s.get("id")}
    mach_map = {m["id"]: m for m in machines if m.get("id")}

    # ── Build customer aggregation (active WOs only) ───────────────────────────
    cust_agg: dict[str, dict] = {}
    for c in customers_list:
        if c.get("id"):
            cust_agg[c["id"]] = {
                "name":        c.get("customer_name", "—"),
                "active_wos":  0,
                "active_mids": set(),
                "rr":          0.0,
            }

    for wo in work_orders:
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd is None or sd > today:
            continue
        if ed is not None and ed < today:
            continue
        cid = wo.get("customer_id", "")
        if cid not in cust_agg:
            continue
        cust_agg[cid]["active_wos"] += 1
        for mc in _parse_mc(wo.get("machine_config")):
            mid = mc.get("machine_id")
            if mid:
                cust_agg[cid]["active_mids"].add(mid)
            cust_agg[cid]["rr"] += float(mc.get("rental_per_month") or 0)

    # ── KPI strip ─────────────────────────────────────────────────────────────
    n_customers      = len(customers_list)
    total_active_wos = sum(a["active_wos"] for a in cust_agg.values())
    total_machines   = sum(len(a["active_mids"]) for a in cust_agg.values())
    total_rr         = sum(a["rr"] for a in cust_agg.values())

    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='kpi-grid' style='grid-template-columns:repeat(4,1fr);'>"
        + _kpi_card("groups",              "Customers",        n_customers,
                    "in master directory",                      "#2563EB")
        + _kpi_card("assignment_turned_in","Active WOs",       total_active_wos,
                    "currently running work orders",            "#10B981")
        + _kpi_card("precision_manufacturing","Machines Out",  total_machines,
                    "unique machines deployed",                 "#8B5CF6")
        + _kpi_card("payments",            "Revenue Run Rate",
                    f"₹{total_rr:,.0f}" if total_rr else "—",
                    "monthly rental across active WOs",         "#F59E0B")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ════════════════════════════════════════════════════════════════════
    # SECTION 1 — CUSTOMER REVENUE SUMMARY
    # ════════════════════════════════════════════════════════════════════
    with st.container(border=True):
        _section_hdr("payments", "Customer Revenue Summary")

        summary_rows = [
            {
                "Customer":            a["name"],
                "Active Machines":     len(a["active_mids"]),
                "Active Work Orders":  a["active_wos"],
                "Revenue Run Rate":    f"₹ {a['rr']:,.0f}" if a["rr"] else "—",
            }
            for a in cust_agg.values()
            if a["active_wos"] > 0
        ]
        summary_rows.sort(key=lambda r: r["Active Work Orders"], reverse=True)

        if summary_rows:
            st.dataframe(
                pd.DataFrame(summary_rows),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#9CA3AF;'>assignment_late</span>"
                "</div>"
                "<h3>No active work orders</h3>"
                "<p>No customers have active work orders at the moment.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 2 — CUSTOMER DEPLOYMENT HISTORY
    # ════════════════════════════════════════════════════════════════════
    _section_hdr("history", "Customer Deployment History")

    if not customers_list:
        st.markdown(
            "<div class='empty-state-v2'>"
            "<div class='empty-icon-ring'>"
            "<span class='msr' style='font-size:36px;color:#2563EB;'>groups</span>"
            "</div>"
            "<h3>No customers found</h3>"
            "<p>Add customers to the system to view their deployment history here.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    cust_sorted = sorted(customers_list, key=lambda c: c.get("customer_name", ""))
    cust_labels = [c.get("customer_name", "—") for c in cust_sorted]
    cust_ids    = [c.get("id", "") for c in cust_sorted]

    with st.container(border=True):
        _section_hdr("person_search", "Select Customer")
        sel_label = st.selectbox(
            "Customer",
            cust_labels,
            label_visibility="collapsed",
            key="cr_customer",
        )

    sel_cid = cust_ids[cust_labels.index(sel_label)]

    # Filter WOs and deployments for this customer
    cust_wos    = [wo  for wo  in work_orders if wo.get("customer_id")  == sel_cid]
    cust_deps   = [dep for dep in deployments if dep.get("customer_id") == sel_cid]

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

    tab_wo, tab_dep, tab_mach, tab_site = st.tabs([
        f"Work Orders ({len(cust_wos)})",
        f"Deployments ({len(cust_deps)})",
        "Machines Supplied",
        "Site History",
    ])

    # ── Work Orders ───────────────────────────────────────────────────────────
    with tab_wo:
        if not cust_wos:
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#9CA3AF;'>assignment</span>"
                "</div>"
                "<h3>No work orders</h3>"
                "<p>This customer has no work orders on record.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            wo_rows = []
            for wo in sorted(
                cust_wos,
                key=lambda w: _parse_date(w.get("start_date")) or date.min,
                reverse=True,
            ):
                mc      = _parse_mc(wo.get("machine_config"))
                rental  = sum(float(r.get("rental_per_month") or 0) for r in mc)
                sd      = _parse_date(wo.get("start_date"))
                ed      = _parse_date(wo.get("end_date"))
                wo_num  = wo.get("wo_number", "—") or "—"
                cli_wo  = wo.get("client_work_ordernumber", "") or ""
                wo_disp = f"{wo_num} / {cli_wo}" if cli_wo and cli_wo != wo_num else wo_num
                wo_rows.append({
                    "Work Order":       wo_disp,
                    "Site":             site_map.get(wo.get("site_id", ""), "—"),
                    "Start Date":       _fmt_date(sd),
                    "End Date":         _fmt_date(ed) if ed else "Open",
                    "No. of Machines":  len([r for r in mc if r.get("machine_id") or r.get("machine_label")]),
                    "Monthly Rental":   f"₹ {rental:,.0f}" if rental else "—",
                    "Status":           _wo_status(sd, ed, today),
                })
            wdf = pd.DataFrame(wo_rows)
            st.dataframe(
                wdf.style.applymap(_status_style, subset=["Status"]),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Export CSV",
                data=wdf.to_csv(index=False).encode("utf-8"),
                file_name=f"wo_{sel_label.replace(' ', '_')}_{today.isoformat()}.csv",
                mime="text/csv",
                key="cr_wo_csv",
            )

    # ── Deployments ───────────────────────────────────────────────────────────
    with tab_dep:
        if not cust_deps:
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#9CA3AF;'>local_shipping</span>"
                "</div>"
                "<h3>No deployments</h3>"
                "<p>This customer has no deployment records on file.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            wo_map = {wo.get("id"): wo for wo in work_orders}
            dep_rows = []
            for dep in sorted(
                cust_deps,
                key=lambda d: _parse_date(d.get("deployment_date")) or date.min,
                reverse=True,
            ):
                wo     = wo_map.get(dep.get("work_order_id", ""), {})
                wo_num = wo.get("wo_number", "—") or "—"
                md_raw = dep.get("machine_deployments")
                n_mach = 0
                if md_raw:
                    try:
                        mds    = json.loads(md_raw) if isinstance(md_raw, str) else md_raw
                        n_mach = len(mds) if isinstance(mds, list) else 0
                    except Exception:
                        pass
                dep_rows.append({
                    "Work Order":       wo_num,
                    "Site":             site_map.get(dep.get("site_id", ""), "—"),
                    "Deployment Date":  _fmt_date(dep.get("deployment_date")),
                    "No. of Machines":  n_mach,
                    "Status":           dep.get("deployment_status", "—") or "—",
                })
            ddf = pd.DataFrame(dep_rows)
            st.dataframe(
                ddf.style.applymap(
                    lambda v: "color:#16a34a;font-weight:700;" if str(v).lower() == "active"
                              else ("color:#6b7280;" if str(v).lower() == "closed" else ""),
                    subset=["Status"],
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.download_button(
                "Export CSV",
                data=ddf.to_csv(index=False).encode("utf-8"),
                file_name=f"dep_{sel_label.replace(' ', '_')}_{today.isoformat()}.csv",
                mime="text/csv",
                key="cr_dep_csv",
            )

    # ── Machines Supplied ─────────────────────────────────────────────────────
    with tab_mach:
        supplied: dict[str, dict] = {}
        for wo in cust_wos:
            sd = _parse_date(wo.get("start_date")) or date.min
            for mc in _parse_mc(wo.get("machine_config")):
                mid = mc.get("machine_id")
                if not mid:
                    continue
                if mid not in supplied:
                    supplied[mid] = {"first": sd, "last": sd}
                else:
                    supplied[mid]["first"] = min(supplied[mid]["first"], sd)
                    supplied[mid]["last"]  = max(supplied[mid]["last"],  sd)

        if not supplied:
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#9CA3AF;'>precision_manufacturing</span>"
                "</div>"
                "<h3>No machines found</h3>"
                "<p>No machines have been assigned to this customer's work orders.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            mach_rows = []
            for mid, dates in supplied.items():
                m = mach_map.get(mid, {})
                mach_rows.append({
                    "Machine Code":   m.get("asset_code",         "—") or "—",
                    "Serial Number":  m.get("serial_number",      "—") or "—",
                    "Make":           m.get("make",               "—") or "—",
                    "Model":          m.get("model",              "—") or "—",
                    "Working Height": m.get("working_capacity",   "—") or "—",
                    "Current Status": m.get("operational_status", "—") or "—",
                    "First Deployed": _fmt_date(dates["first"]),
                    "Last Deployed":  _fmt_date(dates["last"]),
                })
            mach_rows.sort(key=lambda r: r["Machine Code"])
            mdf = pd.DataFrame(mach_rows)
            st.dataframe(mdf, use_container_width=True, hide_index=True)
            st.caption(
                f"{len(mach_rows)} distinct machine{'s' if len(mach_rows) != 1 else ''} "
                f"supplied to this customer."
            )
            st.download_button(
                "Export CSV",
                data=mdf.to_csv(index=False).encode("utf-8"),
                file_name=f"machines_{sel_label.replace(' ', '_')}_{today.isoformat()}.csv",
                mime="text/csv",
                key="cr_mach_csv",
            )

    # ── Site History ──────────────────────────────────────────────────────────
    with tab_site:
        site_agg: dict[str, dict] = {}
        for wo in cust_wos:
            sid = wo.get("site_id", "")
            if not sid:
                continue
            sd = _parse_date(wo.get("start_date")) or date.min
            ed = _parse_date(wo.get("end_date"))
            if sid not in site_agg:
                site_agg[sid] = {
                    "wo_count":   0,
                    "first_date": sd,
                    "last_date":  sd,
                    "machines":   set(),
                }
            a = site_agg[sid]
            a["wo_count"]   += 1
            a["first_date"]  = min(a["first_date"], sd)
            a["last_date"]   = max(a["last_date"],  sd)
            for mc in _parse_mc(wo.get("machine_config")):
                mid = mc.get("machine_id")
                if mid:
                    a["machines"].add(mid)

        if not site_agg:
            st.markdown(
                "<div class='empty-state-v2' style='padding:40px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:30px;color:#9CA3AF;'>location_off</span>"
                "</div>"
                "<h3>No site history</h3>"
                "<p>No site deployments recorded for this customer.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            site_rows = [
                {
                    "Site":              site_map.get(sid, "—"),
                    "Work Orders":       a["wo_count"],
                    "Machines Supplied": len(a["machines"]),
                    "First Deployment":  _fmt_date(a["first_date"]),
                    "Last Deployment":   _fmt_date(a["last_date"]),
                }
                for sid, a in site_agg.items()
            ]
            site_rows.sort(key=lambda r: r["Work Orders"], reverse=True)
            sdf = pd.DataFrame(site_rows)
            st.dataframe(sdf, use_container_width=True, hide_index=True)
            st.download_button(
                "Export CSV",
                data=sdf.to_csv(index=False).encode("utf-8"),
                file_name=f"sites_{sel_label.replace(' ', '_')}_{today.isoformat()}.csv",
                mime="text/csv",
                key="cr_site_csv",
            )
