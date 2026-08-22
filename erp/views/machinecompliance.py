"""erp/views/machinecompliance.py — Machine Compliance tracker & CRUD module."""
from __future__ import annotations

import io
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from erp import auth
from erp.supabase_client import SupabaseClient
from erp.views._documents import render_document_panel

_WARN_DAYS = 30
_COMPLIANCE_TYPES = ["TPI", "PUC", "Form 11", "Insurance", "Other"]

# Maps new-table compliance_type → legacy machines-table column (fallback)
_LEGACY_COL = {
    "TPI":       "TPI_expiry",
    "PUC":       "PUC_expiry",
    "Form 11":   "Form_11_expiry",
    "Insurance": "insurance_expiry",
}


# ── Operational status badge ───────────────────────────────────────────────────

_OP_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "On Rent":    ("#DCFCE7", "#166534"),
    "Available":  ("#DBEAFE", "#1E40AF"),
    "Reserved":   ("#FEF3C7", "#92400E"),
    "Breakdown":  ("#FEE2E2", "#991B1B"),
    "Idle":       ("#F1F5F9", "#6B7280"),
    "In Transit": ("#FFEDD5", "#C2410C"),
    "Sold":       ("#F3F4F6", "#374151"),
}


def _op_status_chip(status: str | None) -> str:
    label = status or "Unknown"
    bg, fg = _OP_STATUS_COLORS.get(label, ("#F1F5F9", "#6B7280"))
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;border-radius:12px;"
        f"font-size:11px;font-weight:700;white-space:nowrap;'>{label}</span>"
    )


# ── Status helpers ─────────────────────────────────────────────────────────────

def _status(expiry_val) -> tuple[str, str, str]:
    """Return (label, bg_color, text_color) for an expiry date value."""
    if not expiry_val:
        return "Not Set", "#F1F5F9", "#9CA3AF"
    try:
        exp = date.fromisoformat(str(expiry_val)[:10])
    except Exception:
        return "Invalid", "#F1F5F9", "#9CA3AF"
    today = date.today()
    if exp < today:
        return "Overdue", "#FEE2E2", "#991B1B"
    if exp <= today + timedelta(days=_WARN_DAYS):
        return "Expiring Soon", "#FEF3C7", "#92400E"
    return "Valid", "#DCFCE7", "#166534"


def _status_chip(label: str, bg: str, fg: str) -> str:
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;border-radius:12px;"
        f"font-size:11px;font-weight:700;white-space:nowrap;'>{label}</span>"
    )


def _worst_status(expiry_dates: list) -> tuple[str, str, str]:
    statuses = [_status(v) for v in expiry_dates]
    for target in ("Overdue", "Expiring Soon", "Valid"):
        for s in statuses:
            if s[0] == target:
                return s
    return "Not Set", "#F1F5F9", "#9CA3AF"


# ── Build per-machine expiry lookup from compliance_records ───────────────────

def _latest_by_type(records: list[dict]) -> dict[str, dict]:
    """Return {compliance_type: latest_record} keeping highest expiry_date."""
    result: dict[str, dict] = {}
    for rec in records:
        ctype = rec.get("compliance_type", "")
        if ctype == "Other":
            ctype = rec.get("custom_type") or "Other"
        existing = result.get(ctype)
        if not existing or (rec.get("expiry_date") or "") >= (existing.get("expiry_date") or ""):
            result[ctype] = rec
    return result


def _machine_expiry(machine: dict, latest: dict[str, dict], ctype: str) -> str | None:
    """Get expiry date for a compliance type: new table first, then legacy column."""
    rec = latest.get(ctype)
    if rec:
        return rec.get("expiry_date")
    legacy_col = _LEGACY_COL.get(ctype)
    if legacy_col:
        return machine.get(legacy_col)
    return None


# ── Export helpers ────────────────────────────────────────────────────────────

_TYPES_EXPORT = ["TPI", "PUC", "Form 11", "Insurance"]
_STATUS_COLORS = {
    "Overdue":       ("#FEE2E2", "#991B1B"),
    "Expiring Soon": ("#FEF3C7", "#92400E"),
    "Valid":         ("#DCFCE7", "#166534"),
    "Not Set":       ("#F1F5F9", "#9CA3AF"),
    "Invalid":       ("#F1F5F9", "#9CA3AF"),
}


def _build_export_df(machines: list[dict], records_by_machine: dict) -> pd.DataFrame:
    rows = []
    for m in machines:
        mid    = str(m.get("id", ""))
        latest = _latest_by_type(records_by_machine.get(mid, []))

        def _exp(ct: str) -> str:
            v = _machine_expiry(m, latest, ct)
            return str(v) if v else ""

        def _st(ct: str) -> str:
            return _status(_machine_expiry(m, latest, ct))[0]

        exps = [_machine_expiry(m, latest, ct) for ct in _TYPES_EXPORT]
        rows.append({
            "Asset Code":         m.get("asset_code", ""),
            "Machine Type":       m.get("machine_type", ""),
            "Make":               m.get("make", ""),
            "Model":              m.get("model", ""),
            "Serial Number":      m.get("serial_number", ""),
            "Operational Status": m.get("operational_status", ""),
            "TPI Expiry":         _exp("TPI"),
            "TPI Status":         _st("TPI"),
            "PUC Expiry":         _exp("PUC"),
            "PUC Status":         _st("PUC"),
            "Form 11 Expiry":     _exp("Form 11"),
            "Form 11 Status":     _st("Form 11"),
            "Insurance Expiry":   _exp("Insurance"),
            "Insurance Status":   _st("Insurance"),
            "Overall Status":     _worst_status(exps)[0],
        })
    return pd.DataFrame(rows)


def _build_pdf_html(machines: list[dict], records_by_machine: dict, today: date) -> str:
    def _get_exp(m: dict, ct: str):
        mid    = str(m.get("id", ""))
        latest = _latest_by_type(records_by_machine.get(mid, []))
        return _machine_expiry(m, latest, ct)

    def _fmt(val) -> str:
        if not val:
            return "—"
        try:
            return date.fromisoformat(str(val)[:10]).strftime("%d %b %Y")
        except Exception:
            return str(val)

    rows_html = ""
    for m in machines:
        exps       = [_get_exp(m, ct) for ct in _TYPES_EXPORT]
        wlbl       = _worst_status(exps)[0]
        wbg, wfg   = _STATUS_COLORS.get(wlbl, ("#F1F5F9", "#9CA3AF"))
        serial     = m.get("serial_number") or "—"
        make_model = f"{m.get('make','') or ''} {m.get('model','') or ''}".strip() or "—"

        cells = ""
        for ct in _TYPES_EXPORT:
            v          = _get_exp(m, ct)
            lbl        = _status(v)[0]
            sbg, sfg   = _STATUS_COLORS.get(lbl, ("#F1F5F9", "#9CA3AF"))
            cells += (
                f"<td style='background:{sbg};color:{sfg};text-align:center;"
                f"font-size:11px;font-weight:600;'>{_fmt(v)}</td>"
            )

        op_status  = m.get("operational_status") or "—"
        opbg, opfg = _OP_STATUS_COLORS.get(op_status, ("#F1F5F9", "#6B7280"))
        rows_html += (
            f"<tr>"
            f"<td><strong>{m.get('asset_code','—')}</strong>"
            f"<br><span style='color:#666;font-size:11px;'>{m.get('machine_type','')}</span></td>"
            f"<td>{make_model}"
            f"<br><span style='color:#666;font-size:11px;'>S/N: {serial}</span></td>"
            f"<td style='background:{opbg};color:{opfg};text-align:center;"
            f"font-size:11px;font-weight:600;'>{op_status}</td>"
            f"<td style='background:{wbg};color:{wfg};text-align:center;"
            f"font-size:11px;font-weight:700;'>{wlbl}</td>"
            f"{cells}</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Machine Compliance Report — {today.strftime('%d %b %Y')}</title>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 24px; color: #111; }}
  h1   {{ font-size: 20px; font-weight: 800; margin: 0 0 4px; color: #1E3A5F; }}
  .sub {{ font-size: 12px; color: #6B7280; margin-bottom: 24px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ background: #1E3A5F; color: #fff; padding: 9px 11px; text-align: left;
        font-size: 10px; letter-spacing: .1em; text-transform: uppercase; }}
  td {{ padding: 8px 11px; border-bottom: 1px solid #E2EBF0; vertical-align: middle; }}
  tr:nth-child(even) td {{ background: #FAFBFC; }}
  @media print {{
    body {{ margin: 0; }}
    h1   {{ color: #000; }}
  }}
</style>
</head>
<body>
<h1>Machine Compliance Report</h1>
<div class="sub">Generated: {today.strftime('%d %b %Y')} &nbsp;&middot;&nbsp; {len(machines)} machines</div>
<table>
<thead><tr>
  <th>Asset / Type</th>
  <th>Make / Model / S/N</th>
  <th>Op. Status</th>
  <th>Overall</th>
  {"".join(f"<th>{ct}</th>" for ct in _TYPES_EXPORT)}
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<script>window.onload = function() {{ window.print(); }};</script>
</body>
</html>"""


# ── Section header ─────────────────────────────────────────────────────────────

def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:6px;margin-bottom:10px;'>"
        f"<span class='msr' style='font-size:16px;color:#2563EB;'>{icon}</span>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:.12em;"
        f"text-transform:uppercase;color:#6B7280;'>{label}</span></div>",
        unsafe_allow_html=True,
    )


# ── Overview tab ───────────────────────────────────────────────────────────────

def _render_overview(
    machines: list[dict],
    all_records: list[dict],
    machine_deploy: dict[str, tuple[str, str]],
) -> None:
    today = date.today()

    # Build per-machine latest map
    records_by_machine: dict[str, list] = {}
    for rec in all_records:
        mid = str(rec.get("machine_id", ""))
        records_by_machine.setdefault(mid, []).append(rec)

    def _get_exp(m: dict, ctype: str) -> str | None:
        mid = str(m.get("id", ""))
        latest = _latest_by_type(records_by_machine.get(mid, []))
        return _machine_expiry(m, latest, ctype)

    # KPI strip
    n_total    = len(machines)
    n_overdue  = 0
    n_expiring = 0
    n_valid    = 0
    for m in machines:
        exps = [_get_exp(m, ct) for ct in ["TPI", "PUC", "Form 11", "Insurance"]]
        lbl = _worst_status(exps)[0]
        if lbl == "Overdue":       n_overdue  += 1
        elif lbl == "Expiring Soon": n_expiring += 1
        elif lbl == "Valid":         n_valid    += 1

    k1, k2, k3, k4 = st.columns(4)
    for col, val, lbl, color in [
        (k1, n_total,    "Total Machines",   "#2563EB"),
        (k2, n_valid,    "Fully Compliant",  "#16A344"),
        (k3, n_expiring, "Expiring Soon",    "#F59E0B"),
        (k4, n_overdue,  "Overdue",          "#DC2626"),
    ]:
        with col:
            st.markdown(
                f"<div style='background:#fff;border:1px solid #E2EBF0;border-radius:10px;"
                f"padding:18px 20px;border-top:3px solid {color};'>"
                f"<div style='font-size:10px;font-weight:700;letter-spacing:.13em;"
                f"text-transform:uppercase;color:#9CA3AF;margin-bottom:6px;'>{lbl}</div>"
                f"<div style='font-size:36px;font-weight:800;color:#111827;'>{val}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

    # Filters
    fc1, fc2, fc3, _ = st.columns([2, 2, 2, 2])
    with fc1:
        filter_status = st.multiselect(
            "Compliance Status", ["Overdue", "Expiring Soon", "Valid", "Not Set"],
            key="ov_filter_status", placeholder="All",
        )
    with fc2:
        machine_types = sorted({m.get("machine_type", "") for m in machines if m.get("machine_type")})
        filter_type = st.multiselect("Machine Type", machine_types, key="ov_filter_type", placeholder="All")
    with fc3:
        op_statuses = sorted({m.get("operational_status", "") for m in machines if m.get("operational_status")})
        filter_op_status = st.multiselect("Op. Status", op_statuses, key="ov_filter_op_status", placeholder="All")

    _TYPES_OVERVIEW = ["TPI", "PUC", "Form 11", "Insurance"]

    def _row_worst(m: dict) -> tuple[str, str, str]:
        exps = [_get_exp(m, ct) for ct in _TYPES_OVERVIEW]
        return _worst_status(exps)

    filtered = [m for m in machines if m.get("is_active", True)]
    if filter_status:
        filtered = [m for m in filtered if _row_worst(m)[0] in filter_status]
    if filter_type:
        filtered = [m for m in filtered if m.get("machine_type") in filter_type]
    if filter_op_status:
        filtered = [m for m in filtered if m.get("operational_status") in filter_op_status]
    _order = {"Overdue": 0, "Expiring Soon": 1, "Valid": 2, "Not Set": 3}
    filtered.sort(key=lambda m: _order.get(_row_worst(m)[0], 4))

    # ── Sort controls ─────────────────────────────────────────────────────────
    _MC_SORT_COLS = ["Compliance Status", "Asset Code", "Machine Type", "Make", "Model"]
    _mc1, _mc2, _ = st.columns([2, 1, 5])
    with _mc1:
        _mc_col = st.selectbox("Sort by", _MC_SORT_COLS, key="mc_sort_col")
    with _mc2:
        _mc_dir = st.selectbox("Order", ["↑ Asc", "↓ Desc"], key="mc_sort_dir",
                               label_visibility="collapsed")
    _MC_SORT_MAP = {
        "Compliance Status": lambda m: _order.get(_row_worst(m)[0], 4),
        "Asset Code":        lambda m: (m.get("asset_code") or "").lower(),
        "Machine Type":      lambda m: (m.get("machine_type") or "").lower(),
        "Make":              lambda m: (m.get("make") or "").lower(),
        "Model":             lambda m: (m.get("model") or "").lower(),
    }
    filtered.sort(key=_MC_SORT_MAP[_mc_col], reverse=(_mc_dir == "↓ Desc"))

    # ── Export buttons ─────────────────────────────────────────────────────────
    ex1, ex2, _ = st.columns([1, 1, 6])

    with ex1:
        export_df = _build_export_df(filtered, records_by_machine)
        buf = io.BytesIO()
        export_df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        st.download_button(
            label="Export Excel",
            data=buf,
            file_name=f"compliance_{today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="comp_export_xlsx",
            use_container_width=True,
        )

    with ex2:
        pdf_html = _build_pdf_html(filtered, records_by_machine, today)
        st.download_button(
            label="Export PDF",
            data=pdf_html.encode("utf-8"),
            file_name=f"compliance_{today}.html",
            mime="text/html",
            key="comp_export_pdf",
            use_container_width=True,
            help="Downloads an HTML file — open it in a browser and Print → Save as PDF",
        )

    st.markdown(
        f"<div style='font-size:12px;color:#6B7280;margin:8px 0 10px;'>"
        f"Showing <b>{len(filtered)}</b> of {n_total} machines</div>",
        unsafe_allow_html=True,
    )

    if not filtered:
        st.info("No machines match the selected filters.")
        return

    def _exp_cell(exp_val) -> str:
        if not exp_val:
            return "<td style='padding:8px 12px;color:#9CA3AF;font-size:12px;'>—</td>"
        try:
            d = date.fromisoformat(str(exp_val)[:10])
            lbl, bg, fg = _status(exp_val)
            return (
                f"<td style='padding:8px 12px;'>"
                f"<span style='background:{bg};color:{fg};padding:2px 8px;"
                f"border-radius:12px;font-size:11px;font-weight:700;white-space:nowrap;'>"
                f"{d.strftime('%d %b %Y')}</span></td>"
            )
        except Exception:
            return f"<td style='padding:8px 12px;font-size:12px;'>{exp_val}</td>"

    hs = ("padding:10px 12px;background:#F8FAFC;font-size:10px;font-weight:700;"
          "letter-spacing:.12em;text-transform:uppercase;color:#6B7280;"
          "border-bottom:2px solid #E2EBF0;white-space:nowrap;")
    rows_html = ""
    for i, m in enumerate(filtered):
        bg_row  = "#FFFFFF" if i % 2 == 0 else "#FAFBFC"
        wlbl, wbg, wfg = _row_worst(m)
        serial_no  = m.get("serial_number") or "—"
        make_model = f"{m.get('make','') or ''} {m.get('model','') or ''}".strip() or "—"
        client_name, site_name = machine_deploy.get(str(m.get("id") or ""), ("—", "—"))
        op_status  = m.get("operational_status") or "—"
        rows_html += (
            f"<tr style='background:{bg_row};border-bottom:1px solid #F1F5F9;'>"
            f"<td style='padding:8px 12px;'>"
            f"<div style='font-weight:600;color:#111827;font-size:12px;'>{m.get('asset_code','—')}</div>"
            f"<div style='font-size:11px;color:#6B7280;'>{m.get('machine_type','—')}</div></td>"
            f"<td style='padding:8px 12px;'>"
            f"<div style='font-size:12px;color:#374151;'>{make_model}</div>"
            f"<div style='font-size:11px;color:#9CA3AF;margin-top:1px;'>S/N: {serial_no}</div></td>"
            f"<td style='padding:8px 12px;'>"
            f"<div style='font-size:12px;color:#374151;'>{client_name}</div>"
            f"<div style='font-size:11px;color:#9CA3AF;margin-top:1px;'>{site_name}</div></td>"
            f"<td style='padding:8px 12px;'>{_op_status_chip(op_status)}</td>"
            f"<td style='padding:8px 12px;'>{_status_chip(wlbl,wbg,wfg)}</td>"
            + "".join(_exp_cell(_get_exp(m, ct)) for ct in _TYPES_OVERVIEW)
            + "</tr>"
        )

    table_html = (
        "<div style='overflow-x:auto;border:1px solid #E2EBF0;border-radius:10px;"
        "box-shadow:0 1px 3px rgba(0,0,0,.05);'>"
        "<table style='width:100%;border-collapse:collapse;font-family:inherit;'>"
        "<thead><tr>"
        f"<th style='{hs}border-radius:10px 0 0 0;'>Asset / Type</th>"
        f"<th style='{hs}'>Make / Model / S/N</th>"
        f"<th style='{hs}'>Client / Site</th>"
        f"<th style='{hs}'>Op. Status</th>"
        f"<th style='{hs}'>Overall</th>"
        + "".join(f"<th style='{hs}'>{ct}</th>" for ct in _TYPES_OVERVIEW)
        + "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown(
        "<div style='display:flex;gap:18px;margin-top:12px;font-size:11px;color:#6B7280;'>"
        "<span><span style='background:#FEE2E2;color:#991B1B;padding:1px 8px;"
        "border-radius:10px;font-weight:700;'>Overdue</span> expired</span>"
        "<span><span style='background:#FEF3C7;color:#92400E;padding:1px 8px;"
        "border-radius:10px;font-weight:700;'>Expiring Soon</span> within 30 days</span>"
        "<span><span style='background:#DCFCE7;color:#166534;padding:1px 8px;"
        "border-radius:10px;font-weight:700;'>Valid</span> > 30 days</span>"
        "<span>— = not set</span>"
        "</div>",
        unsafe_allow_html=True,
    )


# ── Records tab ────────────────────────────────────────────────────────────────

def _render_records(sb: SupabaseClient, machines: list[dict]) -> None:
    machine_map = {m.get("id"): m for m in machines if m.get("id")}
    active_machines = [m for m in machines if m.get("is_active", True)]

    left_col, right_col = st.columns([4, 7], gap="large")

    # ── LEFT — Machine selector ────────────────────────────────────────────────
    with left_col:
        st.markdown(
            "<div style='font-size:11px;font-weight:700;letter-spacing:.12em;"
            "text-transform:uppercase;color:#6B7280;margin-bottom:8px;'>"
            "Select Machine</div>",
            unsafe_allow_html=True,
        )
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search asset code or type…",
            key="comp_rec_search",
        )
        q = search_q.strip().lower()
        filtered_machines = [
            m for m in active_machines
            if not q
            or q in (m.get("asset_code") or "").lower()
            or q in (m.get("machine_type") or "").lower()
            or q in (m.get("make") or "").lower()
        ]

        sel_machine_id = st.session_state.get("_comp_sel_machine_id", "")

        with st.container(height=520):
            for m in sorted(filtered_machines, key=lambda x: x.get("asset_code") or ""):
                mid        = m.get("id", "")
                code       = m.get("asset_code", "—")
                mtype      = m.get("machine_type", "")
                make_val   = (m.get("make")          or "").strip()
                model_val  = (m.get("model")         or "").strip()
                serial_val = m.get("serial_number")  or "—"
                make_model = f"{make_val} {model_val}".strip() or "—"
                is_sel    = mid == sel_machine_id
                bg        = "#EFF6FF" if is_sel else "#FFFFFF"
                border    = "2px solid #2563EB" if is_sel else "1px solid #E2E8F0"
                if st.button(
                    f"**{code}** — {mtype}  \n{make_model}  ·  S/N: {serial_val}",
                    key=f"comp_msel_{mid}",
                    use_container_width=True,
                ):
                    st.session_state["_comp_sel_machine_id"] = mid
                    st.session_state["_comp_rec_mode"]       = "list"
                    st.rerun()

    # ── RIGHT — Records panel ──────────────────────────────────────────────────
    with right_col:
        sel_machine_id = st.session_state.get("_comp_sel_machine_id", "")
        selected_machine = machine_map.get(sel_machine_id)

        if not selected_machine:
            st.markdown(
                "<div style='text-align:center;padding:60px 0;color:#9CA3AF;'>"
                "<div style='font-size:36px;margin-bottom:12px;'>📋</div>"
                "<div style='font-size:14px;'>Select a machine to view compliance records</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        sm       = selected_machine
        code_disp = sm.get("asset_code", "")
        mtype_disp = sm.get("machine_type", "")
        make_disp  = f"{sm.get('make','') or ''} {sm.get('model','') or ''}".strip()

        # Hero banner
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#1E3A5F,#2563EB);border-radius:12px;"
            f"padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;gap:16px;'>"
            f"<div style='background:rgba(255,255,255,.15);border-radius:10px;padding:10px;"
            f"display:flex;align-items:center;justify-content:center;'>"
            f"<span class='msr' style='font-size:28px;color:#fff;'>construction</span></div>"
            f"<div>"
            f"<div style='font-size:18px;font-weight:800;color:#fff;'>{code_disp}</div>"
            f"<div style='font-size:12px;color:rgba(255,255,255,.75);margin-top:2px;'>"
            f"{mtype_disp} &nbsp;·&nbsp; {make_disp}</div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        # Load records for this machine
        try:
            records = sb.list_compliance_records(machine_id=sel_machine_id)
        except Exception as exc:
            st.error(f"Could not load compliance records: {exc}")
            records = []

        # ── Existing records table ─────────────────────────────────────────────
        _section_hdr("verified_user", f"Compliance Records ({len(records)})")

        rec_mode = st.session_state.get("_comp_rec_mode", "list")
        edit_rec_id = st.session_state.get("_comp_edit_rec_id", "")

        if records:
            hs = ("padding:8px 10px;background:#F8FAFC;font-size:10px;font-weight:700;"
                  "letter-spacing:.1em;text-transform:uppercase;color:#6B7280;"
                  "border-bottom:2px solid #E2EBF0;")
            rows_html = ""
            for i, rec in enumerate(records):
                bg_row = "#FFFFFF" if i % 2 == 0 else "#FAFBFC"
                ctype  = rec.get("compliance_type", "")
                if ctype == "Other" and rec.get("custom_type"):
                    ctype = rec["custom_type"]
                issue  = rec.get("issue_date") or "—"
                expiry = rec.get("expiry_date")
                lbl, bg, fg = _status(expiry)
                exp_disp = (
                    f"<span style='background:{bg};color:{fg};padding:2px 7px;"
                    f"border-radius:10px;font-size:11px;font-weight:700;'>"
                    + (date.fromisoformat(str(expiry)[:10]).strftime("%d %b %Y") if expiry else "—")
                    + "</span>"
                )
                rows_html += (
                    f"<tr style='background:{bg_row};border-bottom:1px solid #F1F5F9;'>"
                    f"<td style='padding:8px 10px;font-size:12px;font-weight:600;"
                    f"color:#111827;'>{ctype}</td>"
                    f"<td style='padding:8px 10px;font-size:12px;color:#374151;'>{issue}</td>"
                    f"<td style='padding:8px 10px;'>{exp_disp}</td>"
                    f"<td style='padding:8px 10px;font-size:11px;color:#6B7280;max-width:160px;"
                    f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>"
                    f"{rec.get('remarks') or ''}</td>"
                    f"</tr>"
                )
            st.markdown(
                "<div style='overflow-x:auto;border:1px solid #E2EBF0;border-radius:8px;"
                "margin-bottom:16px;'>"
                "<table style='width:100%;border-collapse:collapse;font-family:inherit;'>"
                "<thead><tr>"
                f"<th style='{hs}'>Type</th>"
                f"<th style='{hs}'>Issue Date</th>"
                f"<th style='{hs}'>Expiry Date</th>"
                f"<th style='{hs}'>Remarks</th>"
                f"</tr></thead><tbody>{rows_html}</tbody></table></div>",
                unsafe_allow_html=True,
            )

            # Per-record edit/deactivate buttons
            with st.expander("Edit / Remove a Record"):
                rec_labels = {
                    r.get("id"): (
                        (r.get("compliance_type") if r.get("compliance_type") != "Other"
                         else r.get("custom_type") or "Other")
                        + (f" — expires {r.get('expiry_date')}" if r.get("expiry_date") else "")
                    )
                    for r in records
                }
                chosen_id = st.selectbox(
                    "Select record",
                    options=list(rec_labels),
                    format_func=lambda rid: rec_labels.get(rid, rid),
                    key="comp_chosen_rec_id",
                )
                ea, eb = st.columns(2)
                with ea:
                    if st.button("✏️ Edit this record", use_container_width=True,
                                 key="comp_edit_rec_btn"):
                        st.session_state["_comp_rec_mode"]   = "edit"
                        st.session_state["_comp_edit_rec_id"] = chosen_id
                        st.rerun()
                with eb:
                    if auth.is_admin():
                        if st.button("🗑️ Remove this record", use_container_width=True,
                                     key="comp_del_rec_btn", type="secondary"):
                            try:
                                sb.deactivate_compliance_record(chosen_id)
                                st.toast("Record removed.", icon="🗑️")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not remove: {exc}")
        else:
            st.info("No compliance records yet for this machine. Add one below.")

        st.markdown("---")

        # ── Add / Edit form ────────────────────────────────────────────────────
        if rec_mode == "edit" and edit_rec_id:
            edit_rec = next((r for r in records if r.get("id") == edit_rec_id), None)
            if edit_rec:
                _section_hdr("edit", "Edit Compliance Record")
            else:
                rec_mode = "add"
                st.session_state["_comp_rec_mode"] = "add"
        else:
            edit_rec = None
            _section_hdr("add_circle", "Add New Compliance Record")

        with st.container(border=True):
            f1, f2 = st.columns(2)
            with f1:
                ctype_val = st.selectbox(
                    "Compliance Type *",
                    options=_COMPLIANCE_TYPES,
                    index=_COMPLIANCE_TYPES.index(edit_rec.get("compliance_type", "TPI"))
                          if edit_rec and edit_rec.get("compliance_type") in _COMPLIANCE_TYPES else 0,
                    key="comp_form_type",
                )
            with f2:
                custom_type_val = ""
                if ctype_val == "Other":
                    custom_type_val = st.text_input(
                        "Specify Type *",
                        value=edit_rec.get("custom_type", "") if edit_rec else "",
                        key="comp_form_custom",
                        placeholder="e.g. Road Permit",
                    )

            d1, d2 = st.columns(2)
            with d1:
                issue_date_val = st.date_input(
                    "Issue Date",
                    value=date.fromisoformat(str(edit_rec["issue_date"])[:10])
                          if edit_rec and edit_rec.get("issue_date") else None,
                    key="comp_form_issue",
                )
            with d2:
                expiry_date_val = st.date_input(
                    "Expiry Date *",
                    value=date.fromisoformat(str(edit_rec["expiry_date"])[:10])
                          if edit_rec and edit_rec.get("expiry_date") else None,
                    key="comp_form_expiry",
                )

            doc_url_val = st.text_input(
                "Document URL",
                value=edit_rec.get("document_url", "") if edit_rec else "",
                key="comp_form_doc_url",
                placeholder="https://… (paste link to scanned document)",
            )
            remarks_val = st.text_area(
                "Remarks",
                value=edit_rec.get("remarks", "") if edit_rec else "",
                key="comp_form_remarks",
                height=68,
                placeholder="Any notes about this document…",
            )

            ba, bb = st.columns(2)
            with ba:
                save_lbl = "💾 Update Record" if rec_mode == "edit" else "💾 Save Record"
                if st.button(save_lbl, type="primary", use_container_width=True,
                             key="comp_save_rec_btn"):
                    if ctype_val == "Other" and not custom_type_val.strip():
                        st.error("Please specify the compliance type name.")
                    elif not expiry_date_val:
                        st.error("Expiry Date is required.")
                    else:
                        payload = dict(
                            machine_id      = sel_machine_id,
                            compliance_type = ctype_val,
                            custom_type     = custom_type_val.strip() or None,
                            issue_date      = issue_date_val.isoformat() if issue_date_val else None,
                            expiry_date     = expiry_date_val.isoformat(),
                            document_url    = doc_url_val.strip() or None,
                            remarks         = remarks_val.strip() or None,
                        )
                        try:
                            if rec_mode == "edit" and edit_rec_id:
                                sb.update_compliance_record(edit_rec_id, payload)
                                st.toast("Record updated.", icon="✅")
                            else:
                                sb.insert_compliance_record(payload)
                                st.toast("Record saved.", icon="✅")
                            st.session_state["_comp_rec_mode"]    = "list"
                            st.session_state["_comp_edit_rec_id"] = ""
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not save: {exc}")
            with bb:
                if rec_mode == "edit":
                    if st.button("Cancel", use_container_width=True, key="comp_cancel_edit"):
                        st.session_state["_comp_rec_mode"]    = "list"
                        st.session_state["_comp_edit_rec_id"] = ""
                        st.rerun()


# ── Main render ────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        "<div class='page-eyebrow'>// Masters</div>"
        "<div class='page-title'>Machine Compliance</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    try:
        sb       = SupabaseClient()
        machines = sb.list_machines()
    except Exception as exc:
        st.error(f"Failed to load machines: {exc}")
        return

    try:
        all_records = sb.list_compliance_records()
    except Exception:
        all_records = []

    # Build machine_id → (customer_name, site_name) from active work orders
    try:
        work_orders    = sb.list_work_orders()
        customers_list = sb.list_customers()
        sites_list     = sb.list_sites()
    except Exception:
        work_orders, customers_list, sites_list = [], [], []

    cust_map = {c["id"]: c.get("customer_name", "—") for c in customers_list if c.get("id")}
    site_map = {s["id"]: s.get("site_name",     "—") for s in sites_list     if s.get("id")}

    today = date.today()

    def _sd(wo):
        try:
            return date.fromisoformat(str(wo["start_date"])[:10]) if wo.get("start_date") else None
        except Exception:
            return None

    def _ed(wo):
        try:
            return date.fromisoformat(str(wo["end_date"])[:10]) if wo.get("end_date") else None
        except Exception:
            return None

    def _add_wo_machines(wo, deploy: dict) -> None:
        cname  = cust_map.get(wo.get("customer_id", ""), "—")
        sname  = site_map.get(wo.get("site_id",     ""), "—")
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            return
        try:
            recs = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            if isinstance(recs, list):
                for r in recs:
                    mid = str(r.get("machine_id") or "")
                    if mid and mid not in deploy:
                        deploy[mid] = (cname, sname)
        except Exception:
            pass

    machine_deploy: dict[str, tuple[str, str]] = {}

    # Pass 1 — currently active WOs (preferred)
    for wo in work_orders:
        sd, ed = _sd(wo), _ed(wo)
        if sd is None or sd > today:
            continue
        if ed is not None and ed < today:
            continue
        _add_wo_machines(wo, machine_deploy)

    # Pass 2 — most-recent WO for machines not yet found (handles ended/idle machines)
    sorted_wos = sorted(
        work_orders,
        key=lambda w: _sd(w) or date.min,
        reverse=True,
    )
    for wo in sorted_wos:
        _add_wo_machines(wo, machine_deploy)

    tab_overview, tab_records, tab_docs = st.tabs([
        "📊 Compliance Overview",
        "📋 Manage Records",
        "📎 Documents",
    ])

    with tab_overview:
        _render_overview(machines, all_records, machine_deploy)

    with tab_records:
        _render_records(sb, machines)

    with tab_docs:
        sel_machine_id = st.session_state.get("_comp_sel_machine_id", "")
        if sel_machine_id:
            render_document_panel(
                sb,
                record_type = "compliance",
                record_id   = sel_machine_id,
                key_prefix  = "comp",
            )
        else:
            st.info("Select a machine from the Manage Records tab to view or attach documents.", icon="ℹ️")
