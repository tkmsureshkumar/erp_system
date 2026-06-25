"""
erp/views/workorder.py
Work Order module — master document for billing with interactive shift schedule.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient

# ── Constants ─────────────────────────────────────────────────────────────────

BILLING_TYPES  = ["Monthly Fixed Rental", "Daily Rental"]
BILLING_CYCLES = ["Calendar Month", "Custom"]

_SCHED_COLS = ["Date", "Weekday", "Start Time", "End Time", "Net Time", "OT", "Operator", "Remarks"]

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


def _parse_time(value) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                return datetime.strptime(value.strip(), fmt).time()
            except ValueError:
                continue
    return None


def _net_hours(start: time | None, end: time | None) -> float | None:
    if not start or not end:
        return None
    diff = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if diff < 0:
        diff += 1440  # crosses midnight
    return round(diff / 60, 2)


def _build_schedule(
    start_date: date,
    end_date: date,
    shift_start: time,
    shift_end: time,
) -> pd.DataFrame:
    rows, cur = [], start_date
    while cur <= end_date:
        is_sunday = cur.strftime("%A") == "Sunday"
        rows.append({
            "Date":       cur,
            "Weekday":    cur.strftime("%A"),
            "Start Time": None if is_sunday else shift_start,
            "End Time":   None if is_sunday else shift_end,
            "Net Time":   None if is_sunday else _net_hours(shift_start, shift_end),
            "OT":         None if is_sunday else 0,
            "Operator":   "",
            "Remarks":    "",
        })
        cur += timedelta(days=1)
    return pd.DataFrame(rows, columns=_SCHED_COLS)


def _style_schedule(df: pd.DataFrame):
    """Highlight Sunday rows with yellow background."""
    def _row_style(row):
        if str(row.get("Weekday", "")) == "Sunday":
            return ["background-color:#fef08a; color:#713f12"] * len(row)
        return [""] * len(row)
    return df.style.apply(_row_style, axis=1)


def _schedule_to_json(df: pd.DataFrame) -> str:
    records = []
    for _, row in df.iterrows():
        d   = row.get("Date")
        st_ = row.get("Start Time")
        et_ = row.get("End Time")
        records.append({
            "date":       d.isoformat() if isinstance(d, date) else (str(d) if d else None),
            "weekday":    str(row.get("Weekday") or ""),
            "start_time": st_.strftime("%H:%M") if isinstance(st_, time) else (str(st_) if st_ else None),
            "end_time":   et_.strftime("%H:%M") if isinstance(et_, time) else (str(et_) if et_ else None),
            "net_time":   float(row.get("Net Time") or 0),
            "ot":         int(row.get("OT") or 0),
            "operator":   str(row.get("Operator") or ""),
            "remarks":    str(row.get("Remarks") or ""),
        })
    return json.dumps(records)


def _json_to_schedule_df(raw) -> pd.DataFrame | None:
    if not raw:
        return None
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(records, list):
            return None
        rows = [
            {
                "Date":       _parse_date(r.get("date")),
                "Weekday":    r.get("weekday", ""),
                "Start Time": _parse_time(r.get("start_time")),
                "End Time":   _parse_time(r.get("end_time")),
                "Net Time":   r.get("net_time"),
                "OT":         r.get("ot", 0),
                "Operator":   r.get("operator", ""),
                "Remarks":    r.get("remarks", ""),
            }
            for r in records
        ]
        return pd.DataFrame(rows, columns=_SCHED_COLS)
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def _compute_billing_summary(
    df: pd.DataFrame | None,
    rental_per_month: float,
    shift_start: time,
    shift_end: time,
) -> dict | None:
    if df is None or df.empty:
        return None
    w = df.drop(columns=["Select"], errors="ignore")
    working_days  = int(w["Start Time"].notna().sum())
    std_hours     = _net_hours(shift_start, shift_end) or 0.0
    working_hours = working_days * std_hours
    actual        = float(w["Net Time"].fillna(0).sum())
    qty           = actual / working_hours if working_hours else 0.0
    billing       = rental_per_month * qty
    ot            = float(w["OT"].fillna(0).sum())
    ot_rate       = rental_per_month / working_hours if working_hours else 0.0
    return dict(
        rental_per_month=rental_per_month,
        working_days=working_days,
        working_hours=working_hours,
        actual=actual,
        qty=qty,
        billing=billing,
        ot=ot,
        ot_rate=ot_rate,
    )


def _render_billing_summary(s: dict) -> None:
    def _n(v: float, dec: int = 0) -> str:
        return f"{v:,.{dec}f}"

    rows_data = [
        ("Rental per month", _n(s["rental_per_month"]),  "Rental per month"),
        ("Working days",     _n(s["working_days"]),       "Count of shift schedule rows"),
        ("Working hours",    _n(s["working_hours"]),      "Working days × net time of 1 day"),
        ("Actual",           _n(s["actual"]),             "Sum of net time"),
        ("Qty",              f"{s['qty']:.4f}",           "Actual ÷ Working hours"),
        ("Billing",          _n(s["billing"]),            "Rental per month × Qty"),
        None,
        ("OT",               _n(s["ot"]),                 "Sum of OT hours"),
        ("OT rate",          _n(s["ot_rate"]),            "Rental per month ÷ Working hours"),
    ]

    tbody = ""
    shading = ["#ffffff", "#f9fafb"]
    shade_idx = 0
    for item in rows_data:
        if item is None:
            tbody += (
                "<tr><td colspan='3' style='height:6px;"
                "background:#f3f4f6;border-bottom:2px solid #e5e7eb;'></td></tr>"
            )
            continue
        label, value, rule = item
        bg = shading[shade_idx % 2]
        shade_idx += 1
        tbody += f"""
        <tr style="background:{bg};border-bottom:1px solid #e5e7eb;">
          <td style="padding:7px 16px;font-size:13px;font-weight:500;color:#374151;">{label}</td>
          <td style="padding:7px 16px;text-align:right;font-size:13px;font-weight:700;
                     color:#E87722;font-variant-numeric:tabular-nums;">{value}</td>
          <td style="padding:7px 16px;font-size:12px;color:#6b7280;font-style:italic;">{rule}</td>
        </tr>"""

    st.markdown(
        f"""
        <div style="margin-top:8px;border:1px solid #e2e8f0;border-radius:8px;
                    overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);">
          <table style="width:100%;border-collapse:collapse;">
            <thead>
              <tr style="background:#1c1c2e;">
                <th style="padding:9px 16px;text-align:left;font-size:10px;font-weight:700;
                           letter-spacing:.12em;text-transform:uppercase;color:#d1d5db;">Field</th>
                <th style="padding:9px 16px;text-align:right;font-size:10px;font-weight:700;
                           letter-spacing:.12em;text-transform:uppercase;color:#E87722;">Value</th>
                <th style="padding:9px 16px;text-align:left;font-size:10px;font-weight:700;
                           letter-spacing:.12em;text-transform:uppercase;color:#9ca3af;">Calculation Rule</th>
              </tr>
            </thead>
            <tbody>{tbody}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
        except Exception as exc:
            st.error(f"Failed to load customers: {exc}")
            return []

    def fetch_sites() -> list[dict]:
        try:
            return sb.list_sites()
        except Exception as exc:
            st.error(f"Failed to load sites: {exc}")
            return []

    def fetch_machines() -> list[dict]:
        try:
            return sb.list_machines()
        except Exception as exc:
            st.error(f"Failed to load machines: {exc}")
            return []

    def fetch_operators() -> list[dict]:
        try:
            return sb.list_operators()
        except Exception as exc:
            st.warning(f"Could not load operators: {exc}")
            return []

    work_orders = fetch_work_orders()
    customers   = fetch_customers()
    sites       = fetch_sites()
    machines    = fetch_machines()
    operators   = fetch_operators()

    customer_map   = {c.get("id"): c for c in customers if c.get("id")}
    site_map       = {s.get("id"): s for s in sites     if s.get("id")}
    machine_map    = {m.get("id"): m for m in machines  if m.get("id")}
    wo_map         = {w.get("id"): w for w in work_orders if w.get("id")}
    operator_names = [""] + sorted(
        op.get("operator_name", "") for op in operators if op.get("operator_name")
    )

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

    # ── Sync session state on WO selection change ──────────────────────────────
    if st.session_state.get("_editing_wo_id") != selected_wo_id:
        st.session_state["_editing_wo_id"]        = selected_wo_id
        wo = selected_wo or {}

        st.session_state["wo_customer_id"]        = wo.get("customer_id", "")
        st.session_state["wo_site_id"]            = wo.get("site_id", "")
        st.session_state["wo_machine_id"]         = wo.get("machine_id", "")
        st.session_state["wo_start_date"]         = _parse_date(wo.get("start_date"))
        st.session_state["wo_end_date"]           = _parse_date(wo.get("end_date"))
        st.session_state["wo_billing_type"]       = wo.get("billing_type", BILLING_TYPES[0])
        st.session_state["wo_billing_cycle_type"] = wo.get("billing_cycle_type", BILLING_CYCLES[0])
        st.session_state["wo_billing_start_date"] = _parse_date(wo.get("billing_start_date"))
        st.session_state["wo_billing_end_date"]   = _parse_date(wo.get("billing_end_date"))
        st.session_state["wo_rental_per_month"]   = float(wo.get("rental_per_month") or 0.0)
        st.session_state["wo_shift_start_time"]   = _parse_time(wo.get("shift_start_time")) or time(8, 0)
        st.session_state["wo_shift_end_time"]     = _parse_time(wo.get("shift_end_time")) or time(20, 0)

    # ── A. Basic Selection ─────────────────────────────────────────────────────
    st.markdown('<p class="filter-label">Basic Selection</p>', unsafe_allow_html=True)

    sel1, sel2 = st.columns(2)
    with sel1:
        selected_customer_id = st.selectbox(
            "Customer *",
            options=[""] + list(customer_map),
            format_func=lambda cid: "Select customer" if not cid
                else customer_map[cid].get("customer_name", "Unknown"),
            key="wo_customer_id",
        )
    with sel2:
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

    selected_machine_id = st.selectbox(
        "Machine *",
        options=[""] + list(machine_map),
        format_func=lambda mid: "Select machine" if not mid
            else f"{machine_map[mid].get('asset_code', '')} — {machine_map[mid].get('machine_type', '')}",
        key="wo_machine_id",
    )

    dt1, dt2 = st.columns(2)
    with dt1:
        start_date = st.date_input("Start Date", key="wo_start_date")
    with dt2:
        end_date = st.date_input("End Date (if applicable)", key="wo_end_date")

    # ── B. Billing & Cycle Configuration ───────────────────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    st.markdown('<p class="filter-label">Billing &amp; Cycle Configuration</p>', unsafe_allow_html=True)

    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        billing_type = st.selectbox(
            "Billing Type",
            options=BILLING_TYPES,
            key="wo_billing_type",
        )
    with bc2:
        billing_cycle_type = st.selectbox(
            "Billing Cycle",
            options=BILLING_CYCLES,
            key="wo_billing_cycle_type",
        )
    with bc3:
        rental_per_month = st.number_input(
            "Rental per Month",
            value=float(st.session_state.get("wo_rental_per_month", 0.0)),
            step=0.01,
            min_value=0.0,
            key="wo_rental_per_month",
        )

    # Billing cycle dates
    if billing_cycle_type == "Calendar Month":
        today              = date.today()
        billing_start_date = today.replace(day=1)
        billing_end_date   = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        bcd1, bcd2 = st.columns(2)
        with bcd1:
            st.date_input("Billing Cycle Start Date", value=billing_start_date,
                          disabled=True, key="wo_billing_start_date_display")
        with bcd2:
            st.date_input("Billing Cycle End Date", value=billing_end_date,
                          disabled=True, key="wo_billing_end_date_display")
    else:
        bcd1, bcd2 = st.columns(2)
        with bcd1:
            billing_start_date = st.date_input("Billing Cycle Start Date",
                                               key="wo_billing_start_date")
        with bcd2:
            billing_end_date = st.date_input("Billing Cycle End Date",
                                             key="wo_billing_end_date")

    # ── C. Shift Configuration ─────────────────────────────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    st.markdown('<p class="filter-label">Shift Configuration</p>', unsafe_allow_html=True)

    sc1, sc2 = st.columns(2)
    with sc1:
        shift_start_time = st.time_input("Shift Start Time", key="wo_shift_start_time")
    with sc2:
        shift_end_time = st.time_input("Shift End Time", key="wo_shift_end_time")

    # ── D. Shift Schedule Table ────────────────────────────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    st.markdown('<p class="filter-label">Shift Schedule</p>', unsafe_allow_html=True)

    edited_schedule: pd.DataFrame | None = None

    if billing_start_date and billing_end_date and billing_start_date <= billing_end_date:
        # base_key identifies the schedule shape; del_count bumps editor key after delete
        base_key = (
            f"sched_{selected_wo_id or 'new'}"
            f"_{billing_start_date}_{billing_end_date}"
            f"_{shift_start_time}_{shift_end_time}"
        )
        del_count    = st.session_state.get(f"sched_del_{base_key}",    0)
        recalc_count = st.session_state.get(f"sched_recalc_{base_key}", 0)
        editor_key   = f"{base_key}_{del_count}_{recalc_count}"

        # Priority: post-delete session data > saved WO schedule > freshly generated
        if f"sched_data_{base_key}" in st.session_state:
            initial_df = st.session_state[f"sched_data_{base_key}"]
        elif selected_wo and selected_wo.get("shift_schedule"):
            saved_df = _json_to_schedule_df(selected_wo.get("shift_schedule"))
            initial_df = saved_df if saved_df is not None else _build_schedule(
                billing_start_date, billing_end_date, shift_start_time, shift_end_time
            )
        else:
            initial_df = _build_schedule(
                billing_start_date, billing_end_date, shift_start_time, shift_end_time
            )

        # Prepend a UI-only Select column (not persisted to DB)
        display_df = initial_df.copy()
        display_df.insert(0, "Select", False)

        edited_schedule = st.data_editor(
            _style_schedule(display_df),
            column_config={
                "Select":     st.column_config.CheckboxColumn(
                                  "Select", default=False, width="small"),
                "Date":       st.column_config.DateColumn(
                                  "Date", disabled=True, width="small"),
                "Weekday":    st.column_config.TextColumn(
                                  "Weekday", disabled=True, width="small"),
                "Start Time": st.column_config.TimeColumn(
                                  "Start Time", width="small"),
                "End Time":   st.column_config.TimeColumn(
                                  "End Time", width="small"),
                "Net Time":   st.column_config.NumberColumn(
                                  "Net Time", format="%.1f",
                                  disabled=True, width="small"),
                "OT":         st.column_config.NumberColumn(
                                  "OT", default=0, step=1, width="small"),
                "Operator":   st.column_config.SelectboxColumn(
                                  "Operator", options=operator_names, width="medium"),
                "Remarks":    st.column_config.TextColumn(
                                  "Remarks", width="medium"),
            },
            num_rows="fixed",
            use_container_width=True,
            hide_index=True,
            key=editor_key,
        )

        # Auto-recalculate Net Time whenever Start Time / End Time changes
        if edited_schedule is not None and not edited_schedule.empty:
            clean = edited_schedule.drop(columns=["Select"], errors="ignore").copy()
            needs_recalc = False
            for idx, row in clean.iterrows():
                st_ = row.get("Start Time")
                et_ = row.get("End Time")
                # Normalise to datetime.time | None
                if st_ and not isinstance(st_, time):
                    try:
                        st_ = _parse_time(str(st_))
                    except Exception:
                        st_ = None
                if et_ and not isinstance(et_, time):
                    try:
                        et_ = _parse_time(str(et_))
                    except Exception:
                        et_ = None
                expected = _net_hours(st_, et_)
                current  = row.get("Net Time")
                cur_na   = current is None or (not isinstance(current, bool) and pd.isna(current))
                exp_na   = expected is None
                if cur_na != exp_na or (
                    not cur_na and not exp_na
                    and abs(float(current) - float(expected)) > 0.001
                ):
                    clean.at[idx, "Net Time"] = expected
                    needs_recalc = True
            if needs_recalc:
                st.session_state[f"sched_data_{base_key}"]   = clean
                st.session_state[f"sched_recalc_{base_key}"] = recalc_count + 1
                st.rerun()

        # Delete only rows where Select=True AND Weekday=Sunday
        if st.button("Delete Selected Sunday Rows", key=f"del_sched_{base_key}"):
            if edited_schedule is not None and not edited_schedule.empty:
                keep = ~(
                    (edited_schedule["Select"] == True) &
                    (edited_schedule["Weekday"] == "Sunday")
                )
                cleaned = (
                    edited_schedule[keep]
                    .drop(columns=["Select"], errors="ignore")
                    .reset_index(drop=True)
                )
                st.session_state[f"sched_data_{base_key}"] = cleaned
                st.session_state[f"sched_del_{base_key}"]  = del_count + 1
                st.rerun()
    else:
        st.info("Set billing cycle start and end dates to generate the shift schedule.")

    # ── E. Billing Summary ─────────────────────────────────────────────────────
    if edited_schedule is not None and not edited_schedule.empty:
        summary = _compute_billing_summary(
            edited_schedule, rental_per_month, shift_start_time, shift_end_time
        )
        if summary:
            st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
            st.markdown('<p class="filter-label">Billing Summary</p>', unsafe_allow_html=True)
            _render_billing_summary(summary)

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    # ── Form (submit) + WO list ────────────────────────────────────────────────
    col_form, col_list = st.columns([2, 3])

    with col_form:
        with st.form("wo_form"):
            if selected_wo:
                st.markdown(
                    f"<span style='font-size:11px;color:#6b7280;'>WO Number: "
                    f"<strong>{selected_wo.get('wo_number', '—')}</strong></span>",
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

            submitted = st.form_submit_button(
                "Update Work Order" if selected_wo else "Create Work Order"
            )

            if submitted:
                if not selected_customer_id:
                    st.error("Customer is required.")
                elif not selected_site_id:
                    st.error("Site is required.")
                elif not selected_machine_id:
                    st.error("Machine is required.")
                else:
                    # Drop UI-only Select column, recalculate Net Time, then serialise
                    schedule_json: str | None = None
                    if edited_schedule is not None and not edited_schedule.empty:
                        save_df = edited_schedule.drop(columns=["Select"], errors="ignore").copy()
                        for idx, row in save_df.iterrows():
                            st_ = row.get("Start Time")
                            et_ = row.get("End Time")
                            if st_ and et_:
                                save_df.at[idx, "Net Time"] = _net_hours(
                                    st_ if isinstance(st_, time) else _parse_time(str(st_)),
                                    et_ if isinstance(et_, time) else _parse_time(str(et_)),
                                )
                        schedule_json = _schedule_to_json(save_df)

                    payload = dict(
                        customer_id=selected_customer_id,
                        site_id=selected_site_id,
                        machine_id=selected_machine_id,
                        start_date=start_date.isoformat() if start_date else None,
                        end_date=end_date.isoformat() if end_date else None,
                        billing_type=billing_type,
                        billing_cycle_type=billing_cycle_type,
                        billing_start_date=billing_start_date.isoformat() if billing_start_date else None,
                        billing_end_date=billing_end_date.isoformat() if billing_end_date else None,
                        rental_per_month=float(rental_per_month) if rental_per_month else None,
                        shift_start_time=shift_start_time.strftime("%H:%M") if shift_start_time else None,
                        shift_end_time=shift_end_time.strftime("%H:%M") if shift_end_time else None,
                        shift_schedule=schedule_json,
                    )
                    try:
                        if selected_wo:
                            sb.update_work_order(selected_wo_id, payload)
                            st.success("Work order updated.")
                        else:
                            created = sb.insert_work_order(payload)
                            wo_num = created.get("wo_number") or created.get("id", "")
                            st.success(f"Work order created: {wo_num}")
                        work_orders = fetch_work_orders()
                    except Exception as exc:
                        st.error(f"Could not save work order: {exc}")

    # ── Work order list ────────────────────────────────────────────────────────
    with col_list:
        col_cap, col_btn = st.columns([3, 1])
        with col_cap:
            st.markdown('<p class="filter-label">All Work Orders</p>', unsafe_allow_html=True)
        with col_btn:
            if st.button("Refresh", key="refresh_wo"):
                work_orders = fetch_work_orders()

        if work_orders:
            st.dataframe(
                [
                    {
                        "WO Number":     w.get("wo_number", ""),
                        "Customer":      customer_map.get(w.get("customer_id", ""), {}).get("customer_name", ""),
                        "Site":          site_map.get(w.get("site_id", ""), {}).get("site_name", ""),
                        "Machine":       machine_map.get(w.get("machine_id", ""), {}).get("asset_code", ""),
                        "Billing Type":  w.get("billing_type", ""),
                        "Billing Cycle": w.get("billing_cycle_type", ""),
                        "Cycle Start":   w.get("billing_start_date", ""),
                        "Cycle End":     w.get("billing_end_date", ""),
                        "Rental/Month":  w.get("rental_per_month", ""),
                        "Shift":         f"{w.get('shift_start_time','')} – {w.get('shift_end_time','')}",
                    }
                    for w in work_orders
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No work orders found.")
