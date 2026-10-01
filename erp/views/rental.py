from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

from .. import auth
from ..supabase_client import SupabaseClient
from ._report_utils import render_export_buttons

# ── Status constants ──────────────────────────────────────────────────────────

_S_DUE      = "Rent Due"
_S_PENDING  = "Pending Approval"
_S_APPROVED = "Approved"
_S_PAID     = "Paid"
_S_FAILED   = "Payment Failed"
_S_REJECTED = "Rejected"

_DEP_PENDING   = "Pending"
_DEP_PAID      = "Paid"
_DEP_RECOVERED = "Recovered"
_DEP_PARTIAL   = "Partially Recovered"

_BROK_PENDING = "Pending"
_BROK_PAID    = "Paid"

_STATUS_COLORS = {
    _S_DUE:      ("#FEF3C7", "#92400E"),
    _S_PENDING:  ("#DBEAFE", "#1E40AF"),
    _S_APPROVED: ("#D1FAE5", "#065F46"),
    _S_PAID:     ("#DCFCE7", "#166534"),
    _S_FAILED:   ("#FEE2E2", "#991B1B"),
    _S_REJECTED: ("#F3F4F6", "#374151"),
}

# ── Rental cycle helpers ──────────────────────────────────────────────────────

def _add_months(d: date, n: int) -> date:
    """Add n months, clamping day to last valid day of target month."""
    month = d.month - 1 + n
    year  = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _period_end(period_start: date) -> date:
    return _add_months(period_start, 1) - timedelta(days=1)


def _compute_periods(unit: dict, up_to: date) -> list[tuple[date, date]]:
    """All rental periods from rental_start_date up to `up_to`."""
    start_str = unit.get("rental_start_date")
    if not start_str:
        return []
    try:
        ps = date.fromisoformat(str(start_str)[:10])
    except Exception:
        return []
    periods: list[tuple[date, date]] = []
    while ps <= up_to:
        pe = _period_end(ps)
        periods.append((ps, pe))
        ps = pe + timedelta(days=1)
    return periods


def _period_label(ps: date, pe: date) -> str:
    return f"{ps.strftime('%d %b %Y')} – {pe.strftime('%d %b %Y')}"


def _fmt_date(v) -> str:
    if not v:
        return "—"
    try:
        return date.fromisoformat(str(v)[:10]).strftime("%d %b %Y")
    except Exception:
        return str(v)


def _fmt_inr(v) -> str:
    if not v and v != 0:
        return "—"
    try:
        return f"₹{float(v):,.0f}"
    except Exception:
        return str(v)


def _parse_date(v) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def _ordinal(n: int) -> str:
    return f"{n}{'st' if n==1 else 'nd' if n==2 else 'rd' if n==3 else 'th'}"

# ── UI helpers ────────────────────────────────────────────────────────────────

def _badge(status: str) -> str:
    bg, fg = _STATUS_COLORS.get(status, ("#F3F4F6", "#374151"))
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 10px;"
        f"border-radius:12px;font-size:11px;font-weight:700;'>{status}</span>"
    )


def _kpi(icon: str, label: str, value, sub: str = "", color: str = "#E87722") -> str:
    return (
        f"<div style='background:#fff;border:1px solid #E2EBF0;border-radius:12px;"
        f"padding:16px 20px;display:flex;gap:12px;align-items:flex-start;'>"
        f"<span class='msr' style='font-size:26px;color:{color};margin-top:2px;'>{icon}</span>"
        f"<div><div style='font-size:11px;color:#6B7280;font-weight:600;text-transform:uppercase;"
        f"letter-spacing:.06em;'>{label}</div>"
        f"<div style='font-size:22px;font-weight:800;color:#111827;line-height:1.2;'>{value}</div>"
        f"<div style='font-size:11px;color:#9CA3AF;margin-top:2px;'>{sub}</div></div></div>"
    )


def _section_hdr(label: str) -> None:
    st.markdown(
        f"<span style='font-size:11px;font-weight:700;color:#E87722;"
        f"text-transform:uppercase;letter-spacing:.08em;'>{label}</span>",
        unsafe_allow_html=True,
    )

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _user_name() -> str:
    p = auth.current_profile() or {}
    return p.get("full_name") or p.get("email") or "unknown"


def _is_admin() -> bool:
    return auth.is_admin()


def _role() -> str:
    p = auth.current_profile() or {}
    return (p.get("role") or "").lower()


# ═════════════════════════════════════════════════════════════════════════════
# Tab 1 — Rental Units
# ═════════════════════════════════════════════════════════════════════════════

def _tab_rental_units(sb: SupabaseClient) -> None:
    today    = date.today()
    is_admin = _is_admin()
    can_edit = is_admin or _role() in ("staff",)

    try:
        units = sb.list_rental_units()
    except Exception as e:
        st.error(f"Could not load rental units: {e}")
        return

    txns: list[dict] = []
    sites: list[dict] = []
    try:
        txns  = sb.list_rent_transactions()
        sites = sb.list_sites()
    except Exception:
        pass

    site_map = {s["id"]: s for s in sites if s.get("id")}
    tx_map   = {
        (t["rental_unit_id"], str(t["rental_period_start"])[:10]): t
        for t in txns if t.get("rental_unit_id") and t.get("rental_period_start")
    }

    # ── KPIs ─────────────────────────────────────────────────────────────────
    active_units = [u for u in units if u.get("unit_status", "Active") == "Active"]
    due_count    = sum(
        1
        for u in active_units
        for ps, pe in _compute_periods(u, today)
        if pe <= today and (u["id"], str(ps)) not in tx_map
    )
    total_monthly = sum(float(u.get("monthly_rent") or 0) for u in active_units)

    st.markdown(
        "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px;'>"
        + _kpi("home_work",               "Total Units",        len(units),
               f"{len(active_units)} active",              "#1E3A5F")
        + _kpi("check_circle",            "Active",             len(active_units),
               f"{len(units)-len(active_units)} closed",   "#10B981")
        + _kpi("notification_important",  "Rent Due",           due_count,
               "periods awaiting generation",
               "#F59E0B" if due_count > 0 else "#6B7280")
        + _kpi("payments",                "Total Monthly Rent", f"₹{total_monthly:,.0f}",
               "all active units",                         "#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ────────────────────────────────────────────────
    if "_ru_mode"   not in st.session_state: st.session_state["_ru_mode"]   = "none"
    if "_ru_sel_id" not in st.session_state: st.session_state["_ru_sel_id"] = ""

    mode    = st.session_state["_ru_mode"]
    sel_id  = st.session_state["_ru_sel_id"]
    unit_map = {u["id"]: u for u in units if u.get("id")}
    sel_unit = unit_map.get(sel_id) if sel_id else None

    sync_key = f"{mode}__{sel_id}"
    if st.session_state.get("_ru_sync_key") != sync_key:
        st.session_state["_ru_sync_key"]   = sync_key
        u = sel_unit or {}
        st.session_state["ru_unit_name"]   = u.get("unit_name") or ""
        st.session_state["ru_site_id"]     = u.get("site_id") or ""
        st.session_state["ru_address"]     = u.get("address") or ""
        st.session_state["ru_city"]        = u.get("city") or ""
        st.session_state["ru_state_val"]   = u.get("state") or ""
        st.session_state["ru_landlord"]    = u.get("landlord_name") or ""
        st.session_state["ru_mobile"]      = u.get("landlord_mobile") or ""
        st.session_state["ru_bank_name"]   = u.get("bank_name") or ""
        st.session_state["ru_acct_holder"] = u.get("account_holder_name") or ""
        st.session_state["ru_acct_number"] = u.get("account_number") or ""
        st.session_state["ru_ifsc"]        = u.get("ifsc") or ""
        st.session_state["ru_rent"]        = float(u.get("monthly_rent") or 0)
        st.session_state["ru_start_date"]  = _parse_date(u.get("rental_start_date"))
        st.session_state["ru_deposit"]     = float(u.get("security_deposit") or 0)
        st.session_state["ru_dep_pd"]      = _parse_date(u.get("deposit_paid_date"))
        dep_stat_raw = u.get("deposit_status") or _DEP_PENDING
        st.session_state["ru_dep_status"]  = dep_stat_raw if dep_stat_raw in [_DEP_PENDING, _DEP_PAID] else _DEP_PENDING
        st.session_state["ru_brokerage"]   = float(u.get("brokerage_amount") or 0)
        st.session_state["ru_brok_pd"]     = _parse_date(u.get("brokerage_paid_date"))
        brok_stat_raw = u.get("brokerage_status") or _BROK_PENDING
        st.session_state["ru_brok_status"] = brok_stat_raw if brok_stat_raw in [_BROK_PENDING, _BROK_PAID] else _BROK_PENDING

    left_col, right_col = st.columns([4, 7], gap="large")

    # ── Left: unit list ───────────────────────────────────────────────────────
    with left_col:
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search by unit name or site…", key="ru_search",
        )
        q = search_q.strip().lower()

        if is_admin:
            show_closed = st.checkbox("Show closed units", value=False, key="ru_show_closed")
            visible = [u for u in units if show_closed or u.get("unit_status", "Active") == "Active"]
        else:
            visible = [u for u in units if u.get("unit_status", "Active") == "Active"]

        if q:
            visible = [
                u for u in visible
                if q in (u.get("unit_name") or "").lower()
                or q in (site_map.get(u.get("site_id"), {}).get("site_name") or "").lower()
            ]

        if can_edit:
            if st.button("+ New Rental Unit", key="ru_btn_new", use_container_width=True):
                st.session_state["_ru_mode"]   = "new"
                st.session_state["_ru_sel_id"] = ""
                st.rerun()

        if not visible:
            st.info("No rental units found.")

        for u in sorted(visible, key=lambda x: (x.get("unit_status","Active") != "Active",
                                                  x.get("unit_name",""))):
            uid     = u["id"]
            site_nm = site_map.get(u.get("site_id"), {}).get("site_name", "—")
            u_status = u.get("unit_status", "Active")
            rent    = float(u.get("monthly_rent") or 0)
            unit_due = sum(
                1 for ps, pe in _compute_periods(u, today)
                if pe <= today and (uid, str(ps)) not in tx_map
            ) if u_status == "Active" else 0

            is_sel    = (uid == sel_id)
            card_bg   = "#EFF6FF" if is_sel else "#FFFFFF"
            border    = "2px solid #2563EB" if is_sel else "1px solid #E2EBF0"
            due_badge = (
                f"<span style='background:#FEF3C7;color:#92400E;padding:1px 8px;"
                f"border-radius:10px;font-size:10px;font-weight:700;'>⚠ {unit_due} Due</span>"
                if unit_due else ""
            )
            closed_badge = (
                "<span style='background:#F3F4F6;color:#6B7280;padding:1px 8px;"
                "border-radius:10px;font-size:10px;font-weight:700;'>Closed</span>"
                if u_status == "Closed" else ""
            )
            st.markdown(
                f"<div style='background:{card_bg};border:{border};border-radius:10px;"
                f"padding:10px 14px;margin-bottom:6px;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<span style='font-weight:700;color:#111827;font-size:13px;'>{u.get('unit_name','')}</span>"
                f"<span>{due_badge}{closed_badge}</span></div>"
                f"<div style='font-size:11px;color:#6B7280;margin-top:3px;'>"
                f"{site_nm} · ₹{rent:,.0f}/mo</div></div>",
                unsafe_allow_html=True,
            )
            if st.button("Select", key=f"ru_sel_{uid}", label_visibility="collapsed"):
                st.session_state["_ru_mode"]   = "edit"
                st.session_state["_ru_sel_id"] = uid
                st.rerun()

    # ── Right: form ───────────────────────────────────────────────────────────
    with right_col:
        if mode == "none":
            st.info("Select a unit from the list, or click **+ New Rental Unit** to add one.")
            return

        is_new = (mode == "new")
        hdr    = "New Rental Unit" if is_new else (sel_unit or {}).get("unit_name", "Edit Unit")
        st.markdown(
            f"<h3 style='margin:0 0 16px;color:#1E3A5F;'>{hdr}</h3>",
            unsafe_allow_html=True,
        )

        # ── Section 1: Basic ─────────────────────────────────────────────────
        with st.container(border=True):
            _section_hdr("Basic Details")
            c1, c2 = st.columns(2)
            with c1:
                unit_name = st.text_input("Unit Name *", key="ru_unit_name", disabled=not can_edit)
                site_opts = [""] + [s["id"] for s in sorted(sites, key=lambda s: s.get("site_name", ""))]
                site_id   = st.selectbox(
                    "Site *", options=site_opts,
                    format_func=lambda sid: "Select a site" if not sid
                        else site_map.get(sid, {}).get("site_name", sid),
                    key="ru_site_id", disabled=not can_edit,
                )
                address = st.text_input("Address", key="ru_address", disabled=not can_edit)
            with c2:
                city          = st.text_input("City",  key="ru_city",      disabled=not can_edit)
                state_val     = st.text_input("State", key="ru_state_val", disabled=not can_edit)
                start_date    = st.date_input("Rental Start Date *", key="ru_start_date", disabled=not can_edit)

        # ── Section 2: Rent & Cycle ───────────────────────────────────────────
        with st.container(border=True):
            _section_hdr("Rent")
            r1, r2 = st.columns(2)
            with r1:
                monthly_rent = st.number_input(
                    "Monthly Rent (₹) *", min_value=0.0, step=500.0,
                    key="ru_rent", disabled=not can_edit,
                )
            with r2:
                if start_date:
                    cd = start_date.day
                    st.markdown(
                        f"<div style='background:#F0FDF4;border:1px solid #BBF7D0;"
                        f"border-radius:8px;padding:10px 14px;margin-top:20px;'>"
                        f"<div style='font-size:10px;font-weight:700;color:#166534;"
                        f"text-transform:uppercase;letter-spacing:.06em;'>Auto-calculated Cycle</div>"
                        f"<div style='font-size:13px;font-weight:700;color:#111827;margin-top:4px;'>"
                        f"{_ordinal(cd)} of each month</div>"
                        f"<div style='font-size:11px;color:#6B7280;margin-top:2px;'>"
                        f"Rent becomes due on last day of cycle</div></div>",
                        unsafe_allow_html=True,
                    )

        # ── Section 3: Landlord & Bank ────────────────────────────────────────
        with st.container(border=True):
            _section_hdr("Landlord & Bank Details")
            ll1, ll2 = st.columns(2)
            with ll1:
                landlord_name = st.text_input("Landlord Name",    key="ru_landlord",    disabled=not can_edit)
                bank_name     = st.text_input("Bank Name",         key="ru_bank_name",   disabled=not can_edit)
                account_number= st.text_input("Account Number",    key="ru_acct_number", disabled=not can_edit)
            with ll2:
                landlord_mobile     = st.text_input("Mobile Number",        key="ru_mobile",      disabled=not can_edit)
                account_holder_name = st.text_input("Account Holder Name",  key="ru_acct_holder", disabled=not can_edit)
                ifsc                = st.text_input("IFSC Code",             key="ru_ifsc",        disabled=not can_edit)

        # ── Section 4: Deposit ────────────────────────────────────────────────
        with st.container(border=True):
            _section_hdr("Security Deposit")
            d1, d2, d3 = st.columns(3)
            with d1:
                security_deposit = st.number_input(
                    "Deposit Amount (₹)", min_value=0.0, step=1000.0,
                    key="ru_deposit", disabled=not can_edit,
                )
            with d2:
                dep_paid_date = st.date_input("Deposit Paid Date", key="ru_dep_pd", disabled=not can_edit)
            with d3:
                dep_status = st.selectbox(
                    "Deposit Status", options=[_DEP_PENDING, _DEP_PAID],
                    key="ru_dep_status", disabled=not can_edit,
                )

        # ── Section 5: Brokerage ──────────────────────────────────────────────
        with st.container(border=True):
            _section_hdr("One-time Brokerage / Setup Cost")
            b1, b2, b3 = st.columns(3)
            with b1:
                brokerage_amount = st.number_input(
                    "Brokerage Amount (₹)", min_value=0.0, step=500.0,
                    key="ru_brokerage", disabled=not can_edit,
                )
            with b2:
                brok_paid_date = st.date_input("Brokerage Paid Date", key="ru_brok_pd", disabled=not can_edit)
            with b3:
                brok_status = st.selectbox(
                    "Brokerage Status", options=[_BROK_PENDING, _BROK_PAID],
                    key="ru_brok_status", disabled=not can_edit,
                )

        # ── Save / Cancel ─────────────────────────────────────────────────────
        if can_edit:
            sc1, sc2, _ = st.columns([2, 2, 4])
            save_clicked   = sc1.button("Save Unit", key="ru_save",   type="primary", use_container_width=True)
            cancel_clicked = sc2.button("Cancel",    key="ru_cancel", use_container_width=True)

            if cancel_clicked:
                st.session_state["_ru_mode"]   = "none"
                st.session_state["_ru_sel_id"] = ""
                st.rerun()

            if save_clicked:
                errs = []
                if not unit_name.strip():
                    errs.append("Unit Name is required.")
                if not site_id:
                    errs.append("Site is required.")
                if not start_date:
                    errs.append("Rental Start Date is required.")
                if errs:
                    for e in errs:
                        st.error(e)
                else:
                    payload = dict(
                        unit_name=unit_name.strip(),
                        site_id=site_id,
                        address=address.strip() or None,
                        city=city.strip() or None,
                        state=state_val.strip() or None,
                        landlord_name=landlord_name.strip() or None,
                        landlord_mobile=landlord_mobile.strip() or None,
                        bank_name=bank_name.strip() or None,
                        account_holder_name=account_holder_name.strip() or None,
                        account_number=account_number.strip() or None,
                        ifsc=ifsc.strip() or None,
                        monthly_rent=monthly_rent or None,
                        rental_start_date=start_date.isoformat() if start_date else None,
                        security_deposit=security_deposit or None,
                        deposit_paid_date=dep_paid_date.isoformat() if dep_paid_date else None,
                        deposit_status=dep_status,
                        brokerage_amount=brokerage_amount or None,
                        brokerage_paid_date=brok_paid_date.isoformat() if brok_paid_date else None,
                        brokerage_status=brok_status,
                        modified_by=_user_name(),
                    )
                    try:
                        if is_new:
                            payload["unit_status"] = "Active"
                            payload["created_by"]  = _user_name()
                            sb.insert_rental_unit(payload)
                            st.success("Rental unit created successfully.")
                        else:
                            sb.update_rental_unit(sel_id, payload)
                            st.success("Rental unit updated.")
                        st.session_state["_ru_mode"]   = "none"
                        st.session_state["_ru_sel_id"] = ""
                        st.session_state.pop("_ru_sync_key", None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Save failed: {exc}")

        # ── Rent history & generate ───────────────────────────────────────────
        if not is_new and sel_unit:
            st.markdown("---")
            st.markdown(
                "<h4 style='color:#1E3A5F;margin-bottom:12px;'>Rent History & Due Periods</h4>",
                unsafe_allow_html=True,
            )
            u_status = sel_unit.get("unit_status", "Active")
            periods  = _compute_periods(sel_unit, today)
            unit_txns = [t for t in txns if t.get("rental_unit_id") == sel_id]
            tx_by_start = {str(t["rental_period_start"])[:10]: t for t in unit_txns}

            if not periods:
                st.info("No rental periods computed. Verify the Rental Start Date.")
            else:
                for ps, pe in reversed(periods):
                    tx     = tx_by_start.get(str(ps))
                    upcoming = pe > today
                    status_label = (
                        tx["status"] if tx
                        else ("Upcoming" if upcoming else _S_DUE)
                    )

                    c_lbl, c_due, c_status, c_action = st.columns([3, 2, 2, 2])
                    c_lbl.markdown(
                        f"<div style='font-size:12px;font-weight:600;color:#111827;"
                        f"padding-top:6px;'>{_period_label(ps, pe)}</div>",
                        unsafe_allow_html=True,
                    )
                    c_due.markdown(
                        f"<div style='font-size:11px;color:#6B7280;padding-top:8px;'>"
                        f"Due: {_fmt_date(pe)}</div>",
                        unsafe_allow_html=True,
                    )

                    if tx:
                        c_status.markdown(
                            f"<div style='padding-top:4px;'>{_badge(tx['status'])}</div>",
                            unsafe_allow_html=True,
                        )
                        amt = tx.get("paid_amount") or tx.get("approved_amount") or tx.get("monthly_rent")
                        c_action.markdown(
                            f"<div style='font-size:12px;font-weight:600;color:#374151;"
                            f"padding-top:6px;'>₹{float(amt):,.0f}</div>",
                            unsafe_allow_html=True,
                        )
                    elif not upcoming and u_status == "Active":
                        c_status.markdown(
                            f"<div style='padding-top:4px;'>{_badge(_S_DUE)}</div>",
                            unsafe_allow_html=True,
                        )
                        if c_action.button("Generate Rent", key=f"gen_{sel_id}_{ps}", type="primary"):
                            try:
                                sb.insert_rent_transaction({
                                    "rental_unit_id":      sel_id,
                                    "rental_period_start": str(ps),
                                    "rental_period_end":   str(pe),
                                    "due_date":            str(pe),
                                    "monthly_rent":        float(sel_unit.get("monthly_rent") or 0),
                                    "requested_amount":    float(sel_unit.get("monthly_rent") or 0),
                                    "status":              _S_PENDING,
                                    "created_by":          _user_name(),
                                })
                                st.success(f"Rent generated for {_period_label(ps, pe)} → sent for approval.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Failed to generate rent: {exc}")
                    else:
                        c_status.markdown(
                            "<div style='font-size:11px;color:#9CA3AF;padding-top:8px;'>Upcoming</div>",
                            unsafe_allow_html=True,
                        )

            # ── Admin: Close Unit ─────────────────────────────────────────────
            if is_admin and u_status == "Active":
                st.markdown("---")
                with st.expander("⚠ Close this Rental Unit"):
                    cl1, cl2 = st.columns(2)
                    closure_date = cl1.date_input("Closure Date", value=today, key="ru_closure_date")
                    closure_rem  = cl2.text_area("Remarks", key="ru_closure_remarks", height=80)
                    if st.button("Confirm — Close Unit", key="ru_close_btn", type="primary"):
                        try:
                            sb.update_rental_unit(sel_id, {
                                "unit_status":     "Closed",
                                "closure_date":    closure_date.isoformat(),
                                "closure_remarks": closure_rem.strip() or None,
                                "modified_by":     _user_name(),
                            })
                            st.success("Rental unit closed. No further rent will be generated.")
                            st.session_state.pop("_ru_sync_key", None)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# Tab 2 — Pending Approval
# ═════════════════════════════════════════════════════════════════════════════

def _tab_pending_approval(sb: SupabaseClient) -> None:
    can_approve = _is_admin() or _role() in ("approver",)
    if not can_approve:
        st.info("Only Approvers and Admins can approve rent submissions.", icon="🔒")
        return

    try:
        txns  = sb.list_rent_transactions(status=_S_PENDING)
        units = sb.list_rental_units()
        sites = sb.list_sites()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    unit_map = {u["id"]: u for u in units if u.get("id")}
    site_map = {s["id"]: s for s in sites if s.get("id")}

    if not txns:
        st.success("No pending approvals. All rent submissions are up to date.")
        return

    st.markdown(
        f"<div style='background:#DBEAFE;border:1px solid #BFDBFE;border-radius:10px;"
        f"padding:12px 18px;margin-bottom:16px;font-weight:600;color:#1E40AF;'>"
        f"🔔 {len(txns)} rent submission{'s' if len(txns)>1 else ''} awaiting your approval</div>",
        unsafe_allow_html=True,
    )

    for tx in sorted(txns, key=lambda t: t.get("due_date") or ""):
        uid    = tx.get("rental_unit_id", "")
        unit   = unit_map.get(uid, {})
        site   = site_map.get(unit.get("site_id", ""), {})
        ps     = _parse_date(tx.get("rental_period_start"))
        pe     = _parse_date(tx.get("rental_period_end"))
        period = _period_label(ps, pe) if ps and pe else "—"
        tx_id  = tx["id"]

        with st.container(border=True):
            h1, h2, h3 = st.columns([3, 3, 2])
            h1.markdown(
                f"<div style='font-weight:700;color:#111827;font-size:14px;'>"
                f"{unit.get('unit_name','—')}</div>"
                f"<div style='font-size:11px;color:#6B7280;'>{site.get('site_name','—')}</div>",
                unsafe_allow_html=True,
            )
            h2.markdown(
                f"<div style='font-size:12px;'><b>Period:</b> {period}</div>"
                f"<div style='font-size:12px;'><b>Due Date:</b> {_fmt_date(tx.get('due_date'))}</div>",
                unsafe_allow_html=True,
            )
            h3.markdown(
                f"<div style='font-size:14px;font-weight:700;color:#1E3A5F;'>"
                f"₹{float(tx.get('monthly_rent') or 0):,.0f}</div>"
                f"<div style='font-size:11px;color:#6B7280;'>Monthly Rent</div>",
                unsafe_allow_html=True,
            )

            i1, i2, i3, i4 = st.columns(4)
            i1.markdown(f"<div style='font-size:11px;color:#6B7280;'>Landlord</div>"
                        f"<div style='font-size:12px;font-weight:600;'>{unit.get('landlord_name','—')}</div>",
                        unsafe_allow_html=True)
            i2.markdown(f"<div style='font-size:11px;color:#6B7280;'>Bank</div>"
                        f"<div style='font-size:12px;font-weight:600;'>{unit.get('bank_name','—')}</div>",
                        unsafe_allow_html=True)
            i3.markdown(f"<div style='font-size:11px;color:#6B7280;'>Account No.</div>"
                        f"<div style='font-size:12px;font-weight:600;font-family:monospace;'>"
                        f"{unit.get('account_number','—')}</div>", unsafe_allow_html=True)
            i4.markdown(f"<div style='font-size:11px;color:#6B7280;'>IFSC</div>"
                        f"<div style='font-size:12px;font-weight:600;font-family:monospace;'>"
                        f"{unit.get('ifsc','—')}</div>", unsafe_allow_html=True)

            a1, a2, a3, a4 = st.columns([3, 1, 1, 1])
            approved_amt = a1.number_input(
                "Approved Amount (₹)",
                min_value=0.0, step=500.0,
                value=float(tx.get("requested_amount") or tx.get("monthly_rent") or 0),
                key=f"apr_amt_{tx_id}",
            )
            a2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if a3.button("Approve", key=f"apr_yes_{tx_id}", type="primary", use_container_width=True):
                try:
                    sb.update_rent_transaction(tx_id, {
                        "status":          _S_APPROVED,
                        "approved_amount": approved_amt,
                        "approved_by":     _user_name(),
                        "approved_at":     date.today().isoformat(),
                    })
                    st.success("Approved.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed: {exc}")
            if a4.button("Reject", key=f"apr_no_{tx_id}", use_container_width=True):
                try:
                    sb.update_rent_transaction(tx_id, {
                        "status":      _S_REJECTED,
                        "approved_by": _user_name(),
                        "approved_at": date.today().isoformat(),
                    })
                    st.warning("Rejected.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# Tab 3 — Accounts / Pending Payment
# ═════════════════════════════════════════════════════════════════════════════

def _tab_accounts(sb: SupabaseClient) -> None:
    can_access = _is_admin() or _role() in ("accounts",)
    if not can_access:
        st.info("Only Accounts and Admins can access this section.", icon="🔒")
        return

    try:
        approved_txns = sb.list_rent_transactions(status=_S_APPROVED)
        failed_txns   = sb.list_rent_transactions(status=_S_FAILED)
        units  = sb.list_rental_units()
        sites  = sb.list_sites()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    unit_map = {u["id"]: u for u in units if u.get("id")}
    site_map = {s["id"]: s for s in sites if s.get("id")}

    all_pending = approved_txns + failed_txns

    if not all_pending:
        st.success("Payment queue is clear. No approved payments pending.")
        return

    # ── Excel / PDF export for bank upload ───────────────────────────────────
    if approved_txns:
        export_rows = []
        for tx in approved_txns:
            uid  = tx.get("rental_unit_id", "")
            unit = unit_map.get(uid, {})
            site = site_map.get(unit.get("site_id", ""), {})
            ps   = _parse_date(tx.get("rental_period_start"))
            pe   = _parse_date(tx.get("rental_period_end"))
            export_rows.append({
                "Site":           site.get("site_name", ""),
                "Unit":           unit.get("unit_name", ""),
                "Rental Period":  _period_label(ps, pe) if ps and pe else "",
                "Amount":         float(tx.get("approved_amount") or 0),
                "Bank Name":      unit.get("bank_name", ""),
                "Account Name":   unit.get("account_holder_name", ""),
                "Account Number": unit.get("account_number", ""),
                "IFSC":           unit.get("ifsc", ""),
            })
        render_export_buttons(
            pd.DataFrame(export_rows),
            base_name="rent_payment_sheet",
            excel_key="rent_acct_xlsx",
            pdf_key="rent_acct_pdf",
            title="Rent Payment Sheet",
            subtitle=f"{len(approved_txns)} approved payments",
            sheet_name="Rent Payments",
        )
        st.markdown("---")

    # ── Failed payments — retry ────────────────────────────────────────────────
    if failed_txns:
        st.markdown(
            f"<div style='background:#FEE2E2;border:1px solid #FECACA;border-radius:10px;"
            f"padding:10px 16px;margin-bottom:12px;font-weight:600;color:#991B1B;'>"
            f"⚠ {len(failed_txns)} payment failure(s) — action required</div>",
            unsafe_allow_html=True,
        )
        for tx in failed_txns:
            uid  = tx.get("rental_unit_id", "")
            unit = unit_map.get(uid, {})
            site = site_map.get(unit.get("site_id", ""), {})
            tx_id = tx["id"]
            with st.container(border=True):
                fc1, fc2, fc3, fc4 = st.columns([3, 3, 2, 1])
                fc1.markdown(
                    f"<b>{unit.get('unit_name','—')}</b><br>"
                    f"<span style='font-size:11px;color:#6B7280;'>{site.get('site_name','—')}</span>",
                    unsafe_allow_html=True,
                )
                fc2.markdown(
                    f"<span style='font-size:12px;'>{_fmt_date(tx.get('rental_period_start'))} – "
                    f"{_fmt_date(tx.get('rental_period_end'))}</span><br>"
                    f"<span style='font-size:11px;color:#991B1B;'>{tx.get('failure_remarks','')}</span>",
                    unsafe_allow_html=True,
                )
                fc3.markdown(
                    f"<b>₹{float(tx.get('approved_amount') or 0):,.0f}</b>",
                    unsafe_allow_html=True,
                )
                if fc4.button("Retry", key=f"retry_{tx_id}", type="primary", use_container_width=True):
                    try:
                        sb.update_rent_transaction(tx_id, {
                            "status":          _S_APPROVED,
                            "failure_remarks": None,
                        })
                        st.success("Moved back to Approved for retry.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed: {exc}")
        st.markdown("---")

    # ── Approved — mark as paid ───────────────────────────────────────────────
    if approved_txns:
        st.markdown(
            f"<div style='font-size:13px;font-weight:700;color:#065F46;margin-bottom:12px;'>"
            f"✓ {len(approved_txns)} payment(s) approved — ready to mark as paid</div>",
            unsafe_allow_html=True,
        )
        for tx in sorted(approved_txns, key=lambda t: t.get("due_date") or ""):
            uid  = tx.get("rental_unit_id", "")
            unit = unit_map.get(uid, {})
            site = site_map.get(unit.get("site_id", ""), {})
            ps   = _parse_date(tx.get("rental_period_start"))
            pe   = _parse_date(tx.get("rental_period_end"))
            period = _period_label(ps, pe) if ps and pe else "—"
            tx_id  = tx["id"]

            with st.container(border=True):
                h1, h2, h3, h4 = st.columns([3, 3, 2, 2])
                h1.markdown(
                    f"<div style='font-weight:700;font-size:13px;'>{unit.get('unit_name','—')}</div>"
                    f"<div style='font-size:11px;color:#6B7280;'>{site.get('site_name','—')}</div>",
                    unsafe_allow_html=True,
                )
                h2.markdown(
                    f"<div style='font-size:12px;'><b>Period:</b> {period}</div>"
                    f"<div style='font-size:12px;'><b>Landlord:</b> {unit.get('landlord_name','—')}</div>",
                    unsafe_allow_html=True,
                )
                h3.markdown(
                    f"<div style='font-size:14px;font-weight:700;color:#065F46;'>"
                    f"₹{float(tx.get('approved_amount') or 0):,.0f}</div>"
                    f"<div style='font-size:11px;color:#6B7280;'>Approved Amount</div>",
                    unsafe_allow_html=True,
                )
                h4.markdown(
                    f"<div style='font-size:11px;font-family:monospace;'>"
                    f"{unit.get('account_number','—')}</div>"
                    f"<div style='font-size:11px;color:#6B7280;'>{unit.get('ifsc','—')}</div>",
                    unsafe_allow_html=True,
                )

                with st.expander("Mark as Paid / Record Failure"):
                    p1, p2, p3 = st.columns(3)
                    pay_date = p1.date_input("Payment Date", value=date.today(), key=f"pay_dt_{tx_id}")
                    pay_amt  = p2.number_input(
                        "Amount Paid (₹)", min_value=0.0, step=500.0,
                        value=float(tx.get("approved_amount") or 0), key=f"pay_amt_{tx_id}",
                    )
                    utr     = p3.text_input("UTR / Reference", key=f"pay_utr_{tx_id}", placeholder="optional")
                    remarks = st.text_input("Remarks", key=f"pay_rem_{tx_id}", placeholder="optional")

                    pa1, pa2, _ = st.columns([2, 2, 4])
                    if pa1.button("Mark as Paid", key=f"paid_{tx_id}", type="primary", use_container_width=True):
                        try:
                            sb.update_rent_transaction(tx_id, {
                                "status":          _S_PAID,
                                "paid_amount":     pay_amt,
                                "payment_date":    pay_date.isoformat(),
                                "utr":             utr.strip() or None,
                                "payment_remarks": remarks.strip() or None,
                                "paid_by":         _user_name(),
                                "paid_at":         date.today().isoformat(),
                            })
                            st.success("Marked as Paid.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed: {exc}")
                    if pa2.button("Record Failure", key=f"fail_{tx_id}", use_container_width=True):
                        try:
                            sb.update_rent_transaction(tx_id, {
                                "status":          _S_FAILED,
                                "failure_remarks": remarks.strip() or "Payment failed — to be retried",
                            })
                            st.warning("Failure recorded.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# Tab 4 — Payment History
# ═════════════════════════════════════════════════════════════════════════════

def _tab_payment_history(sb: SupabaseClient) -> None:
    try:
        txns  = sb.list_rent_transactions()
        units = sb.list_rental_units()
        sites = sb.list_sites()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    unit_map = {u["id"]: u for u in units if u.get("id")}
    site_map = {s["id"]: s for s in sites if s.get("id")}

    if not txns:
        st.info("No payment records yet.")
        return

    enriched = [
        (tx, unit_map.get(tx.get("rental_unit_id",""), {}),
             site_map.get(unit_map.get(tx.get("rental_unit_id",""), {}).get("site_id",""), {}))
        for tx in txns
    ]

    all_sites_names = sorted({s.get("site_name","") for _, _, s in enriched} - {""})
    all_unit_names  = sorted({u.get("unit_name","")  for _, u, _ in enriched} - {""})

    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    flt_site   = f1.selectbox("Site",   ["All"] + all_sites_names, key="ph_site")
    flt_unit   = f2.selectbox("Unit",   ["All"] + all_unit_names,  key="ph_unit")
    flt_status = f3.selectbox("Status", ["All", _S_DUE, _S_PENDING, _S_APPROVED, _S_PAID, _S_FAILED, _S_REJECTED], key="ph_status")
    flt_month  = f4.text_input("Month (YYYY-MM)", key="ph_month", placeholder="e.g. 2026-10")

    filtered = [
        (tx, u, s) for tx, u, s in enriched
        if (flt_site   == "All" or s.get("site_name","") == flt_site)
        and (flt_unit  == "All" or u.get("unit_name","") == flt_unit)
        and (flt_status== "All" or tx.get("status","")  == flt_status)
        and (not flt_month.strip() or str(tx.get("rental_period_start",""))[:7] == flt_month.strip())
    ]

    if not filtered:
        st.info("No records match the selected filters.")
        return

    st.markdown(
        f"<div style='font-size:12px;color:#6B7280;margin-bottom:10px;'>"
        f"Showing {len(filtered)} record{'s' if len(filtered)!=1 else ''}</div>",
        unsafe_allow_html=True,
    )

    hs = ("padding:9px 12px;background:#F8FAFC;font-size:10px;font-weight:700;"
          "letter-spacing:.1em;text-transform:uppercase;color:#6B7280;"
          "border-bottom:2px solid #E2EBF0;white-space:nowrap;")
    ds = "padding:8px 12px;font-size:12px;color:#374151;border-bottom:1px solid #F1F5F9;"
    headers = ["Site", "Unit", "Rental Period", "Due Date", "Approved Amt", "Paid Amt",
               "Payment Date", "UTR", "Status"]

    rows_html = ""
    for tx, u, s in sorted(filtered, key=lambda x: x[0].get("rental_period_start",""), reverse=True):
        ps     = _parse_date(tx.get("rental_period_start"))
        pe     = _parse_date(tx.get("rental_period_end"))
        status = tx.get("status","")
        bg, fg = _STATUS_COLORS.get(status, ("#F3F4F6","#374151"))
        rows_html += (
            f"<tr>"
            f"<td style='{ds}'>{s.get('site_name','—')}</td>"
            f"<td style='{ds}font-weight:600;'>{u.get('unit_name','—')}</td>"
            f"<td style='{ds}'>{_period_label(ps, pe) if ps and pe else '—'}</td>"
            f"<td style='{ds}'>{_fmt_date(tx.get('due_date'))}</td>"
            f"<td style='{ds}font-weight:600;'>{_fmt_inr(tx.get('approved_amount'))}</td>"
            f"<td style='{ds}'>{_fmt_inr(tx.get('paid_amount'))}</td>"
            f"<td style='{ds}'>{_fmt_date(tx.get('payment_date'))}</td>"
            f"<td style='{ds}font-family:monospace;font-size:11px;'>{tx.get('utr') or '—'}</td>"
            f"<td style='{ds}'><span style='background:{bg};color:{fg};padding:2px 9px;"
            f"border-radius:10px;font-size:10px;font-weight:700;'>{status}</span></td>"
            f"</tr>"
        )

    st.markdown(
        "<div style='overflow-x:auto;border:1px solid #E2EBF0;border-radius:10px;"
        "box-shadow:0 1px 3px rgba(0,0,0,.05);'>"
        "<table style='width:100%;border-collapse:collapse;font-family:inherit;'>"
        "<thead><tr>" + "".join(f"<th style='{hs}'>{h}</th>" for h in headers) + "</tr></thead>"
        f"<tbody>{rows_html}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)
    export_rows = [{
        "Site":           s.get("site_name",""),
        "Unit":           u.get("unit_name",""),
        "Rental Period":  _period_label(ps2, pe2) if (ps2 := _parse_date(tx.get("rental_period_start"))) and (pe2 := _parse_date(tx.get("rental_period_end"))) else "",
        "Due Date":       str(tx.get("due_date","") or ""),
        "Approved Amt":   tx.get("approved_amount") or "",
        "Paid Amt":       tx.get("paid_amount") or "",
        "Payment Date":   str(tx.get("payment_date","") or ""),
        "UTR":            tx.get("utr") or "",
        "Status":         tx.get("status",""),
    } for tx, u, s in filtered]

    render_export_buttons(
        pd.DataFrame(export_rows),
        base_name="rent_payment_history",
        excel_key="ph_xlsx",
        pdf_key="ph_pdf",
        title="Rent Payment History",
        sheet_name="Payment History",
    )


# ═════════════════════════════════════════════════════════════════════════════
# Tab 5 — Deposit Recovery
# ═════════════════════════════════════════════════════════════════════════════

def _tab_deposit_recovery(sb: SupabaseClient) -> None:
    can_act = _is_admin() or _role() in ("staff", "accounts")
    try:
        units = sb.list_rental_units()
        sites = sb.list_sites()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    site_map = {s["id"]: s for s in sites if s.get("id")}

    pending = [
        u for u in units
        if u.get("unit_status") == "Closed"
        and float(u.get("security_deposit") or 0) > 0
        and u.get("deposit_status") not in (_DEP_RECOVERED,)
    ]
    recovered = [
        u for u in units
        if u.get("unit_status") == "Closed"
        and u.get("deposit_status") == _DEP_RECOVERED
    ]

    if not pending and not recovered:
        st.info("No closed rental units with deposits recorded.")
        return

    if pending:
        st.markdown(
            f"<div style='background:#FEF3C7;border:1px solid #FDE68A;border-radius:10px;"
            f"padding:12px 18px;margin-bottom:16px;font-weight:600;color:#92400E;'>"
            f"⚠ {len(pending)} deposit(s) outstanding</div>",
            unsafe_allow_html=True,
        )

        for u in pending:
            uid  = u["id"]
            site = site_map.get(u.get("site_id",""), {})
            dep  = float(u.get("security_deposit") or 0)
            rec  = float(u.get("deposit_recovery_amount") or 0)

            with st.container(border=True):
                h1, h2, h3, h4 = st.columns([3, 2, 2, 2])
                h1.markdown(
                    f"<div style='font-weight:700;font-size:13px;'>{u.get('unit_name','—')}</div>"
                    f"<div style='font-size:11px;color:#6B7280;'>{site.get('site_name','—')}</div>"
                    f"<div style='font-size:11px;color:#6B7280;'>Closed: {_fmt_date(u.get('closure_date'))}</div>",
                    unsafe_allow_html=True,
                )
                h2.markdown(
                    f"<div style='font-size:11px;color:#6B7280;'>Deposit Paid</div>"
                    f"<div style='font-size:14px;font-weight:700;color:#1E3A5F;'>₹{dep:,.0f}</div>",
                    unsafe_allow_html=True,
                )
                h3.markdown(
                    f"<div style='font-size:11px;color:#6B7280;'>Recovered So Far</div>"
                    f"<div style='font-size:14px;font-weight:700;color:#065F46;'>₹{rec:,.0f}</div>",
                    unsafe_allow_html=True,
                )
                h4.markdown(
                    f"<div style='font-size:11px;color:#6B7280;'>Outstanding</div>"
                    f"<div style='font-size:14px;font-weight:700;color:#991B1B;'>₹{dep-rec:,.0f}</div>",
                    unsafe_allow_html=True,
                )

                if can_act:
                    with st.expander("Record Recovery"):
                        rc1, rc2, rc3 = st.columns(3)
                        rec_amt  = rc1.number_input(
                            "Recovery Amount (₹)", min_value=0.0, step=1000.0,
                            value=float(dep - rec), key=f"dep_amt_{uid}",
                        )
                        rec_date = rc2.date_input("Recovery Date", value=date.today(), key=f"dep_dt_{uid}")
                        ded_amt  = rc3.number_input(
                            "Deduction (₹)", min_value=0.0, step=100.0,
                            value=0.0, key=f"dep_ded_{uid}",
                        )
                        rec_rem  = st.text_input("Remarks", key=f"dep_rem_{uid}", placeholder="optional")

                        total_recovered = rec + rec_amt
                        new_status = _DEP_RECOVERED if total_recovered >= dep else _DEP_PARTIAL
                        st.markdown(
                            f"<div style='font-size:11px;color:#6B7280;margin-bottom:8px;'>"
                            f"Status after save: <b>{new_status}</b></div>",
                            unsafe_allow_html=True,
                        )

                        if st.button("Save Recovery", key=f"dep_save_{uid}", type="primary"):
                            try:
                                sb.update_rental_unit(uid, {
                                    "deposit_status":          new_status,
                                    "deposit_recovery_amount": total_recovered,
                                    "deposit_recovery_date":   rec_date.isoformat(),
                                    "deposit_deduction":       ded_amt or None,
                                    "deposit_remarks":         rec_rem.strip() or None,
                                    "modified_by":             _user_name(),
                                })
                                st.success(f"Recovery recorded. Status: {new_status}")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Failed: {exc}")

    if recovered:
        st.markdown("---")
        st.markdown(
            f"<div style='font-size:12px;color:#6B7280;margin-bottom:8px;font-weight:600;'>"
            f"✓ {len(recovered)} deposit(s) fully recovered</div>",
            unsafe_allow_html=True,
        )
        for u in recovered:
            site = site_map.get(u.get("site_id",""), {})
            rec_amt = float(u.get("deposit_recovery_amount") or u.get("security_deposit") or 0)
            st.markdown(
                f"<div style='background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;"
                f"padding:8px 14px;margin-bottom:6px;display:flex;justify-content:space-between;'>"
                f"<span style='font-weight:600;font-size:12px;'>{u.get('unit_name','—')}"
                f" · {site.get('site_name','—')}</span>"
                f"<span style='font-size:12px;color:#166534;font-weight:600;'>₹{rec_amt:,.0f} recovered "
                f"on {_fmt_date(u.get('deposit_recovery_date'))}</span></div>",
                unsafe_allow_html=True,
            )


# ═════════════════════════════════════════════════════════════════════════════
# Main render
# ═════════════════════════════════════════════════════════════════════════════

def render() -> None:
    sb = SupabaseClient()

    st.markdown(
        "<h2 style='margin:0 0 4px;color:#1E3A5F;'>Rental</h2>"
        "<p style='color:#6B7280;font-size:13px;margin:0 0 20px;'>"
        "Manage operator accommodation — units, rent approvals, payments, and deposit recovery</p>",
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["Rental Units", "Pending Approval", "Accounts", "Payment History", "Deposit Recovery"])
    with tabs[0]: _tab_rental_units(sb)
    with tabs[1]: _tab_pending_approval(sb)
    with tabs[2]: _tab_accounts(sb)
    with tabs[3]: _tab_payment_history(sb)
    with tabs[4]: _tab_deposit_recovery(sb)
