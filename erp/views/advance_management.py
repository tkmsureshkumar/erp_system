"""
erp/views/advance_management.py — Advance Management module (6 tabs).

Supabase tables required (run in Supabase SQL editor before first use):

    CREATE TABLE IF NOT EXISTS advance_opening_balance (
        id            uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id   text NOT NULL,
        balance       numeric NOT NULL DEFAULT 0,
        as_on_date    date NOT NULL,
        remarks       text,
        entered_by    text,
        entry_date    date DEFAULT CURRENT_DATE,
        created_at    timestamptz DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS advance_batches (
        id             uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        batch_number   text UNIQUE NOT NULL,
        submitted_by   text,
        submitted_at   timestamptz DEFAULT now(),
        employee_count integer DEFAULT 0,
        total_amount   numeric DEFAULT 0,
        status         text DEFAULT 'Submitted',
        created_at     timestamptz DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS advance_requests (
        id                   uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        batch_id             uuid REFERENCES advance_batches(id),
        employee_id          text NOT NULL,
        advance_date         date NOT NULL,
        requested_amount     numeric NOT NULL,
        approved_amount      numeric,
        reason               text,
        payment_mode         text,
        status               text DEFAULT 'Pending',
        approved_by          text,
        approved_at          timestamptz,
        approval_remarks     text,
        amount_change_reason text,
        created_at           timestamptz DEFAULT now()
    );
    -- If table already exists, run: ALTER TABLE advance_requests ADD COLUMN IF NOT EXISTS payment_mode text;

    CREATE TABLE IF NOT EXISTS advance_payments (
        id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        advance_request_id  uuid REFERENCES advance_requests(id),
        employee_id         text NOT NULL,
        payment_date        date,
        amount              numeric NOT NULL,
        payment_status      text DEFAULT 'Pending',
        utr_reference       text,
        paid_by             text,
        paid_at             timestamptz,
        created_at          timestamptz DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS advance_recoveries (
        id               uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id      text NOT NULL,
        payroll_month    text NOT NULL,
        suggested_recovery numeric NOT NULL,
        final_recovery   numeric NOT NULL,
        change_reason    text,
        processed_by     text,
        processed_at     timestamptz DEFAULT now(),
        created_at       timestamptz DEFAULT now()
    );
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from .. import auth
from ..supabase_client import SupabaseClient

_PAYMENT_MODES = ["UPI", "Netbanking"]

# ── helpers ────────────────────────────────────────────────────────────────────

def _user_name() -> str:
    p = auth.current_profile()
    return p.get("full_name") or p.get("email") or "Unknown"


def _generate_batch_number(sb: SupabaseClient) -> str:
    today = date.today()
    prefix = f"ADV-{today.strftime('%Y-%m%d')}"
    existing = sb.list_advance_batches()
    count = sum(1 for b in existing if (b.get("batch_number") or "").startswith(prefix))
    return f"{prefix}-{count + 1:03d}"


def _compute_balance_from(
    openings: list, payments: list, recoveries: list, as_on: date
) -> dict:
    opening = sum(
        float(r.get("balance") or 0)
        for r in openings
        if r.get("as_on_date") and str(r["as_on_date"]) <= str(as_on)
    )
    advances_given = sum(
        float(p.get("amount") or 0)
        for p in payments
        if p.get("payment_status") == "Paid"
        and p.get("payment_date")
        and str(p["payment_date"]) <= str(as_on)
    )
    total_recoveries = sum(
        float(r.get("final_recovery") or 0)
        for r in recoveries
        if r.get("processed_at") and str(r["processed_at"])[:10] <= str(as_on)
    )
    return {
        "opening":        opening,
        "advances_given": advances_given,
        "recoveries":     total_recoveries,
        "balance":        opening + advances_given - total_recoveries,
    }


def _render_ledger(
    sb: SupabaseClient,
    employee_id: str,
    as_on: date | None = None,
    all_openings: list | None = None,
    all_payments: list | None = None,
    all_recoveries: list | None = None,
) -> None:
    opening_recs = [r for r in (all_openings or []) if r.get("employee_id") == employee_id] \
                   if all_openings is not None \
                   else sb.list_advance_opening_balances(employee_id=employee_id)

    raw_payments = [p for p in (all_payments or []) if p.get("employee_id") == employee_id] \
                   if all_payments is not None \
                   else sb.list_advance_payments(employee_id=employee_id)

    payments = [p for p in raw_payments if p.get("payment_status") == "Paid"]

    recoveries = [r for r in (all_recoveries or []) if r.get("employee_id") == employee_id] \
                 if all_recoveries is not None \
                 else sb.list_advance_recoveries(employee_id=employee_id)

    transactions: list[dict] = []
    for r in opening_recs:
        d = r.get("as_on_date")
        if d and (as_on is None or str(d) <= str(as_on)):
            transactions.append({"date": d, "type": "Opening Balance",
                                  "advance": float(r.get("balance") or 0), "recovery": 0.0})
    for p in payments:
        d = p.get("payment_date")
        if d and (as_on is None or str(d) <= str(as_on)):
            transactions.append({"date": d, "type": "Advance",
                                  "advance": float(p.get("amount") or 0), "recovery": 0.0})
    for r in recoveries:
        d = str(r.get("processed_at") or "")[:10]
        if d and (as_on is None or d <= str(as_on)):
            transactions.append({"date": d, "type": "Payroll Recovery",
                                  "advance": 0.0, "recovery": float(r.get("final_recovery") or 0)})

    if not transactions:
        st.info("No transactions found.")
        return

    transactions.sort(key=lambda x: str(x["date"]))
    balance = 0.0
    rows = []
    for t in transactions:
        balance += t["advance"] - t["recovery"]
        rows.append({
            "Date":              t["date"],
            "Transaction":       t["type"],
            "Advance Given (₹)": t["advance"] if t["advance"] > 0 else None,
            "Recovery (₹)":      t["recovery"] if t["recovery"] > 0 else None,
            "Balance (₹)":       balance,
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True, hide_index=True,
        column_config={
            "Advance Given (₹)": st.column_config.NumberColumn(format="₹%,.0f"),
            "Recovery (₹)":      st.column_config.NumberColumn(format="₹%,.0f"),
            "Balance (₹)":       st.column_config.NumberColumn(format="₹%,.0f"),
        },
    )


def _build_print_html(items: list, op_by_id: dict) -> str:
    """Build a printable HTML voucher for the Accounts team."""
    rows_html = ""
    total = 0.0
    for i, p in enumerate(items, 1):
        op        = op_by_id.get(p["_emp_id"], {})
        name      = op.get("operator_name", "—")
        code      = op.get("emp_code", "—")
        amount    = float(p.get("Amount (₹)") or 0)
        total    += amount
        mode      = p.get("Payment Mode", "—")
        bank_acc  = op.get("bank_account_number") or op.get("bank_account") or "—"
        bank_name = op.get("bank_name") or "—"
        ifsc      = op.get("ifsc_code") or op.get("bank_ifsc") or "—"
        rows_html += f"""
        <tr>
            <td>{i}</td>
            <td>{name}</td>
            <td>{code}</td>
            <td style="text-align:right">&#8377;{amount:,.0f}</td>
            <td>{mode}</td>
            <td>{bank_acc}</td>
            <td>{bank_name}</td>
            <td>{ifsc}</td>
        </tr>"""

    print_date = date.today().strftime("%d %b %Y")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 12px; margin: 30px; }}
  h2   {{ color: #1E293B; margin-bottom: 4px; }}
  p    {{ margin: 2px 0 14px; color: #64748B; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ border: 1px solid #CBD5E1; padding: 6px 10px; }}
  th {{ background: #1E293B; color: #fff; text-align: left; font-size: 11px; }}
  tfoot td {{ font-weight: bold; }}
  @media print {{
    button {{ display: none; }}
  }}
</style>
</head><body>
<h2>Advance Payment Voucher</h2>
<p>Date: {print_date} &nbsp;|&nbsp; Total entries: {len(items)}</p>
<table>
<thead><tr>
  <th>#</th><th>Employee Name</th><th>Emp Code</th>
  <th>Amount</th><th>Payment Mode</th>
  <th>Account No.</th><th>Bank Name</th><th>IFSC</th>
</tr></thead>
<tbody>{rows_html}</tbody>
<tfoot><tr>
  <td colspan="3" style="text-align:right">Total</td>
  <td style="text-align:right">&#8377;{total:,.0f}</td>
  <td colspan="4"></td>
</tr></tfoot>
</table>
<br><br>
<p>Prepared by: _____________________________ &nbsp;&nbsp;&nbsp; Authorised by: _____________________________</p>
</body></html>"""


# ── Tab 1: Opening Balance ─────────────────────────────────────────────────────

def _tab_opening_balance() -> None:
    st.markdown("#### Opening Balance")
    sb = SupabaseClient()
    operators  = sb.list_operators()
    op_by_id   = {o["id"]: o for o in operators}
    op_options = {}
    for o in operators:
        code  = (o.get("emp_code") or "").strip()
        name  = (o.get("operator_name") or "").strip()
        label = f"{code} – {name}" if code and name else (code or name)
        if label:
            op_options[label] = o["id"]

    records = sb.list_advance_opening_balances()
    if records:
        rows = []
        for r in records:
            op = op_by_id.get(r.get("employee_id", ""), {})
            rows.append({
                "Employee":    op.get("operator_name", r.get("employee_id", "")),
                "Emp Code":    op.get("emp_code", ""),
                "Balance (₹)": float(r.get("balance") or 0),
                "As on Date":  r.get("as_on_date", ""),
                "Remarks":     r.get("remarks", ""),
                "Entered By":  r.get("entered_by", ""),
                "Entry Date":  r.get("entry_date", ""),
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True, hide_index=True,
            column_config={"Balance (₹)": st.column_config.NumberColumn(format="₹%,.0f")},
        )
    else:
        st.info("No opening balance entries yet.")

    st.markdown("---")
    st.markdown("**Add Opening Balance Entry**")
    with st.form("adv_ob_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
        emp_label = c1.selectbox("Employee *", list(op_options.keys()))
        balance   = c2.number_input("Balance (₹) *", min_value=0.0, step=100.0)
        as_on     = c3.date_input("As on Date *", value=date.today())
        remarks   = c4.text_input("Remarks")
        if st.form_submit_button("Save Opening Balance", type="primary"):
            if not emp_label:
                st.error("Please select an employee.")
            else:
                sb.insert_advance_opening_balance({
                    "employee_id": op_options[emp_label],
                    "balance":     balance,
                    "as_on_date":  str(as_on),
                    "remarks":     remarks,
                    "entered_by":  _user_name(),
                    "entry_date":  str(date.today()),
                })
                st.success("Opening balance saved.")
                st.rerun()


# ── Tab 2: New Advance ─────────────────────────────────────────────────────────

def _tab_new_advance() -> None:
    st.markdown("#### New Advance Request")
    sb        = SupabaseClient()
    operators = sorted(sb.list_operators(), key=lambda o: o.get("emp_code") or "")

    op_labels: list[str] = []
    label_to_id: dict[str, str] = {}
    for o in operators:
        code  = (o.get("emp_code") or "").strip()
        name  = (o.get("operator_name") or "").strip()
        label = f"{code} – {name}" if code and name else (code or name)
        if label:
            op_labels.append(label)
            label_to_id[label] = o["id"]

    if not op_labels:
        st.warning("No operators found. Please add operators in the Operator Master first.")
        return

    _ROWS_KEY = "adv_rows_v4"
    if _ROWS_KEY not in st.session_state:
        st.session_state[_ROWS_KEY] = [
            {"label": op_labels[0], "date": date.today(), "amount": 0.0,
             "payment_mode": "UPI", "reason": ""}
        ]

    h1, h2, h3, h4, h5, h6 = st.columns([2.8, 1.6, 1.6, 1.6, 2.5, 0.5])
    h1.markdown("**Employee**")
    h2.markdown("**Date**")
    h3.markdown("**Amount (₹)**")
    h4.markdown("**Payment Mode \\***")
    h5.markdown("**Reason**")
    h6.markdown("")

    rows      = st.session_state[_ROWS_KEY]
    keep_rows = []
    for i, row in enumerate(rows):
        c1, c2, c3, c4, c5, c6 = st.columns([2.8, 1.6, 1.6, 1.6, 2.5, 0.5])
        cur_idx   = op_labels.index(row["label"]) if row["label"] in op_labels else 0
        mode_idx  = _PAYMENT_MODES.index(row.get("payment_mode", "UPI")) \
                    if row.get("payment_mode") in _PAYMENT_MODES else 0

        sel_label = c1.selectbox("Employee", op_labels, index=cur_idx,
                                 key=f"adv_emp_{i}", label_visibility="collapsed")
        sel_date  = c2.date_input("Date", value=row["date"],
                                  key=f"adv_date_{i}", label_visibility="collapsed")
        sel_amt   = c3.number_input("Amount", min_value=0.0, step=500.0,
                                    value=float(row["amount"]),
                                    key=f"adv_amt_{i}", label_visibility="collapsed")
        sel_mode  = c4.selectbox("Mode", _PAYMENT_MODES, index=mode_idx,
                                 key=f"adv_mode_{i}", label_visibility="collapsed")
        sel_rsn   = c5.text_input("Reason", value=row["reason"],
                                  key=f"adv_rsn_{i}", label_visibility="collapsed")
        remove    = c6.button("✕", key=f"adv_del_{i}")
        if not remove:
            keep_rows.append({
                "label":        sel_label,
                "date":         sel_date,
                "amount":       sel_amt,
                "payment_mode": sel_mode,
                "reason":       sel_rsn,
            })

    st.session_state[_ROWS_KEY] = keep_rows

    col_add, col_submit, _ = st.columns([1, 2, 5])
    if col_add.button("＋ Add Row"):
        st.session_state[_ROWS_KEY].append(
            {"label": op_labels[0], "date": date.today(), "amount": 0.0,
             "payment_mode": "UPI", "reason": ""}
        )
        st.rerun()

    valid = [r for r in keep_rows if float(r["amount"]) > 0]
    total = sum(float(r["amount"]) for r in valid)
    n     = len(valid)

    if n:
        st.markdown(f"**{n} employee(s) | Total: ₹{total:,.0f}**")

    if col_submit.button("Submit to Admin ▶", type="primary", disabled=(n == 0)):
        batch_no = _generate_batch_number(sb)
        batch    = sb.insert_advance_batch({
            "batch_number":   batch_no,
            "submitted_by":   _user_name(),
            "submitted_at":   datetime.now().isoformat(),
            "employee_count": n,
            "total_amount":   total,
            "status":         "Submitted",
        })
        batch_id = batch.get("id")
        _pm_col_missing = False
        for r in valid:
            adv_date = r["date"]
            if hasattr(adv_date, "isoformat"):
                adv_date = adv_date.isoformat()
            payload = {
                "batch_id":         batch_id,
                "employee_id":      label_to_id.get(r["label"], ""),
                "advance_date":     adv_date,
                "requested_amount": float(r["amount"]),
                "payment_mode":     r["payment_mode"],
                "reason":           r["reason"],
                "status":           "Pending",
            }
            try:
                sb.insert_advance_request(payload)
            except Exception as exc:
                if "payment_mode" in str(exc) or "column" in str(exc).lower():
                    _pm_col_missing = True
                    payload.pop("payment_mode", None)
                    sb.insert_advance_request(payload)
                else:
                    raise
        if _pm_col_missing:
            st.warning(
                "Payment Mode was not saved — the `payment_mode` column is missing in Supabase. "
                "Run this once in the Supabase SQL editor to enable it:\n\n"
                "```sql\nALTER TABLE advance_requests "
                "ADD COLUMN IF NOT EXISTS payment_mode text;\n```"
            )
        st.success(
            f"Batch **{batch_no}** submitted — {n} employee(s) | ₹{total:,.0f} | Pending Approval"
        )
        st.session_state[_ROWS_KEY] = [
            {"label": op_labels[0], "date": date.today(), "amount": 0.0,
             "payment_mode": "UPI", "reason": ""}
        ]
        st.rerun()


# ── Tab 3: Pending Approval ────────────────────────────────────────────────────

def _tab_pending_approval() -> None:
    if not auth.is_admin():
        st.info("Only Admin can approve or reject advance requests.", icon="🔒")
        return

    st.markdown("#### Pending Approval")
    sb = SupabaseClient()
    operators = sb.list_operators()
    op_by_id  = {o["id"]: o for o in operators}
    all_reqs  = sb.list_advance_requests(status="Pending")
    batches   = {b["id"]: b for b in sb.list_advance_batches()}

    if not all_reqs:
        st.info("No pending advance requests.")
        return

    today = date.today()
    fc    = st.columns([1, 1, 1, 1])
    period = fc[0].selectbox("Period", ["Today", "Last 2 Days", "Last 7 Days", "Custom"],
                              key="adv_ap_period")
    if period == "Today":
        date_from = today
    elif period == "Last 2 Days":
        date_from = today - timedelta(days=1)
    elif period == "Last 7 Days":
        date_from = today - timedelta(days=6)
    else:
        date_from = fc[1].date_input("From", value=today - timedelta(days=30), key="adv_ap_from")

    emp_names_in_list = sorted({
        op_by_id[r["employee_id"]].get("operator_name", r["employee_id"])
        for r in all_reqs if r.get("employee_id") in op_by_id
    })
    emp_filter = fc[2].selectbox("Employee", ["All"] + emp_names_in_list, key="adv_ap_emp")

    filtered = []
    for r in all_reqs:
        adv_date = date.fromisoformat(r["advance_date"]) if r.get("advance_date") else today
        if adv_date < date_from or adv_date > today:
            continue
        op       = op_by_id.get(r.get("employee_id", ""), {})
        emp_name = op.get("operator_name", "")
        if emp_filter != "All" and emp_name != emp_filter:
            continue
        filtered.append(r)

    if not filtered:
        st.info("No requests match the selected filters.")
        return

    st.markdown(f"**{len(filtered)} request(s) pending**")

    for r in filtered:
        emp_id   = r.get("employee_id", "")
        op       = op_by_id.get(emp_id, {})
        emp_name = op.get("operator_name", emp_id)
        emp_code = op.get("emp_code", "")
        batch    = batches.get(r.get("batch_id", ""), {})
        req_amt  = float(r.get("requested_amount") or 0)

        _emp_pays = sb.list_advance_payments(employee_id=emp_id)
        _emp_open = sb.list_advance_opening_balances(employee_id=emp_id)
        _emp_recv = sb.list_advance_recoveries(employee_id=emp_id)
        bal = _compute_balance_from(_emp_open, _emp_pays, _emp_recv, today)

        title = (
            f"{emp_name}  ({emp_code})  |  "
            f"₹{req_amt:,.0f}  |  "
            f"{r.get('advance_date', '')}  |  "
            f"Mode: {r.get('payment_mode') or '—'}"
        )
        with st.expander(title):
            ic = st.columns(4)
            ic[0].metric("Existing Balance",  f"₹{bal['balance']:,.0f}")
            ic[1].metric("Requested Amount",  f"₹{req_amt:,.0f}")
            ic[2].metric("Submitted By",      batch.get("submitted_by", ""))
            ic[3].metric("Reason",            r.get("reason", "") or "—")

            approved_amt = st.number_input(
                "Approved Amount (₹)",
                min_value=0.0,
                value=req_amt,
                step=100.0,
                key=f"adv_ap_amt_{r['id']}",
            )
            remarks = st.text_input(
                "Remarks / Reason for change",
                key=f"adv_ap_rmk_{r['id']}",
                help="Mandatory when rejecting or when approved amount differs from requested.",
            )

            bc = st.columns([1, 1, 4])
            if bc[0].button("✅ Approve", key=f"adv_ok_{r['id']}", type="primary"):
                if approved_amt != req_amt and not remarks:
                    st.error("Reason is mandatory when changing the approved amount.")
                else:
                    sb.update_advance_request(r["id"], {
                        "status":               "Approved",
                        "approved_amount":      approved_amt,
                        "approval_remarks":     remarks,
                        "amount_change_reason": remarks if approved_amt != req_amt else None,
                        "approved_by":          _user_name(),
                        "approved_at":          datetime.now().isoformat(),
                    })
                    sb.insert_advance_payment({
                        "advance_request_id": r["id"],
                        "employee_id":        emp_id,
                        "amount":             approved_amt,
                        "payment_status":     "Pending",
                    })
                    st.success(f"Approved ₹{approved_amt:,.0f} for {emp_name}.")
                    st.rerun()

            if bc[1].button("❌ Reject", key=f"adv_no_{r['id']}"):
                if not remarks:
                    st.error("Reason is mandatory when rejecting.")
                else:
                    sb.update_advance_request(r["id"], {
                        "status":           "Rejected",
                        "approved_amount":  0,
                        "approval_remarks": remarks,
                        "approved_by":      _user_name(),
                        "approved_at":      datetime.now().isoformat(),
                    })
                    st.success(f"Rejected advance request for {emp_name}.")
                    st.rerun()


# ── Tab 4: Pending Payment ─────────────────────────────────────────────────────

def _tab_pending_payment() -> None:
    st.markdown("#### Pending Payment")
    sb        = SupabaseClient()
    operators = sb.list_operators()
    op_by_id  = {o["id"]: o for o in operators}
    op_labels = {
        o["id"]: f"{o.get('emp_code', '')} – {o.get('operator_name', '')}".strip(" –")
        for o in operators
    }

    all_payments  = sb.list_advance_payments()
    all_reqs_list = sb.list_advance_requests()
    all_requests  = {r["id"]: r for r in all_reqs_list}

    # ── Filters ────────────────────────────────────────────────────────────────
    fc = st.columns([2, 2, 2])
    label_options = ["All"] + [lbl for lbl in op_labels.values() if lbl]
    emp_filter    = fc[0].selectbox("Employee", label_options, key="adv_ph_emp")

    enriched = []
    for p in all_payments:
        emp_id   = p.get("employee_id", "")
        op       = op_by_id.get(emp_id, {})
        emp_name = op.get("operator_name", emp_id)
        emp_code = op.get("emp_code", "")
        emp_lbl  = op_labels.get(emp_id, "")
        if emp_filter != "All" and emp_lbl != emp_filter:
            continue
        req = all_requests.get(p.get("advance_request_id", ""), {})
        enriched.append({
            "Employee":        f"{emp_name} ({emp_code})",
            "Advance Date":    req.get("advance_date", ""),
            "Amount (₹)":      float(p.get("amount") or 0),
            "Payment Mode":    req.get("payment_mode") or "—",
            "Approval Date":   str(req.get("approved_at") or "")[:10],
            "Payment Date":    p.get("payment_date") or "",
            "Status":          p.get("payment_status") or "Pending",
            "UTR / Reference": p.get("utr_reference") or "",
            "_id":             p["id"],
            "_emp_id":         emp_id,
        })

    pending_list = [r for r in enriched if r["Status"] == "Pending"]
    paid_list    = [r for r in enriched if r["Status"] == "Paid"]

    # ── Pending section ────────────────────────────────────────────────────────
    if not pending_list:
        st.info("No pending payments.")
    else:
        st.markdown(f"**{len(pending_list)} payment(s) awaiting disbursement**")

        # Print / download voucher
        print_col, _ = st.columns([2, 6])
        html_voucher = _build_print_html(pending_list, op_by_id)
        print_col.download_button(
            label="🖨 Download Payment Voucher",
            data=html_voucher.encode("utf-8"),
            file_name=f"advance_voucher_{date.today()}.html",
            mime="text/html",
            help="Open the downloaded file in a browser and use Ctrl+P to print.",
        )

        if auth.is_admin():
            st.markdown("**Select entries to mark as paid:**")
            # Select All convenience
            all_key  = "adv_sel_all"
            select_all = st.checkbox("Select All", key=all_key)

            for p in pending_list:
                cb_key   = f"pay_sel_{p['_id']}"
                default  = select_all or st.session_state.get(cb_key, False)
                st.checkbox(
                    f"{p['Employee']}  |  ₹{p['Amount (₹)']:,.0f}  |  "
                    f"Approved: {p['Approval Date']}  |  Mode: {p['Payment Mode']}",
                    key=cb_key,
                    value=default,
                )

            selected = [p for p in pending_list
                        if st.session_state.get(f"pay_sel_{p['_id']}", False)]

            if selected:
                st.markdown(
                    f"**{len(selected)} selected — Total: "
                    f"₹{sum(r['Amount (₹)'] for r in selected):,.0f}**"
                )
                mc1, mc2 = st.columns([1, 2])
                bulk_date = mc1.date_input("Payment Date", value=date.today(),
                                            key="adv_bulk_pdate")
                bulk_utr  = mc2.text_input("UTR / Reference", key="adv_bulk_utr",
                                            placeholder="Common UTR or leave blank")
                if st.button(
                    f"✅ Mark {len(selected)} Payment(s) as Paid", type="primary",
                    key="adv_bulk_mark_paid"
                ):
                    for p in selected:
                        sb.update_advance_payment(p["_id"], {
                            "payment_date":   str(bulk_date),
                            "payment_status": "Paid",
                            "utr_reference":  bulk_utr,
                            "paid_by":        _user_name(),
                            "paid_at":        datetime.now().isoformat(),
                        })
                    st.success(
                        f"Marked {len(selected)} payment(s) as Paid on {bulk_date}."
                    )
                    # Clear checkboxes
                    for p in selected:
                        st.session_state.pop(f"pay_sel_{p['_id']}", None)
                    st.session_state.pop(all_key, None)
                    st.rerun()
        else:
            # Non-admin: read-only view
            df_pending = pd.DataFrame([{
                "Employee":     p["Employee"],
                "Advance Date": p["Advance Date"],
                "Amount (₹)":   p["Amount (₹)"],
                "Payment Mode": p["Payment Mode"],
            } for p in pending_list])
            st.dataframe(
                df_pending, use_container_width=True, hide_index=True,
                column_config={"Amount (₹)": st.column_config.NumberColumn(format="₹%,.0f")},
            )

    # ── Paid history section ───────────────────────────────────────────────────
    if paid_list:
        st.markdown("---")
        st.markdown("**Paid History**")

        if auth.is_admin():
            st.caption("Select entries below to revert them to Unpaid (Pending) status.")
            unp_all_key  = "adv_unp_sel_all"
            unp_select_all = st.checkbox("Select All", key=unp_all_key)

            for p in paid_list:
                cb_key  = f"unp_sel_{p['_id']}"
                default = unp_select_all or st.session_state.get(cb_key, False)
                st.checkbox(
                    f"{p['Employee']}  |  ₹{p['Amount (₹)']:,.0f}  |  "
                    f"Paid: {p['Payment Date']}  |  UTR: {p['UTR / Reference'] or '—'}",
                    key=cb_key,
                    value=default,
                )

            unp_selected = [p for p in paid_list
                            if st.session_state.get(f"unp_sel_{p['_id']}", False)]

            if unp_selected:
                st.markdown(
                    f"**{len(unp_selected)} selected — Total: "
                    f"₹{sum(r['Amount (₹)'] for r in unp_selected):,.0f}**"
                )
                if st.button(
                    f"↩ Mark {len(unp_selected)} Payment(s) as Unpaid",
                    key="adv_bulk_mark_unpaid",
                    type="secondary",
                ):
                    for p in unp_selected:
                        sb.update_advance_payment(p["_id"], {
                            "payment_status": "Pending",
                            "payment_date":   None,
                            "utr_reference":  None,
                            "paid_by":        None,
                            "paid_at":        None,
                        })
                    st.success(
                        f"Reverted {len(unp_selected)} payment(s) back to Pending."
                    )
                    for p in unp_selected:
                        st.session_state.pop(f"unp_sel_{p['_id']}", None)
                    st.session_state.pop(unp_all_key, None)
                    st.rerun()

        st.markdown("")
        df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")}
                           for r in paid_list])
        st.dataframe(
            df, use_container_width=True, hide_index=True,
            column_config={"Amount (₹)": st.column_config.NumberColumn(format="₹%,.0f")},
        )


# ── Tab 5: Current Advance ─────────────────────────────────────────────────────

def _tab_current_advance() -> None:
    st.markdown("#### Current Advance Balances")
    sb        = SupabaseClient()
    operators = sb.list_operators()

    as_on = st.date_input("As on Date", value=date.today(), key="adv_cur_date")

    with st.spinner("Loading advance data…"):
        all_openings   = sb.list_advance_opening_balances()
        all_payments   = sb.list_advance_payments()
        all_recoveries = sb.list_advance_recoveries()

    from collections import defaultdict
    openings_by_emp   = defaultdict(list)
    payments_by_emp   = defaultdict(list)
    recoveries_by_emp = defaultdict(list)
    for r in all_openings:
        openings_by_emp[r.get("employee_id", "")].append(r)
    for p in all_payments:
        payments_by_emp[p.get("employee_id", "")].append(p)
    for r in all_recoveries:
        recoveries_by_emp[r.get("employee_id", "")].append(r)

    rows = []
    for op in operators:
        eid = op["id"]
        bal = _compute_balance_from(
            openings_by_emp[eid],
            payments_by_emp[eid],
            recoveries_by_emp[eid],
            as_on,
        )
        if bal["opening"] == 0 and bal["advances_given"] == 0 and bal["recoveries"] == 0:
            continue
        rows.append({
            "Employee":           op.get("operator_name", eid),
            "Emp Code":           op.get("emp_code", ""),
            "Opening (₹)":        bal["opening"],
            "Advances Given (₹)": bal["advances_given"],
            "Recoveries (₹)":     bal["recoveries"],
            "Balance (₹)":        bal["balance"],
            "_id":                eid,
        })

    if not rows:
        st.info("No advance balances found as on selected date.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(
        df.drop(columns=["_id"]),
        use_container_width=True, hide_index=True,
        column_config={
            "Opening (₹)":        st.column_config.NumberColumn(format="₹%,.0f"),
            "Advances Given (₹)": st.column_config.NumberColumn(format="₹%,.0f"),
            "Recoveries (₹)":     st.column_config.NumberColumn(format="₹%,.0f"),
            "Balance (₹)":        st.column_config.NumberColumn(format="₹%,.0f"),
        },
    )

    emp_options = ["—"] + [r["Employee"] for r in rows]
    sel = st.selectbox("View Ledger for Employee:", emp_options, key="adv_cur_sel")
    if sel != "—":
        emp_id = next(r["_id"] for r in rows if r["Employee"] == sel)
        st.markdown(f"**Advance Ledger — {sel}**")
        _render_ledger(sb, emp_id, as_on,
                       all_openings=all_openings,
                       all_payments=all_payments,
                       all_recoveries=all_recoveries)


# ── Tab 6: Advance Ledger ──────────────────────────────────────────────────────

def _tab_advance_ledger() -> None:
    st.markdown("#### Advance Ledger")
    sb        = SupabaseClient()
    operators = sb.list_operators()
    op_options = {
        f"{o.get('emp_code', '')} – {o.get('operator_name', '')}".strip(" –"): o["id"]
        for o in operators
    }

    sel = st.selectbox("Select Employee", ["—"] + list(op_options.keys()), key="adv_ledger_emp")
    if sel == "—":
        st.info("Select an employee to view their full transaction history.")
        return

    _render_ledger(sb, op_options[sel])


# ── Entry point ────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div style='margin-bottom:4px;font-size:11px;font-weight:700;letter-spacing:.15em;
        color:#94A3B8;text-transform:uppercase;'>// Payroll</div>
        <div style='font-size:28px;font-weight:800;color:#1E293B;margin-bottom:20px;'>
        Advance Management</div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs([
        "📂  Opening Balance",
        "➕  New Advance",
        "⏳  Pending Approval",
        "💳  Pending Payment",
        "💰  Current Advance",
        "📒  Advance Ledger",
    ])
    with tabs[0]: _tab_opening_balance()
    with tabs[1]: _tab_new_advance()
    with tabs[2]: _tab_pending_approval()
    with tabs[3]: _tab_pending_payment()
    with tabs[4]: _tab_current_advance()
    with tabs[5]: _tab_advance_ledger()
