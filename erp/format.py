"""
erp/format.py
Presentation helpers. The schema is Indian (GST, pincode, UPI/NEFT/RTGS), so
money uses the lakh/crore grouping. We format without external locale deps so it
works on any machine.
"""
from __future__ import annotations

from datetime import date


def _group_indian(integer_str: str) -> str:
    """Group an integer string in the Indian system: 12,34,56,789."""
    if len(integer_str) <= 3:
        return integer_str
    head, tail = integer_str[:-3], integer_str[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def format_currency(value: float | int | None) -> str:
    if value is None:
        return "—"
    neg = value < 0
    n = int(round(abs(value)))
    out = "₹" + _group_indian(str(n))
    return ("-" + out) if neg else out


def format_currency_compact(value: float | int | None) -> str:
    """Compact KPI form: ₹1.2Cr, ₹84.0L, ₹9.5K."""
    if value is None:
        return "—"
    v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e7:
        return f"{sign}₹{v / 1e7:.1f}Cr"
    if v >= 1e5:
        return f"{sign}₹{v / 1e5:.1f}L"
    if v >= 1e3:
        return f"{sign}₹{v / 1e3:.1f}K"
    return f"{sign}₹{v:.0f}"


def format_date(d: date | None) -> str:
    if d is None:
        return "—"
    return d.strftime("%d %b %Y")


def days_until(d: date | None) -> int | None:
    if d is None:
        return None
    return (d - date.today()).days
