"""
erp/views/site.py
Site management — premium SaaS redesign.
Left  (35%): searchable site directory with modern cards.
Right (65%): tabbed detail/edit panel.

Mode state  _site_mode:  "none" | "new" | "edit"
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ..state_config import load_state_names
from ..supabase_client import SupabaseClient
from erp.views._lock import status_chip, deactivate_controls
from erp import auth

# ── Constants ─────────────────────────────────────────────────────────────────

_CONTACT_COLS = ["name", "designation", "email", "mobile", "remarks"]

# ── CSS ───────────────────────────────────────────────────────────────────────

_PAGE_CSS = """
<style>
/* ── KPI strip ─────────────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin: 0 0 28px;
}
.kpi-card {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 12px;
    padding: 18px 22px 14px;
    position: relative;
    overflow: hidden;
    transition: box-shadow .18s, transform .18s;
}
.kpi-card:hover {
    box-shadow: 0 6px 20px rgba(0,0,0,.08);
    transform: translateY(-2px);
}
.kpi-accent-bar {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
}
.kpi-label {
    font-size: 10px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: #9CA3AF;
    margin-bottom: 10px;
    display: flex; align-items: center; gap: 6px;
}
.kpi-value {
    font-size: 34px; font-weight: 800;
    color: #111827; line-height: 1;
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.kpi-sub {
    font-size: 11px; color: #6B7280;
}
.kpi-icon {
    position: absolute; top: 16px; right: 18px;
    font-size: 22px; opacity: .12;
}

/* ── Search wrapper ─────────────────────────────────────────────────── */
.search-wrap { position: relative; margin-bottom: 8px; }
.search-icon-abs {
    position: absolute; left: 11px; top: 50%;
    transform: translateY(-50%);
    font-size: 16px; color: #9CA3AF;
    z-index: 10; pointer-events: none;
}
.search-wrap .stTextInput input {
    padding-left: 34px !important;
    border-radius: 8px !important;
}

/* ── Site list cards ─────────────────────────────────────────────────── */
.cl-wrap { display: flex; flex-direction: column; gap: 6px; }
.cl-item {
    background: var(--card, #fff);
    border: 1px solid var(--border, #E2EBF0);
    border-radius: 10px;
    padding: 11px 13px;
    display: flex; align-items: center; gap: 11px;
    transition: box-shadow .16s, border-color .16s, transform .16s;
    cursor: pointer;
    pointer-events: none;
}
.cl-item:hover {
    box-shadow: 0 4px 16px rgba(37,99,235,.10);
    border-color: #93C5FD;
    transform: translateY(-1px);
}
.cl-item.cl-sel {
    border-color: #2563EB !important;
    background: #EFF6FF;
    border-left-width: 3px;
}
.cl-avatar {
    width: 36px; height: 36px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.cl-info { flex: 1; min-width: 0; }
.cl-name {
    font-size: 13px; font-weight: 600; color: #111827;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cl-sub {
    font-size: 11px; color: #6B7280; margin-top: 2px;
    display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
}
.cl-dot {
    width: 3px; height: 3px; border-radius: 50%;
    background: #D1D5DB; flex-shrink: 0;
}
.cl-code {
    font-size: 9px; font-weight: 700;
    background: #F1F5F9; color: #64748B;
    padding: 2px 8px; border-radius: 20px;
    white-space: nowrap; flex-shrink: 0;
    margin-left: auto;
}
.cl-contacts-badge {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 10px; font-weight: 600;
    background: #F0FDF4; color: #166534;
    border: 1px solid #BBF7D0;
    padding: 1px 7px; border-radius: 20px;
}

/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-state-v2 {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 72px 40px;
    background: #FAFBFC;
    border: 2px dashed #E2EBF0;
    border-radius: 16px;
    text-align: center;
    animation: cs-fadeup .35s ease;
}
.empty-icon-ring {
    width: 76px; height: 76px; border-radius: 50%;
    background: linear-gradient(145deg, #EFF6FF, #DBEAFE);
    display: flex; align-items: center; justify-content: center;
    font-size: 36px;
    margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(37,99,235,.14);
}
.empty-state-v2 h3 {
    font-size: 17px; font-weight: 700; color: #111827;
    margin: 0 0 8px;
}
.empty-state-v2 p {
    font-size: 13px; color: #9CA3AF;
    max-width: 270px; line-height: 1.6; margin: 0;
}

/* ── Site hero banner ────────────────────────────────────────────────── */
.cust-hero {
    background: linear-gradient(135deg, #1E2938 0%, #1c3461 100%);
    border-radius: 14px; padding: 22px 24px;
    margin-bottom: 18px;
    display: flex; align-items: center; gap: 16px;
    position: relative; overflow: hidden;
    animation: cs-fadeup .3s ease;
}
.cust-hero::before {
    content: '';
    position: absolute; top: -40px; right: -40px;
    width: 160px; height: 160px; border-radius: 50%;
    background: rgba(255,255,255,.04);
}
.cust-hero::after {
    content: '';
    position: absolute; bottom: -20px; right: 80px;
    width: 100px; height: 100px; border-radius: 50%;
    background: rgba(255,255,255,.03);
}
.cust-hero-avatar {
    width: 52px; height: 52px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; font-weight: 800; color: #fff;
    flex-shrink: 0;
    box-shadow: 0 4px 16px rgba(0,0,0,.30);
}
.cust-hero-name {
    font-size: 20px; font-weight: 800; color: #fff; line-height: 1.2;
}
.cust-hero-meta {
    font-size: 11px; color: rgba(255,255,255,.42);
    letter-spacing: .07em; margin-top: 4px;
}
.cust-hero-badges {
    margin-top: 7px; display: flex; gap: 6px; flex-wrap: wrap;
}
.hero-badge {
    font-size: 10px; font-weight: 700;
    padding: 2px 10px; border-radius: 20px;
    letter-spacing: .05em; text-transform: uppercase;
}
.hero-badge-new {
    background: rgba(16,185,129,.20); color: #6EE7B7;
    border: 1px solid rgba(16,185,129,.30);
}
.hero-badge-edit {
    background: rgba(245,158,11,.18); color: #FCD34D;
    border: 1px solid rgba(245,158,11,.28);
}

/* ── Form sections ───────────────────────────────────────────────────── */
.form-sec-hdr {
    font-size: 10px; font-weight: 700;
    letter-spacing: .13em; text-transform: uppercase;
    color: #E87722;
    margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 1px solid #F1F5F9;
    display: flex; align-items: center; gap: 6px;
}

/* ── Overview info rows ──────────────────────────────────────────────── */
.info-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 14px;
}
.info-field {
    background: #F8FAFC;
    border: 1px solid #E2EBF0;
    border-radius: 8px;
    padding: 11px 14px;
}
.info-field-label {
    font-size: 9px; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 4px;
}
.info-field-value {
    font-size: 13px; font-weight: 600; color: #111827;
    word-break: break-word;
}
.info-field-value.muted {
    font-weight: 400; color: #9CA3AF;
}

/* ── Contact row in overview ─────────────────────────────────────────── */
.contact-row {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid #F1F5F9;
}
.contact-row:last-child { border-bottom: none; }
.contact-initials {
    width: 32px; height: 32px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 800; color: #fff; flex-shrink: 0;
}
.contact-name  { font-size: 13px; font-weight: 600; color: #111827; }
.contact-desig { font-size: 11px; color: #6B7280; margin-top: 1px; }
.contact-pill  {
    font-size: 10px; color: #374151;
    background: #F3F4F6; border-radius: 20px;
    padding: 2px 9px; margin-left: auto;
}

/* ── Tabs polish ─────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    background: transparent !important;
    border-bottom: 2px solid #E2EBF0 !important;
    padding: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-size: 12px !important; font-weight: 600 !important;
    color: #6B7280 !important; padding: 8px 18px !important;
    border-radius: 0 !important;
    background: transparent !important; border: none !important;
    margin: 0 !important;
    border-bottom: 2px solid transparent !important;
    transition: color .14s !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #374151 !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #2563EB !important;
    border-bottom: 2px solid #2563EB !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }
.stTabs [data-baseweb="tab-panel"]     { padding: 18px 0 0 !important; }

/* ── Action button row ───────────────────────────────────────────────── */
.action-bar {
    display: flex; align-items: center; gap: 10px;
    margin-top: 22px; padding-top: 18px;
    border-top: 1px solid #F1F5F9;
}

/* ── No-results state ─────────────────────────────────────────────────── */
.no-results {
    text-align: center; padding: 36px 12px;
    color: #9CA3AF; font-size: 13px;
}
.no-results .nr-icon { font-size: 32px; margin-bottom: 8px; display: block; }

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""


# ── Data helpers ──────────────────────────────────────────────────────────────

def _parse_contacts(raw) -> list[dict]:
    def _norm(c: dict) -> dict:
        return {
            "name":        c.get("name", ""),
            "designation": c.get("designation", ""),
            "email":       c.get("email", ""),
            "mobile":      c.get("mobile", ""),
            "remarks":     c.get("remarks", ""),
        }
    if not raw:
        return []
    if isinstance(raw, list):
        return [_norm(c) for c in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [_norm(c) for c in parsed]
        except (json.JSONDecodeError, ValueError):
            return [{"name": raw, "designation": "", "email": "", "mobile": "", "remarks": ""}]
    return []


def _contacts_to_df(contacts: list[dict]) -> pd.DataFrame:
    rows = contacts or [{"name": "", "designation": "", "email": "", "mobile": "", "remarks": ""}]
    return pd.DataFrame(rows, columns=_CONTACT_COLS)


def _df_to_contacts(df: pd.DataFrame) -> list[dict]:
    result = []
    for _, row in df.iterrows():
        name        = str(row.get("name",        "") or "").strip()
        designation = str(row.get("designation", "") or "").strip()
        email       = str(row.get("email",       "") or "").strip()
        mobile      = str(row.get("mobile",      "") or "").strip()
        remarks     = str(row.get("remarks",     "") or "").strip()
        if name or email or mobile:
            result.append({"name": name, "designation": designation,
                           "email": email, "mobile": mobile, "remarks": remarks})
    return result


def _initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "??"


def _avatar_color(name: str) -> str:
    palette = [
        "#2563EB", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444",
        "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
    ]
    return palette[sum(ord(c) for c in (name or "A")) % len(palette)]


def _open_new_form(state_names: list[str]) -> None:
    """Switch UI to new-site mode and reset form fields."""
    st.session_state["_site_mode"]         = "new"
    st.session_state["_site_sel_id"]       = ""
    st.session_state["_site_sync_key"]     = "__new__"
    st.session_state["site_name"]          = ""
    st.session_state["site_address"]       = ""
    st.session_state["site_city"]          = ""
    st.session_state["site_state"]         = state_names[0] if state_names else ""
    st.session_state["site_pincode"]       = ""
    st.session_state["site_payment_terms"] = 0


# ── HTML builders ─────────────────────────────────────────────────────────────

def _kpi_card(icon: str, label: str, value: int | str,
              sub: str = "", accent: str = "#2563EB") -> str:
    return (
        f"<div class='kpi-card'>"
        f"<div class='kpi-accent-bar' style='background:{accent};'></div>"
        f"<span class='kpi-icon msr'>{icon}</span>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value'>{value}</div>"
        f"<div class='kpi-sub'>{sub}</div>"
        f"</div>"
    )


def _site_card(s: dict, is_sel: bool, n_con: int, customer_name: str) -> str:
    name      = s.get("site_name", "Unknown")
    city_v    = s.get("city",  "")
    state_v   = s.get("state", "")
    location  = ", ".join(filter(None, [city_v, state_v])) or "No location"
    color     = _avatar_color(name)
    sel_cls   = " cl-sel" if is_sel else ""
    cust_html = (
        f"<span class='cl-dot'></span><span>{customer_name}</span>"
        if customer_name else ""
    )
    con_badge = (
        f"<span class='cl-contacts-badge'>"
        f"<span class='msr' style='font-size:11px;'>people</span>"
        f"&thinsp;{n_con}</span>"
    ) if n_con else ""

    return (
        f"<div class='cl-item{sel_cls}'>"
        f"<div class='cl-avatar' style='background:{color};'>{_initials(name)}</div>"
        f"<div class='cl-info'>"
        f"<div class='cl-name'>{name}</div>"
        f"<div class='cl-sub'>"
        f"<span class='msr' style='font-size:12px;opacity:.6;'>location_on</span>"
        f"{location}"
        f"{cust_html}"
        f"{('<span class=\'cl-dot\'></span>' + con_badge) if n_con else ''}"
        f"</div>"
        f"</div>"
        f"</div>"
    )


def _info_field(label: str, value: str, wide: bool = False, muted: bool = False) -> str:
    val_cls = "info-field-value muted" if (muted or not value or value == "—") else "info-field-value"
    disp    = value if value else "—"
    return (
        f"<div class='info-field' style='grid-column:{'span 2' if wide else 'span 1'};'>"
        f"<div class='info-field-label'>{label}</div>"
        f"<div class='{val_cls}'>{disp}</div>"
        f"</div>"
    )


def _contact_row_html(contact: dict) -> str:
    name   = contact.get("name", "—") or "—"
    desig  = contact.get("designation", "") or ""
    email  = contact.get("email", "")  or ""
    mobile = contact.get("mobile", "") or ""
    color  = _avatar_color(name)
    pill   = email or mobile or ""
    return (
        f"<div class='contact-row'>"
        f"<div class='contact-initials' style='background:{color};'>{_initials(name)}</div>"
        f"<div>"
        f"<div class='contact-name'>{name}</div>"
        f"<div class='contact-desig'>{desig}</div>"
        f"</div>"
        f"{'<span class=\"contact-pill\">' + pill[:30] + '</span>' if pill else ''}"
        f"</div>"
    )


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _placeholder_tab(icon: str, title: str, description: str) -> None:
    st.markdown(
        f"<div style='display:flex;flex-direction:column;align-items:center;"
        f"padding:52px 24px;text-align:center;'>"
        f"<div style='width:58px;height:58px;border-radius:14px;"
        f"background:#F8FAFC;border:1px solid #E2EBF0;"
        f"display:flex;align-items:center;justify-content:center;"
        f"font-size:26px;margin-bottom:14px;'>"
        f"<span class='msr' style='color:#9CA3AF;'>{icon}</span></div>"
        f"<div style='font-size:15px;font-weight:700;color:#374151;margin-bottom:6px;'>{title}</div>"
        f"<div style='font-size:12px;color:#9CA3AF;max-width:240px;line-height:1.6;'>{description}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── Main view ──────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    hdr_l, hdr_r = st.columns([5, 1])
    with hdr_l:
        st.markdown(
            "<div class='page-eyebrow'>// Fleet Operations</div>"
            "<div class='page-title'>Sites</div>",
            unsafe_allow_html=True,
        )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    def fetch_sites() -> list[dict]:
        try:
            return sb.list_sites()
        except Exception as exc:
            st.error(f"Failed to load sites: {exc}")
            return []

    def fetch_customers() -> list[dict]:
        try:
            return sb.list_customers()
        except Exception as exc:
            st.error(f"Failed to load customers: {exc}")
            return []

    sites        = fetch_sites()
    customers    = fetch_customers()
    state_names  = load_state_names() or ["Maharashtra", "Tamil Nadu", "Karnataka"]
    site_map     = {s["id"]: s for s in sites if s.get("id")}
    customer_map = {c["id"]: c for c in customers if c.get("id")}

    with hdr_r:
        st.markdown("<div style='padding-top:18px'></div>", unsafe_allow_html=True)
        if st.button("+ New Site", use_container_width=True,
                     type="primary", key="hdr_new_site"):
            _open_new_form(state_names)
            st.rerun()

    # ── KPI strip ──────────────────────────────────────────────────────────────
    n_sites     = len(sites)
    n_contacts  = sum(len(_parse_contacts(s.get("site_contact"))) for s in sites)
    n_cities    = len({s.get("city")  for s in sites if s.get("city")})
    n_customers = len({s.get("customer_id") for s in sites if s.get("customer_id")})

    contact_counts = {
        s["id"]: len(_parse_contacts(s.get("site_contact")))
        for s in sites if s.get("id")
    }

    st.markdown(
        f"<div class='kpi-grid'>"
        + _kpi_card("domain",     "Total Sites",   n_sites,
                    f"across {n_cities} {'city' if n_cities == 1 else 'cities'}",
                    "#2563EB")
        + _kpi_card("contacts",   "Contacts",      n_contacts,
                    f"avg {round(n_contacts/n_sites,1) if n_sites else 0} per site",
                    "#8B5CF6")
        + _kpi_card("location_city", "Cities",     n_cities,
                    "unique site locations", "#10B981")
        + _kpi_card("groups",     "Customers",     n_customers,
                    "with active sites", "#F59E0B")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Mode / selection state ─────────────────────────────────────────────────
    if "_site_mode" not in st.session_state:
        st.session_state["_site_mode"]   = "none"
    if "_site_sel_id" not in st.session_state:
        st.session_state["_site_sel_id"] = ""

    mode        = st.session_state["_site_mode"]          # "none" | "new" | "edit"
    selected_id = st.session_state["_site_sel_id"]
    selected_site = site_map.get(selected_id) if selected_id else None

    # ── Sync form fields when selection or mode changes ────────────────────────
    sync_key = f"{mode}__{selected_id}"
    if st.session_state.get("_site_sync_key") != sync_key:
        st.session_state["_site_sync_key"] = sync_key
        c = selected_site or {}
        st.session_state["site_name"]          = c.get("site_name", "")
        st.session_state["site_customer_id"]   = c.get("customer_id", "")
        st.session_state["site_address"]       = c.get("address", "")
        st.session_state["site_city"]          = c.get("city", "")
        raw_state = c.get("state", "")
        st.session_state["site_state"]         = (
            raw_state if raw_state in state_names else (state_names[0] if state_names else "")
        )
        st.session_state["site_pincode"]       = c.get("pincode", "")
        st.session_state["site_payment_terms"] = int(c.get("payment_terms") or 0)

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — Directory
    # ══════════════════════════════════════════════════════════════════════════
    with left_col:

        # Search input with icon overlay
        st.markdown(
            "<div class='search-wrap'>"
            "<span class='search-icon-abs msr'>search</span>",
            unsafe_allow_html=True,
        )
        search_q = st.text_input(
            "search", label_visibility="collapsed",
            placeholder="Search by name or city…",
            key="site_search_q",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        show_inactive = False
        if auth.is_admin():
            show_inactive = st.checkbox("Show Inactive", value=False, key="site_show_inactive")

        q = search_q.strip().lower()
        filtered_map = {
            sid: s for sid, s in site_map.items()
            if (show_inactive or s.get("is_active", True))
            and (
                not q
                or q in s.get("site_name", "").lower()
                or q in s.get("city", "").lower()
            )
        }

        count_txt = (
            f"<span style='color:#2563EB;font-weight:700;'>{len(filtered_map)}</span>"
            f" of {n_sites} sites"
            if q else
            f"<span style='font-weight:700;color:#111827;'>{n_sites}</span> sites"
        )
        st.markdown(
            f"<div style='font-size:11px;color:#6B7280;margin:4px 0 10px;'>{count_txt}</div>",
            unsafe_allow_html=True,
        )

        with st.container(height=530):
            if not filtered_map:
                st.markdown(
                    "<div class='no-results'>"
                    "<span class='nr-icon msr'>search_off</span>"
                    "No sites match your search."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                for sid, s in filtered_map.items():
                    is_sel      = (sid == selected_id and mode == "edit")
                    name        = s.get("site_name", "Unknown")
                    n_con       = contact_counts.get(sid, 0)
                    cust_name   = (
                        customer_map.get(s.get("customer_id", ""), {}).get("customer_name", "")
                        if s.get("customer_id") else ""
                    )

                    st.markdown(
                        _site_card(s, is_sel, n_con, cust_name),
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "✓ Selected" if is_sel else "Open →",
                        key=f"csel_{sid}",
                        use_container_width=True,
                        help=name,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state["_site_mode"]     = "edit"
                        st.session_state["_site_sel_id"]   = sid
                        st.session_state["_site_sync_key"] = None   # force sync
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — Detail / form
    # ══════════════════════════════════════════════════════════════════════════
    with right_col:

        # ── EMPTY STATE ───────────────────────────────────────────────────────
        if mode == "none":
            st.markdown(
                "<div class='empty-state-v2'>"
                "<div class='empty-icon-ring'>🏢</div>"
                "<h3>No site selected</h3>"
                "<p>Select a site from the directory on the left, "
                "or click <strong>+ New Site</strong> to add one.</p>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── NEW / EDIT FORM ───────────────────────────────────────────────────
        else:
            display_name = (
                st.session_state.get("site_name")
                or (selected_site.get("site_name", "") if selected_site else "")
                or "New Site"
            )
            site_code   = selected_site.get("site_code", "") if selected_site else ""
            col_val     = _avatar_color(display_name)
            badge_cls   = "hero-badge-edit" if mode == "edit" else "hero-badge-new"
            badge_lbl   = "Editing" if mode == "edit" else "New Site"
            meta_line   = f"CODE: {site_code}" if site_code else "Unsaved — fill in details below"

            # Hero banner
            st.markdown(
                f"<div class='cust-hero'>"
                f"<div class='cust-hero-avatar' style='background:{col_val};'>"
                f"{_initials(display_name)}</div>"
                f"<div style='flex:1;min-width:0;position:relative;z-index:1;'>"
                f"<div class='cust-hero-name'>{display_name}</div>"
                f"<div class='cust-hero-meta'>{meta_line}</div>"
                f"<div class='cust-hero-badges'>"
                f"<span class='hero-badge {badge_cls}'>{badge_lbl}</span>"
                f"</div></div></div>",
                unsafe_allow_html=True,
            )
            if mode == "edit" and selected_site:
                st.markdown(
                    status_chip("Active" if selected_site.get("is_active", True) else "Inactive"),
                    unsafe_allow_html=True,
                )

            # Existing contacts for display
            existing_contacts = _parse_contacts(
                selected_site.get("site_contact") if selected_site else None
            )

            # ── TABS ──────────────────────────────────────────────────────────
            tab_overview, tab_edit, tab_contacts_tab, tab_map = st.tabs([
                "🏢 Overview",
                "✏️ Edit Details",
                f"👤 Contacts ({len(existing_contacts)})",
                "🗺️ Map",
            ])

            # ── Tab 1: Overview ───────────────────────────────────────────────
            with tab_overview:
                if mode == "new":
                    st.markdown(
                        "<div style='color:#9CA3AF;font-size:13px;"
                        "text-align:center;padding:24px 0;'>"
                        "Save the site first to see the overview.</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    ss = selected_site or {}
                    cust_disp = (
                        customer_map.get(ss.get("customer_id", ""), {}).get("customer_name", "")
                        if ss.get("customer_id") else ""
                    )
                    pt_val = ss.get("payment_terms")
                    pt_disp = f"{pt_val} days" if pt_val else ""

                    _section_hdr("domain", "Site Information")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("Site Name",      ss.get("site_name"))
                        + _info_field("Customer",       cust_disp)
                        + _info_field("Site Code",      ss.get("site_code"))
                        + _info_field("Payment Terms",  pt_disp)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
                    _section_hdr("location_on", "Address")
                    st.markdown(
                        f"<div class='info-grid'>"
                        + _info_field("City",    ss.get("city"))
                        + _info_field("State",   ss.get("state"))
                        + _info_field("Pincode", ss.get("pincode"))
                        + _info_field("Address", ss.get("address"), wide=True)
                        + "</div>",
                        unsafe_allow_html=True,
                    )

                    first_c = existing_contacts[0] if existing_contacts else {}
                    if first_c.get("email") or first_c.get("mobile"):
                        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
                        _section_hdr("call", "Primary Contact")
                        st.markdown(
                            f"<div class='info-grid'>"
                            + _info_field("Email",  first_c.get("email"))
                            + _info_field("Mobile", first_c.get("mobile"))
                            + "</div>",
                            unsafe_allow_html=True,
                        )

            # ── Tab 2: Edit Details ───────────────────────────────────────────
            with tab_edit:
                customer_options = {
                    c.get("id"): c.get("customer_name", "Unknown")
                    for c in customers if c.get("id")
                }

                with st.container(border=True):
                    _section_hdr("domain", "Site Details")
                    st.text_input(
                        "Site Name *", key="site_name",
                        placeholder="e.g. Mumbai North Hub",
                    )
                    if mode == "edit":
                        st.selectbox(
                            "Customer",
                            options=[""] + list(customer_options),
                            format_func=lambda cid: "Select customer" if not cid
                                else customer_options.get(cid, "Unknown"),
                            key="site_customer_id",
                        )
                    st.number_input(
                        "Payment Terms (days)",
                        step=1,
                        min_value=0,
                        key="site_payment_terms",
                    )

                with st.container(border=True):
                    _section_hdr("location_on", "Address")
                    st.text_area(
                        "Address", key="site_address",
                        placeholder="Street, Area, Landmark…", height=72,
                    )
                    a1, a2 = st.columns(2)
                    with a1:
                        st.text_input(
                            "City", key="site_city", placeholder="e.g. Mumbai"
                        )
                    with a2:
                        st.selectbox(
                            "State", options=state_names, key="site_state"
                        )
                    st.text_input(
                        "Pincode", key="site_pincode", placeholder="e.g. 400001"
                    )

            # ── Tab 3: Contacts ───────────────────────────────────────────────
            with tab_contacts_tab:
                if mode == "edit" and existing_contacts:
                    _section_hdr("people", f"Contact Persons — {len(existing_contacts)} saved")
                    st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)
                    for ct in existing_contacts:
                        st.markdown(_contact_row_html(ct), unsafe_allow_html=True)
                    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

                with st.container(border=True):
                    _section_hdr("edit_note", "Edit Contacts")
                    contacts_df = st.data_editor(
                        _contacts_to_df(existing_contacts),
                        column_config={
                            "name":        st.column_config.TextColumn("Name",        width="medium"),
                            "designation": st.column_config.TextColumn("Designation", width="medium"),
                            "email":       st.column_config.TextColumn("Email",       width="medium"),
                            "mobile":      st.column_config.TextColumn("Mobile",      width="medium"),
                            "remarks":     st.column_config.TextColumn("Remarks",     width="large"),
                        },
                        num_rows="dynamic",
                        use_container_width=True,
                        hide_index=True,
                        key=f"site_contacts_{selected_id or 'new'}",
                    )

            # ── Tab 4: Map (placeholder) ──────────────────────────────────────
            with tab_map:
                _placeholder_tab(
                    "map",
                    "Map view coming soon",
                    "Geographic location and nearby machines for this site will appear here.",
                )

            # ── Action buttons (outside tabs) ─────────────────────────────────
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            sv1, sv2, sv3, _ = st.columns([3, 1, 1, 2])
            with sv1:
                save_clicked = st.button(
                    "💾  Update Site" if mode == "edit" else "💾  Create Site",
                    type="primary",
                    use_container_width=True,
                    key="site_save_btn",
                )
            with sv2:
                if st.button("Cancel", use_container_width=True, key="site_cancel_btn"):
                    st.session_state["_site_mode"]     = "none"
                    st.session_state["_site_sel_id"]   = ""
                    st.session_state["_site_sync_key"] = None
                    st.rerun()
            with sv3:
                if st.button("↻ Refresh", use_container_width=True, key="site_refresh_btn"):
                    st.session_state["_site_sync_key"] = None
                    st.rerun()

            # ── Save logic ─────────────────────────────────────────────────────
            if save_clicked:
                # Resolve form values from session state (robust across tab switches)
                site_name_val   = (st.session_state.get("site_name",        "") or "").strip()
                address_val     = (st.session_state.get("site_address",     "") or "").strip()
                city_val        = (st.session_state.get("site_city",        "") or "").strip()
                state_v         = st.session_state.get("site_state") or None
                pincode_val     = (st.session_state.get("site_pincode",     "") or "").strip()
                payment_terms_v = int(st.session_state.get("site_payment_terms", 0) or 0)

                if not site_name_val:
                    st.error("Site Name is required.")
                else:
                    contacts_list = _df_to_contacts(contacts_df)
                    first = contacts_list[0] if contacts_list else {}
                    payload = dict(
                        site_name=site_name_val,
                        address=address_val or None,
                        city=city_val or None,
                        state=state_v,
                        pincode=pincode_val or None,
                        site_contact=json.dumps(contacts_list) if contacts_list else None,
                        site_contact_number=first.get("mobile") or None,
                        payment_terms=payment_terms_v or None,
                    )
                    if mode == "edit":
                        payload["customer_id"] = st.session_state.get("site_customer_id") or None

                    # Keep st.rerun() OUTSIDE try/except —
                    # RerunException(Exception) would otherwise be swallowed.
                    _err       = None
                    _toast_msg = None
                    _new_id    = None
                    try:
                        if mode == "edit" and selected_site:
                            sb.update_site(selected_id, payload)
                            _toast_msg = f"'{site_name_val}' updated successfully."
                        else:
                            created    = sb.insert_site(payload)
                            _new_id    = created.get("id", "")
                            new_code   = created.get("site_code") or _new_id
                            _toast_msg = f"Site created — Code: {new_code}"
                    except Exception as exc:
                        _err = str(exc)

                    if _err:
                        st.error(f"Could not save site: {_err}")
                    else:
                        if _new_id:
                            st.session_state["_site_mode"]     = "edit"
                            st.session_state["_site_sel_id"]   = _new_id
                            st.session_state["_site_sync_key"] = None
                        st.toast(_toast_msg, icon="✅")
                        st.rerun()

            if mode == "edit" and selected_site:
                _is_active = selected_site.get("is_active", True)
                _sname = selected_site.get("site_name", "")
                _deact = deactivate_controls(
                    "Site", selected_id, _sname, _is_active, key_prefix="site",
                )
                if _deact is True:
                    sb.update_site(selected_id, {"is_active": True})
                    st.rerun()
                elif _deact is False:
                    sb.update_site(selected_id, {"is_active": False})
                    st.rerun()
