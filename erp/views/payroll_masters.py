"""
erp/views/payroll_masters.py
Payroll Masters & Salary History module — Phase 1.

Layout:
  Left  (35%): operator directory with payroll status badges
  Right (65%): payroll setup form / read-only view / history

Approval workflow:
  Staff  → creates New Setup or Salary Revision → status = Pending
  Admin  → approves / rejects from the right panel
  Approved records are read-only; only a new revision can modify them.
"""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from erp import auth
from erp.models import PayrollApprovalStatus
from erp.supabase_client import SupabaseClient

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
.pm-kpi-grid {
    display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 22px;
}
.pm-kpi {
    background: #fff; border: 1px solid #E2EBF0; border-radius: 12px;
    padding: 16px 18px 12px; position: relative; overflow: hidden;
}
.pm-kpi-label { font-size:10px; font-weight:700; letter-spacing:.12em;
    text-transform:uppercase; color:#94A3B8; margin-bottom:6px; }
.pm-kpi-val   { font-size:26px; font-weight:800; color:#0D1B33; line-height:1; }
.pm-kpi-bar   { position:absolute; left:0; top:0; bottom:0; width:3px; border-radius:3px 0 0 3px; }

.pm-op-row {
    display:flex; align-items:center; gap:10px;
    padding:10px 12px; border-radius:10px; cursor:pointer;
    border: 1px solid transparent; margin-bottom:4px; transition: background .12s;
}
.pm-op-row:hover { background:#F1F5F9; }
.pm-op-row.active { background:#EFF6FF; border-color:#BFDBFE; }
.pm-op-avatar {
    width:36px; height:36px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    font-size:14px; font-weight:700; color:#fff; flex-shrink:0;
}
.pm-op-name  { font-size:13px; font-weight:600; color:#0D1B33; }
.pm-op-meta  { font-size:11px; color:#64748B; }
.pm-badge {
    display:inline-block; font-size:10px; font-weight:700;
    letter-spacing:.08em; text-transform:uppercase;
    padding:2px 8px; border-radius:20px;
}
.pm-badge-approved { background:#DCFCE7; color:#166534; }
.pm-badge-pending  { background:#FEF9C3; color:#854D0E; }
.pm-badge-none     { background:#F1F5F9; color:#475569; }
.pm-badge-rejected { background:#FEE2E2; color:#991B1B; }

.pm-info-card {
    background:#F8FAFC; border:1px solid #E2EBF0; border-radius:10px;
    padding:14px 16px; margin-bottom:16px;
}
.pm-info-row { display:flex; gap:24px; flex-wrap:wrap; }
.pm-info-item { min-width:120px; }
.pm-info-label { font-size:10px; font-weight:700; letter-spacing:.10em;
    text-transform:uppercase; color:#94A3B8; margin-bottom:2px; }
.pm-info-val   { font-size:13px; font-weight:600; color:#0D1B33; }

.pm-section-hdr {
    font-size:10px; font-weight:700; letter-spacing:.13em;
    text-transform:uppercase; color:#E87722; margin:18px 0 10px;
    padding-bottom:6px; border-bottom:1px solid #F1F5F9;
}
.pm-banner-pending {
    background:#FFFBEB; border:1px solid #FDE68A; border-left:4px solid #F59E0B;
    border-radius:8px; padding:10px 14px; font-size:13px; color:#92400E;
    margin-bottom:14px;
}
.pm-banner-approved {
    background:#F0FDF4; border:1px solid #BBF7D0; border-left:4px solid #16A34A;
    border-radius:8px; padding:10px 14px; font-size:13px; color:#166534;
    margin-bottom:14px;
}
.pm-banner-rejected {
    background:#FEF2F2; border:1px solid #FECACA; border-left:4px solid #EF4444;
    border-radius:8px; padding:10px 14px; font-size:13px; color:#991B1B;
    margin-bottom:14px;
}
.pm-hist-row {
    display:grid; grid-template-columns:40px 1fr 1fr 1fr 1fr 1fr;
    gap:8px; padding:8px 6px; border-bottom:1px solid #F1F5F9;
    font-size:12px; color:#374151; align-items:center;
}
.pm-hist-hdr { font-weight:700; color:#64748B; font-size:10px;
    letter-spacing:.08em; text-transform:uppercase; }
</style>
"""

_STATUS_COLOR = {
    "Approved": "#16A34A",
    "Pending":  "#F59E0B",
    "Rejected": "#EF4444",
    "none":     "#94A3B8",
}
_BADGE_CLASS = {
    "Approved": "pm-badge-approved",
    "Pending":  "pm-badge-pending",
    "Rejected": "pm-badge-rejected",
    "none":     "pm-badge-none",
}
_AVATAR_COLOR = ["#3B82F6","#8B5CF6","#EC4899","#0EA5E9","#F59E0B","#10B981"]

_CSS_INJECTED = False


def _inject_css() -> None:
    global _CSS_INJECTED
    if not _CSS_INJECTED:
        st.markdown(_CSS, unsafe_allow_html=True)
        _CSS_INJECTED = True


# ── helpers ───────────────────────────────────────────────────────────────────

def _initials(name: str) -> str:
    parts = name.split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _fmt_date(d) -> str:
    if not d:
        return "—"
    try:
        return str(d)[:10]
    except Exception:
        return "—"


def _fmt_salary(v) -> str:
    if v is None:
        return "—"
    try:
        return f"₹{float(v):,.0f}"
    except Exception:
        return "—"


def _payroll_status(history: list) -> str:
    """Return the effective status for an operator: 'Approved'|'Pending'|'Rejected'|'none'"""
    if not history:
        return "none"
    pending  = any(r.get("approval_status") == "Pending"  for r in history)
    approved = any(r.get("approval_status") == "Approved" for r in history)
    if pending:
        return "Pending"
    if approved:
        return "Approved"
    return "Rejected"


# ── KPI strip ─────────────────────────────────────────────────────────────────

def _render_kpis(operators: list, history_map: dict) -> None:
    total     = len(operators)
    approved  = sum(1 for op in operators if _payroll_status(history_map.get(op["id"], [])) == "Approved")
    pending   = sum(1 for op in operators if _payroll_status(history_map.get(op["id"], [])) == "Pending")
    no_record = sum(1 for op in operators if _payroll_status(history_map.get(op["id"], [])) == "none")

    kpis = [
        ("Total Operators", total,     "#3B82F6"),
        ("Approved",        approved,  "#16A34A"),
        ("Pending",         pending,   "#F59E0B"),
        ("No Record",       no_record, "#94A3B8"),
    ]
    cols = st.columns(4)
    for col, (label, val, color) in zip(cols, kpis):
        with col:
            st.markdown(
                f"<div class='pm-kpi'>"
                f"<div class='pm-kpi-bar' style='background:{color};'></div>"
                f"<div class='pm-kpi-label'>{label}</div>"
                f"<div class='pm-kpi-val'>{val}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ── operator list (left panel) ────────────────────────────────────────────────

def _render_operator_list(operators: list, history_map: dict, search: str) -> None:
    sel = st.session_state.get("_pm_sel_op_id", "")
    filtered = [
        op for op in operators
        if not search or search.lower() in op.get("operator_name", "").lower()
        or search.lower() in (op.get("emp_code") or "").lower()
    ]

    if not filtered:
        st.markdown("<div style='color:#94A3B8;font-size:13px;padding:16px 0;'>No operators match.</div>",
                    unsafe_allow_html=True)
        return

    for i, op in enumerate(filtered):
        op_id  = op["id"]
        name   = op.get("operator_name", "—")
        code   = op.get("emp_code", "")
        desig  = op.get("designation", "")
        status = _payroll_status(history_map.get(op_id, []))
        color  = _AVATAR_COLOR[i % len(_AVATAR_COLOR)]
        badge_cls = _BADGE_CLASS.get(status, "pm-badge-none")

        current_rec = next((r for r in history_map.get(op_id, []) if r.get("is_current")), {})
        salary_txt  = _fmt_salary(current_rec.get("fixed_salary")) if current_rec else ""

        is_active = "active" if op_id == sel else ""
        clicked = st.button(
            f"{code} — {name}",
            key=f"_pm_op_{op_id}",
            use_container_width=True,
            help=desig,
        )
        if clicked:
            st.session_state["_pm_sel_op_id"] = op_id
            st.rerun()

        st.markdown(
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:0 4px 6px;margin-top:-8px;'>"
            f"<span style='font-size:11px;color:#64748B;'>{desig} {('· ' + salary_txt) if salary_txt else ''}</span>"
            f"<span class='pm-badge {badge_cls}'>{status if status != 'none' else 'No Record'}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ── payroll form ──────────────────────────────────────────────────────────────

def _payroll_form(sb: SupabaseClient, operator: dict, prefill: dict, is_revision: bool, user_name: str) -> None:
    """Render the new/revision payroll master form and handle submission."""
    heading = "Salary Revision" if is_revision else "New Payroll Setup"
    st.markdown(f"<div class='pm-section-hdr'>{heading}</div>", unsafe_allow_html=True)

    with st.form(f"_pm_form_{operator['id']}", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            salary = st.number_input(
                "Fixed Monthly Salary (₹) *",
                min_value=0.0, step=500.0,
                value=float(prefill.get("fixed_salary") or 0),
                format="%.2f",
            )
        with c2:
            eff_from = st.date_input(
                "Effective From *",
                value=date.fromisoformat(prefill["effective_from"]) if prefill.get("effective_from") else date.today(),
            )

        st.markdown("<div class='pm-section-hdr'>Bank Details</div>", unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        with b1:
            bank_name = st.text_input("Bank Name", value=prefill.get("bank_name") or "")
            account   = st.text_input("Account Number", value=prefill.get("bank_account_number") or "")
        with b2:
            ifsc      = st.text_input("IFSC Code", value=prefill.get("ifsc_code") or "")
            passbook  = st.text_input("Name in Passbook", value=prefill.get("name_in_passbook") or "")

        dol = st.date_input(
            "Date of Leaving (leave blank if still active)",
            value=date.fromisoformat(prefill["dol"]) if prefill.get("dol") else None,
        )
        remarks = st.text_area(
            "Remarks / Reason for Revision" if is_revision else "Remarks",
            value="", height=70,
        )

        submitted = st.form_submit_button(
            "Submit for Approval", use_container_width=True, type="primary"
        )

    if submitted:
        if not salary:
            st.error("Fixed salary is required.")
            return

        # Next revision number
        history = sb.list_payroll_masters_for_operator(operator["id"])
        next_rev = (max((r.get("revision_number") or 0) for r in history) + 1) if history else 1

        payload = {
            "operator_id":        operator["id"],
            "fixed_salary":       float(salary),
            "bank_name":          bank_name.strip() or None,
            "bank_account_number": account.strip() or None,
            "ifsc_code":          ifsc.strip() or None,
            "name_in_passbook":   passbook.strip() or None,
            "dol":                dol.isoformat() if dol else None,
            "effective_from":     eff_from.isoformat(),
            "approval_status":    "Pending",
            "is_current":         False,
            "revision_number":    next_rev,
            "created_by":         user_name,
            "review_remarks":     remarks.strip() or None,
        }
        try:
            sb.insert_payroll_master(payload)
            st.toast("Submitted for approval.", icon="✅")
            st.session_state.pop("_pm_show_form", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Failed to submit: {exc}")


# ── read-only record display ──────────────────────────────────────────────────

def _render_record(rec: dict) -> None:
    fields = [
        ("Fixed Salary",    _fmt_salary(rec.get("fixed_salary"))),
        ("Effective From",  _fmt_date(rec.get("effective_from"))),
        ("Bank Name",       rec.get("bank_name") or "—"),
        ("Account No.",     rec.get("bank_account_number") or "—"),
        ("IFSC",            rec.get("ifsc_code") or "—"),
        ("Name in Passbook",rec.get("name_in_passbook") or "—"),
        ("Date of Leaving", _fmt_date(rec.get("dol"))),
        ("Submitted By",    rec.get("created_by") or "—"),
    ]
    html = "<div class='pm-info-card'><div class='pm-info-row'>"
    for label, val in fields:
        html += (
            f"<div class='pm-info-item'>"
            f"<div class='pm-info-label'>{label}</div>"
            f"<div class='pm-info-val'>{val}</div>"
            f"</div>"
        )
    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)

    if rec.get("review_remarks"):
        st.markdown(
            f"<div style='font-size:12px;color:#64748B;margin-top:-6px;'>"
            f"<b>Remarks:</b> {rec['review_remarks']}</div>",
            unsafe_allow_html=True,
        )


# ── history tab ───────────────────────────────────────────────────────────────

def _render_history(history: list) -> None:
    if not history:
        st.markdown("<div style='color:#94A3B8;font-size:13px;padding:16px 0;'>No history yet.</div>",
                    unsafe_allow_html=True)
        return

    header = ["Rev", "Salary", "Eff. From", "Status", "By", "Approved By"]
    html = "<div class='pm-hist-row pm-hist-hdr'>"
    for h in header:
        html += f"<span>{h}</span>"
    html += "</div>"

    for r in history:
        status = r.get("approval_status", "—")
        badge_cls = _BADGE_CLASS.get(status, "pm-badge-none")
        html += (
            f"<div class='pm-hist-row'>"
            f"<span style='font-weight:700;color:#64748B;'>#{r.get('revision_number','—')}</span>"
            f"<span style='font-weight:600;'>{_fmt_salary(r.get('fixed_salary'))}</span>"
            f"<span>{_fmt_date(r.get('effective_from'))}</span>"
            f"<span><span class='pm-badge {badge_cls}'>{status}</span></span>"
            f"<span style='color:#64748B;'>{r.get('created_by') or '—'}</span>"
            f"<span style='color:#64748B;'>{r.get('reviewed_by') or '—'}</span>"
            f"</div>"
        )
    st.markdown(html, unsafe_allow_html=True)


# ── right panel ───────────────────────────────────────────────────────────────

def _render_right(sb: SupabaseClient, operator: dict, is_adm: bool, user_name: str) -> None:
    op_id   = operator["id"]
    history = sb.list_payroll_masters_for_operator(op_id)
    current = next((r for r in history if r.get("is_current")), {})
    pending = next((r for r in history if r.get("approval_status") == "Pending"), {})

    # Operator info header
    st.markdown(
        f"<div class='pm-info-card'><div class='pm-info-row'>"
        f"<div class='pm-info-item'><div class='pm-info-label'>Emp Code</div>"
        f"<div class='pm-info-val'>{operator.get('emp_code','—')}</div></div>"
        f"<div class='pm-info-item'><div class='pm-info-label'>Name</div>"
        f"<div class='pm-info-val'>{operator.get('operator_name','—')}</div></div>"
        f"<div class='pm-info-item'><div class='pm-info-label'>Designation</div>"
        f"<div class='pm-info-val'>{operator.get('designation','—')}</div></div>"
        f"<div class='pm-info-item'><div class='pm-info-label'>Mobile</div>"
        f"<div class='pm-info-val'>{operator.get('mobile_number','—')}</div></div>"
        f"<div class='pm-info-item'><div class='pm-info-label'>Date of Joining</div>"
        f"<div class='pm-info-val'>{_fmt_date(operator.get('joining_date'))}</div></div>"
        f"<div class='pm-info-item'><div class='pm-info-label'>Status</div>"
        f"<div class='pm-info-val'>{operator.get('status','—')}</div></div>"
        f"</div></div>",
        unsafe_allow_html=True,
    )

    tab_labels = ["Payroll Setup", "Salary History"]
    tabs = st.tabs(tab_labels)

    # ── Tab: Payroll Setup ────────────────────────────────────────────────────
    with tabs[0]:
        show_form_key = f"_pm_show_form_{op_id}"

        if not history:
            # No record exists
            st.markdown("<div class='pm-banner-pending'>No payroll master set up yet for this operator.</div>",
                        unsafe_allow_html=True)
            if not st.session_state.get(show_form_key):
                if st.button("+ New Payroll Setup", key=f"_pm_new_{op_id}", type="primary"):
                    st.session_state[show_form_key] = True
                    st.rerun()
            else:
                _payroll_form(sb, operator, {}, is_revision=False, user_name=user_name)

        elif pending:
            # Pending record exists
            rev_no = pending.get("revision_number", 1)
            label  = "New Setup" if rev_no == 1 else f"Salary Revision #{rev_no}"
            st.markdown(
                f"<div class='pm-banner-pending'>⏳ {label} is awaiting admin approval.</div>",
                unsafe_allow_html=True,
            )
            _render_record(pending)

            if is_adm:
                st.markdown("<div class='pm-section-hdr'>Admin Decision</div>", unsafe_allow_html=True)
                review_remarks = st.text_area("Remarks", key=f"_pm_rev_rem_{op_id}", height=70)
                a_col, r_col = st.columns(2)
                with a_col:
                    if st.button("Approve", key=f"_pm_approve_{op_id}",
                                 type="primary", use_container_width=True):
                        try:
                            sb.approve_payroll_master(
                                record_id   = pending["id"],
                                operator_id = op_id,
                                reviewed_by = user_name,
                                remarks     = review_remarks,
                            )
                            st.toast("Payroll master approved.", icon="✅")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Approval failed: {exc}")
                with r_col:
                    if st.button("Reject", key=f"_pm_reject_{op_id}",
                                 use_container_width=True):
                        try:
                            sb.reject_payroll_master(
                                record_id   = pending["id"],
                                reviewed_by = user_name,
                                remarks     = review_remarks,
                            )
                            st.toast("Record rejected.", icon="🚫")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Rejection failed: {exc}")

        else:
            # Approved (or all rejected — show last approved / last rejected)
            if current:
                st.markdown("<div class='pm-banner-approved'>✓ Payroll master is approved and active.</div>",
                            unsafe_allow_html=True)
                _render_record(current)
            else:
                last = history[0] if history else {}
                st.markdown(
                    f"<div class='pm-banner-rejected'>Last revision was rejected. "
                    f"Remarks: {last.get('review_remarks') or '—'}</div>",
                    unsafe_allow_html=True,
                )
                _render_record(last)

            if not st.session_state.get(show_form_key):
                if st.button("Create Salary Revision", key=f"_pm_rev_{op_id}",
                             use_container_width=True):
                    st.session_state[show_form_key] = True
                    st.rerun()
            else:
                prefill = current or history[0] if history else {}
                _payroll_form(sb, operator, prefill, is_revision=True, user_name=user_name)

    # ── Tab: Salary History ───────────────────────────────────────────────────
    with tabs[1]:
        _render_history(history)


# ── main render ───────────────────────────────────────────────────────────────

def render() -> None:
    _inject_css()

    sb        = SupabaseClient()
    is_adm    = auth.is_admin()
    user_name = auth.current_profile().get("full_name", "")

    # Load all operators + their payroll history
    try:
        operators = sb.list_operators()
    except Exception as exc:
        st.error(f"Could not load operators: {exc}")
        return

    try:
        all_masters = sb.list_payroll_masters()
    except Exception:
        all_masters = []

    # Build history map: operator_id → [records]
    history_map: dict[str, list] = {}
    for rec in all_masters:
        op_id = rec.get("operator_id", "")
        if op_id:
            history_map.setdefault(op_id, []).append(rec)

    # Pending badge for admins in header
    pending_count = sum(
        1 for op in operators
        if any(r.get("approval_status") == "Pending" for r in history_map.get(op["id"], []))
    )

    title_extra = (
        f" <span style='background:#FEF9C3;color:#854D0E;font-size:12px;"
        f"font-weight:700;padding:2px 10px;border-radius:20px;'>{pending_count} Pending</span>"
        if is_adm and pending_count else ""
    )
    st.markdown(
        f"<h2 style='font-size:22px;font-weight:800;color:#0D1B33;margin-bottom:4px;'>"
        f"Payroll Masters{title_extra}</h2>"
        f"<p style='font-size:13px;color:#64748B;margin-bottom:20px;'>"
        f"Salary setup and approval workflow for all operators.</p>",
        unsafe_allow_html=True,
    )

    _render_kpis(operators, history_map)

    left, right = st.columns([2, 3], gap="large")

    with left:
        search = st.text_input("Search operators", placeholder="Name or Emp Code…",
                               label_visibility="collapsed",
                               key="_pm_search")
        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        _render_operator_list(operators, history_map, search)

    with right:
        sel_id = st.session_state.get("_pm_sel_op_id", "")
        if not sel_id:
            st.markdown(
                "<div style='color:#94A3B8;font-size:13px;padding:40px 0;text-align:center;'>"
                "Select an operator to view or set up their payroll master.</div>",
                unsafe_allow_html=True,
            )
        else:
            sel_op = next((op for op in operators if op["id"] == sel_id), None)
            if sel_op:
                _render_right(sb, sel_op, is_adm, user_name)
            else:
                st.warning("Operator not found.")
