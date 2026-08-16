"""
erp/views/machinesale.py
Machine Sale module — record equipment disposal and exclude sold machines
from active fleet KPIs while preserving all historical operational data.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import streamlit as st

from ..supabase_client import SupabaseClient

# ── Constants ─────────────────────────────────────────────────────────────────
PAYMENT_STATUSES = ["Pending", "Received"]

# ── Page CSS ──────────────────────────────────────────────────────────────────
_CSS = """
<style>
.ms-info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
    gap: 10px;
    margin-bottom: 16px;
}
.ms-info-card {
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 10px 14px;
}
.ms-info-label {
    font-size: 10px;
    font-weight: 600;
    color: #6B7280;
    text-transform: uppercase;
    letter-spacing: .06em;
}
.ms-info-value {
    font-size: 14px;
    font-weight: 600;
    color: #111827;
    margin-top: 3px;
    word-break: break-word;
}
.ms-section {
    font-size: 12px;
    font-weight: 700;
    color: #2563EB;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin: 18px 0 8px;
    border-bottom: 1px solid #DBEAFE;
    padding-bottom: 4px;
}
.ms-sold-banner {
    background: #FEF2F2;
    border: 1px solid #FECACA;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 14px;
    font-size: 13px;
    color: #991B1B;
    font-weight: 600;
}
.ms-check-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    font-size: 13px;
}
.ms-check-pass { color: #16a34a; font-weight: 700; }
.ms-check-fail { color: #DC2626; font-weight: 700; }
.ms-checklist {
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 16px;
}
.ms-checklist-title {
    font-size: 12px;
    font-weight: 700;
    color: #374151;
    text-transform: uppercase;
    letter-spacing: .05em;
    margin-bottom: 8px;
}
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ic(label: str, value: str) -> str:
    return (
        f"<div class='ms-info-card'>"
        f"<div class='ms-info-label'>{label}</div>"
        f"<div class='ms-info-value'>{value or '—'}</div>"
        f"</div>"
    )


def _fmt_inr(v: float | None) -> str:
    if v is None:
        return "—"
    return f"₹{v:,.0f}"


def _parse_date(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).date()
        except Exception:
            pass
    return None


def _check_row(label: str, ok: bool, detail: str = "") -> str:
    icon  = "✅" if ok else "❌"
    cls   = "ms-check-pass" if ok else "ms-check-fail"
    det   = f"&nbsp;<span style='color:#6B7280;font-size:11px;'>— {detail}</span>" if detail else ""
    return (
        f"<div class='ms-check-row'>"
        f"<span class='{cls}'>{icon}</span>"
        f"<span style='font-weight:600;color:#111827;'>{label}</span>{det}"
        f"</div>"
    )


# ── Validation helpers ────────────────────────────────────────────────────────

def _machine_clients(machine_id: str, work_orders: list, cust_map: dict, site_map: dict) -> tuple[str, str]:
    """Return (customer_name, site_name) from most-recent WO for this machine."""
    today = date.today()
    active: list[dict] = []
    historic: list[dict] = []
    for wo in work_orders:
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            recs = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            ids  = [str(r.get("machine_id") or "") for r in (recs if isinstance(recs, list) else [])]
        except Exception:
            ids = []
        if str(machine_id) not in ids:
            continue
        sd = _parse_date(wo.get("start_date"))
        ed = _parse_date(wo.get("end_date"))
        if sd and sd <= today and (ed is None or ed >= today):
            active.append(wo)
        else:
            historic.append(wo)
    best = (active or sorted(historic, key=lambda w: _parse_date(w.get("start_date")) or date.min, reverse=True))
    if not best:
        return "—", "—"
    wo = best[0]
    return (
        cust_map.get(wo.get("customer_id", ""), "—"),
        site_map.get(wo.get("site_id",     ""), "—"),
    )


def _active_wo_count(machine_id: str, work_orders: list) -> int:
    count = 0
    for wo in work_orders:
        if wo.get("status") == "Closed":
            continue
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            recs = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            ids  = [str(r.get("machine_id") or "") for r in (recs if isinstance(recs, list) else [])]
        except Exception:
            ids = []
        if str(machine_id) in ids:
            count += 1
    return count


def _draft_wl_count(machine_id: str, worklogs: list) -> int:
    return sum(
        1 for w in worklogs
        if str(w.get("machine_id") or "") == str(machine_id) and w.get("is_draft", True)
    )


def _pending_invoice_count(machine_id: str, work_orders: list, invoices: list) -> int:
    wo_ids: set[str] = set()
    for wo in work_orders:
        mc_raw = wo.get("machine_config")
        if not mc_raw:
            continue
        try:
            recs = json.loads(mc_raw) if isinstance(mc_raw, str) else mc_raw
            ids  = [str(r.get("machine_id") or "") for r in (recs if isinstance(recs, list) else [])]
        except Exception:
            ids = []
        if str(machine_id) in ids:
            wid = wo.get("id")
            if wid:
                wo_ids.add(str(wid))
    return sum(
        1 for inv in invoices
        if str(inv.get("work_order_id") or "") in wo_ids
        and str(inv.get("status") or "").lower() not in ("paid", "cancelled")
    )


# ── Dialog: edit existing sale ────────────────────────────────────────────────

@st.dialog("Edit Sale Record", width="large")
def _edit_sale_dialog(sale: dict, sb: SupabaseClient, user_email: str) -> None:
    st.caption("Editing sale record — changes are audited.")

    col1, col2 = st.columns(2)
    with col1:
        sale_date = st.date_input(
            "Sale Date *",
            value=_parse_date(sale.get("sale_date")) or date.today(),
            key="ms_edit_sale_date",
        )
        sale_price = st.number_input(
            "Sale Price (₹)",
            value=float(sale.get("sale_price") or 0),
            min_value=0.0, step=1000.0,
            key="ms_edit_sale_price",
        )
        sale_invoice_no = st.text_input(
            "Sale Invoice Number",
            value=sale.get("sale_invoice_number") or "",
            key="ms_edit_sale_inv_no",
        )
        sale_invoice_date = st.date_input(
            "Sale Invoice Date",
            value=_parse_date(sale.get("sale_invoice_date")),
            key="ms_edit_sale_inv_date",
        )
        payment_status = st.selectbox(
            "Payment Status",
            PAYMENT_STATUSES,
            index=PAYMENT_STATUSES.index(sale.get("payment_status") or "Pending"),
            key="ms_edit_payment_status",
        )
        payment_date = st.date_input(
            "Payment Date",
            value=_parse_date(sale.get("payment_date")),
            key="ms_edit_payment_date",
        ) if payment_status == "Received" else None

    with col2:
        buyer_name    = st.text_input("Buyer Name",    value=sale.get("buyer_name")    or "", key="ms_edit_buyer_name")
        buyer_gst     = st.text_input("Buyer GST",     value=sale.get("buyer_gst")     or "", key="ms_edit_buyer_gst")
        buyer_contact = st.text_input("Contact Person",value=sale.get("buyer_contact_person") or "", key="ms_edit_buyer_contact")
        buyer_mobile  = st.text_input("Mobile",        value=sale.get("buyer_mobile")  or "", key="ms_edit_buyer_mobile")
        buyer_email   = st.text_input("Email",         value=sale.get("buyer_email")   or "", key="ms_edit_buyer_email")
        buyer_address = st.text_area( "Address",       value=sale.get("buyer_address") or "", key="ms_edit_buyer_addr", height=80)

    remarks = st.text_area("Remarks", value=sale.get("remarks") or "", key="ms_edit_remarks", height=70)

    if st.button("💾 Save Changes", key="ms_edit_save", use_container_width=True, type="primary"):
        try:
            payload: dict[str, Any] = {
                "sale_date":              sale_date.isoformat(),
                "sale_price":             sale_price if sale_price > 0 else None,
                "buyer_name":             buyer_name  or None,
                "buyer_gst":              buyer_gst   or None,
                "buyer_contact_person":   buyer_contact or None,
                "buyer_mobile":           buyer_mobile  or None,
                "buyer_email":            buyer_email   or None,
                "buyer_address":          buyer_address or None,
                "sale_invoice_number":    sale_invoice_no   or None,
                "sale_invoice_date":      sale_invoice_date.isoformat() if isinstance(sale_invoice_date, date) else None,
                "payment_status":         payment_status,
                "payment_date":           payment_date.isoformat() if isinstance(payment_date, date) else None,
                "remarks":                remarks or None,
                "updated_at":             datetime.utcnow().isoformat(),
                "updated_by":             user_email,
            }
            sb.update_machine_sale(sale["id"], payload)
            st.success("Sale record updated.")
            st.session_state["ms_sale_saved"] = True
            st.rerun()
        except Exception as exc:
            st.error(f"Could not save: {exc}")


# ── Main render ───────────────────────────────────────────────────────────────

def render() -> None:
    sb = SupabaseClient()
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div class='page-eyebrow'>// Operations</div>"
        "<div class='page-title'>Machine Sale</div>",
        unsafe_allow_html=True,
    )

    # Derive current user for audit
    try:
        from .. import auth as _auth
        user_email = _auth.get_current_user() or "system"
        _is_admin  = _auth.is_admin()
    except Exception:
        user_email = "system"
        _is_admin  = False

    # ── Load data ──────────────────────────────────────────────────────────────
    try:
        machines     = sb.list_machines()
        work_orders  = sb.list_work_orders()
        worklogs     = sb.list_all_worklogs()
        all_invoices = sb.list_all_invoices()
        all_sales    = sb.list_machine_sales()
        customers    = sb.list_customers()
        sites        = sb.list_sites()
    except Exception as exc:
        st.error(f"Failed to load data: {exc}")
        return

    cust_map  = {c["id"]: c.get("customer_name", "—") for c in customers if c.get("id")}
    site_map  = {s["id"]: s.get("site_name",     "—") for s in sites     if s.get("id")}
    sale_by_m = {s.get("machine_id"): s for s in all_sales if s.get("machine_id")}

    # ── Machine selector ───────────────────────────────────────────────────────
    mach_sorted = sorted(machines, key=lambda m: (
        m.get("operational_status") == "Sold",
        (m.get("asset_code") or "").upper()
    ))

    def _mach_label(m: dict) -> str:
        ac  = m.get("asset_code") or m.get("id", "?")
        mk  = m.get("make",  "") or ""
        mdl = m.get("model", "") or ""
        lbl = f"{ac} — {mk} {mdl}".strip().rstrip("—").strip()
        if m.get("operational_status") == "Sold":
            lbl += "  [SOLD]"
        return lbl

    labels = ["— Select Machine —"] + [_mach_label(m) for m in mach_sorted]
    ids    = [None]                  + [m["id"]        for m in mach_sorted]

    chosen = st.selectbox("Select Machine", labels, key="ms_machine_sel")
    mid    = ids[labels.index(chosen)]

    if mid is None:
        st.info("Select a machine to record or view a sale.")
        return

    mach         = next((m for m in machines if m.get("id") == mid), None)
    if not mach:
        st.error("Machine not found.")
        return

    is_sold      = mach.get("operational_status") == "Sold"
    existing_rec = sale_by_m.get(mid)

    # ── Machine info banner ────────────────────────────────────────────────────
    cur_client, cur_site = _machine_clients(mid, work_orders, cust_map, site_map)
    location = mach.get("current_location") or mach.get("location") or "—"

    st.markdown("<div class='ms-section'>Machine Information</div>", unsafe_allow_html=True)
    cards = (
        _ic("Machine Code",        mach.get("asset_code", "—"))
        + _ic("Make",              mach.get("make", "—"))
        + _ic("Model",             mach.get("model", "—"))
        + _ic("Serial Number",     mach.get("serial_number", "—"))
        + _ic("Year of Mfg",       str(mach.get("year_of_manufacture") or "—"))
        + _ic("Purchase Date",     str(_parse_date(mach.get("purchase_date")) or "—"))
        + _ic("Current Location",  location)
        + _ic("Current Client",    cur_client)
        + _ic("Current Site",      cur_site)
        + _ic("Current Status",    mach.get("operational_status", "—"))
    )
    st.markdown(f"<div class='ms-info-grid'>{cards}</div>", unsafe_allow_html=True)

    # ── Already Sold — view/edit mode ─────────────────────────────────────────
    if is_sold:
        st.markdown(
            "<div class='ms-sold-banner'>🔴 This machine has been sold and is no longer part of the active fleet.</div>",
            unsafe_allow_html=True,
        )

        if existing_rec:
            st.markdown("<div class='ms-section'>Sale Record</div>", unsafe_allow_html=True)
            r = existing_rec
            sale_cards = (
                _ic("Sale Date",         str(_parse_date(r.get("sale_date")) or "—"))
                + _ic("Sale Price",      _fmt_inr(r.get("sale_price")))
                + _ic("Invoice No.",     r.get("sale_invoice_number") or "—")
                + _ic("Invoice Date",    str(_parse_date(r.get("sale_invoice_date")) or "—"))
                + _ic("Payment Status",  r.get("payment_status") or "—")
                + _ic("Payment Date",    str(_parse_date(r.get("payment_date")) or "—"))
            )
            st.markdown(f"<div class='ms-info-grid'>{sale_cards}</div>", unsafe_allow_html=True)

            buyer_cards = (
                _ic("Buyer Name",    r.get("buyer_name") or "—")
                + _ic("Buyer GST",   r.get("buyer_gst")  or "—")
                + _ic("Contact",     r.get("buyer_contact_person") or "—")
                + _ic("Mobile",      r.get("buyer_mobile") or "—")
                + _ic("Email",       r.get("buyer_email")  or "—")
            )
            st.markdown(f"<div class='ms-info-grid'>{buyer_cards}</div>", unsafe_allow_html=True)

            if r.get("buyer_address"):
                st.markdown(f"**Address:** {r['buyer_address']}")
            if r.get("remarks"):
                st.markdown(f"**Remarks:** {r['remarks']}")

            # Audit trail
            with st.expander("Audit Trail", expanded=False):
                ac1, ac2, ac3, ac4 = st.columns(4)
                ac1.metric("Created By",   r.get("created_by")  or "—")
                ac2.metric("Created At",   str(r.get("created_at") or "—")[:19])
                ac3.metric("Updated By",   r.get("updated_by")  or "—")
                ac4.metric("Updated At",   str(r.get("updated_at") or "—")[:19])

            # Attachments
            st.markdown("<div class='ms-section'>Attachments</div>", unsafe_allow_html=True)
            try:
                docs = sb.list_documents("machine_sale", existing_rec["id"])
                if docs:
                    for doc in docs:
                        dc1, dc2 = st.columns([4, 1])
                        dc1.write(f"📎 {doc.get('file_name','?')}")
                        url = sb.get_signed_url(doc.get("storage_path", ""))
                        if url:
                            dc2.link_button("Download", url)
                else:
                    st.caption("No attachments.")
            except Exception:
                st.caption("Attachments unavailable.")

            if _is_admin:
                if st.button("✏️ Edit Sale Record", key="ms_edit_btn"):
                    _edit_sale_dialog(existing_rec, sb, user_email)
                    st.rerun()
        else:
            st.warning("Sale record not found for this machine. The machine is marked Sold but has no sale record.")
        return

    # ── New Sale — validation checklist ───────────────────────────────────────
    n_active_wo   = _active_wo_count(mid, work_orders)
    n_draft_wl    = _draft_wl_count(mid, worklogs)
    n_pending_inv = _pending_invoice_count(mid, work_orders, all_invoices)

    checks_pass = (n_active_wo == 0 and n_draft_wl == 0 and n_pending_inv == 0)

    st.markdown("<div class='ms-section'>Pre-Sale Validation</div>", unsafe_allow_html=True)
    checklist_html = (
        "<div class='ms-checklist'>"
        "<div class='ms-checklist-title'>All conditions must be cleared before recording a sale</div>"
        + _check_row(
            "No Active Work Orders",
            n_active_wo == 0,
            f"{n_active_wo} active WO(s) found — close billing first" if n_active_wo else "Clear",
        )
        + _check_row(
            "No Pending / Draft Worklogs",
            n_draft_wl == 0,
            f"{n_draft_wl} draft worklog(s) — submit or delete first" if n_draft_wl else "Clear",
        )
        + _check_row(
            "No Pending Invoices",
            n_pending_inv == 0,
            f"{n_pending_inv} unpaid invoice(s) — settle first" if n_pending_inv else "Clear",
        )
        + "</div>"
    )
    st.markdown(checklist_html, unsafe_allow_html=True)

    if not checks_pass:
        st.error(
            "This machine cannot be sold until all active work orders are closed, "
            "pending worklogs are submitted, and outstanding invoices are settled.",
            icon="🚫",
        )
        return

    st.success("All pre-sale checks passed. You may proceed to record the sale.", icon="✅")

    # ── Sale form ──────────────────────────────────────────────────────────────
    st.markdown("<div class='ms-section'>Sale Information</div>", unsafe_allow_html=True)

    fc1, fc2 = st.columns(2)
    with fc1:
        sale_date = st.date_input(
            "Sale Date *",
            value=date.today(),
            max_value=date.today(),
            key="ms_sale_date",
        )
        sale_price = st.number_input(
            "Sale Price (₹) *",
            min_value=0.0, step=1000.0, value=0.0,
            key="ms_sale_price",
        )
        sale_invoice_no = st.text_input("Sale Invoice Number", key="ms_sale_inv_no")
        sale_invoice_date = st.date_input(
            "Sale Invoice Date",
            value=None,
            key="ms_sale_inv_date",
        )
        payment_status = st.selectbox(
            "Payment Status *",
            PAYMENT_STATUSES,
            key="ms_payment_status",
        )
        if payment_status == "Received":
            payment_date = st.date_input(
                "Payment Date",
                value=date.today(),
                key="ms_payment_date",
            )
        else:
            payment_date = None

    with fc2:
        buyer_name    = st.text_input("Buyer Name *",       key="ms_buyer_name")
        buyer_gst     = st.text_input("Buyer GST",          key="ms_buyer_gst")
        buyer_contact = st.text_input("Contact Person",     key="ms_buyer_contact")
        buyer_mobile  = st.text_input("Mobile",             key="ms_buyer_mobile")
        buyer_email   = st.text_input("Email",              key="ms_buyer_email")
        buyer_address = st.text_area( "Buyer Address",      key="ms_buyer_addr", height=90)

    remarks = st.text_area("Remarks", key="ms_remarks", height=70)

    # ── Attachments ────────────────────────────────────────────────────────────
    st.markdown("<div class='ms-section'>Attachments</div>", unsafe_allow_html=True)
    st.caption("Upload supporting documents (sale agreement, invoice scan, etc.)")
    uploaded_files = st.file_uploader(
        "Upload Documents",
        accept_multiple_files=True,
        type=["pdf", "jpg", "jpeg", "png", "doc", "docx"],
        key="ms_uploads",
        label_visibility="collapsed",
    )

    # ── Submit ─────────────────────────────────────────────────────────────────
    st.markdown("---")
    _, btn_col = st.columns([3, 1])
    with btn_col:
        submit = st.button(
            "🔴 Record Sale & Mark as Sold",
            key="ms_submit",
            use_container_width=True,
            type="primary",
        )

    if submit:
        if not buyer_name.strip():
            st.error("Buyer Name is required.")
            return
        if sale_price <= 0:
            st.error("Sale Price must be greater than zero.")
            return

        try:
            now_str = datetime.utcnow().isoformat()
            sale_payload: dict[str, Any] = {
                "machine_id":           mid,
                "sale_date":            sale_date.isoformat(),
                "sale_price":           sale_price,
                "buyer_name":           buyer_name.strip(),
                "buyer_gst":            buyer_gst.strip()     or None,
                "buyer_contact_person": buyer_contact.strip() or None,
                "buyer_mobile":         buyer_mobile.strip()  or None,
                "buyer_email":          buyer_email.strip()   or None,
                "buyer_address":        buyer_address.strip() or None,
                "sale_invoice_number":  sale_invoice_no.strip() or None,
                "sale_invoice_date":    sale_invoice_date.isoformat() if isinstance(sale_invoice_date, date) else None,
                "payment_status":       payment_status,
                "payment_date":         payment_date.isoformat() if isinstance(payment_date, date) else None,
                "remarks":              remarks.strip() or None,
                "created_by":           user_email,
                "created_at":           now_str,
                "updated_at":           now_str,
            }
            new_sale = sb.insert_machine_sale(sale_payload)

            # Mark machine as Sold with sale_date
            sb.update_machine(mid, {
                "operational_status": "Sold",
                "sale_date":          sale_date.isoformat(),
            })

            # Upload any attachments
            sale_id = new_sale.get("id")
            if sale_id and uploaded_files:
                for f in uploaded_files:
                    try:
                        sb.upload_document(
                            record_type  = "machine_sale",
                            record_id    = sale_id,
                            file_bytes   = f.read(),
                            file_name    = f.name,
                            file_size_kb = max(1, f.size // 1024),
                            uploaded_by  = user_email,
                        )
                    except Exception:
                        pass

            st.success(
                f"✅ Sale recorded successfully. "
                f"{mach.get('asset_code','Machine')} has been marked as **Sold** "
                f"and removed from the active fleet.",
                icon="✅",
            )
            st.session_state["ms_machine_sel"] = "— Select Machine —"
            st.rerun()

        except Exception as exc:
            st.error(f"Could not record sale: {exc}")
