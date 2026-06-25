"""
erp/views/workorder.py
Work Order — one WO can contain multiple machines, each with its own
billing configuration. Start Date and End Date are at the WO level.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient

# ── Constants ─────────────────────────────────────────────────────────────────

BILLING_TYPES  = ["Monthly Fixed Rental", "Daily Rental"]
BILLING_CYCLES = ["Calendar Month", "Custom"]

_MC_COLS = [
    "Machine",
    "Billing Type", "Billing Cycle",
    "Rental / Month",
    "Cycle Start", "Cycle End",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _default_cycle_dates(ref: date | None) -> tuple[date, date]:
    d = ref or date.today()
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _parse_machine_config(raw, id_to_label: dict) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=_MC_COLS)
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(records, list):
            return pd.DataFrame(columns=_MC_COLS)
        rows = []
        for r in records:
            rows.append({
                "Machine":        id_to_label.get(r.get("machine_id", ""), r.get("machine_label", "")),
                "Billing Type":   r.get("billing_type", BILLING_TYPES[0]),
                "Billing Cycle":  r.get("billing_cycle", BILLING_CYCLES[0]),
                "Rental / Month": float(r.get("rental_per_month") or 0.0),
                "Cycle Start":    _parse_date(r.get("billing_cycle_start_date")),
                "Cycle End":      _parse_date(r.get("billing_cycle_end_date")),
            })
        return pd.DataFrame(rows, columns=_MC_COLS)
    except Exception:
        return pd.DataFrame(columns=_MC_COLS)


def _machine_config_to_json(df: pd.DataFrame, label_to_id: dict) -> str:
    records = []
    for _, row in df.iterrows():
        label = str(row.get("Machine") or "").strip()
        if not label:
            continue
        cs = row.get("Cycle Start")
        ce = row.get("Cycle End")
        records.append({
            "machine_id":               label_to_id.get(label),
            "machine_label":            label,
            "billing_type":             str(row.get("Billing Type") or ""),
            "billing_cycle":            str(row.get("Billing Cycle") or ""),
            "rental_per_month":         float(row.get("Rental / Month") or 0),
            "billing_cycle_start_date": cs.isoformat() if isinstance(cs, date) else None,
            "billing_cycle_end_date":   ce.isoformat() if isinstance(ce, date) else None,
        })
    return json.dumps(records)


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Work Orders</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error("Supabase client initialization failed.")
        st.write(str(exc))
        return

    # ── Fetchers ───────────────────────────────────────────────────────────────
    def fetch_work_orders() -> list[dict]:
        try:
            return sb.list_work_orders()
        except Exception as exc:
            st.error(f"Failed to load work orders: {exc}")
            return []

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception:
            return []

    def fetch_sites() -> list[dict]:
        try:
            return sb.list_sites()
        except Exception:
            return []

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception:
            return []

    work_orders = fetch_work_orders()
    customers   = fetch_customers()
    sites       = fetch_sites()
    machines    = fetch_machines()

    customer_map = {c.get("id"): c for c in customers if c.get("id")}
    site_map     = {s.get("id"): s for s in sites     if s.get("id")}
    wo_map       = {w.get("id"): w for w in work_orders if w.get("id")}

    # Machine label ↔ ID lookups
    id_to_label  = {
        m.get("id"): f"{m.get('asset_code', '')} — {m.get('machine_type', '')}".strip("— ")
        for m in machines if m.get("id")
    }
    label_to_id  = {v: k for k, v in id_to_label.items()}
    machine_opts = [""] + sorted(id_to_label.values())

    # ── Edit selector ──────────────────────────────────────────────────────────
    selected_wo_id = st.selectbox(
        "Edit existing work order",
        options=[""] + list(wo_map),
        format_func=lambda wid: "New work order" if not wid
            else f"{wo_map[wid].get('wo_number', 'Unknown')} — "
                 f"{customer_map.get(wo_map[wid].get('customer_id', ''), {}).get('customer_name', '')}",
        key="selected_wo_id",
    )
    selected_wo = wo_map.get(selected_wo_id)
    wo_key = selected_wo_id or "new"

    # ── Sync session state on selection change ─────────────────────────────────
    if st.session_state.get("_editing_wo_id") != selected_wo_id:
        st.session_state["_editing_wo_id"] = selected_wo_id
        wo = selected_wo or {}
        st.session_state["wo_customer_id"] = wo.get("customer_id", "")
        st.session_state["wo_site_id"]     = wo.get("site_id", "")
        st.session_state["wo_start_date"]  = _parse_date(wo.get("start_date"))
        st.session_state["wo_end_date"]    = _parse_date(wo.get("end_date"))
        for k in [f"mc_data_{wo_key}", f"mc_recalc_{wo_key}"]:
            st.session_state.pop(k, None)

    # ── A. Basic Selection ─────────────────────────────────────────────────────
    st.markdown(
        "<div style='margin-bottom:6px;border-top:2px solid #E87722;padding-top:10px;"
        "font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        "text-transform:uppercase;'>A — Basic Selection</div>",
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        selected_customer_id = st.selectbox(
            "Customer *",
            options=[""] + list(customer_map),
            format_func=lambda cid: "Select customer" if not cid
                else customer_map[cid].get("customer_name", "Unknown"),
            key="wo_customer_id",
        )
    with col2:
        filtered_sites = {
            sid: s for sid, s in site_map.items()
            if str(s.get("customer_id", "")) == str(selected_customer_id)
        }
        if st.session_state.get("wo_site_id") not in filtered_sites:
            st.session_state["wo_site_id"] = ""
        selected_site_id = st.selectbox(
            "Site *",
            options=[""] + list(filtered_sites),
            format_func=lambda sid: "Select site" if not sid
                else filtered_sites[sid].get("site_name", "Unknown"),
            key="wo_site_id",
        )
    with col3:
        selected_start_date = st.date_input("Start Date *", key="wo_start_date")
    with col4:
        selected_end_date = st.date_input("End Date", key="wo_end_date")

    # ── B. Machine Configuration ───────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='margin-bottom:6px;border-top:2px solid #E87722;padding-top:10px;"
        "font-size:10px;font-weight:700;letter-spacing:.12em;color:#E87722;"
        "text-transform:uppercase;'>B — Machine Configuration</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='font-size:12px;color:#6b7280;margin:0 0 10px;'>"
        "Add one or more machines. <strong>Calendar Month</strong> cycle dates "
        "auto-fill from the WO Start Date.</p>",
        unsafe_allow_html=True,
    )

    recalc_count = st.session_state.get(f"mc_recalc_{wo_key}", 0)
    editor_key   = f"mc_{wo_key}_{recalc_count}"

    # Determine initial DataFrame
    if f"mc_data_{wo_key}" in st.session_state:
        initial_df = st.session_state[f"mc_data_{wo_key}"]
    elif selected_wo and selected_wo.get("machine_config"):
        initial_df = _parse_machine_config(selected_wo.get("machine_config"), id_to_label)
    else:
        cs, ce = _default_cycle_dates(selected_start_date)
        initial_df = pd.DataFrame([{
            "Machine":        "",
            "Billing Type":   BILLING_TYPES[0],
            "Billing Cycle":  BILLING_CYCLES[0],
            "Rental / Month": 0.0,
            "Cycle Start":    cs,
            "Cycle End":      ce,
        }], columns=_MC_COLS)

    edited_machines = st.data_editor(
        initial_df,
        column_config={
            "Machine":        st.column_config.SelectboxColumn(
                                  "Machine *", options=machine_opts, width="large"),
            "Billing Type":   st.column_config.SelectboxColumn(
                                  "Billing Type", options=BILLING_TYPES, width="medium"),
            "Billing Cycle":  st.column_config.SelectboxColumn(
                                  "Billing Cycle", options=BILLING_CYCLES, width="medium"),
            "Rental / Month": st.column_config.NumberColumn(
                                  "Rental / Month", format="%.0f", step=1000,
                                  min_value=0, width="medium"),
            "Cycle Start":    st.column_config.DateColumn(
                                  "Cycle Start", width="medium"),
            "Cycle End":      st.column_config.DateColumn(
                                  "Cycle End", width="medium"),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=editor_key,
    )

    # Auto-fill Cycle Start / Cycle End for Calendar Month rows using WO Start Date
    if edited_machines is not None and not edited_machines.empty:
        updated   = edited_machines.copy()
        needs_upd = False
        ref_date  = selected_start_date if isinstance(selected_start_date, date) else None
        exp_cs, exp_ce = _default_cycle_dates(ref_date)
        for idx, row in updated.iterrows():
            if str(row.get("Billing Cycle", "")) == "Calendar Month":
                cs = row.get("Cycle Start")
                ce = row.get("Cycle End")
                if cs != exp_cs or ce != exp_ce:
                    updated.at[idx, "Cycle Start"] = exp_cs
                    updated.at[idx, "Cycle End"]   = exp_ce
                    needs_upd = True
        if needs_upd:
            st.session_state[f"mc_data_{wo_key}"]   = updated
            st.session_state[f"mc_recalc_{wo_key}"] = recalc_count + 1
            st.rerun()

    # Summary bar beneath the table
    if edited_machines is not None and not edited_machines.empty:
        valid = edited_machines[
            edited_machines["Machine"].notna() & (edited_machines["Machine"] != "")
        ]
        if not valid.empty:
            st.markdown(
                f"<div style='display:flex;gap:32px;padding:8px 12px;"
                f"background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;"
                f"margin-top:4px;font-size:12px;'>"
                f"<span style='color:#6b7280;'>Machines: "
                f"<strong style='color:#111827;'>{len(valid)}</strong></span>"
                f"<span style='color:#6b7280;'>Total Rental / Month: "
                f"<strong style='color:#E87722;'>{float(valid['Rental / Month'].fillna(0).sum()):,.0f}</strong></span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

    # ── Form (submit) ──────────────────────────────────────────────────────────
    with st.form("wo_form"):
        if selected_wo:
            st.markdown(
                f"<span style='font-size:11px;color:#6b7280;'>WO Number: "
                f"<strong>{selected_wo.get('wo_number', '—')}</strong></span>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

        submitted = st.form_submit_button(
            "Update Work Order" if selected_wo else "Create Work Order"
        )

        if submitted:
            if not selected_customer_id:
                st.error("Customer is required.")
            elif not selected_site_id:
                st.error("Site is required.")
            elif not selected_start_date:
                st.error("Start Date is required.")
            else:
                valid_rows = (
                    edited_machines[
                        edited_machines["Machine"].notna() &
                        (edited_machines["Machine"] != "")
                    ]
                    if edited_machines is not None
                    else pd.DataFrame()
                )
                if valid_rows.empty:
                    st.error("Add at least one machine.")
                else:
                    machine_config_json = _machine_config_to_json(valid_rows, label_to_id)
                    payload = dict(
                        customer_id=selected_customer_id,
                        site_id=selected_site_id,
                        start_date=selected_start_date.isoformat() if isinstance(selected_start_date, date) else None,
                        end_date=selected_end_date.isoformat()     if isinstance(selected_end_date, date)   else None,
                        machine_config=machine_config_json,
                    )
                    try:
                        if selected_wo:
                            sb.update_work_order(selected_wo_id, payload)
                            st.success("Work order updated.")
                        else:
                            created = sb.insert_work_order(payload)
                            wo_num  = created.get("wo_number") or created.get("id", "")
                            st.success(f"Work order created: {wo_num}")
                        work_orders = fetch_work_orders()
                    except Exception as exc:
                        st.error(f"Could not save work order: {exc}")

    # ── Work order list ────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    col_cap, col_btn = st.columns([5, 1])
    with col_cap:
        st.markdown('<p class="filter-label">All Work Orders</p>', unsafe_allow_html=True)
    with col_btn:
        if st.button("Refresh", key="refresh_wo"):
            work_orders = fetch_work_orders()

    if work_orders:
        rows = []
        for w in work_orders:
            mc_raw    = w.get("machine_config")
            mc_list   = []
            total_rnt = 0.0
            if mc_raw:
                try:
                    mc_records = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
                    mc_list    = [r.get("machine_label", "") for r in mc_records if r.get("machine_label")]
                    total_rnt  = sum(float(r.get("rental_per_month") or 0) for r in mc_records)
                except Exception:
                    pass
            rows.append({
                "WO Number":    w.get("wo_number", ""),
                "Customer":     customer_map.get(w.get("customer_id", ""), {}).get("customer_name", ""),
                "Site":         site_map.get(w.get("site_id", ""), {}).get("site_name", ""),
                "Start Date":   w.get("start_date", ""),
                "End Date":     w.get("end_date", ""),
                "Machines":     len(mc_list),
                "Machine List": ", ".join(mc_list) if mc_list else "—",
                "Total Rental": f"{total_rnt:,.0f}" if total_rnt else "—",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No work orders found.")
