"""
erp/views/customerreport.py
Customer Reports — Revenue Summary and Deployment History per customer.
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
    if v == "closed":
        return "color:#6b7280;font-weight:600;"
    if v == "upcoming":
        return "color:#2563eb;font-weight:700;"
    return ""


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        "<div class='page-eyebrow'>// Reports</div>"
        "<div class='page-title'>Customer Reports</div>",
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

    today    = date.today()
    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}
    mach_map = {m["id"]: m for m in machines if m.get("id")}

    # ════════════════════════════════════════════════════════════════════
    # SECTION 1 — CUSTOMER REVENUE SUMMARY
    # ════════════════════════════════════════════════════════════════════
    _section_header("Customer Revenue Summary")

    # Aggregate per customer across active WOs
    cust_agg: dict[str, dict] = {}
    for c in customers_list:
        if c.get("id"):
            cust_agg[c["id"]] = {
                "name":          c.get("customer_name", "—"),
                "active_wos":    0,
                "active_mids":   set(),
                "rr":            0.0,
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
        st.info("No active customer work orders found.")

    st.markdown("<div style='margin-top:40px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 2 — CUSTOMER DEPLOYMENT HISTORY
    # ════════════════════════════════════════════════════════════════════
    _section_header("Customer Deployment History")

    if not customers_list:
        st.info("No customers found.")
        return

    cust_sorted   = sorted(customers_list, key=lambda c: c.get("customer_name", ""))
    cust_labels   = [c.get("customer_name", "—") for c in cust_sorted]
    cust_ids      = [c.get("id", "") for c in cust_sorted]

    sel_label = st.selectbox(
        "Customer",
        cust_labels,
        label_visibility="collapsed",
        key="cr_customer",
    )
    sel_cid = cust_ids[cust_labels.index(sel_label)]

    # Filter WOs and deployments for this customer
    cust_wos  = [wo  for wo  in work_orders  if wo.get("customer_id")  == sel_cid]
    cust_deps = [dep for dep in deployments  if dep.get("customer_id") == sel_cid]
    cust_wo_ids = {wo.get("id") for wo in cust_wos}

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
            st.info("No work orders for this customer.")
        else:
            wo_rows = []
            for wo in sorted(cust_wos, key=lambda w: _parse_date(w.get("start_date")) or date.min, reverse=True):
                mc      = _parse_mc(wo.get("machine_config"))
                rental  = sum(float(r.get("rental_per_month") or 0) for r in mc)
                sd      = _parse_date(wo.get("start_date"))
                ed      = _parse_date(wo.get("end_date"))
                wo_num  = wo.get("wo_number", "—") or "—"
                cli_wo  = wo.get("client_work_ordernumber", "") or ""
                wo_disp = f"{wo_num} / {cli_wo}" if cli_wo and cli_wo != wo_num else wo_num
                wo_rows.append({
                    "Work Order":        wo_disp,
                    "Site":              site_map.get(wo.get("site_id", ""), "—"),
                    "Start Date":        _fmt_date(sd),
                    "End Date":          _fmt_date(ed) if ed else "Open",
                    "No. of Machines":   len([r for r in mc if r.get("machine_id") or r.get("machine_label")]),
                    "Monthly Rental":    f"₹ {rental:,.0f}" if rental else "—",
                    "Status":            _wo_status(sd, ed, today),
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
            st.info("No deployments for this customer.")
        else:
            wo_map = {wo.get("id"): wo for wo in work_orders}
            dep_rows = []
            for dep in sorted(
                cust_deps,
                key=lambda d: _parse_date(d.get("deployment_date")) or date.min,
                reverse=True,
            ):
                wo      = wo_map.get(dep.get("work_order_id", ""), {})
                wo_num  = wo.get("wo_number", "—") or "—"
                # Count machines in this deployment
                md_raw  = dep.get("machine_deployments")
                n_mach  = 0
                if md_raw:
                    try:
                        mds    = json.loads(md_raw) if isinstance(md_raw, str) else md_raw
                        n_mach = len(mds) if isinstance(mds, list) else 0
                    except Exception:
                        pass
                dep_rows.append({
                    "Work Order":        wo_num,
                    "Site":              site_map.get(dep.get("site_id", ""), "—"),
                    "Deployment Date":   _fmt_date(dep.get("deployment_date")),
                    "No. of Machines":   n_mach,
                    "Status":            dep.get("deployment_status", "—") or "—",
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
        # Collect unique machine_ids across all WOs for this customer
        supplied: dict[str, dict] = {}   # machine_id → {machine, first_wo_date, last_wo_date}
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
            st.info("No machines found for this customer.")
        else:
            mach_rows = []
            for mid, dates in supplied.items():
                m = mach_map.get(mid, {})
                mach_rows.append({
                    "Machine Code":    m.get("asset_code",        "—") or "—",
                    "Serial Number":   m.get("serial_number",     "—") or "—",
                    "Make":            m.get("make",              "—") or "—",
                    "Model":           m.get("model",             "—") or "—",
                    "Working Height":  m.get("working_capacity",  "—") or "—",
                    "Current Status":  m.get("operational_status","—") or "—",
                    "First Deployed":  _fmt_date(dates["first"]),
                    "Last Deployed":   _fmt_date(dates["last"]),
                })
            mach_rows.sort(key=lambda r: r["Machine Code"])
            mdf = pd.DataFrame(mach_rows)
            st.dataframe(mdf, use_container_width=True, hide_index=True)
            st.caption(f"{len(mach_rows)} distinct machine{'s' if len(mach_rows) != 1 else ''} supplied to this customer.")
            st.download_button(
                "Export CSV",
                data=mdf.to_csv(index=False).encode("utf-8"),
                file_name=f"machines_{sel_label.replace(' ', '_')}_{today.isoformat()}.csv",
                mime="text/csv",
                key="cr_mach_csv",
            )

    # ── Site History ──────────────────────────────────────────────────────────
    with tab_site:
        # Group WOs by site
        site_agg: dict[str, dict] = {}
        for wo in cust_wos:
            sid = wo.get("site_id", "")
            if not sid:
                continue
            sd = _parse_date(wo.get("start_date")) or date.min
            ed = _parse_date(wo.get("end_date"))
            mc_count = len([r for r in _parse_mc(wo.get("machine_config"))
                            if r.get("machine_id") or r.get("machine_label")])
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
            st.info("No site history for this customer.")
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
