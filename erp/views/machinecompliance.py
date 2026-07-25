"""erp/views/machinecompliance.py — Machine Compliance tracker."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from erp.supabase_client import SupabaseClient

_WARN_DAYS = 30   # days before expiry to show "Expiring Soon"

_CERT_FIELDS = [
    ("TPI_expiry",      "TPI"),
    ("PUC_expiry",      "PUC"),
    ("Form_11_expiry",  "Form 11"),
    ("insurance_expiry","Insurance"),
]


def _status(expiry_val) -> tuple[str, str, str]:
    """Return (status_label, bg_color, text_color) for a date value."""
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


def _cell(val) -> str:
    """Return HTML table cell for an expiry date."""
    if not val:
        return "<td style='padding:8px 12px;color:#9CA3AF;font-size:12px;'>—</td>"
    try:
        exp     = date.fromisoformat(str(val)[:10])
        lbl, bg, fg = _status(val)
        disp    = exp.strftime("%d %b %Y")
        return (
            f"<td style='padding:8px 12px;'>"
            f"<span style='background:{bg};color:{fg};padding:2px 8px;border-radius:12px;"
            f"font-size:11px;font-weight:700;white-space:nowrap;'>{disp}</span></td>"
        )
    except Exception:
        return f"<td style='padding:8px 12px;font-size:12px;'>{val}</td>"


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

    # ── Filter out inactive if column exists ──────────────────────────────────
    machines = [m for m in machines if m.get("is_active", True)]

    today = date.today()

    def _worst(m: dict) -> str:
        """Return worst compliance status across all certs for a machine."""
        vals = [m.get(f) for f, _ in _CERT_FIELDS]
        statuses = [_status(v)[0] for v in vals]
        if "Overdue"      in statuses: return "Overdue"
        if "Expiring Soon" in statuses: return "Expiring Soon"
        if "Valid"         in statuses: return "Valid"
        return "Not Set"

    # ── KPI strip ─────────────────────────────────────────────────────────────
    n_total    = len(machines)
    n_overdue  = sum(1 for m in machines if _worst(m) == "Overdue")
    n_expiring = sum(1 for m in machines if _worst(m) == "Expiring Soon")
    n_valid    = sum(1 for m in machines if _worst(m) == "Valid")

    k1, k2, k3, k4 = st.columns(4)
    for col, val, lbl, color in [
        (k1, n_total,    "Total Machines",  "#2563EB"),
        (k2, n_valid,    "Fully Compliant", "#16A344"),
        (k3, n_expiring, "Expiring Soon",   "#F59E0B"),
        (k4, n_overdue,  "Overdue",         "#DC2626"),
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

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    # ── Filters ───────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([2, 2, 4])
    with fc1:
        filter_status = st.selectbox(
            "Compliance Status",
            ["All", "Overdue", "Expiring Soon", "Valid", "Not Set"],
            key="comp_filter_status",
        )
    with fc2:
        machine_types = sorted({m.get("machine_type", "") for m in machines if m.get("machine_type")})
        filter_type = st.selectbox(
            "Machine Type",
            ["All"] + machine_types,
            key="comp_filter_type",
        )

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = machines
    if filter_status != "All":
        filtered = [m for m in filtered if _worst(m) == filter_status]
    if filter_type != "All":
        filtered = [m for m in filtered if m.get("machine_type") == filter_type]

    # Sort: Overdue first, then Expiring Soon, then Valid, then Not Set
    _order = {"Overdue": 0, "Expiring Soon": 1, "Valid": 2, "Not Set": 3}
    filtered.sort(key=lambda m: _order.get(_worst(m), 4))

    st.markdown(
        f"<div style='font-size:12px;color:#6B7280;margin-bottom:10px;'>"
        f"Showing <b>{len(filtered)}</b> of {n_total} machines</div>",
        unsafe_allow_html=True,
    )

    if not filtered:
        st.info("No machines match the selected filters.")
        return

    # ── Compliance table ──────────────────────────────────────────────────────
    header_style = (
        "padding:10px 12px;background:#F8FAFC;font-size:10px;font-weight:700;"
        "letter-spacing:.12em;text-transform:uppercase;color:#6B7280;"
        "border-bottom:2px solid #E2EBF0;white-space:nowrap;"
    )
    rows_html = ""
    for i, m in enumerate(filtered):
        bg_row   = "#FFFFFF" if i % 2 == 0 else "#FAFBFC"
        worst    = _worst(m)
        row_left = (
            f"<td style='padding:8px 12px;font-size:12px;'>"
            f"<div style='font-weight:600;color:#111827;'>{m.get('asset_code','—')}</div>"
            f"<div style='font-size:11px;color:#6B7280;margin-top:1px;'>{m.get('machine_type','—')}</div>"
            f"</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{m.get('make','') or ''} {m.get('model','') or ''}</td>"
            f"<td style='padding:8px 12px;font-size:12px;color:#374151;'>"
            f"{m.get('serial_number','—')}</td>"
        )
        cert_cells = "".join(_cell(m.get(fld)) for fld, _ in _CERT_FIELDS)
        rows_html += (
            f"<tr style='background:{bg_row};border-bottom:1px solid #F1F5F9;'>"
            f"{row_left}{cert_cells}</tr>"
        )

    table_html = (
        "<div style='overflow-x:auto;border:1px solid #E2EBF0;border-radius:10px;"
        "box-shadow:0 1px 3px rgba(0,0,0,.05);'>"
        "<table style='width:100%;border-collapse:collapse;font-family:inherit;'>"
        "<thead><tr>"
        f"<th style='{header_style}border-radius:10px 0 0 0;'>Asset / Type</th>"
        f"<th style='{header_style}'>Make / Model</th>"
        f"<th style='{header_style}'>Serial No.</th>"
        + "".join(
            f"<th style='{header_style}'>{lbl}</th>"
            for _, lbl in _CERT_FIELDS
        )
        + "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Legend ────────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='display:flex;gap:18px;margin-top:14px;font-size:11px;color:#6B7280;'>"
        "<span><span style='background:#FEE2E2;color:#991B1B;padding:1px 8px;"
        "border-radius:10px;font-weight:700;'>Overdue</span> — expired</span>"
        "<span><span style='background:#FEF3C7;color:#92400E;padding:1px 8px;"
        "border-radius:10px;font-weight:700;'>Expiring Soon</span> — within 30 days</span>"
        "<span><span style='background:#DCFCE7;color:#166534;padding:1px 8px;"
        "border-radius:10px;font-weight:700;'>Valid</span> — more than 30 days</span>"
        "<span>— = not set</span>"
        "</div>",
        unsafe_allow_html=True,
    )
