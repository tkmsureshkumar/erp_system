"""
erp/views/pf_payments.py — PF Records (5.1) and Customer Direct Payments (5.2).

Supabase tables required:

    CREATE TABLE IF NOT EXISTS payroll_pf (
        id                   uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id          text NOT NULL,
        site_id              text,
        payroll_month        text NOT NULL,
        pf_paid_by_cto       numeric DEFAULT 0,
        pf_paid_by_customer  numeric DEFAULT 0,
        amount_to_deduct     numeric DEFAULT 0,
        payment_date         date,
        reference            text,
        remarks              text,
        supporting_doc       text,
        entered_by           text,
        created_at           timestamptz DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS payroll_customer_payments (
        id                           uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        employee_id                  text NOT NULL,
        site_id                      text,
        payroll_month                text NOT NULL,
        salary_paid_by_customer      numeric DEFAULT 0,
        pf_paid_by_customer          numeric DEFAULT 0,
        salary_deduct_from_payroll   numeric DEFAULT 0,
        pf_deduct_from_payroll       numeric DEFAULT 0,
        payment_date                 date,
        reference                    text,
        remarks                      text,
        supporting_doc               text,
        entered_by                   text,
        created_at                   timestamptz DEFAULT now()
    );

NOTE — No statutory PF calculations are done by this module.
All amounts are entered as determined offline.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from .. import auth
from ..supabase_client import SupabaseClient


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


# ── Tab 5.1: PF Records ────────────────────────────────────────────────────────

def _tab_pf(sb: SupabaseClient, operators: list, op_map: dict,
             op_by_id: dict, sites: list) -> None:
    st.markdown("#### PF Records")
    st.caption(
        "Record PF amounts as determined offline. No statutory formula is applied. "
        "Only **Amount to Deduct from Employee Salary** flows into payroll."
    )

    today      = date.today()
    site_map   = {s["site_name"]: s["id"] for s in sites}
    site_by_id = {s["id"]: s["site_name"] for s in sites}

    # ── Filters ────────────────────────────────────────────────────────────────
    fc     = st.columns([2, 1, 1])
    op_f   = fc[0].selectbox("Employee", ["All"] + list(op_map.keys()), key="pf_f_emp")
    yr_f   = fc[1].number_input("Year", min_value=2020, max_value=2035,
                                  value=today.year, step=1, key="pf_f_yr")
    mo_f   = fc[2].selectbox("Month", ["All"] + list(range(1, 13)),
                               format_func=lambda m: "All" if m == "All" else _month_label(m),
                               key="pf_f_mo")
    pm_filter = f"{int(yr_f)}-{int(mo_f):02d}" if mo_f != "All" else None

    records = sb.list_payroll_pf(payroll_month=pm_filter)

    rows = []
    for r in records:
        op       = op_by_id.get(r.get("employee_id", ""), {})
        emp_name = op.get("operator_name", r.get("employee_id", ""))
        emp_code = op.get("emp_code", "")
        emp_lbl  = f"{emp_code} – {emp_name}" if emp_code else emp_name
        if op_f != "All" and emp_lbl != op_f:
            continue
        rows.append({
            "Employee":               emp_lbl,
            "Site":                   site_by_id.get(r.get("site_id", ""), ""),
            "Month":                  r.get("payroll_month", ""),
            "PF Paid by CTO (₹)":     float(r.get("pf_paid_by_cto") or 0),
            "PF Paid by Customer (₹)":float(r.get("pf_paid_by_customer") or 0),
            "Deduct from Salary (₹)": float(r.get("amount_to_deduct") or 0),
            "Date":                   r.get("payment_date") or "",
            "Reference":              r.get("reference") or "",
            "Remarks":                r.get("remarks") or "",
            "Supporting Doc":         r.get("supporting_doc") or "",
            "Entered By":             r.get("entered_by") or "",
            "_id":                    r["id"],
        })

    if rows:
        total_cto  = sum(r["PF Paid by CTO (₹)"] for r in rows)
        total_cust = sum(r["PF Paid by Customer (₹)"] for r in rows)
        total_ded  = sum(r["Deduct from Salary (₹)"] for r in rows)
        m1, m2, m3 = st.columns(3)
        m1.metric("PF Paid by CTO",      f"₹{total_cto:,.0f}")
        m2.metric("PF Paid by Customer", f"₹{total_cust:,.0f}")
        m3.metric("Total Salary Deduction", f"₹{total_ded:,.0f}")

        st.dataframe(
            pd.DataFrame([{k: v for k, v in r.items() if k != "_id"} for r in rows]),
            use_container_width=True, hide_index=True,
            column_config={
                "PF Paid by CTO (₹)":      st.column_config.NumberColumn(format="₹%,.0f"),
                "PF Paid by Customer (₹)": st.column_config.NumberColumn(format="₹%,.0f"),
                "Deduct from Salary (₹)":  st.column_config.NumberColumn(format="₹%,.0f"),
            },
        )
        if auth.is_admin():
            for r in rows:
                with st.expander(
                    f"{r['Employee']}  |  {r['Month']}  |  Deduct: ₹{r['Deduct from Salary (₹)']:,.0f}"
                ):
                    if st.button("Delete Record", key=f"pf_del_{r['_id']}"):
                        sb.delete_payroll_pf(r["_id"])
                        st.toast("Record deleted.", icon="🗑️")
                        st.rerun()
    else:
        st.info("No PF records found for the selected filters.")

    # ── Add form ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Add PF Record**")
    with st.form("pf_add_form", clear_on_submit=True):
        r1a, r1b, r1c, r1d = st.columns([2.5, 1.5, 1, 1])
        emp_label  = r1a.selectbox("Employee *", list(op_map.keys()))
        site_name  = r1b.selectbox("Site", ["—"] + list(site_map.keys()))
        form_year  = r1c.number_input("Year", min_value=2020, max_value=2035,
                                       value=today.year, step=1)
        form_month = r1d.selectbox("Month", list(range(1, 13)),
                                    index=today.month - 1, format_func=_month_label)

        r2a, r2b, r2c = st.columns(3)
        pf_cto  = r2a.number_input("PF Paid by CTO (₹)",      min_value=0.0, step=50.0, format="%.2f")
        pf_cust = r2b.number_input("PF Paid by Customer (₹)", min_value=0.0, step=50.0, format="%.2f")
        deduct  = r2c.number_input(
            "Amount to Deduct from Employee Salary (₹) *",
            min_value=0.0, step=50.0, format="%.2f",
            help="This is the ONLY amount that enters payroll as a deduction.",
        )

        r3a, r3b, r3c, r3d = st.columns([1.2, 1.5, 1.5, 1.5])
        pay_date  = r3a.date_input("Date", value=today)
        reference = r3b.text_input("Reference")
        remarks   = r3c.text_input("Remarks")
        doc_ref   = r3d.text_input("Supporting Doc Reference")

        if st.form_submit_button("Save PF Record", type="primary"):
            if not emp_label:
                st.error("Please select an employee.")
            else:
                payroll_month = f"{int(form_year)}-{int(form_month):02d}"
                sb.insert_payroll_pf({
                    "employee_id":         op_map[emp_label],
                    "site_id":             site_map.get(site_name) if site_name != "—" else None,
                    "payroll_month":       payroll_month,
                    "pf_paid_by_cto":      float(pf_cto),
                    "pf_paid_by_customer": float(pf_cust),
                    "amount_to_deduct":    float(deduct),
                    "payment_date":        str(pay_date),
                    "reference":           reference.strip() or None,
                    "remarks":             remarks.strip() or None,
                    "supporting_doc":      doc_ref.strip() or None,
                    "entered_by":          _user_name(),
                })
                st.success(
                    f"PF record saved — {emp_label} | {payroll_month} | "
                    f"Deduction: ₹{deduct:,.0f}"
                )
                st.rerun()


# ── Tab 5.2: Customer Direct Payments ─────────────────────────────────────────

def _tab_customer_payments(sb: SupabaseClient, operators: list, op_map: dict,
                            op_by_id: dict, sites: list) -> None:
    st.markdown("#### Customer Direct Payments")
    st.caption(
        "Record salary and PF paid directly by the customer. "
        "**Salary Amount to Deduct** and **PF Amount to Deduct** are the only values that flow into payroll."
    )

    today      = date.today()
    site_map   = {s["site_name"]: s["id"] for s in sites}
    site_by_id = {s["id"]: s["site_name"] for s in sites}

    # ── Filters ────────────────────────────────────────────────────────────────
    fc   = st.columns([2, 1, 1])
    op_f = fc[0].selectbox("Employee", ["All"] + list(op_map.keys()), key="cdp_f_emp")
    yr_f = fc[1].number_input("Year", min_value=2020, max_value=2035,
                                value=today.year, step=1, key="cdp_f_yr")
    mo_f = fc[2].selectbox("Month", ["All"] + list(range(1, 13)),
                             format_func=lambda m: "All" if m == "All" else _month_label(m),
                             key="cdp_f_mo")
    pm_filter = f"{int(yr_f)}-{int(mo_f):02d}" if mo_f != "All" else None

    records = sb.list_payroll_customer_payments(payroll_month=pm_filter)

    rows = []
    for r in records:
        op       = op_by_id.get(r.get("employee_id", ""), {})
        emp_name = op.get("operator_name", r.get("employee_id", ""))
        emp_code = op.get("emp_code", "")
        emp_lbl  = f"{emp_code} – {emp_name}" if emp_code else emp_name
        if op_f != "All" and emp_lbl != op_f:
            continue
        sal  = float(r.get("salary_paid_by_customer") or 0)
        pf   = float(r.get("pf_paid_by_customer") or 0)
        rows.append({
            "Employee":                     emp_lbl,
            "Customer / Site":              site_by_id.get(r.get("site_id", ""), ""),
            "Month":                        r.get("payroll_month", ""),
            "Salary Paid by Customer (₹)":  sal,
            "PF Paid by Customer (₹)":      pf,
            "Total Customer Payment (₹)":   sal + pf,
            "Salary Deduct from Payroll (₹)": float(r.get("salary_deduct_from_payroll") or 0),
            "PF Deduct from Payroll (₹)":   float(r.get("pf_deduct_from_payroll") or 0),
            "Date":                         r.get("payment_date") or "",
            "Reference":                    r.get("reference") or "",
            "Remarks":                      r.get("remarks") or "",
            "Supporting Doc":               r.get("supporting_doc") or "",
            "_id":                          r["id"],
        })

    if rows:
        total_sal  = sum(r["Salary Paid by Customer (₹)"] for r in rows)
        total_pf   = sum(r["PF Paid by Customer (₹)"] for r in rows)
        total_tot  = total_sal + total_pf
        total_dsal = sum(r["Salary Deduct from Payroll (₹)"] for r in rows)
        total_dpf  = sum(r["PF Deduct from Payroll (₹)"] for r in rows)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Customer Salary Paid",   f"₹{total_sal:,.0f}")
        m2.metric("Customer PF Paid",       f"₹{total_pf:,.0f}")
        m3.metric("Total Customer Payment", f"₹{total_tot:,.0f}")
        m4.metric("Salary Payroll Deduct",  f"₹{total_dsal:,.0f}")
        m5.metric("PF Payroll Deduct",      f"₹{total_dpf:,.0f}")

        st.dataframe(
            pd.DataFrame([{k: v for k, v in r.items() if k != "_id"} for r in rows]),
            use_container_width=True, hide_index=True,
            column_config={
                "Salary Paid by Customer (₹)":      st.column_config.NumberColumn(format="₹%,.0f"),
                "PF Paid by Customer (₹)":          st.column_config.NumberColumn(format="₹%,.0f"),
                "Total Customer Payment (₹)":       st.column_config.NumberColumn(format="₹%,.0f"),
                "Salary Deduct from Payroll (₹)":   st.column_config.NumberColumn(format="₹%,.0f"),
                "PF Deduct from Payroll (₹)":       st.column_config.NumberColumn(format="₹%,.0f"),
            },
        )
        if auth.is_admin():
            for r in rows:
                with st.expander(
                    f"{r['Employee']}  |  {r['Customer / Site']}  |  "
                    f"{r['Month']}  |  Total: ₹{r['Total Customer Payment (₹)']:,.0f}"
                ):
                    if st.button("Delete Record", key=f"cdp_del_{r['_id']}"):
                        sb.delete_payroll_customer_payment(r["_id"])
                        st.toast("Record deleted.", icon="🗑️")
                        st.rerun()
    else:
        st.info("No customer direct payment records found for the selected filters.")

    # ── Add form ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Add Customer Direct Payment**")
    with st.form("cdp_add_form", clear_on_submit=True):
        r1a, r1b, r1c, r1d = st.columns([2.5, 1.5, 1, 1])
        emp_label  = r1a.selectbox("Employee *", list(op_map.keys()))
        site_name  = r1b.selectbox("Customer / Site *", ["—"] + list(site_map.keys()))
        form_year  = r1c.number_input("Year", min_value=2020, max_value=2035,
                                       value=today.year, step=1)
        form_month = r1d.selectbox("Month", list(range(1, 13)),
                                    index=today.month - 1, format_func=_month_label)

        st.markdown("**What the customer paid:**")
        p1, p2, p3 = st.columns(3)
        sal_paid  = p1.number_input("Salary Paid by Customer (₹)",
                                     min_value=0.0, step=100.0, format="%.2f")
        pf_paid   = p2.number_input("PF Paid by Customer (₹)",
                                     min_value=0.0, step=50.0, format="%.2f")
        total_disp = sal_paid + pf_paid
        p3.metric("Total Customer Payment", f"₹{total_disp:,.0f}")

        st.markdown("**What to deduct from payroll:**")
        d1, d2 = st.columns(2)
        sal_ded = d1.number_input(
            "Salary Amount to Deduct from Payroll (₹) *",
            min_value=0.0, max_value=float(sal_paid) if sal_paid > 0 else 9_999_999.0,
            value=float(sal_paid), step=100.0, format="%.2f",
        )
        pf_ded  = d2.number_input(
            "PF Amount to Deduct from Payroll (₹)",
            min_value=0.0, max_value=float(pf_paid) if pf_paid > 0 else 9_999_999.0,
            value=0.0, step=50.0, format="%.2f",
            help="Enter 0 if customer PF payment should not affect employee's payroll deduction.",
        )

        r3a, r3b, r3c, r3d = st.columns([1.2, 1.5, 1.5, 1.5])
        pay_date  = r3a.date_input("Date", value=today)
        reference = r3b.text_input("Reference")
        remarks   = r3c.text_input("Remarks")
        doc_ref   = r3d.text_input("Supporting Doc Reference")

        if st.form_submit_button("Save Customer Payment", type="primary"):
            if not emp_label:
                st.error("Please select an employee.")
            elif site_name == "—":
                st.error("Please select a Customer / Site.")
            else:
                payroll_month = f"{int(form_year)}-{int(form_month):02d}"
                sb.insert_payroll_customer_payment({
                    "employee_id":                op_map[emp_label],
                    "site_id":                    site_map.get(site_name),
                    "payroll_month":              payroll_month,
                    "salary_paid_by_customer":    float(sal_paid),
                    "pf_paid_by_customer":        float(pf_paid),
                    "salary_deduct_from_payroll": float(sal_ded),
                    "pf_deduct_from_payroll":     float(pf_ded),
                    "payment_date":               str(pay_date),
                    "reference":                  reference.strip() or None,
                    "remarks":                    remarks.strip() or None,
                    "supporting_doc":             doc_ref.strip() or None,
                    "entered_by":                 _user_name(),
                })
                st.success(
                    f"Record saved — {emp_label} | {payroll_month} | "
                    f"Total: ₹{sal_paid + pf_paid:,.0f}"
                )
                st.rerun()


# ── Entry point ────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        """
        <div style='margin-bottom:4px;font-size:11px;font-weight:700;letter-spacing:.15em;
        color:#94A3B8;text-transform:uppercase;'>// Payroll</div>
        <div style='font-size:28px;font-weight:800;color:#1E293B;margin-bottom:20px;'>
        PF &amp; Customer Direct Payments</div>
        """,
        unsafe_allow_html=True,
    )

    sb        = SupabaseClient()
    operators = sb.list_operators()
    op_map    = _op_map(operators)
    op_by_id  = {o["id"]: o for o in operators}
    sites     = sb.list_sites()

    tab_pf, tab_cdp = st.tabs(["🏦  PF Records", "🏢  Customer Direct Payments"])

    with tab_pf:
        _tab_pf(sb, operators, op_map, op_by_id, sites)

    with tab_cdp:
        _tab_customer_payments(sb, operators, op_map, op_by_id, sites)
