"""
erp/views/invoicereport.py
Invoice Report — searchable, filterable list of all invoices with inline
preview, print, and Excel / PDF export.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as _components

from ..supabase_client import SupabaseClient
from ._report_utils import (
    render_export_buttons,
    render_drilldown_table,
)
from .invoice import _build_html, _build_docx, _build_pdf_bytes  # reuse invoice builders


# ── Status palette ─────────────────────────────────────────────────────────────
# DB stores "Final"; we display it as "Completed" throughout this page.
_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "Draft":     ("#FEF3C7", "#92400E"),
    "Completed": ("#D1FAE5", "#065F46"),
    "Cancelled": ("#FEE2E2", "#991B1B"),
}

def _display_status(raw: str) -> str:
    """Map DB status values to UI labels ('Final' → 'Completed')."""
    return "Completed" if raw == "Final" else str(raw)


def _status_chip(status: str) -> str:
    label = _display_status(status)
    bg, fg = _STATUS_COLORS.get(label, ("#F1F5F9", "#374151"))
    return (
        f"<span style='display:inline-block;padding:2px 10px;border-radius:20px;"
        f"background:{bg};color:{fg};font-size:10px;font-weight:700;'>{label}</span>"
    )


def _fmt_date(val: str | None) -> str:
    if not val:
        return "—"
    try:
        return datetime.strptime(val[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        return str(val)[:10]


def _style_status(col: pd.Series) -> list[str]:
    out = []
    for v in col:
        label = _display_status(str(v))
        bg, fg = _STATUS_COLORS.get(label, ("#F1F5F9", "#374151"))
        out.append(f"background-color:{bg};color:{fg};font-weight:700;")
    return out


# ── Main render ────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div class="page-eyebrow">// Reports</div>
        <div class="page-title">Invoice Report</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    # ── Load data ──────────────────────────────────────────────────────────────
    try:
        invoices = sb.list_all_invoices()
    except Exception as exc:
        st.error(f"Failed to load invoices: {exc}")
        return

    try:
        work_orders = sb.list_work_orders()
        customers   = sb.list_customers()
        sites       = sb.list_sites()
    except Exception:
        work_orders, customers, sites = [], [], []

    wo_map   = {w["id"]: w for w in work_orders if w.get("id")}
    cust_map = {c["id"]: c for c in customers   if c.get("id")}
    site_map = {s["id"]: s for s in sites       if s.get("id")}

    if not invoices:
        st.info("No invoices found.")
        return

    # ── Build display DataFrame ────────────────────────────────────────────────
    rows = []
    for inv in invoices:
        wo      = wo_map.get(inv.get("work_order_id") or "", {})
        cust    = cust_map.get(inv.get("customer_id") or "", {})
        site    = site_map.get(inv.get("site_id") or "", {})
        rows.append({
            "_id":           inv.get("id", ""),
            "Invoice No.":   inv.get("invoice_number") or "—",
            "Date":          _fmt_date(inv.get("invoice_date")),
            "_raw_date":     inv.get("invoice_date") or "",
            "WO Number":     wo.get("wo_number") or "—",
            "Customer":      cust.get("customer_name") or "—",
            "Site":          site.get("site_name") or "—",
            "Subtotal (₹)":  float(inv.get("subtotal") or 0),
            "Tax (₹)":       float(inv.get("tax_amount") or 0),
            "Grand Total (₹)": float(inv.get("grand_total") or 0),
            "Status":        _display_status(inv.get("status") or "Draft"),
        })

    full_df = pd.DataFrame(rows)

    # ── KPI strip ──────────────────────────────────────────────────────────────
    total_inv   = len(full_df)
    total_value = full_df["Grand Total (₹)"].sum()
    draft_count     = int((full_df["Status"] == "Draft").sum())
    completed_count = int((full_df["Status"] == "Completed").sum())

    def _kpi(icon: str, label: str, value: str, color: str = "#111827") -> str:
        return (
            "<div style='background:#fff;border:1px solid #e5e7eb;border-radius:12px;"
            "padding:14px 18px;flex:1;min-width:0;'>"
            f"<div style='font-size:18px;margin-bottom:4px;'>{icon}</div>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;"
            f"text-transform:uppercase;color:#9ca3af;margin-bottom:4px;'>{label}</div>"
            f"<div style='font-size:22px;font-weight:800;color:{color};"
            f"font-variant-numeric:tabular-nums;'>{value}</div>"
            "</div>"
        )

    st.markdown(
        "<div style='display:flex;gap:12px;margin-bottom:20px;'>"
        + _kpi("🧾", "Total Invoices",  str(total_inv))
        + _kpi("💰", "Total Value",     f"₹ {total_value:,.0f}", "#E87722")
        + _kpi("📝", "Draft",           str(draft_count),     "#92400E")
        + _kpi("✅", "Completed",       str(completed_count), "#065F46")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Search & Filters ───────────────────────────────────────────────────────
    with st.container(border=True):
        fc1, fc2, fc3, fc4, fc5 = st.columns([2, 1, 1, 1, 1])
        with fc1:
            search = st.text_input(
                "Search",
                placeholder="Invoice No., WO, Customer, Site…",
                key="ir_search",
                label_visibility="collapsed",
            )
        with fc2:
            status_opts = ["All"] + sorted(full_df["Status"].dropna().unique().tolist())
            sel_status = st.selectbox("Status", status_opts, key="ir_status",
                                      label_visibility="collapsed")
        with fc3:
            cust_opts = ["All Customers"] + sorted(
                full_df["Customer"].dropna().unique().tolist()
            )
            sel_cust = st.selectbox("Customer", cust_opts, key="ir_cust",
                                    label_visibility="collapsed")
        with fc4:
            date_from = st.date_input("From", value=None, key="ir_from",
                                      label_visibility="collapsed")
        with fc5:
            date_to = st.date_input("To", value=None, key="ir_to",
                                    label_visibility="collapsed")

    # ── Apply filters ──────────────────────────────────────────────────────────
    df = full_df.copy()

    if search.strip():
        q = search.strip().lower()
        mask = (
            df["Invoice No."].str.lower().str.contains(q, na=False) |
            df["WO Number"].str.lower().str.contains(q, na=False)   |
            df["Customer"].str.lower().str.contains(q, na=False)    |
            df["Site"].str.lower().str.contains(q, na=False)
        )
        df = df[mask]

    if sel_status != "All":
        df = df[df["Status"] == sel_status]

    if sel_cust != "All Customers":
        df = df[df["Customer"] == sel_cust]

    if date_from:
        df = df[df["_raw_date"] >= date_from.isoformat()]

    if date_to:
        df = df[df["_raw_date"] <= date_to.isoformat()]

    df = df.reset_index(drop=True)

    if df.empty:
        st.info("No invoices match the current filters.")
        return

    # ── Display columns (hide internal cols) ───────────────────────────────────
    display_cols = [
        "Invoice No.", "Date", "WO Number", "Customer", "Site",
        "Subtotal (₹)", "Tax (₹)", "Grand Total (₹)", "Status",
    ]
    display_df = df[display_cols].copy()

    col_cfg = {
        "Invoice No.":    st.column_config.TextColumn("Invoice No.", width="medium"),
        "Date":           st.column_config.TextColumn("Date",        width="small"),
        "WO Number":      st.column_config.TextColumn("WO",          width="small"),
        "Customer":       st.column_config.TextColumn("Customer",    width="medium"),
        "Site":           st.column_config.TextColumn("Site",        width="medium"),
        "Subtotal (₹)":   st.column_config.NumberColumn("Subtotal",  format="₹ %.2f", width="small"),
        "Tax (₹)":        st.column_config.NumberColumn("Tax",       format="₹ %.2f", width="small"),
        "Grand Total (₹)":st.column_config.NumberColumn("Grand Total",format="₹ %.2f",width="small"),
        "Status":         st.column_config.TextColumn("Status",      width="small"),
    }

    def _style_fn(s: "pd.io.formats.style.Styler"):  # type: ignore[name-defined]
        return s.apply(_style_status, subset=["Status"])

    st.markdown(
        f"<div style='font-size:12px;color:#6B7280;margin-bottom:6px;'>"
        f"Showing <b>{len(df)}</b> of <b>{total_inv}</b> invoices</div>",
        unsafe_allow_html=True,
    )

    sel_row = render_drilldown_table(
        display_df,
        table_key="ir_table",
        column_config=col_cfg,
        height=min(38 + len(df) * 35 + 4, 520),
        style_fn=_style_fn,
    )

    # ── Export buttons ─────────────────────────────────────────────────────────
    render_export_buttons(
        display_df,
        base_name="invoice_report",
        excel_key="ir_xl",
        pdf_key="ir_pdf",
        title="Invoice Report",
        subtitle=f"{len(df)} invoices",
        sheet_name="Invoices",
    )

    # ── Invoice detail panel ───────────────────────────────────────────────────
    if sel_row is not None:
        inv_row   = df.iloc[sel_row]
        inv_id    = inv_row["_id"]

        st.markdown(
            "<div style='margin-top:24px;border-top:2px solid #e5e7eb;padding-top:20px;'></div>",
            unsafe_allow_html=True,
        )

        # Fetch full invoice record
        try:
            inv = sb.get_invoice_by_id(inv_id)
        except Exception as exc:
            st.error(f"Could not load invoice: {exc}")
            return

        if not inv:
            st.warning("Invoice record not found.")
            return

        inv_no   = inv.get("invoice_number") or "—"
        inv_date_raw = inv.get("invoice_date") or date.today().isoformat()
        try:
            inv_date = datetime.strptime(inv_date_raw[:10], "%Y-%m-%d").date()
        except Exception:
            inv_date = date.today()

        # Header row: title + print button
        dh1, dh2 = st.columns([5, 1])
        with dh1:
            st.markdown(
                f"<div style='font-size:18px;font-weight:800;color:#111827;'>"
                f"Invoice — {inv_no}</div>"
                f"<div style='font-size:12px;color:#6B7280;margin-top:2px;'>"
                f"{inv_row['Customer']} &bull; {inv_row['WO Number']} &bull; "
                f"{_fmt_date(inv.get('invoice_date'))}"
                f"&nbsp;&nbsp;{_status_chip(inv.get('status') or 'Draft')}</div>",
                unsafe_allow_html=True,
            )
        with dh2:
            if st.button("🖨️ Print", key="ir_print_btn", use_container_width=True):
                st.session_state["ir_print_trigger"] = inv_id

        # Rebuild invoice HTML from stored data
        wo      = wo_map.get(inv.get("work_order_id") or "", {})
        cust    = cust_map.get(inv.get("customer_id") or "", {})
        site    = site_map.get(inv.get("site_id") or "", {})
        tax_on  = float(inv.get("tax_amount") or 0) > 0
        tax_type = inv.get("tax_type") or "CGST/SGST"
        notes   = inv.get("notes") or ""

        # Parse stored line_items back to groups list
        try:
            raw_li = inv.get("line_items")
            groups = json.loads(raw_li) if isinstance(raw_li, str) else (raw_li or [])
        except Exception:
            groups = []

        # Detect if any group has item_code or hsn
        ic_on  = any(g.get("item_code") for g in groups)
        hsn_on = False
        hsn_code = ""

        try:
            inv_html = _build_html(
                inv_no       = inv_no,
                inv_date     = inv_date,
                wo           = wo,
                customer     = cust,
                site         = site,
                groups       = groups,
                tax_type     = tax_type,
                tax_on       = tax_on,
                hsn_on       = hsn_on,
                hsn_code     = hsn_code,
                item_code_on = ic_on,
                notes        = notes,
            )
        except Exception as exc:
            st.error(f"Could not rebuild invoice preview: {exc}")
            return

        # Print trigger
        if st.session_state.get("ir_print_trigger") == inv_id:
            st.session_state.pop("ir_print_trigger", None)
            _components.html(inv_html, height=980, scrolling=True)
        else:
            with st.expander("📄 Invoice Preview", expanded=True):
                _components.html(inv_html, height=960, scrolling=True)

        # ── Download section ───────────────────────────────────────────────────
        _inv_fname = inv_no.replace("/", "_")

        # kwargs shared by all file builders
        _build_kwargs = dict(
            inv_no=inv_no, inv_date=inv_date,
            wo=wo, customer=cust, site=site,
            groups=groups, tax_type=tax_type, tax_on=tax_on,
            hsn_on=hsn_on, hsn_code=hsn_code,
            item_code_on=ic_on, notes=notes,
        )

        # Resolve Word bytes: stored original → fallback regenerated
        _word_data: bytes | None = None
        _word_src = ""
        try:
            _raw = sb.download_invoice_file(inv_no, "docx")
            if _raw:
                _word_data = bytes(_raw)
                _word_src  = "original"
        except Exception:
            pass
        if _word_data is None:
            try:
                _word_data = bytes(_build_docx(**_build_kwargs))
                _word_src  = "generated"
            except Exception as _e:
                _word_src  = f"error: {_e}"

        # Resolve PDF bytes: stored original → fallback regenerated
        _pdf_data: bytes | None = None
        _pdf_src = ""
        try:
            _raw = sb.download_invoice_file(inv_no, "pdf")
            if _raw:
                _pdf_data = bytes(_raw)
                _pdf_src  = "original"
        except Exception:
            pass
        if _pdf_data is None:
            try:
                _pdf_data = bytes(_build_pdf_bytes(**_build_kwargs))
                _pdf_src  = "generated"
            except Exception as _e:
                _pdf_src  = f"error: {_e}"

        # Source indicator strip
        _src_parts = []
        if _word_src:
            _src_parts.append(
                f"Word: {'🗄 stored' if _word_src == 'original' else ('⚙ generated' if _word_src == 'generated' else '❌ ' + _word_src)}"
            )
        if _pdf_src:
            _src_parts.append(
                f"PDF: {'🗄 stored' if _pdf_src == 'original' else ('⚙ generated' if _pdf_src == 'generated' else '❌ ' + _pdf_src)}"
            )
        if _src_parts:
            st.caption("  ·  ".join(_src_parts))

        # Download buttons — always rendered
        _dl1, _dl2, _dl3 = st.columns(3)
        with _dl1:
            st.download_button(
                "⬇ Download (HTML)",
                data=inv_html.encode("utf-8"),
                file_name=f"{_inv_fname}.html",
                mime="text/html",
                key="ir_dl_html",
                use_container_width=True,
            )
        with _dl2:
            if _word_data:
                try:
                    st.download_button(
                        "⬇ Download (Word)",
                        data=_word_data,
                        file_name=f"{_inv_fname}.docx",
                        mime="application/vnd.openxmlformats-officedocument"
                             ".wordprocessingml.document",
                        key="ir_dl_docx",
                        use_container_width=True,
                    )
                except Exception as _btn_err:
                    st.error(f"Word download error: {_btn_err}")
            else:
                st.button("⬇ Download (Word)", disabled=True,
                          key="ir_dl_docx_na", use_container_width=True)
        with _dl3:
            if _pdf_data:
                try:
                    st.download_button(
                        "⬇ Download (PDF)",
                        data=_pdf_data,
                        file_name=f"{_inv_fname}.pdf",
                        mime="application/pdf",
                        key="ir_dl_pdf",
                        use_container_width=True,
                    )
                except Exception as _btn_err:
                    st.error(f"PDF download error: {_btn_err}")
            else:
                st.button("⬇ Download (PDF)", disabled=True,
                          key="ir_dl_pdf_na", use_container_width=True)
