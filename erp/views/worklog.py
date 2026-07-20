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


_SCHED_COLS = [
    "Date", "Weekday",
    "Start Time", "End Time", "Net Time",
    "Start HMR", "End HMR", "Net HMR", "Breakdown Hours",
    "OT", "Operator", "Remarks",
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
    # pd.Timestamp / datetime.datetime — extract time component
    if isinstance(value, datetime):
        return value.time()
    # pd.Timedelta / datetime.timedelta — Arrow round-trips TimeColumn as duration-from-midnight
    if hasattr(value, "total_seconds"):
        try:
            secs = int(value.total_seconds()) % 86400
            return time(secs // 3600, (secs % 3600) // 60, secs % 60)
        except Exception:
            pass
    if isinstance(value, str):
        value = value.strip()
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
        # "HH:MM:SS.ffffff" or ISO fragment with date prefix
        try:
            return datetime.fromisoformat(value).time()
        except (ValueError, TypeError):
            pass
    return None


def _recalc_df(
    df: pd.DataFrame,
    shift_start_t: "time | None",
    shift_end_t: "time | None",
) -> "tuple[pd.DataFrame, bool]":
    """Recompute Net Time, OT, and Net HMR from Start/End times in *df*.

    Returns (updated_df, changed). Called both pre-render (on df_to_show) and
    post-render (on edited) so derived columns are always consistent.
    """
    shift_dur = _net_hours(shift_start_t, shift_end_t)
    out = df.copy()
    changed = False

    for idx, row in out.iterrows():
        st_ = _parse_time(row.get("Start Time"))
        et_ = _parse_time(row.get("End Time"))
        raw_net   = _net_hours(st_, et_)
        is_sunday = str(row.get("Weekday", "")) == "Sunday"

        if raw_net is not None:
            if is_sunday:
                exp_net = None
                exp_ot  = round(raw_net, 2)
                exp_bd  = 0.0
            elif shift_dur is not None:
                exp_net = raw_net
                exp_ot  = round(max(0.0, raw_net - shift_dur), 2)
                exp_bd  = round(max(0.0, shift_dur - raw_net), 2)
            else:
                exp_net = raw_net
                exp_ot  = 0.0
                exp_bd  = 0.0

            cur_net    = row.get("Net Time")
            cur_net_na = cur_net is None or _safe_isnan(cur_net)
            if cur_net_na != (exp_net is None) or (
                not cur_net_na and exp_net is not None
                and abs(float(cur_net) - float(exp_net)) > 0.001
            ):
                out.at[idx, "Net Time"] = exp_net
                changed = True

            cur_ot    = row.get("OT")
            cur_ot_na = cur_ot is None or _safe_isnan(cur_ot)
            if cur_ot_na or abs(float(cur_ot if not cur_ot_na else 0) - exp_ot) > 0.001:
                out.at[idx, "OT"] = exp_ot
                changed = True

            cur_bd    = row.get("Breakdown Hours")
            cur_bd_na = cur_bd is None or _safe_isnan(cur_bd)
            if cur_bd_na or abs(float(cur_bd if not cur_bd_na else 0) - exp_bd) > 0.001:
                out.at[idx, "Breakdown Hours"] = exp_bd
                changed = True

        # Net HMR = End HMR − Start HMR
        s_hmr = row.get("Start HMR")
        e_hmr = row.get("End HMR")
        s_ok  = s_hmr is not None and not _safe_isnan(s_hmr)
        e_ok  = e_hmr is not None and not _safe_isnan(e_hmr)
        if s_ok and e_ok:
            exp_hmr    = round(float(e_hmr) - float(s_hmr), 2)
            cur_hmr    = row.get("Net HMR")
            cur_hmr_na = cur_hmr is None or _safe_isnan(cur_hmr)
            if cur_hmr_na or abs(float(cur_hmr) - exp_hmr) > 0.001:
                out.at[idx, "Net HMR"] = exp_hmr
                changed = True

    return out, changed



def _net_hours(start: time | None, end: time | None) -> float | None:
    if start is None or end is None:
        return None
    diff = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if diff < 0:
        diff += 1440
    return round(diff / 60, 2)


_DEFAULT_START = time(8, 0)   # 08:00:00
_DEFAULT_END   = time(21, 0)  # 21:00:00
_DEFAULT_NET   = _net_hours(_DEFAULT_START, _DEFAULT_END)  # 13.0


def _build_schedule(
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    rows, cur = [], start_date
    while cur <= end_date:
        is_sunday = cur.strftime("%A") == "Sunday"
        weekday   = cur.strftime("%A")
        rows.append({
            "Date":            cur,
            "Weekday":         weekday,
            "Start Time":      None          if is_sunday else _DEFAULT_START,
            "End Time":        None          if is_sunday else _DEFAULT_END,
            "Net Time":        None          if is_sunday else _DEFAULT_NET,
            "Start HMR":       None,
            "End HMR":         None,
            "Net HMR":         None,
            "Breakdown Hours": None          if is_sunday else 0.0,
            "OT":              None          if is_sunday else 0.0,
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
            "net_time":        float(row.get("Net Time") or 0) if pd.notna(row.get("Net Time")) else None,
            "start_hmr":       float(row.get("Start HMR")) if pd.notna(row.get("Start HMR")) else None,
            "end_hmr":         float(row.get("End HMR"))   if pd.notna(row.get("End HMR"))   else None,
            "net_hmr":         float(row.get("Net HMR"))   if pd.notna(row.get("Net HMR"))   else None,
            "breakdown_hours": float(row.get("Breakdown Hours")) if pd.notna(row.get("Breakdown Hours")) else None,
            "ot":              float(row.get("OT")) if pd.notna(row.get("OT")) else None,
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
                "Net HMR":         r.get("net_hmr"),
                "Breakdown Hours": r.get("breakdown_hours"),
                "OT":              r.get("ot"),
                "Operator":        r.get("operator", ""),
                "Remarks":         r.get("remarks", ""),
            }
            for r in records
        ]
        df = pd.DataFrame(rows, columns=_SCHED_COLS)
        return _ensure_ot_rows(df)
    except (json.JSONDecodeError, ValueError, KeyError):
        return None


def _ensure_ot_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Strip legacy columns and deduplicate by Date from saved data."""
    if df.empty:
        return df
    df = df.drop(columns=["Type"], errors="ignore").reset_index(drop=True)
    if "Date" in df.columns and df["Date"].duplicated().any():
        df = df.drop_duplicates(subset=["Date"], keep="first").reset_index(drop=True)
    return df



def _safe_isnan(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float):
        import math
        return math.isnan(val)
    try:
        return bool(pd.isna(val))
    except (TypeError, ValueError):
        return False


def _style_schedule(df: pd.DataFrame):
    # ── Palette ───────────────────────────────────────────────────────────
    _WKND_BG  = "#DBEAFE"          # soft sky blue — Saturday / Sunday
    _WKND_FG  = "#1E40AF"          # indigo text on blue
    _OT_BG    = "#FEF3C7"          # warm amber — positive OT cells
    _OT_FG    = "#92400E"          # brown text on amber
    _NONE_FG  = "#9CA3AF"          # cool gray for None / empty cells

    numeric_right = {"Net Time", "Net HMR", "Breakdown Hours", "OT"}
    time_center   = {"Start Time", "End Time"}

    def _row_style(row):
        weekday    = str(row.get("Weekday", ""))
        is_weekend = weekday == "Sunday"

        result = []
        for col in row.index:
            val = row[col]
            if is_weekend:
                s = f"background-color:{_WKND_BG}; color:{_WKND_FG}; font-weight:600"
            elif col == "OT":
                try:
                    ot = float(val) if not _safe_isnan(val) else 0.0
                    if ot > 0:
                        s = f"background-color:{_OT_BG}; color:{_OT_FG}; font-weight:700"
                    else:
                        s = ""
                except (TypeError, ValueError):
                    s = ""
            else:
                s = ""

            if col in numeric_right:
                s += "; text-align:right"
            elif col in time_center:
                s += "; text-align:center"

            result.append(s)
        return result

    def _none_style(val):
        if _safe_isnan(val):
            return f"color:{_NONE_FG}"
        return ""

    header_styles = [
        {
            "selector": "thead th",
            "props": [
                ("background-color", "#15803D"),
                ("color", "#FFFFFF"),
                ("font-weight", "700"),
                ("letter-spacing", "0.03em"),
            ],
        }
    ]

    return (
        df.style
        .apply(_row_style, axis=1)
        .map(_none_style)
        .set_table_styles(header_styles)
    )


def _parse_machine_configs(raw) -> list[dict]:
    if not raw:
        return []
    try:
        records = json.loads(raw) if isinstance(raw, str) else raw
        return records if isinstance(records, list) else []
    except Exception:
        return []


# ── OT Continuation Log helpers ───────────────────────────────────────────────

def _totals_cell(label: str, value: str) -> str:
    return (
        f"<td style='padding:8px 14px;border-right:1px solid #374151;'>"
        f"<div style='font-size:9px;font-weight:700;letter-spacing:.1em;"
        f"text-transform:uppercase;color:#9ca3af;margin-bottom:2px;'>{label}</div>"
        f"<div style='font-size:14px;font-weight:800;color:#E87722;"
        f"font-variant-numeric:tabular-nums;'>{value}</div></td>"
    )


def _compute_billing_summary(
    df: pd.DataFrame | None,
    rental_per_month: float,
    shift_start: time,
    shift_end: time,
    ot_rate_input: float = 0.0,
    no_of_days: int | None = None,
    deduction: float = 0.0,
) -> dict | None:
    if df is None or df.empty:
        return None
    w       = df.drop(columns=["Select", "Type"], errors="ignore")
    working_days     = no_of_days if (no_of_days and no_of_days > 0) \
                       else int(w["Start Time"].notna().sum())
    std_hours        = _net_hours(shift_start, shift_end) or 0.0
    working_hours    = working_days * std_hours
    actual           = float(w["Net Time"].astype(float).fillna(0).sum())
    qty              = actual / working_hours if working_hours else 0.0
    billing          = rental_per_month * qty
    ot_hours         = float(w["OT"].astype(float).fillna(0).sum())
    breakdown_hours  = float(w["Breakdown Hours"].astype(float).fillna(0).sum())
    ot_rate          = float(ot_rate_input or 0.0)
    ot_billing       = ot_hours * ot_rate
    total_billing    = billing + ot_billing
    deduction_amt    = float(deduction or 0.0)
    adjusted_billing = total_billing - deduction_amt
    return dict(
        rental_per_month=rental_per_month,
        working_days=working_days,
        std_hours=std_hours,
        working_hours=working_hours,
        actual=actual,
        qty=qty,
        billing=billing,
        ot_hours=ot_hours,
        ot_rate=ot_rate,
        ot_billing=ot_billing,
        breakdown_hours=breakdown_hours,
        total_billing=total_billing,
        deduction=deduction_amt,
        adjusted_billing=adjusted_billing,
    )


def _render_billing_summary(
    s: dict,
    wo_number: str = "",
    machine_label: str = "",
    month_label: str = "",
) -> None:

    def _inr(v: float) -> str:
        """Indian number system: ₹ X,XX,XXX"""
        neg = v < 0
        s_ = str(int(round(abs(v))))
        if len(s_) > 3:
            last3 = s_[-3:]
            rest  = s_[:-3]
            chunks: list[str] = []
            while len(rest) > 2:
                chunks.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                chunks.insert(0, rest)
            s_ = ",".join(chunks) + "," + last3
        return ("− " if neg else "") + "₹ " + s_

    def _n2(v: float) -> str:
        return f"{v:,.2f}"

    rental    = s["rental_per_month"]
    wd        = s["working_days"]
    std_h     = s.get("std_hours", 0.0)
    wh        = s["working_hours"]
    actual    = s["actual"]
    qty       = s["qty"]
    billing   = s["billing"]
    ot_hrs    = s["ot_hours"]
    ot_rate   = s["ot_rate"]
    ot_bill   = s["ot_billing"]
    bd_hrs    = s.get("breakdown_hours", 0.0)
    total     = s["total_billing"]
    ded       = s["deduction"]
    adj       = s["adjusted_billing"]
    util_pct  = qty * 100

    # ── Header ─────────────────────────────────────────────────────────────────
    sub_parts = [p for p in ["Work Log", wo_number, machine_label, month_label] if p]
    subtitle  = " &bull; ".join(sub_parts)

    st.markdown(
        "<div style='display:flex;justify-content:space-between;align-items:flex-start;"
        "padding:16px 0 12px;border-bottom:2px solid #e5e7eb;margin-bottom:16px;'>"
        "<div style='display:flex;align-items:center;gap:12px;'>"
        "<div style='background:#f0f9ff;border-radius:10px;padding:10px;font-size:24px;line-height:1;'>🧾</div>"
        "<div>"
        "<div style='font-size:24px;font-weight:800;color:#111827;letter-spacing:-.02em;'>Billing Summary</div>"
        f"<div style='font-size:13px;color:#6b7280;margin-top:3px;'>{subtitle}</div>"
        "</div></div>"
        "<div style='border:1px solid #d1d5db;border-radius:8px;padding:8px 16px;"
        "background:#fff;display:flex;align-items:center;gap:8px;'>"
        "<span style='font-size:16px;'>📊</span>"
        "<span style='font-size:13px;font-weight:600;color:#374151;'>View Calculation Details</span>"
        "</div></div>",
        unsafe_allow_html=True,
    )

    # ── KPI cards ─────────────────────────────────────────────────────────────
    def _kpi_card(icon: str, label: str, value: str, sub: str, val_color: str) -> str:
        return (
            "<div style='background:#fff;border:1px solid #e5e7eb;border-radius:12px;"
            "padding:14px 16px;flex:1;min-width:0;'>"
            f"<div style='font-size:20px;margin-bottom:6px;'>{icon}</div>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;"
            f"color:#9ca3af;margin-bottom:4px;'>{label}</div>"
            f"<div style='font-size:20px;font-weight:800;color:{val_color};"
            f"font-variant-numeric:tabular-nums;line-height:1.2;'>{value}</div>"
            f"<div style='font-size:11px;color:#9ca3af;margin-top:4px;'>{sub}</div>"
            "</div>"
        )

    kpi_html = (
        "<div style='display:flex;gap:12px;margin-bottom:20px;'>"
        + _kpi_card("📅", "Rental / Month",   _inr(rental),    "Fixed Rental",    "#111827")
        + _kpi_card("📋", "Working Days",      str(wd),         "From Work Order", "#16a34a")
        + _kpi_card("🕐", "Worked Hours",      _n2(actual),     "Total Logged",    "#f97316")
        + _kpi_card("⏱️", "OT Hours",          _n2(ot_hrs),     "Total Logged",    "#3b82f6")
        + _kpi_card("🔧", "Breakdown Hours",   _n2(bd_hrs),     "Total Logged",    "#f97316")
        + _kpi_card("💰", "Adjusted Billing",  _inr(adj),       "Excluding Taxes", "#111827")
        + "</div>"
    )
    st.markdown(kpi_html, unsafe_allow_html=True)

    # ── Two-column layout ──────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 1], gap="large")

    # ── LEFT: Billing Calculation table ───────────────────────────────────────
    with col_left:
        def _section_row(label: str, color: str, bg: str) -> str:
            return (
                f"<tr style='background:{bg};'>"
                "<td colspan='5' style='padding:8px 16px;'>"
                f"<span style='display:inline-flex;align-items:center;gap:8px;"
                f"background:{color}18;border:1px solid {color}44;border-radius:6px;"
                f"padding:3px 10px;font-size:12px;font-weight:700;color:{color};'>"
                f"&#9632; {label}</span></td></tr>"
            )

        def _data_row(num: int, field: str, value: str, rule: str,
                      impact: str = "&mdash;", impact_color: str = "#9ca3af",
                      bg: str = "#ffffff") -> str:
            return (
                f"<tr style='background:{bg};border-bottom:1px solid #f3f4f6;'>"
                f"<td style='padding:9px 12px 9px 16px;font-size:12px;color:#9ca3af;"
                f"font-weight:600;width:32px;'>{num}</td>"
                f"<td style='padding:9px 12px;font-size:13px;color:#374151;"
                f"font-weight:500;'>{field}</td>"
                f"<td style='padding:9px 12px;text-align:right;font-size:13px;"
                f"font-weight:700;color:#E87722;font-variant-numeric:tabular-nums;"
                f"white-space:nowrap;'>{value}</td>"
                f"<td style='padding:9px 12px;font-size:12px;color:#6b7280;"
                f"font-style:italic;'>{rule}</td>"
                f"<td style='padding:9px 16px 9px 12px;text-align:right;font-size:13px;"
                f"font-weight:700;color:{impact_color};white-space:nowrap;"
                f"font-variant-numeric:tabular-nums;'>{impact}</td>"
                "</tr>"
            )

        STRIPE = "#f9fafb"

        tbody = (
            _section_row("Base Rental", "#2563eb", "#eff6ff")
            + _data_row(1, "Rental per month",       _inr(rental),
                        "Rental / Month (From Work Order)")
            + _data_row(2, "Working days",            str(wd),
                        "No of Days from Work Order (machine config)",  bg=STRIPE)
            + _data_row(3, "Working hours",           _n2(wh),
                        f"Working days &times; Working hours per day ({std_h:.2f})")
            + _data_row(4, "Actual hours (Net Time)", _n2(actual),
                        "Sum of Net Time from Work Log",                bg=STRIPE)
            + _data_row(5, "Qty (Utilization Factor)",f"{qty:.4f}",
                        f"Actual &divide; Working hours ({actual:,.2f} &divide; {wh:,.2f})")
            + _data_row(6, "Billing (Rental &times; Qty)", _inr(billing),
                        f"Rental per month &times; Qty ({_inr(rental)} &times; {qty:.4f})",
                        impact=f"+ {_inr(billing)}", impact_color="#16a34a", bg=STRIPE)

            + _section_row("Overtime", "#d97706", "#fffbeb")
            + _data_row(7, "OT hours",    _n2(ot_hrs),
                        "Sum of OT Hrs from Shift Schedule")
            + _data_row(8, "OT rate",     _inr(ot_rate),
                        "From OT Rate field in Work Order",             bg=STRIPE)
            + _data_row(9, "OT billing",  _inr(ot_bill),
                        f"OT hours &times; OT rate ({_n2(ot_hrs)} &times; {ot_rate:,.0f})",
                        impact=f"+ {_inr(ot_bill)}", impact_color="#16a34a")

            + _section_row("Final Amounts", "#16a34a", "#f0fdf4")
            + _data_row(10, "Total Billing",    _inr(total),
                        f"Billing + OT Billing ({_inr(billing)} + {_inr(ot_bill)})",
                        impact=f"+ {_inr(total)}", impact_color="#16a34a", bg=STRIPE)
            + _data_row(11, "Deduction",        f"&minus; {_inr(ded)}",
                        "Manual entry (if any)",
                        impact=f"&minus; {_inr(ded)}", impact_color="#dc2626")
            + _data_row(12, "Adjusted Billing", _inr(adj),
                        f"Total Billing &minus; Deduction ({_inr(total)} &minus; {_inr(ded)})",
                        impact=f"= {_inr(adj)}", impact_color="#374151", bg=STRIPE)
        )

        st.markdown(
            "<div style='border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;"
            "box-shadow:0 1px 4px rgba(0,0,0,.06);'>"
            "<div style='padding:14px 16px 10px;border-bottom:1px solid #e5e7eb;"
            "background:#fafafa;'>"
            "<div style='font-size:16px;font-weight:700;color:#111827;display:flex;"
            "align-items:center;gap:8px;'>🧮 Billing Calculation</div>"
            "<div style='font-size:12px;color:#6b7280;margin-top:2px;'>"
            "Detailed breakdown of billing calculation and rules</div></div>"
            "<table style='width:100%;border-collapse:collapse;'>"
            "<thead><tr style='background:#f8fafc;border-bottom:2px solid #e5e7eb;'>"
            "<th style='padding:9px 12px 9px 16px;text-align:left;font-size:10px;font-weight:700;"
            "letter-spacing:.1em;text-transform:uppercase;color:#9ca3af;width:32px;'>#</th>"
            "<th style='padding:9px 12px;text-align:left;font-size:10px;font-weight:700;"
            "letter-spacing:.1em;text-transform:uppercase;color:#374151;'>Field</th>"
            "<th style='padding:9px 12px;text-align:right;font-size:10px;font-weight:700;"
            "letter-spacing:.1em;text-transform:uppercase;color:#374151;'>Value</th>"
            "<th style='padding:9px 12px;text-align:left;font-size:10px;font-weight:700;"
            "letter-spacing:.1em;text-transform:uppercase;color:#374151;'>Calculation Rule</th>"
            "<th style='padding:9px 16px 9px 12px;text-align:right;font-size:10px;font-weight:700;"
            "letter-spacing:.1em;text-transform:uppercase;color:#374151;'>Impact</th>"
            f"</tr></thead><tbody>{tbody}</tbody></table></div>",
            unsafe_allow_html=True,
        )

    # ── RIGHT: Billing Summary sidebar ────────────────────────────────────────
    with col_right:
        def _sb_row(label: str, value: str, val_color: str = "#111827",
                    bold: bool = False) -> str:
            fw = "800" if bold else "600"
            return (
                f"<tr style='border-bottom:1px solid #f3f4f6;'>"
                f"<td style='padding:9px 12px;font-size:13px;color:#6b7280;"
                f"font-weight:500;'>{label}</td>"
                f"<td style='padding:9px 12px;text-align:right;font-size:13px;"
                f"font-weight:{fw};color:{val_color};"
                f"font-variant-numeric:tabular-nums;white-space:nowrap;'>{value}</td>"
                "</tr>"
            )

        sb_rows = (
            _sb_row("Rental per month",     _inr(rental))
            + _sb_row("Working Days",       str(wd))
            + _sb_row("Worked Hours",       _n2(actual))
            + _sb_row("Utilization (Qty)",  f"{util_pct:.2f}%")
            + _sb_row("Base Rental (After Qty)", _inr(billing), "#E87722", True)
            + _sb_row("OT Hours",           _n2(ot_hrs))
            + _sb_row("OT Billing",         _inr(ot_bill))
            + _sb_row("Total Billing",      _inr(total), "#111827", True)
            + _sb_row("Deduction",          f"&minus; {_inr(ded)}", "#dc2626")
        )

        st.markdown(
            "<div style='border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;"
            "box-shadow:0 1px 4px rgba(0,0,0,.06);'>"
            "<div style='padding:12px 14px;border-bottom:1px solid #e5e7eb;background:#fafafa;'>"
            "<div style='font-size:14px;font-weight:700;color:#111827;display:flex;"
            "align-items:center;gap:6px;'>🧾 Billing Summary</div></div>"
            "<table style='width:100%;border-collapse:collapse;'>"
            f"<tbody>{sb_rows}</tbody></table>"
            "<div style='margin:12px;padding:14px;background:linear-gradient(135deg,#fff7ed,#fef3c7);"
            "border:1px solid #fed7aa;border-radius:10px;'>"
            "<div style='font-size:11px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:.08em;color:#92400e;margin-bottom:6px;'>Adjusted Billing</div>"
            f"<div style='font-size:26px;font-weight:900;color:#111827;"
            f"font-variant-numeric:tabular-nums;'>{_inr(adj)}</div>"
            "<div style='font-size:11px;color:#78716c;margin-top:4px;'>(Excluding Taxes)</div>"
            "</div>"
            "<div style='padding:10px 14px;background:#f0f9ff;border-top:1px solid #e0f2fe;"
            "display:flex;align-items:flex-start;gap:8px;'>"
            "<span style='font-size:14px;flex-shrink:0;margin-top:1px;'>ℹ️</span>"
            "<div style='font-size:11px;color:#0369a1;line-height:1.5;'>"
            "All amounts are excluding taxes.<br><strong>Currency: INR</strong></div>"
            "</div></div>",
            unsafe_allow_html=True,
        )


# ── Double-shift helpers ──────────────────────────────────────────────────────

def _is_double_schedule(raw) -> bool:
    if not raw:
        return False
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return isinstance(data, dict) and data.get("shift_type") == "double"
    except Exception:
        return False


def _double_schedule_to_json(df1: pd.DataFrame, df2: pd.DataFrame) -> str:
    r1 = json.loads(_schedule_to_json(df1))
    r2 = json.loads(_schedule_to_json(df2))
    return json.dumps({"shift_type": "double", "shift1": r1, "shift2": r2})


def _json_to_double_dfs(raw) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return _json_to_schedule_df(data.get("shift1", [])), \
               _json_to_schedule_df(data.get("shift2", []))
    except Exception:
        return None, None


def _history_fill(
    blank_df: pd.DataFrame,
    prev_df: pd.DataFrame,
    shift_start_t: time,
    shift_end_t: time,
) -> pd.DataFrame:
    """
    Pre-fill *blank_df* using per-weekday modal Start Time, End Time, and
    Operator from *prev_df* (the previous month's schedule).  HMR columns
    are intentionally left blank — they accumulate over machine life and
    must be entered fresh each month.
    """
    if prev_df is None or prev_df.empty:
        return blank_df

    shift_dur = _net_hours(shift_start_t, shift_end_t)

    # Build per-weekday defaults from previous month
    defaults: dict = {}
    for wd in prev_df["Weekday"].dropna().unique():
        if wd == "Sunday":
            continue
        wd_rows = prev_df[
            (prev_df["Weekday"] == wd) & prev_df["Start Time"].notna()
        ]
        if wd_rows.empty:
            continue
        sm = wd_rows["Start Time"].mode()
        em = wd_rows["End Time"].dropna().mode()
        om = wd_rows["Operator"].dropna().mode()
        if sm.empty:
            continue
        defaults[wd] = {
            "Start Time": sm.iloc[0],
            "End Time":   em.iloc[0] if not em.empty else None,
            "Operator":   str(om.iloc[0]) if not om.empty else "",
        }

    if not defaults:
        return blank_df

    result = blank_df.copy()
    for idx, row in result.iterrows():
        wd = str(row.get("Weekday", ""))
        if wd not in defaults:
            continue
        d = defaults[wd]
        prev_st, prev_et = d["Start Time"], d["End Time"]
        if prev_st is None or prev_et is None:
            continue
        result.at[idx, "Start Time"] = prev_st
        result.at[idx, "End Time"]   = prev_et
        result.at[idx, "Operator"]   = d["Operator"]
        raw_net = _net_hours(prev_st, prev_et)
        if raw_net is not None:
            result.at[idx, "Net Time"] = raw_net
            result.at[idx, "OT"] = (
                round(max(0.0, raw_net - shift_dur), 2) if shift_dur is not None else 0.0
            )
    return result


def _render_shift_editor(
    base_key: str,
    initial_df: pd.DataFrame,
    shift_start_t: time,
    shift_end_t: time,
    operator_names: list[str],
) -> pd.DataFrame | None:
    """Render a shift schedule data editor and auto-recalculate Net Time / OT."""
    recalc_count = st.session_state.get(f"sched_recalc_{base_key}", 0)
    editor_key   = f"{base_key}_{recalc_count}"
    df_to_show   = st.session_state.get(f"sched_data_{base_key}", initial_df)

    # Deduplicate rows — stale session state from old copy/paste code can leave
    # doubled DataFrames; also guards against duplicated DB records.
    if "Date" in df_to_show.columns and df_to_show["Date"].duplicated().any():
        df_to_show = df_to_show.drop_duplicates(subset=["Date"], keep="first").reset_index(drop=True)
        st.session_state[f"sched_data_{base_key}"] = df_to_show

    # Pre-render recalc: fix Net Time / OT / Net HMR that may be stale in
    # session state (e.g. history-filled times without Net Time, or data loaded
    # from DB before this formula was deployed).  Uses df_to_show which always
    # carries proper datetime.time objects so type coercion is not needed here.
    _pre_df, _pre_changed = _recalc_df(df_to_show, shift_start_t, shift_end_t)
    if _pre_changed:
        df_to_show = _pre_df
        st.session_state[f"sched_data_{base_key}"]   = df_to_show
        st.session_state[f"sched_recalc_{base_key}"] = recalc_count + 1
        st.rerun()

    # ── Data editor ────────────────────────────────────────────────────────────
    editor_height = 38 + len(df_to_show) * 35 + 4

    edited = st.data_editor(
        _style_schedule(df_to_show),
        height=editor_height,
        column_config={
            "Date":            st.column_config.DateColumn("Date", disabled=True, width="small", format="DD-MM-YYYY"),
            "Weekday":         st.column_config.TextColumn("Weekday", disabled=True, width="small"),
            "Start Time":      st.column_config.TimeColumn("Start Time", width="small"),
            "End Time":        st.column_config.TimeColumn("End Time", width="small"),
            "Net Time":        st.column_config.NumberColumn("Net Time", format="%.1f",
                                   disabled=True, width="small"),
            "Start HMR":       st.column_config.NumberColumn("Start HMR", format="%.1f",
                                   min_value=0, step=0.1, width="small"),
            "End HMR":         st.column_config.NumberColumn("End HMR", format="%.1f",
                                   min_value=0, step=0.1, width="small"),
            "Net HMR":         st.column_config.NumberColumn("Net HMR", format="%.1f",
                                   disabled=True, width="small"),
            "Breakdown Hours": st.column_config.NumberColumn("B/D Hrs", format="%.1f",
                                   disabled=True, width="small"),
            "OT":              st.column_config.NumberColumn("OT Hrs", format="%.1f",
                                   disabled=True, width="small"),
            "Operator":        st.column_config.SelectboxColumn("Operator",
                                   options=operator_names, width="medium"),
            "Remarks":         st.column_config.TextColumn("Remarks", width="medium"),
        },
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
        key=editor_key,
    )

    # Post-render recalc: detect user edits to Start/End Time or HMR and
    # recompute derived columns.  _recalc_df uses _parse_time on every value
    # so it handles all types Streamlit's Arrow round-trip may return
    # (datetime.time, pd.Timestamp, pd.Timedelta, str).
    if edited is not None and not edited.empty:
        clean, needs_recalc = _recalc_df(
            edited.drop(columns=["Select"], errors="ignore"),
            shift_start_t,
            shift_end_t,
        )
        if needs_recalc:
            st.session_state[f"sched_data_{base_key}"]   = clean
            st.session_state[f"sched_recalc_{base_key}"] = recalc_count + 1
            st.rerun()

    return edited


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

    # ── Customer selector ──────────────────────────────────────────────────────
    # Only list customers that have at least one work order (keeps it short).
    _cids_with_wo = sorted(
        {wo.get("customer_id") for wo in work_orders if wo.get("customer_id")},
        key=lambda cid: customer_map.get(cid, {}).get("customer_name", ""),
    )
    selected_customer_id = st.selectbox(
        "Select Customer",
        options=[""] + _cids_with_wo,
        format_func=lambda cid: "Select a customer" if not cid
            else customer_map.get(cid, {}).get("customer_name", cid),
        key="wl_selected_customer_id",
    )

    # Reset WO selection whenever the customer changes.
    if st.session_state.get("_wl_prev_customer") != selected_customer_id:
        st.session_state["_wl_prev_customer"] = selected_customer_id
        st.session_state["wl_selected_wo_id"] = ""

    if not selected_customer_id:
        st.info("Select a customer above to continue.")
        return

    # ── Work order selector (filtered by selected customer) ────────────────────
    _filtered_wo_ids = sorted(
        [wid for wid, wo in wo_map.items()
         if wo.get("customer_id") == selected_customer_id],
        key=lambda wid: wo_map[wid].get("wo_number", ""),
    )
    selected_wo_id = st.selectbox(
        "Select Work Order",
        options=[""] + _filtered_wo_ids,
        format_func=lambda wid: "Select a work order" if not wid
            else wo_map[wid].get("wo_number", "Unknown"),
        key="wl_selected_wo_id",
    )
    selected_wo = wo_map.get(selected_wo_id)

    if not selected_wo:
        st.info("Select a work order above to view and edit its shift schedule.")
        return

    # ── Parse machine configs from WO ──────────────────────────────────────────
    machine_configs = _parse_machine_configs(selected_wo.get("machine_config"))

    # ── WO info card ───────────────────────────────────────────────────────────
    _wo_start = _parse_date(selected_wo.get("start_date"))
    _wo_end   = _parse_date(selected_wo.get("end_date"))
    _wo_start_fmt = _wo_start.strftime("%d-%m-%Y") if _wo_start else "—"
    _wo_end_fmt   = _wo_end.strftime("%d-%m-%Y")   if _wo_end   else "Ongoing"

    def _wo_field(label: str, value: str, val_color: str = "#111827",
                  val_size: str = "15px", val_weight: str = "700") -> str:
        return (
            "<div style='display:flex;flex-direction:column;gap:3px;'>"
            f"<div style='font-size:10px;font-weight:800;letter-spacing:.12em;"
            f"text-transform:uppercase;color:#64748b;'>{label}</div>"
            f"<div style='font-size:{val_size};font-weight:{val_weight};"
            f"color:{val_color};line-height:1.2;'>{value}</div>"
            "</div>"
        )

    st.markdown(
        "<div style='background:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;"
        "padding:14px 22px;margin-bottom:14px;"
        "box-shadow:0 1px 4px rgba(0,0,0,.06);'>"
        "<div style='display:flex;flex-wrap:wrap;gap:0;align-items:stretch;'>"
        + _wo_field("WO Number",  selected_wo.get("wo_number", "—"), "#E87722", "20px", "900")
        + "<div style='width:1px;background:#e2e8f0;margin:0 20px;'></div>"
        + _wo_field("Customer",   customer_map.get(selected_wo.get("customer_id", ""), {}).get("customer_name", "—"))
        + "<div style='width:1px;background:#e2e8f0;margin:0 20px;'></div>"
        + _wo_field("Site",       site_map.get(selected_wo.get("site_id", ""), {}).get("site_name", "—"))
        + "<div style='width:1px;background:#e2e8f0;margin:0 20px;'></div>"
        + _wo_field("WO Period",  f"{_wo_start_fmt} &rarr; {_wo_end_fmt}")
        + "<div style='width:1px;background:#e2e8f0;margin:0 20px;'></div>"
        + _wo_field("Machines",   str(len(machine_configs)), "#E87722", "18px", "900")
        + "</div></div>",
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
        st.session_state["wl_ot_rate"] = float(selected_machine.get("ot_rate") or 0.0)

    # ── Machine config card ────────────────────────────────────────────────────
    _rental = selected_machine.get("rental_per_month")
    _cs_d   = _parse_date(selected_machine.get("billing_cycle_start_date"))
    _ce_d   = _parse_date(selected_machine.get("billing_cycle_end_date"))
    _cycle_period_display = (
        f"Day {_cs_d.day} &rarr; Day {_ce_d.day}"
        if (_cs_d and _ce_d) else "—"
    )
    def _mc_field(label: str, value: str, val_color: str = "#111827",
                  val_size: str = "15px", val_weight: str = "700") -> str:
        return (
            "<div style='display:flex;flex-direction:column;gap:3px;'>"
            f"<div style='font-size:10px;font-weight:800;letter-spacing:.12em;"
            f"text-transform:uppercase;color:#92400e;'>{label}</div>"
            f"<div style='font-size:{val_size};font-weight:{val_weight};"
            f"color:{val_color};line-height:1.2;'>{value}</div>"
            "</div>"
        )

    _rental_display = f"&#8377; {float(_rental):,.0f}" if _rental else "—"

    st.markdown(
        "<div style='background:linear-gradient(135deg,#fff7ed,#fef9f0);"
        "border:1px solid #fbbf24;border-left:4px solid #E87722;border-radius:10px;"
        "padding:14px 22px;margin-bottom:14px;"
        "box-shadow:0 1px 4px rgba(232,119,34,.10);'>"
        "<div style='display:flex;flex-wrap:wrap;gap:0;align-items:stretch;'>"
        + _mc_field("Machine",      selected_machine_label,                          "#111827", "16px", "800")
        + "<div style='width:1px;background:#fcd34d;margin:0 20px;'></div>"
        + _mc_field("Billing Type", selected_machine.get("billing_type", "—"))
        + "<div style='width:1px;background:#fcd34d;margin:0 20px;'></div>"
        + _mc_field("Billing Cycle",selected_machine.get("billing_cycle", "—"))
        + "<div style='width:1px;background:#fcd34d;margin:0 20px;'></div>"
        + _mc_field("Cycle Period", _cycle_period_display)
        + "<div style='width:1px;background:#fcd34d;margin:0 20px;'></div>"
        + _mc_field("Rental / Month", _rental_display, "#E87722", "18px", "900")
        + "</div></div>",
        unsafe_allow_html=True,
    )

    # ── Billing dates ──────────────────────────────────────────────────────────
    billing_start_date = _parse_date(selected_machine.get("billing_cycle_start_date"))
    billing_end_date   = _parse_date(selected_machine.get("billing_cycle_end_date"))
    rental_per_month   = float(selected_machine.get("rental_per_month") or 0.0)
    _billing_cycle     = selected_machine.get("billing_cycle", "Calendar Month")

    # For Custom billing, the cycle start comes from the Deployment's billing_start_date.
    _dep_billing_start: date | None = None
    if _billing_cycle == "Custom":
        try:
            _dep = sb.get_deployment_by_wo(selected_wo_id)
            _dep_mds_raw = _dep.get("machine_deployments")
            if _dep_mds_raw:
                _dep_mds = json.loads(_dep_mds_raw) if isinstance(_dep_mds_raw, str) \
                           else _dep_mds_raw
                _mkey_lookup = selected_machine.get("machine_id") or selected_machine_label
                for _md in (_dep_mds if isinstance(_dep_mds, list) else []):
                    if (_md.get("machine_id") == _mkey_lookup or
                            _md.get("machine_label") == selected_machine_label):
                        _dep_billing_start = _parse_date(_md.get("billing_start_date"))
                        break
        except Exception:
            pass

        if not _dep_billing_start:
            st.warning(
                "No Billing Start Date found in the Deployment record for this machine. "
                "Please set it in the Deployments page first."
            )
            return
    elif not billing_start_date or not billing_end_date:
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

    # Schedule date range: always use the machine's Cycle Start / Cycle End day.
    # billing_start_date / billing_end_date are stored as dummy "2000-01-<day>" dates,
    # so .day gives the configured day number (e.g. 15 and 14).
    _cycle_start_day = billing_start_date.day if billing_start_date else 1
    _cycle_end_day   = billing_end_date.day   if billing_end_date   else None

    _max_cur    = calendar.monthrange(selected_year, selected_month_num)[1]
    month_start = date(selected_year, selected_month_num,
                       min(_cycle_start_day, _max_cur))

    if _cycle_end_day is not None and _cycle_end_day < _cycle_start_day:
        # End day falls in the NEXT calendar month (e.g. cycle 15 → 14)
        _ny, _nm  = (selected_year + 1, 1) if selected_month_num == 12 \
                    else (selected_year, selected_month_num + 1)
        _max_next = calendar.monthrange(_ny, _nm)[1]
        month_end = date(_ny, _nm, min(_cycle_end_day, _max_next))
    elif _cycle_end_day is not None:
        # End day is within the same calendar month (e.g. cycle 1 → 31)
        month_end = date(selected_year, selected_month_num,
                         min(_cycle_end_day, _max_cur))
    else:
        # Fallback: last day of selected month
        month_end = date(selected_year, selected_month_num, _max_cur)

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
            st.session_state["wl_ot_rate"]   = float(_wl_rec_sync.get("ot_rate") or 0.0)
            st.session_state["wl_deduction"] = float(_wl_rec_sync.get("deduction") or 0.0)
        else:
            st.session_state["wl_ot_rate"]   = float(selected_machine.get("ot_rate") or 0.0)
            st.session_state["wl_deduction"] = 0.0

        # Cache previous month's schedule for history auto-fill (one DB fetch per month/machine change)
        _prev_pm = selected_month_num - 1 if selected_month_num > 1 else 12
        _prev_py = selected_year if selected_month_num > 1 else selected_year - 1
        try:
            _prev_wl = sb.get_worklog_by_month(selected_wo_id, _mkey, _prev_py, _prev_pm)
        except Exception:
            _prev_wl = {}
        if _prev_wl and _prev_wl.get("schedule_data"):
            _prev_raw = _prev_wl["schedule_data"]
            if _is_double_schedule(_prev_raw):
                _p1, _p2 = _json_to_double_dfs(_prev_raw)
            else:
                _p1 = _json_to_schedule_df(_prev_raw)
                _p2 = None
        else:
            _p1, _p2 = None, None
        st.session_state[f"_wl_prev1_{wl_sync_key}"] = _p1
        st.session_state[f"_wl_prev2_{wl_sync_key}"] = _p2

    _prev_df1: pd.DataFrame | None = st.session_state.get(f"_wl_prev1_{wl_sync_key}")
    _prev_df2: pd.DataFrame | None = st.session_state.get(f"_wl_prev2_{wl_sync_key}")

    shift_start_time = _parse_time(selected_machine.get("shift_start_time")) or time(8, 0)
    shift_end_time   = _parse_time(selected_machine.get("shift_end_time"))   or time(20, 0)

    _no_of_days_raw = selected_machine.get("no_of_days")
    _no_of_days     = int(_no_of_days_raw) if _no_of_days_raw else None

    or1, or2, or3, _ = st.columns([1, 1, 1, 1])
    with or1:
        ot_rate_input = st.number_input(
            "OT Rate",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            help="Leave as 0 to auto-calculate (Rental ÷ Working hours)",
            key="wl_ot_rate",
        )
    with or2:
        deduction_input = st.number_input(
            "Deduction",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            help="Amount to subtract from Total Billing to get Adjusted Billing",
            key="wl_deduction",
        )
    with or3:
        working_days_input = st.number_input(
            "Working Days",
            min_value=1,
            max_value=100,
            value=_no_of_days if _no_of_days else 26,
            step=1,
            help="Defaults to No. of Days from Work Order. Edit here to override for this billing calculation.",
            key="wl_working_days",
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

    # ── Shift Schedule ─────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    base_key = (
        f"wl_{selected_wo_id}_{machine_idx}"
        f"_{selected_year}_{selected_month_num:02d}"
    )

    # Pre-select shift type from the saved DB record when the month/machine changes
    _stype_key = f"wl_stype_{selected_wo_id}_{machine_idx}"
    if st.session_state.get("_wl_stype_sync") != wl_sync_key:
        st.session_state["_wl_stype_sync"] = wl_sync_key
        if _wl_rec and _is_double_schedule(_wl_rec.get("schedule_data")):
            st.session_state[_stype_key] = "Double Shift"
        elif _stype_key not in st.session_state:
            st.session_state[_stype_key] = "Regular Shift"

    sc1, sc2 = st.columns([2, 4])
    with sc1:
        st.markdown('<p class="filter-label">Shift Schedule</p>', unsafe_allow_html=True)
        shift_type = st.selectbox(
            "Shift Type",
            options=["Regular Shift", "Double Shift"],
            key=_stype_key,
            label_visibility="collapsed",
        )
    is_double = shift_type == "Double Shift"

    # Load initial DFs from DB record (detect single vs double format)
    _db_df1: pd.DataFrame | None = None
    _db_df2: pd.DataFrame | None = None
    if _wl_rec and _wl_rec.get("schedule_data"):
        if _is_double_schedule(_wl_rec["schedule_data"]):
            _db_df1, _db_df2 = _json_to_double_dfs(_wl_rec["schedule_data"])
        else:
            _db_df1 = _json_to_schedule_df(_wl_rec["schedule_data"])

    def _get_initial(suffix: str, fallback: pd.DataFrame | None) -> pd.DataFrame:
        key = f"sched_data_{base_key}{suffix}"
        if key in st.session_state:
            return st.session_state[key]
        if fallback is not None:
            return fallback
        blank = _build_schedule(month_start, month_end)
        if _prev_df1 is not None:
            return _history_fill(blank, _prev_df1, shift_start_time, shift_end_time)
        return blank

    # ── Totals helper (defined before editors so it can be called inline) ────────
    _wd_display = str(int(working_days_input))

    def _show_totals(df: pd.DataFrame, label: str) -> None:
        _d = df.drop(columns=["Select", "Type", "📋", "📌"], errors="ignore")
        st.markdown(
            "<div style='border:1px solid #374151;border-radius:0 0 6px 6px;"
            "background:#1c1c2e;margin-top:-8px;overflow:hidden;'>"
            "<table style='width:100%;border-collapse:collapse;'><tbody><tr>"
            f"<td style='padding:8px 14px;border-right:1px solid #374151;'>"
            f"<div style='font-size:10px;font-weight:800;letter-spacing:.12em;"
            f"text-transform:uppercase;color:#fff;'>{label}</div></td>"
            + _totals_cell("Working Days", _wd_display)
            + _totals_cell("Net Time (hrs)", f"{float(_d['Net Time'].astype(float).fillna(0).sum()):.1f}")
            + _totals_cell("Shift OT (hrs)", f"{float(_d['OT'].astype(float).fillna(0).sum()):.1f}")
            + _totals_cell("Net HMR", f"{float(_d['Net HMR'].astype(float).fillna(0).sum()):.1f}")
            + _totals_cell("Breakdown (hrs)", f"{float(_d['Breakdown Hours'].astype(float).fillna(0).sum()):.1f}")
            + "<td style='padding:8px 14px;' colspan='2'></td>"
            "</tr></tbody></table></div>",
            unsafe_allow_html=True,
        )

    # ── Render editors — totals bar follows each table immediately ────────────
    if is_double:
        st.markdown(
            "<div style='font-size:13px;font-weight:700;color:#2563EB;"
            "margin:10px 0 4px;letter-spacing:.01em;'>Regular Shift</div>",
            unsafe_allow_html=True,
        )
    edited_s1 = _render_shift_editor(
        f"{base_key}_s1",
        _get_initial("_s1", _db_df1),
        shift_start_time, shift_end_time, operator_names,
    )
    if edited_s1 is not None and not edited_s1.empty:
        _show_totals(edited_s1, "REGULAR SHIFT" if is_double else "TOTAL")

    shift_start_time_s2 = shift_start_time
    shift_end_time_s2   = shift_end_time
    base_key_s2: str | None = None
    edited_s2 = None

    if is_double:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='font-size:13px;font-weight:700;color:#2563EB;"
            "margin:10px 0 4px;letter-spacing:.01em;'>Night Shift</div>",
            unsafe_allow_html=True,
        )
        shift_start_time_s2 = _parse_time(selected_machine.get("shift_start_time")) or time(8, 0)
        shift_end_time_s2   = _parse_time(selected_machine.get("shift_end_time"))   or time(20, 0)

        base_key_s2 = (
            f"wl_{selected_wo_id}_{machine_idx}"
            f"_{selected_year}_{selected_month_num:02d}_s2"
        )

        if f"sched_data_{base_key_s2}" in st.session_state:
            _initial_s2 = st.session_state[f"sched_data_{base_key_s2}"]
        elif _db_df2 is not None:
            _initial_s2 = _db_df2
        else:
            _blank_s2  = _build_schedule(month_start, month_end)
            _prev_s2   = _prev_df2 if _prev_df2 is not None else _prev_df1
            _initial_s2 = (
                _history_fill(_blank_s2, _prev_s2, shift_start_time_s2, shift_end_time_s2)
                if _prev_s2 is not None else _blank_s2
            )

        st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
        edited_s2 = _render_shift_editor(
            base_key_s2,
            _initial_s2,
            shift_start_time_s2, shift_end_time_s2, operator_names,
        )
        if edited_s2 is not None and not edited_s2.empty:
            _show_totals(edited_s2, "NIGHT SHIFT")

    # ── Billing Summary ────────────────────────────────────────────────────────
    _combined: pd.DataFrame | None = None
    if edited_s1 is not None and not edited_s1.empty:
        _combined = edited_s1
        if is_double and edited_s2 is not None and not edited_s2.empty:
            _combined = pd.concat([edited_s1, edited_s2], ignore_index=True)

    if _combined is not None:
        summary = _compute_billing_summary(
            _combined, rental_per_month, shift_start_time, shift_end_time,
            ot_rate_input=ot_rate_input,
            no_of_days=int(working_days_input),
            deduction=deduction_input,
        )
        if summary:
            st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
            _render_billing_summary(
                summary,
                wo_number=selected_wo.get("wo_number", ""),
                machine_label=selected_machine.get("machine_label", ""),
                month_label=selected_month_label,
            )

    # ── Action buttons ─────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    _btn_save, _btn_draft, _btn_discard = st.columns([3, 3, 2])

    _mlabel            = selected_machine.get("machine_label", f"Machine {machine_idx + 1}")
    _billing_month_str = f"{calendar.month_name[selected_month_num]} {selected_year}"

    def _finalize_df(df: pd.DataFrame | None) -> pd.DataFrame | None:
        if df is None or df.empty:
            return None
        out = df.drop(columns=["Select"], errors="ignore").copy()
        for idx, row in out.iterrows():
            st_ = row.get("Start Time")
            et_ = row.get("End Time")
            if st_ is not None and et_ is not None:
                out.at[idx, "Net Time"] = _net_hours(
                    st_ if isinstance(st_, time) else _parse_time(st_),
                    et_ if isinstance(et_, time) else _parse_time(et_),
                )
        return out

    def _make_schedule_json() -> str | None:
        df1 = _finalize_df(edited_s1)
        df2 = _finalize_df(edited_s2) if is_double else None
        if df1 is None:
            return None
        if is_double and df2 is not None:
            return _double_schedule_to_json(df1, df2)
        return _schedule_to_json(df1)

    def _clear_session() -> None:
        for sfx in ("_s1", "_s2", ""):
            st.session_state.pop(f"sched_data_{base_key}{sfx}", None)
        if base_key_s2:
            st.session_state.pop(f"sched_data_{base_key_s2}", None)

    # ── Save Draft ─────────────────────────────────────────────────────────────
    with _btn_draft:
        if st.button("📝 Save Draft", key="save_draft_btn", use_container_width=True):
            _sjson = _make_schedule_json()
            if _sjson:
                try:
                    sb.upsert_worklog(dict(
                        work_order_id=selected_wo_id,
                        machine_id=_mkey,
                        machine_label=_mlabel,
                        year=_billing_month_str,
                        ot_rate=ot_rate_input if ot_rate_input > 0 else 0.0,
                        deduction=deduction_input,
                        schedule_data=_sjson,
                        is_draft=True,
                    ))
                    _clear_session()
                    st.toast("Draft saved. Click Save Work Log to commit.", icon="📝")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save draft: {exc}")

    # ── Discard Draft ──────────────────────────────────────────────────────────
    with _btn_discard:
        if _is_db_draft:
            if st.button("Discard Draft", key="discard_draft_btn", use_container_width=True):
                try:
                    sb.delete_worklog(selected_wo_id, _mkey, _billing_month_str)
                except Exception:
                    pass
                _clear_session()
                st.rerun()

    # ── Save Work Log ──────────────────────────────────────────────────────────
    with _btn_save:
        if st.button("💾 Save Work Log", type="primary", key="save_worklog",
                     use_container_width=True):
            wl_payload = dict(
                work_order_id=selected_wo_id,
                machine_id=_mkey,
                machine_label=_mlabel,
                year=_billing_month_str,
                ot_rate=ot_rate_input if ot_rate_input > 0 else 0.0,
                deduction=deduction_input,
                schedule_data=_make_schedule_json(),
                is_draft=False,
            )
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
                _clear_session()
                st.success(f"✅ Work log for {selected_month_label} saved to database.")
            except Exception as exc:
                st.error(f"Could not save work log: {exc}")
