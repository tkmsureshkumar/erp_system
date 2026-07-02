"""
erp/views/worklog.py
Work Log — shift schedule entry and billing summary per machine per work order.
Machine config (billing dates, rental) comes from the WO's machine_config JSON.
Schedules are saved back per-machine inside machine_config.
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from ..supabase_client import SupabaseClient

# ── Constants ─────────────────────────────────────────────────────────────────

_MINUTES = [f"{m:02d}" for m in range(0, 60, 5)]   # 00, 05, 10 … 55

_SCHED_COLS = [
    "Date", "Weekday",
    "Start Time", "End Time", "Net Time",
    "Start HMR", "End HMR", "Breakdown Hours",
    "OT", "HSD in Ltr", "Operator", "Remarks",
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


def _set_ampm_state(key: str, t: time) -> None:
    """Write hour / minute / period sub-keys for an AM/PM time picker."""
    h12 = t.hour % 12 or 12
    nearest_m = _MINUTES[min(range(len(_MINUTES)), key=lambda i: abs(int(_MINUTES[i]) - t.minute))]
    st.session_state[f"{key}_h"] = str(h12)
    st.session_state[f"{key}_m"] = nearest_m
    st.session_state[f"{key}_p"] = "AM" if t.hour < 12 else "PM"


def _time_input_ampm(title: str, key: str) -> time:
    """Render a labelled Hour / Min / AM-PM picker; returns a time object."""
    st.markdown(
        f"<div style='font-size:0.875rem;color:#31333f;margin-bottom:2px;'>{title}</div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        h = st.selectbox("Hour", options=[str(h) for h in range(1, 13)],
                         key=f"{key}_h", label_visibility="collapsed")
    with c2:
        m = st.selectbox("Min",  options=_MINUTES,
                         key=f"{key}_m", label_visibility="collapsed")
    with c3:
        p = st.selectbox("AM/PM", options=["AM", "PM"],
                         key=f"{key}_p", label_visibility="collapsed")
    hour_24 = int(h) % 12 + (12 if p == "PM" else 0)
    return time(hour_24, int(m))


def _net_hours(start: time | None, end: time | None) -> float | None:
    if not start or not end:
        return None
    diff = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if diff < 0:
        diff += 1440
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
            "Date":            cur,
            "Weekday":         cur.strftime("%A"),
            "Start Time":      None if is_sunday else shift_start,
            "End Time":        None if is_sunday else shift_end,
            "Net Time":        None if is_sunday else _net_hours(shift_start, shift_end),
            "Start HMR":       None,
            "End HMR":         None,
            "Breakdown Hours": None if is_sunday else 0.0,
            "OT":              None if is_sunday else 0,
            "HSD in Ltr":      None if is_sunday else 0.0,
            "Operator":        "",
            "Remarks":         "",
        })
        cur += timedelta(days=1)
    return pd.DataFrame(rows, columns=_SCHED_COLS)


def _schedule_to_json(df: pd.DataFrame) -> str:
    records = []
    for _, row in df.iterrows():
        d   = row.get("Date")
        st_ = row.get("Start Time")
        et_ = row.get("End Time")
        records.append({
            "date":            d.isoformat() if isinstance(d, date) else (str(d) if d else None),
            "weekday":         str(row.get("Weekday") or ""),
            "start_time":      st_.strftime("%H:%M") if isinstance(st_, time) else (str(st_) if st_ else None),
            "end_time":        et_.strftime("%H:%M") if isinstance(et_, time) else (str(et_) if et_ else None),
            "net_time":        float(row.get("Net Time") or 0) if pd.notna(row.get("Net Time")) else 0.0,
            "start_hmr":       float(row.get("Start HMR")) if pd.notna(row.get("Start HMR")) else None,
            "end_hmr":         float(row.get("End HMR"))   if pd.notna(row.get("End HMR"))   else None,
            "breakdown_hours": float(row.get("Breakdown Hours")) if pd.notna(row.get("Breakdown Hours")) else 0.0,
            "ot":              int(row.get("OT")) if pd.notna(row.get("OT")) else 0,
            "hsd_in_ltr":      float(row.get("HSD in Ltr")) if pd.notna(row.get("HSD in Ltr")) else 0.0,
            "operator":        str(row.get("Operator") or ""),
            "remarks":         str(row.get("Remarks") or ""),
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
                "Date":            _parse_date(r.get("date")),
                "Weekday":         r.get("weekday", ""),
                "Start Time":      _parse_time(r.get("start_time")),
                "End Time":        _parse_time(r.get("end_time")),
                "Net Time":        r.get("net_time"),
                "Start HMR":       r.get("start_hmr"),
                "End HMR":         r.get("end_hmr"),
                "Breakdown Hours": r.get("breakdown_hours", 0),
                "OT":              r.get("ot", 0),
                "HSD in Ltr":      r.get("hsd_in_ltr", 0.0),
                "Operator":        r.get("operator", ""),
                "Remarks":         r.get("remarks", ""),
            }
            for r in records
        ]
        return pd.DataFrame(rows, columns=_SCHED_COLS)
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def _style_schedule(df: pd.DataFrame):
    def _row_style(row):
        if str(row.get("Weekday", "")) == "Sunday":
            return ["background-color:#fef08a; color:#713f12"] * len(row)
        return [""] * len(row)
    return df.style.apply(_row_style, axis=1)


def _parse_machine_configs(raw) -> list[dict]:
    if not raw:
        return []
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        return records if isinstance(records, list) else []
    except Exception:
        return []


def _compute_billing_summary(
    df: pd.DataFrame | None,
    rental_per_month: float,
    shift_start: time,
    shift_end: time,
    ot_rate_input: float = 0.0,
    no_of_days: int | None = None,
) -> dict | None:
    if df is None or df.empty:
        return None
    w = df.drop(columns=["Select"], errors="ignore")
    # Prefer No of Days from the Work Order machine config; fall back to
    # counting rows that have a Start Time entered.
    working_days     = no_of_days if (no_of_days and no_of_days > 0) \
                       else int(w["Start Time"].notna().sum())
    std_hours        = _net_hours(shift_start, shift_end) or 0.0
    working_hours    = working_days * std_hours
    actual           = float(w["Net Time"].fillna(0).sum())
    qty              = actual / working_hours if working_hours else 0.0
    billing          = rental_per_month * qty
    ot_hours         = float(w["OT"].fillna(0).sum())
    ot_rate          = float(ot_rate_input or 0.0)
    ot_billing       = ot_hours * ot_rate
    total_billing    = billing + ot_billing
    deduction_amt    = total_billing - billing
    adjusted_billing = total_billing - deduction_amt
    return dict(
        rental_per_month=rental_per_month,
        working_days=working_days,
        working_hours=working_hours,
        actual=actual,
        qty=qty,
        billing=billing,
        ot_hours=ot_hours,
        ot_rate=ot_rate,
        ot_billing=ot_billing,
        total_billing=total_billing,
        deduction=deduction_amt,
        adjusted_billing=adjusted_billing,
    )


def _render_billing_summary(s: dict) -> None:
    def _n(v: float, dec: int = 0) -> str:
        return f"{v:,.{dec}f}"

    rows_data = [
        ("Rental per month", _n(s["rental_per_month"]),  "Rental / Month"),
        ("Working days",     _n(s["working_days"]),       "No of Days from Work Order (machine config)"),
        ("Working hours",    _n(s["working_hours"]),      "Working days × Working hours"),
        ("Actual",           _n(s["actual"]),             "Sum(Net Time)"),
        ("Qty",              f"{s['qty']:.4f}",           "Actual ÷ Working hours"),
        ("Billing",          _n(s["billing"]),            "Rental per month × Qty"),
        None,
        ("OT hours",         _n(s["ot_hours"]),             "Sum(Over Time Hrs.)"),
        ("OT rate",          _n(s["ot_rate"], 2),           "From OT Rate field"),
        ("OT billing",       _n(s["ot_billing"]),           "OT hours × OT rate"),
        None,
        ("Total Billing",    _n(s["total_billing"]),        "Billing + OT Billing"),
        ("Deduction",        _n(s["deduction"]),            "Total Billing − Billing"),
        ("Adjusted Billing", _n(s["adjusted_billing"]),     "Total Billing − Deduction"),
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
        tbody += (
            f"<tr style='background:{bg};border-bottom:1px solid #e5e7eb;'>"
            f"<td style='padding:7px 16px;font-size:13px;font-weight:500;color:#374151;'>{label}</td>"
            f"<td style='padding:7px 16px;text-align:right;font-size:13px;font-weight:700;"
            f"color:#E87722;font-variant-numeric:tabular-nums;'>{value}</td>"
            f"<td style='padding:7px 16px;font-size:12px;color:#6b7280;font-style:italic;'>{rule}</td>"
            f"</tr>"
        )

    st.markdown(
        "<div style='margin-top:8px;border:1px solid #e2e8f0;border-radius:8px;"
        "overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);'>"
        "<table style='width:100%;border-collapse:collapse;'>"
        "<thead><tr style='background:#1c1c2e;'>"
        "<th style='padding:9px 16px;text-align:left;font-size:10px;font-weight:700;"
        "letter-spacing:.12em;text-transform:uppercase;color:#d1d5db;'>Field</th>"
        "<th style='padding:9px 16px;text-align:right;font-size:10px;font-weight:700;"
        "letter-spacing:.12em;text-transform:uppercase;color:#E87722;'>Value</th>"
        "<th style='padding:9px 16px;text-align:left;font-size:10px;font-weight:700;"
        "letter-spacing:.12em;text-transform:uppercase;color:#9ca3af;'>Calculation Rule</th>"
        f"</tr></thead><tbody>{tbody}</tbody></table></div>",
        unsafe_allow_html=True,
    )


# ── View ──────────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Fleet Operations</div>
        <div class="page-title">Work Log</div>
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

    def fetch_operators() -> list[dict]:
        try:
            return sb.list_operators()
        except Exception as exc:
            st.warning(f"Could not load operators: {exc}")
            return []

    work_orders = fetch_work_orders()
    customers   = fetch_customers()
    sites       = fetch_sites()
    operators   = fetch_operators()

    customer_map   = {c.get("id"): c for c in customers if c.get("id")}
    site_map       = {s.get("id"): s for s in sites     if s.get("id")}
    wo_map         = {w.get("id"): w for w in work_orders if w.get("id")}
    operator_names = [""] + sorted(
        op.get("operator_name", "") for op in operators if op.get("operator_name")
    )

    # ── Work order selector ────────────────────────────────────────────────────
    selected_wo_id = st.selectbox(
        "Select Work Order",
        options=[""] + list(wo_map),
        format_func=lambda wid: "Select a work order" if not wid
            else (
                f"{wo_map[wid].get('wo_number', 'Unknown')} — "
                f"{customer_map.get(wo_map[wid].get('customer_id', ''), {}).get('customer_name', '')}"
            ),
        key="wl_selected_wo_id",
    )
    selected_wo = wo_map.get(selected_wo_id)

    if not selected_wo:
        st.info("Select a work order above to view and edit its shift schedule.")
        return

    # ── Parse machine configs from WO ──────────────────────────────────────────
    machine_configs = _parse_machine_configs(selected_wo.get("machine_config"))

    # ── WO info card ───────────────────────────────────────────────────────────
    st.markdown(
        "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;"
        "padding:14px 20px;margin-bottom:16px;'>"
        "<div style='display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start;'>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>WO Number</div>"
        f"<div style='font-size:18px;font-weight:800;color:#E87722;'>{selected_wo.get('wo_number', '—')}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Customer</div>"
        f"<div style='font-size:14px;font-weight:600;color:#111827;'>{customer_map.get(selected_wo.get('customer_id', ''), {}).get('customer_name', '—')}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Site</div>"
        f"<div style='font-size:14px;font-weight:600;color:#111827;'>{site_map.get(selected_wo.get('site_id', ''), {}).get('site_name', '—')}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>WO Period</div>"
        f"<div style='font-size:14px;font-weight:600;color:#111827;'>{selected_wo.get('start_date', '—')} &rarr; {selected_wo.get('end_date', '—')}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Machines</div>"
        f"<div style='font-size:14px;font-weight:700;color:#E87722;'>{len(machine_configs)}</div></div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    if not machine_configs:
        st.warning(
            "This work order has no machines configured. "
            "Please add machines in Work Orders before entering the work log."
        )
        return

    # ── Machine selector ───────────────────────────────────────────────────────
    machine_labels = [m.get("machine_label", f"Machine {i+1}") for i, m in enumerate(machine_configs)]
    selected_machine_label = st.selectbox(
        "Select Machine",
        options=machine_labels,
        key="wl_selected_machine",
    )
    machine_idx = machine_labels.index(selected_machine_label) if selected_machine_label in machine_labels else 0
    selected_machine = machine_configs[machine_idx]

    # ── Sync session state when WO or machine changes ──────────────────────────
    sync_key = f"{selected_wo_id}_{machine_idx}"
    if st.session_state.get("_editing_wl_key") != sync_key:
        st.session_state["_editing_wl_key"] = sync_key
        saved_st = _parse_time(selected_machine.get("shift_start_time")) or time(8, 0)
        saved_et = _parse_time(selected_machine.get("shift_end_time"))   or time(20, 0)
        _set_ampm_state("wl_shift_start", saved_st)
        _set_ampm_state("wl_shift_end",   saved_et)
        st.session_state["wl_ot_rate"] = float(selected_machine.get("ot_rate") or 0.0)

    # ── Machine config card ────────────────────────────────────────────────────
    _rental = selected_machine.get("rental_per_month")
    st.markdown(
        "<div style='background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;"
        "padding:12px 18px;margin-bottom:16px;'>"
        "<div style='display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start;'>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Machine</div>"
        f"<div style='font-size:14px;font-weight:700;color:#111827;'>{selected_machine_label}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Billing Type</div>"
        f"<div style='font-size:13px;font-weight:600;color:#374151;'>{selected_machine.get('billing_type', '—')}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Billing Cycle</div>"
        f"<div style='font-size:13px;font-weight:600;color:#374151;'>{selected_machine.get('billing_cycle', '—')}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Cycle Period</div>"
        f"<div style='font-size:13px;font-weight:600;color:#374151;'>{selected_machine.get('billing_cycle_start_date', '—')} &rarr; {selected_machine.get('billing_cycle_end_date', '—')}</div></div>"
        "<div><div style='font-size:10px;font-weight:700;letter-spacing:.1em;"
        "text-transform:uppercase;color:#9ca3af;'>Rental / Month</div>"
        f"<div style='font-size:14px;font-weight:700;color:#E87722;'>{f'{float(_rental):,.0f}' if _rental else '—'}</div></div>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    # ── Billing dates from selected machine ────────────────────────────────────
    billing_start_date = _parse_date(selected_machine.get("billing_cycle_start_date"))
    billing_end_date   = _parse_date(selected_machine.get("billing_cycle_end_date"))
    rental_per_month   = float(selected_machine.get("rental_per_month") or 0.0)

    if not billing_start_date or not billing_end_date:
        st.warning(
            "The selected machine has no billing cycle dates. "
            "Please update them in Work Orders before entering the work log."
        )
        return

    # ── Month / Year selectors ─────────────────────────────────────────────────
    _today    = date.today()
    _cur_year = _today.year
    _year_opts  = [_cur_year - 1, _cur_year, _cur_year + 1]
    _month_opts = list(calendar.month_name)[1:]   # Jan … Dec

    moc1, moc2, _ = st.columns([1, 1, 2])
    with moc1:
        selected_month_name = st.selectbox(
            "Month",
            options=_month_opts,
            index=_today.month - 1,
            key="wl_selected_month",
        )
    with moc2:
        selected_year = st.selectbox(
            "Year",
            options=_year_opts,
            index=1,          # default = current year
            key="wl_selected_year",
        )

    selected_month_num   = _month_opts.index(selected_month_name) + 1
    selected_month_label = f"{selected_month_name} {selected_year}"
    last_day    = calendar.monthrange(selected_year, selected_month_num)[1]
    month_start = date(selected_year, selected_month_num, 1)
    month_end   = date(selected_year, selected_month_num, last_day)

    # Sync ot_rate when WO / machine / month changes (before number_input renders).
    # Loads from DB — picks up both draft and committed records.
    wl_sync_key = f"{selected_wo_id}_{machine_idx}_{selected_year}_{selected_month_num}"
    if st.session_state.get("_wl_month_sync") != wl_sync_key:
        st.session_state["_wl_month_sync"] = wl_sync_key
        _mkey = selected_machine.get("machine_id") or str(machine_idx)
        try:
            _wl_rec_sync = sb.get_worklog_by_month(
                selected_wo_id, _mkey, selected_year, selected_month_num
            )
        except Exception:
            _wl_rec_sync = {}
        if _wl_rec_sync:
            st.session_state["wl_ot_rate"] = float(_wl_rec_sync.get("ot_rate") or 0.0)
        else:
            st.session_state["wl_ot_rate"] = float(selected_machine.get("ot_rate") or 0.0)

    # ── Shift Configuration ────────────────────────────────────────────────────
    st.markdown('<p class="filter-label">Shift Configuration</p>', unsafe_allow_html=True)
    sc1, sc2 = st.columns(2)
    with sc1:
        shift_start_time = _time_input_ampm("Shift Start Time", "wl_shift_start")
    with sc2:
        shift_end_time = _time_input_ampm("Shift End Time", "wl_shift_end")

    or1, _ = st.columns([1, 3])
    with or1:
        ot_rate_input = st.number_input(
            "OT Rate",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            help="Leave as 0 to auto-calculate (Rental ÷ Working hours)",
            key="wl_ot_rate",
        )

    # ── Load DB record once (draft banner + schedule init) ────────────────────
    _mkey = selected_machine.get("machine_id") or str(machine_idx)
    try:
        _wl_rec = sb.get_worklog_by_month(
            selected_wo_id, _mkey, selected_year, selected_month_num
        )
    except Exception:
        _wl_rec = {}
    _is_db_draft = bool(_wl_rec.get("is_draft", False))

    # ── Draft status banner ────────────────────────────────────────────────────
    if _is_db_draft:
        st.markdown(
            """
            <div style='background:#fff7ed;border:1px solid #f97316;border-radius:6px;
                        padding:10px 16px;margin:8px 0 12px;
                        display:flex;align-items:center;gap:12px;'>
              <span style='font-size:20px;flex-shrink:0;'>📝</span>
              <div>
                <div style='font-size:13px;font-weight:700;color:#9a3412;'>
                  Draft Work Log — not yet committed to database
                </div>
                <div style='font-size:12px;color:#c2410c;margin-top:2px;'>
                  Click <b>Save Work Log</b> to persist to the database,
                  or <b>Save Draft</b> to update this draft.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Shift Schedule Table ───────────────────────────────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    st.markdown('<p class="filter-label">Shift Schedule</p>', unsafe_allow_html=True)

    edited_schedule: pd.DataFrame | None = None

    base_key = (
        f"wl_{selected_wo_id}_{machine_idx}"
        f"_{selected_year}_{selected_month_num:02d}"
        f"_{shift_start_time}_{shift_end_time}"
    )
    recalc_count = st.session_state.get(f"sched_recalc_{base_key}", 0)
    editor_key   = f"{base_key}_{recalc_count}"

    if f"sched_data_{base_key}" in st.session_state:
        # In-memory recalculation buffer takes highest priority
        initial_df = st.session_state[f"sched_data_{base_key}"]
    elif _wl_rec and _wl_rec.get("schedule_data"):
        saved_df   = _json_to_schedule_df(_wl_rec["schedule_data"])
        initial_df = saved_df if saved_df is not None else _build_schedule(
            month_start, month_end, shift_start_time, shift_end_time
        )
    else:
        initial_df = _build_schedule(
            month_start, month_end, shift_start_time, shift_end_time
        )

    edited_schedule = st.data_editor(
        _style_schedule(initial_df),
        column_config={
            "Date":            st.column_config.DateColumn("Date", disabled=True, width="small"),
            "Weekday":         st.column_config.TextColumn("Weekday", disabled=True, width="small"),
            "Start Time":      st.column_config.TimeColumn("Start Time", width="small"),
            "End Time":        st.column_config.TimeColumn("End Time", width="small"),
            "Net Time":        st.column_config.NumberColumn("Net Time", format="%.1f",
                                   disabled=True, width="small"),
            "Start HMR":       st.column_config.NumberColumn("Start HMR", format="%.1f",
                                   min_value=0, step=0.1, width="small"),
            "End HMR":         st.column_config.NumberColumn("End HMR", format="%.1f",
                                   min_value=0, step=0.1, width="small"),
            "Breakdown Hours": st.column_config.NumberColumn("B/D Hrs", format="%.1f",
                                   min_value=0, step=0.5, width="small"),
            "OT":              st.column_config.NumberColumn("Over Time Hrs.", default=0, step=1, width="small"),
            "HSD in Ltr":      st.column_config.NumberColumn("HSD in Ltr", format="%.1f",
                                   min_value=0, step=0.5, width="small"),
            "Operator":        st.column_config.SelectboxColumn("Operator",
                                   options=operator_names, width="medium"),
            "Remarks":         st.column_config.TextColumn("Remarks", width="medium"),
        },
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
        key=editor_key,
    )

    # Auto-recalculate Net Time and OT whenever Start/End Time are present.
    # Sunday rule: all worked hours are OT (Net Time stays blank).
    # Weekday rule: Net Time = min(raw, shift_dur); OT = excess over shift_dur.
    if edited_schedule is not None and not edited_schedule.empty:
        clean        = edited_schedule.drop(columns=["Select"], errors="ignore").copy()
        shift_dur    = _net_hours(shift_start_time, shift_end_time)
        needs_recalc = False
        for idx, row in clean.iterrows():
            st_ = row.get("Start Time")
            et_ = row.get("End Time")
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

            raw_net    = _net_hours(st_, et_)
            is_sunday  = str(row.get("Weekday", "")) == "Sunday"

            if raw_net is not None and is_sunday:
                # Sunday: full worked hours → OT, Net Time stays None
                expected_net = None
                expected_ot  = round(raw_net, 2)
            elif raw_net is not None and shift_dur is not None:
                # Weekday: cap Net Time at shift duration, excess → OT
                expected_net = min(raw_net, shift_dur)
                expected_ot  = round(max(0.0, raw_net - shift_dur), 2)
            else:
                expected_net = raw_net
                expected_ot  = None

            # Update Net Time if changed
            cur_net    = row.get("Net Time")
            cur_net_na = cur_net is None or (not isinstance(cur_net, bool) and pd.isna(cur_net))
            exp_net_na = expected_net is None
            if cur_net_na != exp_net_na or (
                not cur_net_na and not exp_net_na
                and abs(float(cur_net) - float(expected_net)) > 0.001
            ):
                clean.at[idx, "Net Time"] = expected_net
                needs_recalc = True

            # Update OT if changed
            if expected_ot is not None:
                cur_ot    = row.get("OT")
                cur_ot_na = cur_ot is None or (not isinstance(cur_ot, bool) and pd.isna(cur_ot))
                if cur_ot_na or abs(float(cur_ot) - expected_ot) > 0.001:
                    clean.at[idx, "OT"] = expected_ot
                    needs_recalc = True

        if needs_recalc:
            st.session_state[f"sched_data_{base_key}"]   = clean
            st.session_state[f"sched_recalc_{base_key}"] = recalc_count + 1
            st.rerun()

    # ── Schedule Totals Row ────────────────────────────────────────────────────
    _no_of_days_raw = selected_machine.get("no_of_days")
    _no_of_days     = int(_no_of_days_raw) if _no_of_days_raw else None

    if edited_schedule is not None and not edited_schedule.empty:
        _df_t      = edited_schedule.drop(columns=["Select"], errors="ignore")
        _total_net = float(_df_t["Net Time"].fillna(0).sum())
        _total_ot  = float(_df_t["OT"].fillna(0).sum())
        _total_bd  = float(_df_t["Breakdown Hours"].fillna(0).sum())
        _total_hsd = float(_df_t["HSD in Ltr"].fillna(0).sum())
        _wd_display = str(_no_of_days) if _no_of_days else "—"

        def _tc(label: str, value: str) -> str:
            return (
                f"<td style='padding:8px 14px;border-right:1px solid #374151;'>"
                f"<div style='font-size:9px;font-weight:700;letter-spacing:.1em;"
                f"text-transform:uppercase;color:#9ca3af;margin-bottom:2px;'>{label}</div>"
                f"<div style='font-size:14px;font-weight:800;color:#E87722;"
                f"font-variant-numeric:tabular-nums;'>{value}</div></td>"
            )

        st.markdown(
            "<div style='border:1px solid #374151;border-radius:0 0 6px 6px;"
            "background:#1c1c2e;margin-top:-8px;overflow:hidden;'>"
            "<table style='width:100%;border-collapse:collapse;'><tbody><tr>"
            "<td style='padding:8px 14px;border-right:1px solid #374151;'>"
            "<div style='font-size:10px;font-weight:800;letter-spacing:.12em;"
            "text-transform:uppercase;color:#ffffff;'>TOTAL</div></td>"
            + _tc("Working Days", _wd_display)
            + _tc("Net Time (hrs)", f"{_total_net:.1f}")
            + _tc("Over Time (hrs)", f"{_total_ot:.1f}")
            + _tc("Breakdown (hrs)", f"{_total_bd:.1f}")
            + _tc("HSD (Ltr)", f"{_total_hsd:.1f}")
            + "<td style='padding:8px 14px;' colspan='2'></td>"
            "</tr></tbody></table></div>",
            unsafe_allow_html=True,
        )

    # ── Billing Summary ────────────────────────────────────────────────────────
    if edited_schedule is not None and not edited_schedule.empty:
        summary = _compute_billing_summary(
            edited_schedule, rental_per_month, shift_start_time, shift_end_time,
            ot_rate_input=ot_rate_input,
            no_of_days=_no_of_days,
        )
        if summary:
            st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
            st.markdown('<p class="filter-label">Billing Summary</p>', unsafe_allow_html=True)
            _render_billing_summary(summary)

    # ── Action buttons ─────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    _btn_save, _btn_draft, _btn_discard = st.columns([3, 3, 2])

    _mlabel           = selected_machine.get("machine_label", f"Machine {machine_idx + 1}")
    _billing_month_str = f"{calendar.month_name[selected_month_num]} {selected_year}"

    # ── Save Draft (persists to DB with is_draft=True) ─────────────────────────
    with _btn_draft:
        if st.button("📝 Save Draft", key="save_draft_btn", use_container_width=True):
            if edited_schedule is not None and not edited_schedule.empty:
                _draft_df = edited_schedule.drop(columns=["Select"], errors="ignore").copy()
                _draft_payload = dict(
                    work_order_id=selected_wo_id,
                    machine_id=_mkey,
                    machine_label=_mlabel,
                    year=_billing_month_str,
                    ot_rate=ot_rate_input if ot_rate_input > 0 else 0.0,
                    schedule_data=_schedule_to_json(_draft_df),
                    is_draft=True,
                )
                try:
                    sb.upsert_worklog(_draft_payload)
                    st.session_state.pop(f"sched_data_{base_key}", None)
                    st.toast("Draft saved — persists after logout. Click Save Work Log to commit.", icon="📝")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save draft: {exc}")

    # ── Discard Draft (deletes the DB draft record) ────────────────────────────
    with _btn_discard:
        if _is_db_draft:
            if st.button("Discard Draft", key="discard_draft_btn", use_container_width=True):
                try:
                    sb.delete_worklog(selected_wo_id, _mkey, _billing_month_str)
                except Exception:
                    pass
                st.session_state.pop(f"sched_data_{base_key}", None)
                st.rerun()

    # ── Save Work Log (commits to DB with is_draft=False) ─────────────────────
    with _btn_save:
        if st.button("💾 Save Work Log", type="primary", key="save_worklog",
                     use_container_width=True):
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

            wl_payload = dict(
                work_order_id=selected_wo_id,
                machine_id=_mkey,
                machine_label=_mlabel,
                year=_billing_month_str,
                ot_rate=ot_rate_input if ot_rate_input > 0 else 0.0,
                schedule_data=schedule_json,
                is_draft=False,
            )

            # Keep shift defaults in machine_config for future months
            updated_configs = [dict(m) for m in machine_configs]
            updated_configs[machine_idx]["shift_start_time"] = (
                shift_start_time.strftime("%H:%M") if shift_start_time else None
            )
            updated_configs[machine_idx]["shift_end_time"] = (
                shift_end_time.strftime("%H:%M") if shift_end_time else None
            )
            updated_configs[machine_idx]["ot_rate"] = ot_rate_input if ot_rate_input > 0 else None

            try:
                sb.upsert_worklog(wl_payload)
                sb.update_work_order(selected_wo_id, {
                    "machine_config": json.dumps(updated_configs),
                })
                st.session_state.pop(f"sched_data_{base_key}", None)
                st.success(f"✅ Work log for {selected_month_label} saved to database.")
            except Exception as exc:
                st.error(f"Could not save work log: {exc}")
