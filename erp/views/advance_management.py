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
            })
        total = sum(r["Balance (₹)"] for r in rows)

        # Header
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"margin-bottom:10px;'>"
            f"<span style='font-size:13px;font-weight:700;color:#1E293B;'>"
            f"{len(rows)} Opening Balance Entr{'y' if len(rows)==1 else 'ies'}</span>"
            f"<span style='font-size:13px;font-weight:800;color:#10B981;'>"
            f"Total: ₹{total:,.0f}</span></div>",
            unsafe_allow_html=True,
        )

        # Table with bold employee names
        hs = ("padding:8px 12px;background:#F8FAFC;font-size:10px;font-weight:700;"
              "letter-spacing:.1em;text-transform:uppercase;color:#64748B;"
              "border-bottom:2px solid #E2EBF0;")
        cs = "padding:9px 12px;font-size:13px;border-bottom:1px solid #F1F5F9;"
        cols = ["Employee", "Emp Code", "Balance (₹)", "As on Date", "Remarks", "Entered By"]
        head = "".join(f"<th style='{hs}'>{c}</th>" for c in cols)
        body = ""
        for r in rows:
            body += (
                f"<tr>"
                f"<td style='{cs}font-weight:700;color:#1E293B;'>{r['Employee']}</td>"
                f"<td style='{cs}color:#64748B;'>{r['Emp Code']}</td>"
                f"<td style='{cs}font-variant-numeric:tabular-nums;font-weight:600;color:#0F766E;'>"
                f"₹{r['Balance (₹)']:,.0f}</td>"
                f"<td style='{cs}color:#64748B;'>{r['As on Date']}</td>"
                f"<td style='{cs}color:#64748B;'>{r['Remarks'] or '—'}</td>"
                f"<td style='{cs}color:#64748B;'>{r['Entered By'] or '—'}</td>"
                f"</tr>"
            )
        total_row = (
            f"<tr style='background:#F0FDF4;font-weight:800;'>"
            f"<td style='{cs}color:#166534;' colspan='2'>Total</td>"
            f"<td style='{cs}color:#166534;font-size:14px;'>₹{total:,.0f}</td>"
            f"<td colspan='3' style='{cs}'></td></tr>"
        )
        st.markdown(
            f"<div style='overflow-x:auto;border:1px solid #E2EBF0;border-radius:10px;'>"
            f"<table style='width:100%;border-collapse:collapse;'>"
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{body}{total_row}</tbody>"
            f"</table></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("No opening balance entries yet.")

    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(
            "<span style='font-size:11px;font-weight:700;letter-spacing:.1em;"
            "text-transform:uppercase;color:#E87722;'>Add Opening Balance Entry</span>",
            unsafe_allow_html=True,
        )
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

    st.markdown(
        f"<div style='font-size:13px;color:#64748B;margin-bottom:16px;'>"
        f"<strong style='color:#1E293B;'>{len(filtered)}</strong> request(s) awaiting approval</div>",
        unsafe_allow_html=True,
    )

    # Pre-fetch bulk data to avoid N+1 queries
    all_opens  = sb.list_advance_opening_balances()
    all_pays   = sb.list_advance_payments()
    all_recvs  = sb.list_advance_recoveries()

    for r in filtered:
        emp_id   = r.get("employee_id", "")
        op       = op_by_id.get(emp_id, {})
        emp_name = op.get("operator_name", emp_id)
        emp_code = op.get("emp_code", "")
        batch    = batches.get(r.get("batch_id", ""), {})
        req_amt  = float(r.get("requested_amount") or 0)

        bal = _compute_balance_from(
            [x for x in all_opens if x.get("employee_id") == emp_id],
            [x for x in all_pays  if x.get("employee_id") == emp_id],
            [x for x in all_recvs if x.get("employee_id") == emp_id],
            today,
        )

        parts    = emp_name.strip().split()
        initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

        reason_html = (
            f"<div style='margin-top:8px;font-size:12px;color:#64748B;'>"
            f"📝 <em>{r.get('reason', '')}</em></div>"
            if r.get("reason") else ""
        )

        st.markdown(
            f"""
            <div style='border:1px solid #E2EBF0;border-radius:14px;padding:18px 20px 14px;
                        margin-bottom:4px;background:#FFFFFF;box-shadow:0 1px 4px rgba(0,0,0,.06);'>
              <div style='display:flex;align-items:flex-start;gap:14px;'>
                <div style='width:44px;height:44px;border-radius:50%;background:#E0F2FE;
                            display:flex;align-items:center;justify-content:center;
                            font-size:16px;font-weight:800;color:#0284C7;flex-shrink:0;'>
                  {initials}
                </div>
                <div style='flex:1;'>
                  <div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap;'>
                    <span style='font-size:15px;font-weight:800;color:#1E293B;'>{emp_name}</span>
                    <span style='font-size:11px;color:#64748B;background:#F1F5F9;
                                 padding:2px 8px;border-radius:20px;'>{emp_code}</span>
                    <span style='font-size:11px;font-weight:700;color:#D97706;background:#FEF3C7;
                                 padding:2px 8px;border-radius:20px;'>⏳ Awaiting Approval</span>
                  </div>
                  <div style='display:flex;gap:28px;margin-top:10px;flex-wrap:wrap;'>
                    <div>
                      <div style='font-size:10px;color:#94A3B8;text-transform:uppercase;
                                  letter-spacing:.08em;'>Requested Amount</div>
                      <div style='font-size:22px;font-weight:800;color:#1E293B;'>
                        ₹{req_amt:,.0f}</div>
                    </div>
                    <div>
                      <div style='font-size:10px;color:#94A3B8;text-transform:uppercase;
                                  letter-spacing:.08em;'>Existing Balance</div>
                      <div style='font-size:18px;font-weight:700;
                                  color:{"#DC2626" if bal["balance"]>0 else "#64748B"};'>
                        ₹{bal['balance']:,.0f}</div>
                    </div>
                    <div>
                      <div style='font-size:10px;color:#94A3B8;text-transform:uppercase;
                                  letter-spacing:.08em;'>Payment Mode</div>
                      <div style='font-size:14px;font-weight:600;color:#475569;'>
                        {r.get('payment_mode') or '—'}</div>
                    </div>
                    <div>
                      <div style='font-size:10px;color:#94A3B8;text-transform:uppercase;
                                  letter-spacing:.08em;'>Advance Date</div>
                      <div style='font-size:14px;font-weight:600;color:#475569;'>
                        {r.get('advance_date', '')}</div>
                    </div>
                    <div>
                      <div style='font-size:10px;color:#94A3B8;text-transform:uppercase;
                                  letter-spacing:.08em;'>Submitted By</div>
                      <div style='font-size:14px;font-weight:600;color:#475569;'>
                        {batch.get('submitted_by', '—')}</div>
                    </div>
                  </div>
                  {reason_html}
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        ci1, ci2, ci3 = st.columns([1.2, 2, 4])
        approved_amt = ci1.number_input(
            "Approved Amount (₹)",
            min_value=0.0, value=req_amt, step=100.0,
            key=f"adv_ap_amt_{r['id']}",
        )
        remarks = ci2.text_input(
            "Comment / Reason for change",
            key=f"adv_ap_rmk_{r['id']}",
            help="Mandatory when rejecting or changing the approved amount.",
        )

        bc1, bc2, _ = st.columns([1, 1, 6])
        if bc1.button("✅ Approve", key=f"adv_ok_{r['id']}", type="primary"):
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

        if bc2.button("❌ Reject", key=f"adv_no_{r['id']}"):
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

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)


# ── Tab 4: Pending Payment ─────────────────────────────────────────────────────

def _tab_pending_payment() -> None:
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

    today = date.today()

    # ── Filter bar ─────────────────────────────────────────────────────────────
    fc = st.columns([2, 1.5, 1.5, 1.5])
    label_options = ["All"] + sorted(lbl for lbl in op_labels.values() if lbl)
    emp_filter  = fc[0].selectbox("Employee", label_options, key="adv_ph_emp")
    mode_filter = fc[1].selectbox("Payment Mode", ["All"] + _PAYMENT_MODES, key="adv_ph_mode")
    period      = fc[2].selectbox("Date Range",
                                   ["All Time", "Last 7 Days", "This Month", "Custom"],
                                   key="adv_ph_period")
    if period == "Last 7 Days":
        date_from, date_to = today - timedelta(days=6), today
    elif period == "This Month":
        date_from, date_to = today.replace(day=1), today
    elif period == "Custom":
        dc = fc[3].date_input("Range", value=(today - timedelta(days=30), today),
                               key="adv_ph_range")
        date_from = dc[0] if isinstance(dc, tuple) else dc
        date_to   = dc[1] if isinstance(dc, tuple) and len(dc) > 1 else today
    else:
        date_from = date_to = None

    # ── Enrich and filter ──────────────────────────────────────────────────────
    enriched = []
    for p in all_payments:
        emp_id   = p.get("employee_id", "")
        op       = op_by_id.get(emp_id, {})
        emp_name = op.get("operator_name", emp_id)
        emp_code = op.get("emp_code", "")
        emp_lbl  = op_labels.get(emp_id, "")
        req      = all_requests.get(p.get("advance_request_id", ""), {})
        mode     = req.get("payment_mode") or "—"
        appr_date = str(req.get("approved_at") or "")[:10]
        pay_date  = p.get("payment_date") or ""

        if emp_filter != "All" and emp_lbl != emp_filter:
            continue
        if mode_filter != "All" and mode != mode_filter:
            continue
        ref_d = appr_date or pay_date
        if date_from and ref_d and ref_d < str(date_from):
            continue
        if date_to and ref_d and ref_d > str(date_to):
            continue

        enriched.append({
            "Employee":        f"{emp_name} ({emp_code})",
            "Advance Date":    req.get("advance_date", ""),
            "Amount (₹)":      float(p.get("amount") or 0),
            "Payment Mode":    mode,
            "Approval Date":   appr_date,
            "Payment Date":    pay_date,
            "Status":          p.get("payment_status") or "Pending",
            "UTR / Reference": p.get("utr_reference") or "",
            "_id":             p["id"],
            "_emp_id":         emp_id,
        })

    pending_list = [r for r in enriched if r["Status"] == "Pending"]
    paid_list    = [r for r in enriched if r["Status"] == "Paid"]

    # ── Pending section ────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:13px;font-weight:700;color:#1E293B;margin:12px 0 8px;'>"
        f"Awaiting Disbursement "
        f"<span style='font-weight:400;color:#64748B;'>({len(pending_list)} payment(s))</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not pending_list:
        st.info("No pending payments.")
    else:
        total_pending = sum(r["Amount (₹)"] for r in pending_list)
        act1, act2, _ = st.columns([1.5, 1.5, 5])

        html_voucher = _build_print_html(pending_list, op_by_id)
        act1.download_button(
            label="Download Voucher",
            data=html_voucher.encode("utf-8"),
            file_name=f"advance_voucher_{date.today()}.html",
            mime="text/html",
            help="Open in a browser and use Ctrl+P to print.",
        )

        if auth.is_admin():
            # Build data_editor table with Select column
            _SEL_KEY = "adv_pending_sel"
            df_pending = pd.DataFrame([{
                "Select":         st.session_state.get(f"psel_{p['_id']}", False),
                "Employee":       p["Employee"],
                "Advance Date":   p["Advance Date"],
                "Amount (₹)":     p["Amount (₹)"],
                "Payment Mode":   p["Payment Mode"],
                "Approval Date":  p["Approval Date"],
                "_id":            p["_id"],
            } for p in pending_list])

            edited = st.data_editor(
                df_pending.drop(columns=["_id"]),
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config={
                    "Select":      st.column_config.CheckboxColumn("Select", default=False),
                    "Amount (₹)":  st.column_config.NumberColumn(format="₹%,.0f"),
                },
                disabled=["Employee", "Advance Date", "Amount (₹)", "Payment Mode",
                          "Approval Date"],
                key=_SEL_KEY,
            )

            selected_rows = edited[edited["Select"] == True] if "Select" in edited.columns else pd.DataFrame()  # noqa: E712
            sel_ids = list(df_pending.loc[selected_rows.index, "_id"]) if not selected_rows.empty else []
            selected = [p for p in pending_list if p["_id"] in sel_ids]

            if selected:
                sel_total = sum(r["Amount (₹)"] for r in selected)
                st.markdown(
                    f"<div style='font-size:12px;font-weight:700;color:#0F766E;"
                    f"margin:4px 0 8px;'>{len(selected)} selected — Total: ₹{sel_total:,.0f}</div>",
                    unsafe_allow_html=True,
                )
                mc1, mc2, mc3 = st.columns([1, 2, 3])
                bulk_date = mc1.date_input("Payment Date", value=date.today(), key="adv_bulk_pdate")
                bulk_utr  = mc2.text_input("UTR / Reference", key="adv_bulk_utr",
                                            placeholder="Common UTR or leave blank")
                if mc3.button(
                    f"Mark {len(selected)} Payment(s) as Paid", type="primary",
                    key="adv_bulk_mark_paid",
                ):
                    for p in selected:
                        sb.update_advance_payment(p["_id"], {
                            "payment_date":   str(bulk_date),
                            "payment_status": "Paid",
                            "utr_reference":  bulk_utr,
                            "paid_by":        _user_name(),
                            "paid_at":        datetime.now().isoformat(),
                        })
                    st.success(f"Marked {len(selected)} payment(s) as Paid on {bulk_date}.")
                    st.rerun()
        else:
            st.dataframe(
                pd.DataFrame([{
                    "Employee":     p["Employee"],
                    "Advance Date": p["Advance Date"],
                    "Amount (₹)":   p["Amount (₹)"],
                    "Payment Mode": p["Payment Mode"],
                } for p in pending_list]),
                use_container_width=True, hide_index=True,
                column_config={"Amount (₹)": st.column_config.NumberColumn(format="₹%,.0f")},
            )

    # ── Paid history section ───────────────────────────────────────────────────
    if paid_list:
        st.markdown(
            f"<div style='font-size:13px;font-weight:700;color:#1E293B;margin:20px 0 8px;'>"
            f"Paid History "
            f"<span style='font-weight:400;color:#64748B;'>({len(paid_list)} record(s))</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if auth.is_admin():
            st.caption("Select entries to revert them to Pending status.")
            df_paid = pd.DataFrame([{
                "Select":        False,
                "Employee":      p["Employee"],
                "Amount (₹)":    p["Amount (₹)"],
                "Payment Mode":  p["Payment Mode"],
                "Payment Date":  p["Payment Date"],
                "UTR":           p["UTR / Reference"],
                "_id":           p["_id"],
            } for p in paid_list])

            edited_paid = st.data_editor(
                df_paid.drop(columns=["_id"]),
                use_container_width=True, hide_index=True, num_rows="fixed",
                column_config={
                    "Select":     st.column_config.CheckboxColumn("Select", default=False),
                    "Amount (₹)": st.column_config.NumberColumn(format="₹%,.0f"),
                },
                disabled=["Employee", "Amount (₹)", "Payment Mode", "Payment Date", "UTR"],
                key="adv_paid_sel",
            )

            unp_selected_rows = edited_paid[edited_paid["Select"] == True] if "Select" in edited_paid.columns else pd.DataFrame()  # noqa: E712
            unp_ids = list(df_paid.loc[unp_selected_rows.index, "_id"]) if not unp_selected_rows.empty else []
            unp_selected = [p for p in paid_list if p["_id"] in unp_ids]

            if unp_selected:
                unp_total = sum(r["Amount (₹)"] for r in unp_selected)
                st.markdown(
                    f"<div style='font-size:12px;font-weight:700;color:#DC2626;margin:4px 0 8px;'>"
                    f"{len(unp_selected)} selected — Total: ₹{unp_total:,.0f}</div>",
                    unsafe_allow_html=True,
                )
                if st.button(
                    f"Revert {len(unp_selected)} to Pending",
                    key="adv_bulk_mark_unpaid", type="secondary",
                ):
                    for p in unp_selected:
                        sb.update_advance_payment(p["_id"], {
                            "payment_status": "Pending",
                            "payment_date":   None,
                            "utr_reference":  None,
                            "paid_by":        None,
                            "paid_at":        None,
                        })
                    st.success(f"Reverted {len(unp_selected)} payment(s) back to Pending.")
                    st.rerun()
        else:
            df = pd.DataFrame([{
                "Employee":     p["Employee"],
                "Amount (₹)":   p["Amount (₹)"],
                "Payment Mode": p["Payment Mode"],
                "Payment Date": p["Payment Date"],
                "UTR":          p["UTR / Reference"],
            } for p in paid_list])
            st.dataframe(
                df, use_container_width=True, hide_index=True,
                column_config={"Amount (₹)": st.column_config.NumberColumn(format="₹%,.0f")},
            )


# ── Tab 5: Current Advance ─────────────────────────────────────────────────────

def _tab_current_advance() -> None:
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
    total_balance = 0.0
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
        total_balance += bal["balance"]
        rows.append({
            "Employee":           op.get("operator_name", eid),
            "Emp Code":           op.get("emp_code", ""),
            "Opening (₹)":        bal["opening"],
            "Advances Given (₹)": bal["advances_given"],
            "Recoveries (₹)":     bal["recoveries"],
            "Balance (₹)":        bal["balance"],
        })

    if not rows:
        st.info("No advance balances found as on selected date.")
        return

    m1, m2 = st.columns(2)
    m1.metric("Employees with Advance", len(rows))
    m2.metric("Total Outstanding", f"₹{total_balance:,.0f}")

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True, hide_index=True,
        column_config={
            "Opening (₹)":        st.column_config.NumberColumn(format="₹%,.0f"),
            "Advances Given (₹)": st.column_config.NumberColumn(format="₹%,.0f"),
            "Recoveries (₹)":     st.column_config.NumberColumn(format="₹%,.0f"),
            "Balance (₹)":        st.column_config.NumberColumn(format="₹%,.0f"),
        },
    )
    st.caption("To view an employee's full transaction ledger, use the Advance Ledger tab.")


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


# ── Tab 7: Payment History ─────────────────────────────────────────────────────

def _tab_payment_history() -> None:
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
    batches       = {b["id"]: b for b in sb.list_advance_batches()}

    # ── Filters ────────────────────────────────────────────────────────────────
    fc = st.columns([2, 1.5, 1.5, 1.5, 1.5])
    label_options  = ["All"] + sorted(lbl for lbl in op_labels.values() if lbl)
    emp_filter     = fc[0].selectbox("Employee",  label_options,               key="adv_hist_emp")
    status_filter  = fc[1].selectbox("Status",    ["All", "Pending", "Paid"],  key="adv_hist_status")

    today = date.today()
    period = fc[2].selectbox("Period",
                              ["All Time", "This Month", "Last 3 Months", "Custom"],
                              key="adv_hist_period")
    if period == "This Month":
        date_from = today.replace(day=1)
        date_to   = today
    elif period == "Last 3 Months":
        date_from = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        date_from = date_from.replace(month=max(1, date_from.month - 2))
        date_to   = today
    elif period == "Custom":
        date_from = fc[3].date_input("From", value=today - timedelta(days=30), key="adv_hist_from")
        date_to   = fc[4].date_input("To",   value=today,                      key="adv_hist_to")
    else:
        date_from = None
        date_to   = None

    rows = []
    for p in all_payments:
        emp_id   = p.get("employee_id", "")
        op       = op_by_id.get(emp_id, {})
        emp_name = op.get("operator_name", emp_id)
        emp_code = op.get("emp_code", "")
        emp_lbl  = op_labels.get(emp_id, "")

        if emp_filter != "All" and emp_lbl != emp_filter:
            continue

        status = p.get("payment_status") or "Pending"
        if status_filter != "All" and status != status_filter:
            continue

        req       = all_requests.get(p.get("advance_request_id", ""), {})
        batch     = batches.get(req.get("batch_id", ""), {})
        pay_date  = p.get("payment_date") or ""
        appr_date = str(req.get("approved_at") or "")[:10]

        ref_date_str = pay_date or appr_date
        if date_from and ref_date_str and ref_date_str < str(date_from):
            continue
        if date_to and ref_date_str and ref_date_str > str(date_to):
            continue

        rows.append({
            "Employee":        f"{emp_name} ({emp_code})",
            "Advance Date":    req.get("advance_date", ""),
            "Amount (₹)":      float(p.get("amount") or 0),
            "Approval Date":   appr_date,
            "Payment Date":    pay_date,
            "Payment Status":  status,
            "UTR / Reference": p.get("utr_reference") or "—",
            "Batch No.":       batch.get("batch_number") or "—",
        })

    if not rows:
        st.info("No payment records found for the selected filters.")
        return

    total_paid    = sum(r["Amount (₹)"] for r in rows if r["Payment Status"] == "Paid")
    total_pending = sum(r["Amount (₹)"] for r in rows if r["Payment Status"] == "Pending")
    n_paid        = sum(1 for r in rows if r["Payment Status"] == "Paid")
    n_pending     = sum(1 for r in rows if r["Payment Status"] == "Pending")

    # Summary cards
    st.markdown(
        f"""
        <div style='display:flex;gap:14px;margin-bottom:16px;flex-wrap:wrap;'>
          <div style='flex:1;min-width:140px;background:#F0FDF4;border:1px solid #BBF7D0;
                      border-radius:12px;padding:14px 18px;'>
            <div style='font-size:10px;font-weight:700;text-transform:uppercase;
                        letter-spacing:.1em;color:#166534;'>Total Paid</div>
            <div style='font-size:22px;font-weight:800;color:#15803D;'>₹{total_paid:,.0f}</div>
            <div style='font-size:11px;color:#166534;'>{n_paid} payment(s)</div>
          </div>
          <div style='flex:1;min-width:140px;background:#FFF7ED;border:1px solid #FED7AA;
                      border-radius:12px;padding:14px 18px;'>
            <div style='font-size:10px;font-weight:700;text-transform:uppercase;
                        letter-spacing:.1em;color:#92400E;'>Total Pending</div>
            <div style='font-size:22px;font-weight:800;color:#D97706;'>₹{total_pending:,.0f}</div>
            <div style='font-size:11px;color:#92400E;'>{n_pending} payment(s)</div>
          </div>
          <div style='flex:1;min-width:140px;background:#F8FAFC;border:1px solid #E2EBF0;
                      border-radius:12px;padding:14px 18px;'>
            <div style='font-size:10px;font-weight:700;text-transform:uppercase;
                        letter-spacing:.1em;color:#64748B;'>Total Records</div>
            <div style='font-size:22px;font-weight:800;color:#1E293B;'>{len(rows)}</div>
            <div style='font-size:11px;color:#64748B;'>matching filters</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Amount (₹)":     st.column_config.NumberColumn(format="₹%,.0f"),
            "Payment Status": st.column_config.TextColumn(),
        },
    )


# ── Tab 8: Advance Recovery Through Payroll ───────────────────────────────────

def _tab_advance_recovery() -> None:
    import calendar

    if not auth.is_admin():
        st.info("Only Admin can process advance recovery.", icon="🔒")
        return

    sb = SupabaseClient()
    operators = sb.list_operators()

    # ── Month / Year selector ─────────────────────────────────────────────────
    cy, cm, _ = st.columns([1, 1, 4])
    sel_year  = cy.number_input(
        "Year", min_value=2020, max_value=2035,
        value=date.today().year, step=1, key="rec_year",
    )
    sel_month = cm.selectbox(
        "Month", list(range(1, 13)),
        index=date.today().month - 1,
        format_func=lambda m: date(2000, m, 1).strftime("%B"),
        key="rec_month",
    )
    payroll_month = f"{int(sel_year)}-{int(sel_month):02d}"
    last_day      = calendar.monthrange(int(sel_year), int(sel_month))[1]
    as_on         = date(int(sel_year), int(sel_month), last_day)

    month_label = date(int(sel_year), int(sel_month), 1).strftime("%B %Y")
    st.markdown(
        f"<div style='font-size:13px;font-weight:700;color:#1E293B;margin:8px 0 14px;'>"
        f"Recovery for <span style='color:#E87722;'>{month_label}</span></div>",
        unsafe_allow_html=True,
    )

    # ── Bulk data load ─────────────────────────────────────────────────────────
    with st.spinner("Loading advance balances…"):
        all_openings   = sb.list_advance_opening_balances()
        all_payments   = sb.list_advance_payments()
        all_recoveries = sb.list_advance_recoveries()

    from collections import defaultdict
    openings_by_emp   = defaultdict(list)
    payments_by_emp   = defaultdict(list)
    recoveries_by_emp = defaultdict(list)
    for r in all_openings:   openings_by_emp[r.get("employee_id", "")].append(r)
    for p in all_payments:   payments_by_emp[p.get("employee_id", "")].append(p)
    for r in all_recoveries: recoveries_by_emp[r.get("employee_id", "")].append(r)

    already_processed = {
        r["employee_id"]: r for r in all_recoveries
        if r.get("payroll_month") == payroll_month
    }

    # ── Build eligible operator list ──────────────────────────────────────────
    eligible = []
    for op in operators:
        eid = op["id"]
        bal = _compute_balance_from(
            openings_by_emp[eid],
            payments_by_emp[eid],
            recoveries_by_emp[eid],
            as_on,
        )
        if bal["balance"] <= 0 and eid not in already_processed:
            continue
        if eid in already_processed:
            done_rec = already_processed[eid]
            eligible.append({
                "emp_id":      eid,
                "emp_name":    op.get("operator_name", eid),
                "emp_code":    op.get("emp_code", ""),
                "outstanding": round(bal["balance"], 2),
                "suggested":   round(float(done_rec.get("suggested_recovery") or 0), 2),
                "final":       round(float(done_rec.get("final_recovery") or 0), 2),
                "reason":      done_rec.get("change_reason") or "",
                "done":        True,
            })
        else:
            eligible.append({
                "emp_id":      eid,
                "emp_name":    op.get("operator_name", eid),
                "emp_code":    op.get("emp_code", ""),
                "outstanding": round(bal["balance"], 2),
                "suggested":   round(bal["balance"], 2),
                "final":       round(bal["balance"], 2),
                "reason":      "",
                "done":        False,
            })

    if not eligible:
        st.info(f"No operators with outstanding advance balance as of {month_label}.")
        return

    processable = [e for e in eligible if not e["done"]]
    done_list   = [e for e in eligible if e["done"]]

    # ── data_editor for pending operators ─────────────────────────────────────
    _DE_KEY = f"adv_rec_de_{payroll_month}"

    if processable:
        st.markdown(
            f"<div style='font-size:12px;font-weight:700;color:#1E293B;margin-bottom:6px;'>"
            f"Pending — {len(processable)} operator(s)</div>",
            unsafe_allow_html=True,
        )

        init_df = pd.DataFrame([{
            "Employee":         f"{e['emp_name']} ({e['emp_code']})",
            "Outstanding (₹)":  e["outstanding"],
            "Suggested (₹)":    e["suggested"],
            "Final Recovery (₹)": e["final"],
            "Reason":           e["reason"],
            "_id":              e["emp_id"],
        } for e in processable])

        if _DE_KEY not in st.session_state:
            st.session_state[_DE_KEY] = init_df.copy()

        edited = st.data_editor(
            st.session_state[_DE_KEY].drop(columns=["_id"]),
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Outstanding (₹)":    st.column_config.NumberColumn(format="₹%,.0f"),
                "Suggested (₹)":      st.column_config.NumberColumn(format="₹%,.0f"),
                "Final Recovery (₹)": st.column_config.NumberColumn(
                    format="₹%,.0f", min_value=0,
                    help="Edit to set final recovery amount. Add Reason if different from Suggested.",
                ),
                "Reason": st.column_config.TextColumn(
                    help="Required when Final Recovery differs from Suggested",
                ),
            },
            disabled=["Employee", "Outstanding (₹)", "Suggested (₹)"],
            key=f"adv_rec_editor_{payroll_month}",
        )

        # Validation
        validation_errors: list[str] = []
        for i, row in edited.iterrows():
            final_val = float(row["Final Recovery (₹)"] or 0)
            sugg_val  = float(init_df.at[i, "Suggested (₹)"] or 0)
            if round(final_val, 2) != round(sugg_val, 2) and not str(row["Reason"]).strip():
                validation_errors.append(
                    f"{row['Employee']}: Reason is required when final recovery differs from suggested."
                )

        # Summary
        total_out      = sum(e["outstanding"] for e in processable)
        total_recovery = edited["Final Recovery (₹)"].fillna(0).astype(float).sum()
        total_balance  = total_out - total_recovery

        st.markdown(
            f"""
            <div style='display:flex;gap:12px;margin:10px 0;flex-wrap:wrap;'>
              <div style='background:#F8FAFC;border:1px solid #E2EBF0;border-radius:10px;
                          padding:10px 16px;min-width:120px;'>
                <div style='font-size:9px;font-weight:700;color:#94A3B8;
                            text-transform:uppercase;letter-spacing:.1em;'>Operators</div>
                <div style='font-size:18px;font-weight:800;color:#1E293B;'>{len(processable)}</div>
              </div>
              <div style='background:#F8FAFC;border:1px solid #E2EBF0;border-radius:10px;
                          padding:10px 16px;min-width:120px;'>
                <div style='font-size:9px;font-weight:700;color:#94A3B8;
                            text-transform:uppercase;letter-spacing:.1em;'>Total Outstanding</div>
                <div style='font-size:18px;font-weight:800;color:#DC2626;'>₹{total_out:,.0f}</div>
              </div>
              <div style='background:#F0FDF4;border:1px solid #BBF7D0;border-radius:10px;
                          padding:10px 16px;min-width:120px;'>
                <div style='font-size:9px;font-weight:700;color:#166534;
                            text-transform:uppercase;letter-spacing:.1em;'>Total Recovery</div>
                <div style='font-size:18px;font-weight:800;color:#15803D;'>₹{total_recovery:,.0f}</div>
              </div>
              <div style='background:#FFF7ED;border:1px solid #FED7AA;border-radius:10px;
                          padding:10px 16px;min-width:120px;'>
                <div style='font-size:9px;font-weight:700;color:#92400E;
                            text-transform:uppercase;letter-spacing:.1em;'>Balance Remaining</div>
                <div style='font-size:18px;font-weight:800;color:#D97706;'>₹{total_balance:,.0f}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if validation_errors:
            for err in validation_errors:
                st.error(err)

        if st.button(
            f"Submit & Process Recovery — {month_label}",
            type="primary", key="adv_rec_submit",
            disabled=bool(validation_errors),
        ):
            for i, row in edited.iterrows():
                eid       = init_df.at[i, "_id"]
                final_val = float(row["Final Recovery (₹)"] or 0)
                sugg_val  = float(init_df.at[i, "Suggested (₹)"] or 0)
                reason    = str(row["Reason"]).strip() if str(row["Reason"]).strip() else None
                sb.insert_advance_recovery({
                    "employee_id":        eid,
                    "payroll_month":      payroll_month,
                    "suggested_recovery": sugg_val,
                    "final_recovery":     final_val,
                    "change_reason":      reason,
                    "processed_by":       _user_name(),
                })
            st.success(
                f"Recovery processed for {len(processable)} operator(s) — {month_label}."
            )
            st.session_state.pop(_DE_KEY, None)
            st.rerun()

    # ── Already processed section ──────────────────────────────────────────────
    if done_list:
        st.markdown(
            f"<div style='font-size:12px;font-weight:700;color:#64748B;margin:18px 0 6px;'>"
            f"Already Processed — {len(done_list)} operator(s)</div>",
            unsafe_allow_html=True,
        )
        df_done = pd.DataFrame([{
            "Employee":         f"{e['emp_name']} ({e['emp_code']})",
            "Outstanding (₹)":  e["outstanding"],
            "Suggested (₹)":    e["suggested"],
            "Final Recovery (₹)": e["final"],
            "Reason":           e["reason"] or "—",
        } for e in done_list])
        st.dataframe(
            df_done, use_container_width=True, hide_index=True,
            column_config={
                "Outstanding (₹)":    st.column_config.NumberColumn(format="₹%,.0f"),
                "Suggested (₹)":      st.column_config.NumberColumn(format="₹%,.0f"),
                "Final Recovery (₹)": st.column_config.NumberColumn(format="₹%,.0f"),
            },
        )


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
        "🗂  Payment History",
        "🔄  Advance Recovery",
    ])
    with tabs[0]: _tab_opening_balance()
    with tabs[1]: _tab_new_advance()
    with tabs[2]: _tab_pending_approval()
    with tabs[3]: _tab_pending_payment()
    with tabs[4]: _tab_current_advance()
    with tabs[5]: _tab_advance_ledger()
    with tabs[6]: _tab_payment_history()
    with tabs[7]: _tab_advance_recovery()
