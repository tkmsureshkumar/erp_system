"""
erp/views/payroll_inputs.py — Payroll Inputs: Additions and Deductions.
"""
from __future__ import annotations

from datetime import date
from collections import defaultdict

import pandas as pd
import streamlit as st

from .. import auth
from ..supabase_client import SupabaseClient

_ADDITION_CATEGORIES = [
    "Bonus", "Incentive", "Special Allowance", "Arrears",
    "Reimbursement", "Festival Payment", "Other Addition",
]
_DEDUCTION_CATEGORIES = [
    "Accommodation", "Food", "Travel", "Damage Recovery",
    "Uniform", "Penalty", "Other Deduction",
]
_STATUSES = ["Submitted", "Approved", "Cancelled"]

_STATUS_STYLE = {
    "Submitted": ("#FEF3C7", "#D97706"),
    "Approved":  ("#DCFCE7", "#166534"),
    "Cancelled": ("#F3F4F6", "#6B7280"),
}

_CAT_COLOR = {
    "Bonus":             "#3B82F6",
    "Incentive":         "#8B5CF6",
    "Special Allowance": "#0EA5E9",
    "Arrears":           "#F59E0B",
    "Reimbursement":     "#10B981",
    "Festival Payment":  "#EC4899",
    "Accommodation":     "#EF4444",
    "Food":              "#F97316",
    "Travel":            "#6366F1",
    "Damage Recovery":   "#DC2626",
    "Uniform":           "#64748B",
    "Penalty":           "#B91C1C",
}

_PAGE_CSS = """
<style>
.pi-kpi-grid {
    display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px;
}
.pi-kpi {
    background:#fff; border:1px solid #E2EBF0; border-radius:12px;
    padding:14px 18px 10px; position:relative; overflow:hidden;
}
.pi-kpi-bar {
    position:absolute; top:0; left:0; right:0; height:3px; border-radius:12px 12px 0 0;
}
.pi-kpi-label {
    font-size:10px; font-weight:700; letter-spacing:.13em; text-transform:uppercase;
    color:#9CA3AF; margin-bottom:5px;
}
.pi-kpi-value { font-size:22px; font-weight:800; color:#111827; line-height:1; }
.pi-kpi-sub   { font-size:11px; color:#6B7280; margin-top:2px; }
.pi-section-hdr {
    font-size:10px; font-weight:700; letter-spacing:.13em; text-transform:uppercase;
    color:#E87722; margin:16px 0 8px; padding-bottom:5px; border-bottom:1px solid #F1F5F9;
}
.pi-badge {
    display:inline-block; font-size:10px; font-weight:700; padding:2px 8px;
    border-radius:20px; letter-spacing:.04em;
}
.pi-cat-chip {
    display:inline-block; font-size:10px; font-weight:600; padding:2px 8px;
    border-radius:20px; color:#fff; opacity:.9;
}
.pi-summary-bar {
    display:flex; gap:20px; flex-wrap:wrap; align-items:center;
    background:#F8FAFC; border:1px solid #E2EBF0; border-radius:10px;
    padding:10px 16px; margin-bottom:12px; font-size:12px;
}
.pi-summary-item { display:flex; flex-direction:column; }
.pi-summary-label { color:#94A3B8; font-size:9px; font-weight:700;
    text-transform:uppercase; letter-spacing:.1em; }
.pi-summary-val   { color:#1E293B; font-size:14px; font-weight:800; }
</style>
"""


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


def _status_badge(status: str) -> str:
    bg, fg = _STATUS_STYLE.get(status, ("#F1F5F9", "#475569"))
    return (
        f"<span class='pi-badge' style='background:{bg};color:{fg};'>{status}</span>"
    )


def _cat_chip(cat: str) -> str:
    color = _CAT_COLOR.get(cat, "#94A3B8")
    return f"<span class='pi-cat-chip' style='background:{color};'>{cat}</span>"


def _kpi(label: str, value, sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='pi-kpi'>"
        f"<div class='pi-kpi-bar' style='background:{accent}'></div>"
        f"<div class='pi-kpi-label'>{label}</div>"
        f"<div class='pi-kpi-value'>{value}</div>"
        f"<div class='pi-kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _render_kpi_grid(add_recs: list, ded_recs: list) -> None:
    today_month = date.today().strftime("%Y-%m")
    this_add = [r for r in add_recs if r.get("payroll_month", "") == today_month]
    this_ded = [r for r in ded_recs if r.get("payroll_month", "") == today_month]

    total_add  = sum(float(r.get("amount") or 0) for r in this_add)
    total_ded  = sum(float(r.get("amount") or 0) for r in this_ded)
    pending    = sum(1 for r in add_recs + ded_recs if r.get("status") == "Submitted")
    approved   = sum(1 for r in add_recs + ded_recs if r.get("status") == "Approved")

    st.markdown(
        "<div class='pi-kpi-grid'>"
        + _kpi("Total Additions",   f"₹{total_add:,.0f}", "this month",    "#10B981")
        + _kpi("Total Deductions",  f"₹{total_ded:,.0f}", "this month",    "#EF4444")
        + _kpi("Pending Approval",  pending,               "items",         "#F59E0B")
        + _kpi("Approved",          approved,              "items",         "#2563EB")
        + "</div>",
        unsafe_allow_html=True,
    )


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
) -> None:
    today = date.today()

    # ── Filters ────────────────────────────────────────────────────────────────
    fc = st.columns([2, 1, 1, 1.5, 1.5])
    op_labels = ["All"] + list(op_map.keys())
    emp_f    = fc[0].selectbox("Employee",   op_labels,                       key=f"{table_key}_f_emp")
    year_f   = fc[1].number_input("Year",    min_value=2020, max_value=2035,
                                   value=today.year, step=1,                  key=f"{table_key}_f_yr")
    month_f  = fc[2].selectbox("Month",      ["All"] + list(range(1, 13)),
                                 format_func=lambda m: "All" if m == "All" else _month_label(m),
                                 key=f"{table_key}_f_mo")
    status_f = fc[3].selectbox("Status",     ["All"] + _STATUSES,             key=f"{table_key}_f_st")
    cat_f    = fc[4].selectbox("Category",   ["All"] + categories,            key=f"{table_key}_f_cat")

    pm_filter = f"{int(year_f)}-{int(month_f):02d}" if month_f != "All" else None
    records = list_fn(payroll_month=pm_filter)

    # ── Build rows ─────────────────────────────────────────────────────────────
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
        if cat_f != "All" and r.get("category") != cat_f:
            continue

        rows.append({
            "Employee":       emp_lbl,
            "emp_name":       emp_name,
            "Month":          r.get("payroll_month", ""),
            "Date":           r.get("transaction_date", ""),
            "Category":       r.get("category", ""),
            "Amount":         float(r.get("amount") or 0),
            "Reason":         r.get("reason") or "—",
            "Remarks":        r.get("remarks") or "—",
            "Entered By":     r.get("entered_by") or "—",
            "Status":         r.get("status") or "Submitted",
            "_id":            r["id"],
        })

    # ── Summary bar ────────────────────────────────────────────────────────────
    if rows:
        total_amt  = sum(r["Amount"] for r in rows)
        n_approved = sum(1 for r in rows if r["Status"] == "Approved")
        n_pending  = sum(1 for r in rows if r["Status"] == "Submitted")
        n_cancel   = sum(1 for r in rows if r["Status"] == "Cancelled")

        # Category breakdown dict
        by_cat = defaultdict(float)
        for r in rows:
            by_cat[r["Category"]] += r["Amount"]
        top_cats = sorted(by_cat.items(), key=lambda x: -x[1])[:3]
        cat_txt = "  ·  ".join(f"{c}: ₹{v:,.0f}" for c, v in top_cats)

        st.markdown(
            f"<div class='pi-summary-bar'>"
            f"<div class='pi-summary-item'><span class='pi-summary-label'>Total</span>"
            f"<span class='pi-summary-val'>₹{total_amt:,.0f}</span></div>"
            f"<div class='pi-summary-item'><span class='pi-summary-label'>Records</span>"
            f"<span class='pi-summary-val'>{len(rows)}</span></div>"
            f"<div class='pi-summary-item'><span class='pi-summary-label'>Approved</span>"
            f"<span class='pi-summary-val' style='color:#166534;'>{n_approved}</span></div>"
            f"<div class='pi-summary-item'><span class='pi-summary-label'>Pending</span>"
            f"<span class='pi-summary-val' style='color:#D97706;'>{n_pending}</span></div>"
            f"<div class='pi-summary-item'><span class='pi-summary-label'>Cancelled</span>"
            f"<span class='pi-summary-val' style='color:#6B7280;'>{n_cancel}</span></div>"
            + (f"<div style='flex:1;font-size:11px;color:#64748B;text-align:right;'>"
               f"Top: {cat_txt}</div>" if cat_txt else "")
            + "</div>",
            unsafe_allow_html=True,
        )

        # ── HTML Table ─────────────────────────────────────────────────────────
        hs = ("padding:8px 12px;background:#F8FAFC;font-size:10px;font-weight:700;"
              "letter-spacing:.1em;text-transform:uppercase;color:#64748B;"
              "border-bottom:2px solid #E2EBF0;white-space:nowrap;")
        cs = "padding:9px 12px;font-size:13px;border-bottom:1px solid #F1F5F9;vertical-align:middle;"

        cols_hdr = ["Employee", "Month", "Date", "Category", "Amount (₹)", "Reason", "Entered By", "Status"]
        head = "".join(f"<th style='{hs}'>{c}</th>" for c in cols_hdr)

        body = ""
        for r in rows:
            reason_txt   = r["Reason"]
            emp_txt      = r["Employee"]
            month_txt    = r["Month"]
            date_txt     = r["Date"]
            cat_html     = _cat_chip(r["Category"])
            amt_val      = r["Amount"]
            entby_txt    = r["Entered By"]
            status_html  = _status_badge(r["Status"])
            body += (
                f"<tr>"
                f"<td style='{cs}font-weight:700;color:#1E293B;'>{emp_txt}</td>"
                f"<td style='{cs}color:#64748B;'>{month_txt}</td>"
                f"<td style='{cs}color:#64748B;'>{date_txt}</td>"
                f"<td style='{cs}'>{cat_html}</td>"
                f"<td style='{cs}font-variant-numeric:tabular-nums;font-weight:700;"
                f"color:#0F766E;'>₹{amt_val:,.0f}</td>"
                f"<td style='{cs}color:#64748B;max-width:200px;overflow:hidden;"
                f"text-overflow:ellipsis;white-space:nowrap;'>{reason_txt}</td>"
                f"<td style='{cs}color:#64748B;'>{entby_txt}</td>"
                f"<td style='{cs}'>{status_html}</td>"
                f"</tr>"
            )

        # Total row
        body += (
            f"<tr style='background:#F0FDF4;font-weight:800;'>"
            f"<td style='{cs}color:#166534;' colspan='4'>Total ({len(rows)} records)</td>"
            f"<td style='{cs}color:#166534;font-variant-numeric:tabular-nums;"
            f"font-size:14px;'>₹{total_amt:,.0f}</td>"
            f"<td colspan='3' style='{cs}'></td>"
            f"</tr>"
        )

        st.markdown(
            f"<div style='overflow-x:auto;border:1px solid #E2EBF0;border-radius:10px;'>"
            f"<table style='width:100%;border-collapse:collapse;'>"
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody>"
            f"</table></div>",
            unsafe_allow_html=True,
        )

        # ── Admin actions ──────────────────────────────────────────────────────
        if auth.is_admin():
            st.markdown(
                "<div class='pi-section-hdr'>Admin Actions</div>",
                unsafe_allow_html=True,
            )

            # Build data_editor for status update
            de_data = pd.DataFrame([{
                "Employee":  r["Employee"],
                "Month":     r["Month"],
                "Category":  r["Category"],
                "Amount (₹)": r["Amount"],
                "Current Status": r["Status"],
                "New Status": r["Status"],
                "_id":       r["_id"],
            } for r in rows if r["Status"] != "Cancelled"])

            if not de_data.empty:
                edited = st.data_editor(
                    de_data.drop(columns=["_id"]),
                    use_container_width=True, hide_index=True, num_rows="fixed",
                    column_config={
                        "Employee":       st.column_config.TextColumn("Employee",     width="medium"),
                        "Month":          st.column_config.TextColumn("Month",        width="small"),
                        "Category":       st.column_config.TextColumn("Category",     width="medium"),
                        "Amount (₹)":     st.column_config.NumberColumn("Amount",     format="₹%,.0f"),
                        "Current Status": st.column_config.TextColumn("Current",      width="small"),
                        "New Status":     st.column_config.SelectboxColumn(
                            "New Status", options=_STATUSES, width="small",
                        ),
                    },
                    disabled=["Employee", "Month", "Category", "Amount (₹)", "Current Status"],
                    key=f"{table_key}_admin_de",
                )

                # Find changed rows
                changed = []
                for i, (orig_row, new_status) in enumerate(zip(
                    de_data["Current Status"].values, edited["New Status"].values
                )):
                    if orig_row != new_status:
                        changed.append((de_data.iloc[i]["_id"], new_status,
                                        de_data.iloc[i]["Employee"]))

                if changed:
                    st.markdown(
                        f"<div style='font-size:12px;color:#D97706;margin:4px 0 8px;'>"
                        f"{len(changed)} status change(s) pending — click Apply to save.</div>",
                        unsafe_allow_html=True,
                    )
                    col_apply, col_del, _ = st.columns([1.5, 1.5, 5])
                    if col_apply.button("Apply Status Changes", type="primary",
                                         key=f"{table_key}_apply_status"):
                        for rec_id, new_st, emp in changed:
                            update_fn(rec_id, {"status": new_st})
                        st.success(f"Updated {len(changed)} record(s).")
                        st.rerun()

                # Delete section
                with st.expander("Delete records", expanded=False):
                    del_opts = {f"{r['Employee']} | {r['Category']} | ₹{r['Amount']:,.0f} | {r['Month']}": r["_id"]
                                for r in rows}
                    del_sel = st.multiselect("Select records to delete", list(del_opts.keys()),
                                              key=f"{table_key}_del_sel")
                    if del_sel and st.button("Delete Selected", key=f"{table_key}_del_btn",
                                              type="secondary"):
                        for label in del_sel:
                            delete_fn(del_opts[label])
                        st.success(f"Deleted {len(del_sel)} record(s).")
                        st.rerun()
    else:
        st.info("No records found for the selected filters.")

    # ── Add new entry ──────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(
            "<span style='font-size:11px;font-weight:700;letter-spacing:.1em;"
            "text-transform:uppercase;color:#E87722;'>Add New Entry</span>",
            unsafe_allow_html=True,
        )
        with st.form(f"{table_key}_add_form", clear_on_submit=True):
            r1c1, r1c2, r1c3, r1c4 = st.columns([2.5, 1, 1, 1.5])
            emp_label  = r1c1.selectbox("Employee *", list(op_map.keys()))
            form_year  = r1c2.number_input("Year",  min_value=2020, max_value=2035,
                                            value=today.year, step=1)
            form_month = r1c3.selectbox("Month", list(range(1, 13)),
                                         index=today.month - 1, format_func=_month_label)
            txn_date   = r1c4.date_input("Transaction Date *", value=today)

            r2c1, r2c2, r2c3 = st.columns([2, 1.5, 1.5])
            category  = r2c1.selectbox("Category *", categories)
            amount    = r2c2.number_input("Amount (₹) *", min_value=0.0, step=100.0, format="%.2f")
            doc_ref   = r2c3.text_input("Supporting Doc Reference")

            r3c1, r3c2 = st.columns([1, 1])
            reason  = r3c1.text_input("Reason")
            remarks = r3c2.text_input("Remarks")

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
                    st.success(f"Saved — {emp_label} | {category} | ₹{amount:,.0f}")
                    st.rerun()


# ── Entry point ────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:.15em;"
        "text-transform:uppercase;color:#94A3B8;margin-bottom:4px;'>// Payroll</div>"
        "<div style='font-size:26px;font-weight:900;color:#111827;"
        "letter-spacing:-.5px;margin-bottom:16px;'>Payroll Inputs</div>",
        unsafe_allow_html=True,
    )

    sb        = SupabaseClient()
    operators = sb.list_operators()
    op_map    = _op_map(operators)
    op_by_id  = {o["id"]: o for o in operators}

    # Load current-month data for KPI strip
    try:
        all_add = sb.list_payroll_additions()
        all_ded = sb.list_payroll_deductions()
    except Exception:
        all_add, all_ded = [], []

    _render_kpi_grid(all_add, all_ded)

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
        )
