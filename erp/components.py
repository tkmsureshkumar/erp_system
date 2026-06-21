"""
erp/components.py
Shared UI atoms. Streamlit has no Tailwind, so the signature StatusBadge is
rendered as an inline-styled HTML span. Every workflow status maps to a tone that
encodes meaning, exactly as in the React build:
  slate=idle · amber=in-transition · emerald=earning/healthy · rose=stop ·
  violet=financial-in-flight · sky=done.
"""
from __future__ import annotations

from enum import Enum

# tone -> (background, foreground, ring)
_TONE: dict[str, tuple[str, str, str]] = {
    "slate": ("#f1f5f9", "#475569", "#e2e8f0"),
    "amber": ("#fffbeb", "#b45309", "#fde68a"),
    "emerald": ("#ecfdf5", "#047857", "#a7f3d0"),
    "rose": ("#fff1f2", "#be123c", "#fecdd3"),
    "violet": ("#f5f3ff", "#6d28d9", "#ddd6fe"),
    "sky": ("#f0f9ff", "#0369a1", "#bae6fd"),
}

STATUS_TONE: dict[str, str] = {
    # operational_status
    "Available": "slate",
    "Reserved": "amber",
    "Mobilizing": "amber",
    "On Rent": "emerald",
    "Demobilizing": "amber",
    "Sold": "slate",
    # condition_status
    "Running": "emerald",
    "Breakdown": "rose",
    "Under Repair": "amber",
    "BER": "rose",
    # operator_status
    "Active": "emerald",
    "Inactive": "slate",
    "On Leave": "amber",
    # work_order_status / deployment_status
    "Draft": "slate",
    "Completed": "sky",
    "Cancelled": "rose",
    "Closed": "slate",
    # log_sheet_status
    "Submitted": "amber",
    "Approved": "emerald",
    "Rejected": "rose",
    # pi / invoice
    "Sent": "violet",
    "Accepted": "emerald",
    "Partially Paid": "violet",
    "Paid": "emerald",
    "Overdue": "rose",
}

# Solid fills for the utilization bar.
BAR_TONE: dict[str, str] = {
    "Available": "#cbd5e1",
    "Reserved": "#fcd34d",
    "Mobilizing": "#fbbf24",
    "On Rent": "#10b981",
    "Demobilizing": "#f59e0b",
    "Sold": "#94a3b8",
}


def _label(status: str | Enum) -> str:
    return status.value if isinstance(status, Enum) else str(status)


def badge_html(status: str | Enum, dot: bool = True) -> str:
    """Return an inline-styled HTML badge for a status value."""
    text = _label(status)
    bg, fg, ring = _TONE[STATUS_TONE.get(text, "slate")]
    dot_html = (
        f"<span style='display:inline-block;width:6px;height:6px;border-radius:9999px;"
        f"background:{fg};opacity:.7;margin-right:6px;'></span>"
        if dot
        else ""
    )
    return (
        f"<span style='display:inline-flex;align-items:center;font-size:12px;"
        f"font-weight:500;line-height:1;padding:4px 10px;border-radius:9999px;"
        f"background:{bg};color:{fg};box-shadow:inset 0 0 0 1px {ring};"
        f"white-space:nowrap;'>{dot_html}{text}</span>"
    )
