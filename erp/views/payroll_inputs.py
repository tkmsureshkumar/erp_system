"""
erp/views/payroll_inputs.py — Payroll Inputs: Additions (4.1) and Deductions (4.2).

Supabase tables required:

    CREATE TABLE IF NOT EXISTS payroll_additions (
        id               uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id      text NOT NULL,
        payroll_month    text NOT NULL,
        transaction_date date NOT NULL,
        category         text NOT NULL,
        amount           numeric NOT NULL,
        reason           text,
        remarks          text,
        supporting_doc   text,
        entered_by       text,
        status           text DEFAULT 'Submitted',
        created_at       timestamptz DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS payroll_deductions (
        id               uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id      text NOT NULL,
        payroll_month    text NOT NULL,
        transaction_date date NOT NULL,
        category         text NOT NULL,
        amount           numeric NOT NULL,
        reason           text,
        remarks          text,
        supporting_doc   text,
        entered_by       text,
        status           text DEFAULT 'Submitted',
        created_at       timestamptz DEFAULT now()
    );
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from .. import auth
from ..supabase_client import SupabaseClient

_ADDITION_CATEGORIES = [
    "Bonus",
    "Incentive",
    "Special Allowance",
    "Arrears",
    "Reimbursement",
    "Festival Payment",
    "Other Addition",
]

_DEDUCTION_CATEGORIES = [
    "Accommodation",
    "Food",
    "Travel",
    "Damage Recovery",
    "Uniform",
    "Penalty",
    "Other Deduction",
]

_STATUSES = ["Submitted", "Approved", "Cancelled"]


def _user_name() -> str:
    p = auth.current_profile()
    return p.get("full_name") or p.get("email") or "Unknown"


def _month_label(m: int) -> str:
    return date(2000, m, 1).strftime("%B")


def _op_map(operators: list) -> dict[str, str]:
    result = {}
    for o in operators:
        code  = (o.get("emp_code") or "").strip()
        name  = (o.get("operator_name") or "").strip()
        label = f"{code} – {name}" if code and name else (code or name)
        if label:
            result[label] = o["id"]
    return result


# ── Shared list + form section ─────────────────────────────────────────────────

def _render_section(
    table_key: str,
    categories: list[str],
    list_fn,
    insert_fn,
    update_fn,
    delete_fn,
    operators: list,
    op_map: dict,
    op_by_id: dict,
    sites: list,
) -> None:
    sb = SupabaseClient()

    # ── Filters ────────────────────────────────────────────────────────────────
    today     = date.today()
    fc        = st.columns([2, 1, 1, 1.5])
    op_labels = ["All"] + list(op_map.keys())
    emp_f     = fc[0].selectbox("Employee",      op_labels,                   key=f"{table_key}_f_emp")
    year_f    = fc[1].number_input("Year",  min_value=2020, max_value=2035,
                                    value=today.year, step=1,                 key=f"{table_key}_f_yr")
    month_f   = fc[2].selectbox("Month", ["All"] + list(range(1, 13)),
                                  format_func=lambda m: "All" if m == "All" else _month_label(m),
                                  key=f"{table_key}_f_mo")
    status_f  = fc[3].selectbox("Status", ["All"] + _STATUSES,               key=f"{table_key}_f_st")

    pm_filter = f"{int(year_f)}-{int(month_f):02d}" if month_f != "All" else None

    records = list_fn(payroll_month=pm_filter)

    # ── Table ─────────────────────────────────────────────────────────────────
    rows = []
    for r in records:
        op       = op_by_id.get(r.get("employee_id", ""), {})
        emp_name = op.get("operator_name", r.get("employee_id", ""))
        emp_code = op.get("emp_code", "")
        emp_lbl  = f"{emp_code} – {emp_name}" if emp_code else emp_name
        if emp_f != "All" and emp_lbl != emp_f:
            continue
        if status_f != "All" and r.get("status") != status_f:
            continue
        rows.append({
            "Employee":         emp_lbl,
            "Month":            r.get("payroll_month", ""),
            "Date":             r.get("transaction_date", ""),
            "Category":         r.get("category", ""),
            "Amount (₹)":       float(r.get("amount") or 0),
            "Reason":           r.get("reason") or "",
            "Remarks":          r.get("remarks") or "",
            "Supporting Doc":   r.get("supporting_doc") or "",
            "Entered By":       r.get("entered_by") or "",
            "Status":           r.get("status") or "Submitted",
            "_id":              r["id"],
        })

    if rows:
        total = sum(r["Amount (₹)"] for r in rows)
        m1, m2 = st.columns([1, 5])
        m1.metric("Total", f"₹{total:,.0f}")
        st.dataframe(
            pd.DataFrame([{k: v for k, v in r.items() if k != "_id"} for r in rows]),
            use_container_width=True, hide_index=True,
            column_config={"Amount (₹)": st.column_config.NumberColumn(format="₹%,.0f")},
        )
        # Admin actions on existing records
        if auth.is_admin():
            st.markdown("**Update Status / Delete**")
            for r in rows:
                with st.expander(
                    f"{r['Employee']}  |  {r['Category']}  |  ₹{r['Amount (₹)']:,.0f}  |  {r['Month']}"
                ):
                    ac = st.columns([2, 1, 1])
                    new_status = ac[0].selectbox(
                        "Status", _STATUSES,
                        index=_STATUSES.index(r["Status"]) if r["Status"] in _STATUSES else 0,
                        key=f"{table_key}_st_{r['_id']}",
                    )
                    if ac[1].button("Update", key=f"{table_key}_upd_{r['_id']}", type="primary"):
                        update_fn(r["_id"], {"status": new_status})
                        st.toast("Status updated.", icon="✅")
                        st.rerun()
                    if ac[2].button("Delete", key=f"{table_key}_del_{r['_id']}"):
                        delete_fn(r["_id"])
                        st.toast("Record deleted.", icon="🗑️")
                        st.rerun()
    else:
        st.info("No records found for the selected filters.")

    # ── Add new entry ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Add New Entry**")
    with st.form(f"{table_key}_add_form", clear_on_submit=True):
        r1c1, r1c2, r1c3, r1c4 = st.columns([2.5, 1, 1, 1.5])
        emp_label   = r1c1.selectbox("Employee *", list(op_map.keys()))
        form_year   = r1c2.number_input("Year",  min_value=2020, max_value=2035,
                                         value=today.year, step=1)
        form_month  = r1c3.selectbox("Month", list(range(1, 13)),
                                      index=today.month - 1,
                                      format_func=_month_label)
        txn_date    = r1c4.date_input("Transaction Date *", value=today)

        r2c1, r2c2, r2c3 = st.columns([2, 1.5, 1.5])
        category    = r2c1.selectbox("Category *", categories)
        amount      = r2c2.number_input("Amount (₹) *", min_value=0.0, step=100.0, format="%.2f")
        doc_ref     = r2c3.text_input("Supporting Doc Reference")

        r3c1, r3c2 = st.columns([1, 1])
        reason      = r3c1.text_input("Reason")
        remarks     = r3c2.text_input("Remarks")

        if st.form_submit_button("Save Entry", type="primary"):
            if not emp_label:
                st.error("Please select an employee.")
            elif amount <= 0:
                st.error("Amount must be greater than 0.")
            else:
                payroll_month = f"{int(form_year)}-{int(form_month):02d}"
                insert_fn({
                    "employee_id":      op_map[emp_label],
                    "payroll_month":    payroll_month,
                    "transaction_date": str(txn_date),
                    "category":         category,
                    "amount":           float(amount),
                    "reason":           reason.strip() or None,
                    "remarks":          remarks.strip() or None,
                    "supporting_doc":   doc_ref.strip() or None,
                    "entered_by":       _user_name(),
                    "status":           "Submitted",
                })
                st.success(f"Entry saved — {emp_label} | {category} | ₹{amount:,.0f}")
                st.rerun()


# ── Entry point ────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div style='margin-bottom:4px;font-size:11px;font-weight:700;letter-spacing:.15em;
        color:#94A3B8;text-transform:uppercase;'>// Payroll</div>
        <div style='font-size:28px;font-weight:800;color:#1E293B;margin-bottom:20px;'>
        Payroll Inputs</div>
        """,
        unsafe_allow_html=True,
    )

    sb         = SupabaseClient()
    operators  = sb.list_operators()
    op_map     = _op_map(operators)
    op_by_id   = {o["id"]: o for o in operators}
    sites      = sb.list_sites()

    tab_add, tab_ded = st.tabs(["➕  Additions", "➖  Deductions"])

    with tab_add:
        _render_section(
            table_key="add",
            categories=_ADDITION_CATEGORIES,
            list_fn=sb.list_payroll_additions,
            insert_fn=sb.insert_payroll_addition,
            update_fn=sb.update_payroll_addition,
            delete_fn=sb.delete_payroll_addition,
            operators=operators,
            op_map=op_map,
            op_by_id=op_by_id,
            sites=sites,
        )

    with tab_ded:
        _render_section(
            table_key="ded",
            categories=_DEDUCTION_CATEGORIES,
            list_fn=sb.list_payroll_deductions,
            insert_fn=sb.insert_payroll_deduction,
            update_fn=sb.update_payroll_deduction,
            delete_fn=sb.delete_payroll_deduction,
            operators=operators,
            op_map=op_map,
            op_by_id=op_by_id,
            sites=sites,
        )
