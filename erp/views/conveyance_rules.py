"""
erp/views/conveyance_rules.py
Conveyance Rules module — Phase 1.

Two sections (tabs):
  1. Site Default Rules   — one rate per site with effective dates + active flag
  2. Employee Overrides   — per-employee site rate that supersedes the default
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from erp import auth
from erp.models import ConveyanceUnit
from erp.supabase_client import SupabaseClient

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
.cv-sec-hdr {
    font-size:10px; font-weight:700; letter-spacing:.13em;
    text-transform:uppercase; color:#E87722;
    margin-bottom:10px; padding-bottom:7px;
    border-bottom:1px solid #F1F5F9;
    display:flex; align-items:center; gap:6px;
}
.cv-row {
    display:grid; gap:8px; padding:10px 6px;
    border-bottom:1px solid #F1F5F9; font-size:12px;
    color:#374151; align-items:center;
}
.cv-row-site     { grid-template-columns: 2fr 1fr 1fr 1fr 1fr 70px 80px; }
.cv-row-override { grid-template-columns: 2fr 2fr 1fr 1fr 1fr 1fr 80px; }
.cv-hdr { font-weight:700; color:#64748B; font-size:10px;
    letter-spacing:.08em; text-transform:uppercase; }
.cv-badge-active   { background:#DCFCE7; color:#166534;
    padding:2px 8px; border-radius:20px; font-size:10px; font-weight:700; }
.cv-badge-inactive { background:#F1F5F9; color:#475569;
    padding:2px 8px; border-radius:20px; font-size:10px; font-weight:700; }
.cv-empty { text-align:center; padding:28px 0; color:#94A3B8; font-size:13px; }
</style>
"""

_UNITS = [u.value for u in ConveyanceUnit]

_CSS_INJECTED = False


def _inject_css() -> None:
    global _CSS_INJECTED
    if not _CSS_INJECTED:
        st.markdown(_CSS, unsafe_allow_html=True)
        _CSS_INJECTED = True


def _fmt_date(d) -> str:
    return str(d)[:10] if d else "—"


# ── Site Default Rules ────────────────────────────────────────────────────────

@st.dialog("Site Conveyance Rule", width="large")
def _site_rule_dialog(sb: SupabaseClient, sites: list, prefill: dict, user_name: str) -> None:
    is_edit = bool(prefill.get("id"))
    st.markdown(
        f"<p style='font-size:13px;color:#64748B;margin-bottom:16px;'>"
        f"{'Edit' if is_edit else 'Add'} a conveyance rate for a site.</p>",
        unsafe_allow_html=True,
    )

    site_opts = {s["site_name"]: s["id"] for s in sites}
    current_site_name = ""
    if is_edit and prefill.get("site_id"):
        current_site_name = next((s["site_name"] for s in sites if s["id"] == prefill["site_id"]), "")

    with st.form("_cv_site_form"):
        site_name = st.selectbox(
            "Site *",
            options=list(site_opts.keys()),
            index=list(site_opts.keys()).index(current_site_name) if current_site_name in site_opts else 0,
        )
        c1, c2 = st.columns(2)
        with c1:
            rate = st.number_input(
                "Rate (₹) *", min_value=0.0, step=50.0,
                value=float(prefill.get("rate") or 0),
                format="%.2f",
            )
        with c2:
            unit = st.selectbox(
                "Unit *", options=_UNITS,
                index=_UNITS.index(prefill.get("unit", "Per Day")) if prefill.get("unit") in _UNITS else 0,
            )
        d1, d2 = st.columns(2)
        with d1:
            eff_from = st.date_input(
                "Effective From *",
                value=date.fromisoformat(prefill["effective_from"]) if prefill.get("effective_from") else date.today(),
            )
        with d2:
            eff_to = st.date_input(
                "Effective To (leave blank = open-ended)",
                value=date.fromisoformat(prefill["effective_to"]) if prefill.get("effective_to") else None,
            )
        is_active = st.checkbox("Active", value=bool(prefill.get("is_active", True)))
        remarks   = st.text_input("Remarks", value=prefill.get("remarks") or "")

        submitted = st.form_submit_button("Save", use_container_width=True, type="primary")

    if submitted:
        if not site_name or not rate:
            st.error("Site and Rate are required.")
            return
        payload: dict = {
            "site_id":       site_opts[site_name],
            "rate":          float(rate),
            "unit":          unit,
            "effective_from": eff_from.isoformat(),
            "effective_to":  eff_to.isoformat() if eff_to else None,
            "is_active":     is_active,
            "remarks":       remarks.strip() or None,
            "created_by":    user_name,
        }
        if is_edit:
            payload["id"] = prefill["id"]
        try:
            sb.upsert_conveyance_site_rule(payload)
            st.toast("Rule saved.", icon="✅")
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")


def _render_site_rules(sb: SupabaseClient, is_adm: bool, sites: list, user_name: str) -> None:
    try:
        rules = sb.list_conveyance_site_rules()
    except Exception as exc:
        st.warning(f"Could not load rules: {exc}")
        return

    # Build site_id → site_name lookup
    site_lookup = {s["id"]: s["site_name"] for s in sites}

    col_add, _ = st.columns([1, 5])
    with col_add:
        if st.button("+ Add Rule", key="_cv_add_site", type="primary"):
            st.session_state["_cv_site_edit"] = {}
            _site_rule_dialog(sb, sites, {}, user_name)

    if not rules:
        st.markdown("<div class='cv-empty'>No site conveyance rules defined yet.</div>",
                    unsafe_allow_html=True)
        return

    # Table header
    hdrs = ["Site", "Rate", "Unit", "Eff. From", "Eff. To", "Active", "Actions"]
    html = "<div class='cv-row cv-row-site cv-hdr'>"
    for h in hdrs:
        html += f"<span>{h}</span>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

    for rule in rules:
        site_name  = site_lookup.get(rule.get("site_id", ""), rule.get("site_id", "—"))
        rate_txt   = f"₹{float(rule.get('rate',0)):,.2f}"
        badge_cls  = "cv-badge-active" if rule.get("is_active") else "cv-badge-inactive"
        badge_txt  = "Active" if rule.get("is_active") else "Inactive"

        st.markdown(
            f"<div class='cv-row cv-row-site'>"
            f"<span style='font-weight:600;'>{site_name}</span>"
            f"<span>{rate_txt}</span>"
            f"<span>{rule.get('unit','—')}</span>"
            f"<span>{_fmt_date(rule.get('effective_from'))}</span>"
            f"<span>{_fmt_date(rule.get('effective_to'))}</span>"
            f"<span><span class='{badge_cls}'>{badge_txt}</span></span>"
            f"<span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        e_col, d_col = st.columns([1, 1])
        with e_col:
            if st.button("Edit", key=f"_cv_site_ed_{rule['id']}", use_container_width=True):
                _site_rule_dialog(sb, sites, rule, user_name)
        with d_col:
            if is_adm:
                if st.button("Delete", key=f"_cv_site_del_{rule['id']}", use_container_width=True):
                    try:
                        sb.delete_conveyance_site_rule(rule["id"])
                        st.toast("Rule deleted.", icon="🗑️")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Delete failed: {exc}")


# ── Employee Overrides ────────────────────────────────────────────────────────

@st.dialog("Employee Conveyance Override", width="large")
def _override_dialog(sb: SupabaseClient, operators: list, sites: list, prefill: dict, user_name: str) -> None:
    is_edit = bool(prefill.get("id"))
    st.markdown(
        f"<p style='font-size:13px;color:#64748B;margin-bottom:16px;'>"
        f"{'Edit' if is_edit else 'Add'} a per-employee site conveyance override.</p>",
        unsafe_allow_html=True,
    )

    op_opts   = {f"{op.get('emp_code','')} — {op.get('operator_name','')}": op["id"] for op in operators}
    site_opts = {s["site_name"]: s["id"] for s in sites}

    current_op_label = ""
    current_site_name = ""
    if is_edit:
        if prefill.get("operator_id"):
            op = next((o for o in operators if o["id"] == prefill["operator_id"]), None)
            if op:
                current_op_label = f"{op.get('emp_code','')} — {op.get('operator_name','')}"
        if prefill.get("site_id"):
            current_site_name = next((s["site_name"] for s in sites if s["id"] == prefill["site_id"]), "")

    with st.form("_cv_override_form"):
        op_label = st.selectbox(
            "Operator *", options=list(op_opts.keys()),
            index=list(op_opts.keys()).index(current_op_label) if current_op_label in op_opts else 0,
        )
        site_name = st.selectbox(
            "Site *", options=list(site_opts.keys()),
            index=list(site_opts.keys()).index(current_site_name) if current_site_name in site_opts else 0,
        )
        c1, c2 = st.columns(2)
        with c1:
            rate = st.number_input(
                "Override Rate (₹) *", min_value=0.0, step=50.0,
                value=float(prefill.get("rate") or 0), format="%.2f",
            )
        with c2:
            unit = st.selectbox(
                "Unit *", options=_UNITS,
                index=_UNITS.index(prefill.get("unit", "Per Day")) if prefill.get("unit") in _UNITS else 0,
            )
        d1, d2 = st.columns(2)
        with d1:
            eff_from = st.date_input(
                "Effective From *",
                value=date.fromisoformat(prefill["effective_from"]) if prefill.get("effective_from") else date.today(),
            )
        with d2:
            eff_to = st.date_input(
                "Effective To (leave blank = open-ended)",
                value=date.fromisoformat(prefill["effective_to"]) if prefill.get("effective_to") else None,
            )
        is_active = st.checkbox("Active", value=bool(prefill.get("is_active", True)))
        reason    = st.text_area("Reason for Override *", value=prefill.get("reason") or "", height=70)

        submitted = st.form_submit_button("Save", use_container_width=True, type="primary")

    if submitted:
        if not op_label or not site_name or not rate:
            st.error("Operator, Site and Rate are required.")
            return
        if not reason.strip():
            st.error("Please enter a reason for the override.")
            return
        payload: dict = {
            "operator_id":    op_opts[op_label],
            "site_id":        site_opts[site_name],
            "rate":           float(rate),
            "unit":           unit,
            "effective_from": eff_from.isoformat(),
            "effective_to":   eff_to.isoformat() if eff_to else None,
            "is_active":      is_active,
            "reason":         reason.strip(),
            "created_by":     user_name,
        }
        if is_edit:
            payload["id"] = prefill["id"]
        try:
            sb.upsert_conveyance_override(payload)
            st.toast("Override saved.", icon="✅")
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")


def _render_overrides(sb: SupabaseClient, is_adm: bool, operators: list, sites: list, user_name: str) -> None:
    try:
        overrides = sb.list_conveyance_overrides()
    except Exception as exc:
        st.warning(f"Could not load overrides: {exc}")
        return

    op_lookup   = {op["id"]: f"{op.get('emp_code','')} — {op.get('operator_name','')}" for op in operators}
    site_lookup = {s["id"]: s["site_name"] for s in sites}

    col_add, _ = st.columns([1, 5])
    with col_add:
        if st.button("+ Add Override", key="_cv_add_override", type="primary"):
            _override_dialog(sb, operators, sites, {}, user_name)

    if not overrides:
        st.markdown("<div class='cv-empty'>No employee overrides defined yet.</div>",
                    unsafe_allow_html=True)
        return

    hdrs = ["Employee", "Site", "Rate", "Unit", "Eff. From", "Active", "Actions"]
    html = "<div class='cv-row cv-row-override cv-hdr'>"
    for h in hdrs:
        html += f"<span>{h}</span>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

    for ov in overrides:
        op_name    = op_lookup.get(ov.get("operator_id", ""), "—")
        site_name  = site_lookup.get(ov.get("site_id", ""), "—")
        rate_txt   = f"₹{float(ov.get('rate',0)):,.2f}"
        badge_cls  = "cv-badge-active" if ov.get("is_active") else "cv-badge-inactive"
        badge_txt  = "Active" if ov.get("is_active") else "Inactive"

        st.markdown(
            f"<div class='cv-row cv-row-override'>"
            f"<span style='font-weight:600;'>{op_name}</span>"
            f"<span>{site_name}</span>"
            f"<span>{rate_txt}</span>"
            f"<span>{ov.get('unit','—')}</span>"
            f"<span>{_fmt_date(ov.get('effective_from'))}</span>"
            f"<span><span class='{badge_cls}'>{badge_txt}</span></span>"
            f"<span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        e_col, d_col = st.columns([1, 1])
        with e_col:
            if st.button("Edit", key=f"_cv_ov_ed_{ov['id']}", use_container_width=True):
                _override_dialog(sb, operators, sites, ov, user_name)
        with d_col:
            if is_adm:
                if st.button("Delete", key=f"_cv_ov_del_{ov['id']}", use_container_width=True):
                    try:
                        sb.delete_conveyance_override(ov["id"])
                        st.toast("Override deleted.", icon="🗑️")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Delete failed: {exc}")


# ── main render ───────────────────────────────────────────────────────────────

def render() -> None:
    _inject_css()

    sb        = SupabaseClient()
    is_adm    = auth.is_admin()
    user_name = auth.current_profile().get("full_name", "")

    try:
        operators = sb.list_operators()
    except Exception as exc:
        st.error(f"Could not load operators: {exc}")
        return

    try:
        sites = sb.list_sites()
    except Exception as exc:
        st.error(f"Could not load sites: {exc}")
        return

    st.markdown(
        "<h2 style='font-size:22px;font-weight:800;color:#0D1B33;margin-bottom:4px;'>"
        "Conveyance Rules</h2>"
        "<p style='font-size:13px;color:#64748B;margin-bottom:20px;'>"
        "Site default rates and per-employee overrides for conveyance calculation.</p>",
        unsafe_allow_html=True,
    )

    tab_site, tab_emp = st.tabs(["Site Default Rules", "Employee Overrides"])

    with tab_site:
        st.markdown("<div class='cv-sec-hdr'>"
                    "<span class='msr' style='font-size:14px;color:#E87722;'>location_on</span>"
                    "Site Default Conveyance Rates</div>", unsafe_allow_html=True)
        _render_site_rules(sb, is_adm, sites, user_name)

    with tab_emp:
        st.markdown("<div class='cv-sec-hdr'>"
                    "<span class='msr' style='font-size:14px;color:#E87722;'>person_pin</span>"
                    "Employee + Site Overrides</div>", unsafe_allow_html=True)
        _render_overrides(sb, is_adm, operators, sites, user_name)
