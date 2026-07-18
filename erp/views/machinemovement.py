"""
erp/views/machinemovement.py
Machine Movement — record Load, Transit, and Unload movements for a machine.

SQL DDL (reference only — do not execute here):

CREATE TABLE machine_movements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    movement_code   TEXT NOT NULL UNIQUE,
    machine_id      UUID NOT NULL REFERENCES machines(id),
    asset_code      TEXT NOT NULL,
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('Load','Transit','Unload')),
    from_location   TEXT,
    to_location     TEXT,
    movement_date   DATE NOT NULL,
    comments        TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    created_by      TEXT
);
CREATE INDEX ON machine_movements(machine_id);
CREATE INDEX ON machine_movements(movement_date DESC);
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from erp.supabase_client import SupabaseClient
from erp import auth as _auth  # noqa: F401 — imported as required by spec

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

/* ── Info chips (read-only machine info strip) ──────────────────────── */
.info-chip {
    background: #F8FAFC;
    border: 1px solid #E2EBF0;
    border-radius: 8px;
    padding: 8px 12px;
    min-width: 100px;
}
.info-chip .ic-label {
    font-size: 11px; color: #64748B; font-weight: 500; margin-bottom: 2px;
}
.info-chip .ic-value {
    font-size: 13px; color: #1E293B; font-weight: 600;
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

/* ── Animations ─────────────────────────────────────────────────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
"""

_OTHER_LOCATION = "Other / Yard / Workshop"

# ── HTML helpers ──────────────────────────────────────────────────────────────

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


def _section_hdr(icon: str, label: str) -> None:
    st.markdown(
        f"<div class='form-sec-hdr'>"
        f"<span class='msr' style='font-size:14px;color:#E87722;'>{icon}</span>"
        f"{label}</div>",
        unsafe_allow_html=True,
    )


def _info_chip(label: str, value: str, badge_html: str = "") -> str:
    inner = (
        badge_html
        if badge_html
        else f"<div class='ic-value'>{value or '—'}</div>"
    )
    return (
        f"<div class='info-chip'>"
        f"<div class='ic-label'>{label}</div>"
        f"{inner}"
        f"</div>"
    )


def _op_badge_cls(status: str) -> str:
    return {
        "Available":    "badge-available",
        "On Rent":      "badge-on-rent",
        "Reserved":     "badge-reserved",
        "Mobilizing":   "badge-mobilizing",
        "Demobilizing": "badge-demobilizing",
        "Sold":         "badge-sold",
    }.get(status, "badge-available")


def _mov_code(asset_code: str) -> str:
    return f"MOV-{asset_code}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _site_label(s: dict) -> str:
    city = s.get("city") or ""
    city_part = f" ({city})" if city else ""
    return f"{s.get('site_code', '')} · {s.get('site_name', '')}{city_part}"


# ── Save helper ──────────────────────────────────────────────────────────────

def _save_movement(
    sb: SupabaseClient,
    machine: dict,
    movement_type: str,
    from_location: str | None,
    to_location: str | None,
    movement_date: date,
    comments: str | None,
) -> None:
    asset_code = machine.get("asset_code", "UNK")
    payload = {
        "movement_code":  _mov_code(asset_code),
        "machine_id":     machine["id"],
        "asset_code":     asset_code,
        "movement_type":  movement_type,
        "from_location":  from_location or None,
        "to_location":    to_location or None,
        "movement_date":  movement_date.isoformat(),
        "comments":       (comments or "").strip() or None,
    }
    sb.insert_machine_movement(payload)


# ── Main view ──────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    # ── Page header ────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='page-eyebrow'>// Fleet Operations</div>"
        "<div class='page-title'>Machine Movement</div>",
        unsafe_allow_html=True,
    )

    # ── Data load ──────────────────────────────────────────────────────────────
    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    try:
        all_machines = sb.list_machines()
    except Exception as exc:
        st.error(f"Failed to load machines: {exc}")
        return

    try:
        all_sites = sb.list_sites()
    except Exception as exc:
        st.warning(f"Could not load sites: {exc}")
        all_sites = []

    # KPI strip — computed from ALL movements
    try:
        all_movements = sb.list_machine_movements()
    except Exception:
        all_movements = []

    n_total    = len(all_movements)
    n_load     = sum(1 for m in all_movements if m.get("movement_type") == "Load")
    n_transit  = sum(1 for m in all_movements if m.get("movement_type") == "Transit")
    n_unload   = sum(1 for m in all_movements if m.get("movement_type") == "Unload")

    st.markdown(
        f"<div class='kpi-grid'>"
        + _kpi_card("swap_vert",      "Total Movements",  n_total,
                    "all recorded movements", "#2563EB")
        + _kpi_card("upload",         "Load Events",      n_load,
                    "machines loaded to site", "#10B981")
        + _kpi_card("local_shipping", "Transit Updates",  n_transit,
                    "in-transit records", "#F59E0B")
        + _kpi_card("download",       "Unload Events",    n_unload,
                    "machines returned", "#8B5CF6")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Session state ──────────────────────────────────────────────────────────
    if "_mm_sel_id" not in st.session_state:
        st.session_state["_mm_sel_id"] = ""

    # ── Machine Selector Card ─────────────────────────────────────────────────
    with st.container(border=True):
        _section_hdr("precision_manufacturing", "Select Machine")

        # Build sorted options
        active_machines = sorted(
            [m for m in all_machines if m.get("asset_code")],
            key=lambda m: m.get("asset_code", ""),
        )
        machine_options = [""] + [
            f"{m['asset_code']} · {' '.join(filter(None, [m.get('make'), m.get('model')]))}"
            if (m.get("make") or m.get("model"))
            else m["asset_code"]
            for m in active_machines
        ]
        machine_id_map = {
            f"{m['asset_code']} · {' '.join(filter(None, [m.get('make'), m.get('model')]))}"
            if (m.get("make") or m.get("model"))
            else m["asset_code"]: m
            for m in active_machines
        }

        # Determine current index from session state
        saved_id    = st.session_state.get("_mm_sel_id", "")
        saved_label = ""
        if saved_id:
            for label, m in machine_id_map.items():
                if m.get("id") == saved_id:
                    saved_label = label
                    break
        sel_idx = machine_options.index(saved_label) if saved_label in machine_options else 0

        selected_label = st.selectbox(
            "Asset Code",
            options=machine_options,
            index=sel_idx,
            format_func=lambda v: "Select a machine…" if not v else v,
            key="mm_machine_sel",
        )

        selected_machine: dict | None = machine_id_map.get(selected_label) if selected_label else None

        if selected_machine:
            st.session_state["_mm_sel_id"] = selected_machine.get("id", "")

            # Info strip
            op_status = selected_machine.get("operational_status", "")
            badge_cls = _op_badge_cls(op_status)
            badge_html = f"<span class='{badge_cls}' style='margin-top:2px;display:inline-block;'>{op_status}</span>"

            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.markdown(_info_chip("Machine Type", selected_machine.get("machine_type", "")),
                            unsafe_allow_html=True)
            with c2:
                st.markdown(_info_chip("Make", selected_machine.get("make", "")),
                            unsafe_allow_html=True)
            with c3:
                st.markdown(_info_chip("Model", selected_machine.get("model", "")),
                            unsafe_allow_html=True)
            with c4:
                st.markdown(_info_chip("Current Location", selected_machine.get("current_location", "")),
                            unsafe_allow_html=True)
            with c5:
                st.markdown(_info_chip("Operational Status", op_status, badge_html=badge_html),
                            unsafe_allow_html=True)

        else:
            st.markdown(
                "<div class='empty-state-v2' style='padding:32px 24px;'>"
                "<div class='empty-icon-ring'>"
                "<span class='msr' style='font-size:32px;color:#2563EB;'>precision_manufacturing</span>"
                "</div>"
                "<h3>No machine selected</h3>"
                "<p>Choose an asset code from the dropdown above to record a movement.</p>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

    # ── Business rule enforcement ─────────────────────────────────────────────
    op_status = selected_machine.get("operational_status", "")

    if op_status == "On Rent":
        st.error(
            "This machine is currently **On Rent** and cannot be moved.",
            icon="🚫",
        )
        return

    if op_status == "Reserved":
        st.warning(
            "This machine is **Reserved**. It can be moved, but please verify with the "
            "deployment team before proceeding.",
            icon="⚠",
        )

    # ── Build site DDL options ────────────────────────────────────────────────
    site_labels   = [_site_label(s) for s in all_sites if s.get("site_code")]
    site_options  = sorted(site_labels) + [_OTHER_LOCATION]

    asset_code    = selected_machine.get("asset_code", "")
    from_loc      = selected_machine.get("current_location") or ""

    # ── Movement Forms ────────────────────────────────────────────────────────

    # Section A: Load Machine
    with st.container(border=True):
        _section_hdr("upload", "Load Machine")
        la1, la2 = st.columns([3, 2])
        with la1:
            load_dest = st.selectbox(
                "To Location (Site)",
                options=site_options,
                key="mm_load_to_site",
            )
            load_to_custom = ""
            if load_dest == _OTHER_LOCATION:
                load_to_custom = st.text_input(
                    "Custom To Location",
                    placeholder="e.g. Mumbai Yard, Workshop, Transit Hub",
                    key="mm_load_to_custom",
                )
        with la2:
            load_date = st.date_input(
                "Movement Date",
                value=date.today(),
                key="mm_load_date",
            )
        if st.button("Machine Load", type="primary", key="mm_load_save"):
            to_loc = load_to_custom.strip() if load_dest == _OTHER_LOCATION else load_dest
            if not to_loc:
                st.error("Please specify a destination location.")
            else:
                try:
                    _save_movement(
                        sb, selected_machine,
                        movement_type="Load",
                        from_location=from_loc or None,
                        to_location=to_loc,
                        movement_date=load_date,
                        comments=None,
                    )
                    st.toast(f"Load movement recorded for {asset_code}.", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save movement: {exc}")

    # Section B: Transit Update
    with st.container(border=True):
        _section_hdr("local_shipping", "Transit Update")
        tb1, tb2 = st.columns([3, 2])
        with tb1:
            transit_comments = st.text_area(
                "Transit details / route / remarks",
                placeholder="e.g. En route Mumbai → Pune via NH-48, ETA tomorrow",
                height=90,
                key="mm_transit_comments",
            )
        with tb2:
            transit_date = st.date_input(
                "Movement Date",
                value=date.today(),
                key="mm_transit_date",
            )
        if st.button("Record Transit", type="primary", key="mm_transit_save"):
            try:
                _save_movement(
                    sb, selected_machine,
                    movement_type="Transit",
                    from_location=from_loc or None,
                    to_location=None,
                    movement_date=transit_date,
                    comments=transit_comments,
                )
                st.toast(f"Transit update recorded for {asset_code}.", icon="✅")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save movement: {exc}")

    # Section C: Unload Machine
    with st.container(border=True):
        _section_hdr("download", "Unload Machine")
        uc1, uc2 = st.columns([3, 2])
        with uc1:
            unload_dest = st.selectbox(
                "To Location (Site)",
                options=site_options,
                key="mm_unload_to_site",
            )
            unload_to_custom = ""
            if unload_dest == _OTHER_LOCATION:
                unload_to_custom = st.text_input(
                    "Custom To Location",
                    placeholder="e.g. Mumbai Yard, Workshop",
                    key="mm_unload_to_custom",
                )
        with uc2:
            unload_date = st.date_input(
                "Movement Date",
                value=date.today(),
                key="mm_unload_date",
            )
        if st.button("Record Unload", type="primary", key="mm_unload_save"):
            to_loc = unload_to_custom.strip() if unload_dest == _OTHER_LOCATION else unload_dest
            if not to_loc:
                st.error("Please specify a destination location.")
            else:
                try:
                    _save_movement(
                        sb, selected_machine,
                        movement_type="Unload",
                        from_location=from_loc or None,
                        to_location=to_loc,
                        movement_date=unload_date,
                        comments=None,
                    )
                    # Also update current_location on the machine record
                    try:
                        sb.update_machine(selected_machine["id"], {"current_location": to_loc})
                    except Exception:
                        pass  # Non-fatal — movement is already recorded
                    st.toast(f"Unload recorded for {asset_code}. Location updated to: {to_loc}", icon="✅")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save movement: {exc}")

    # ── Movement History ──────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
    _section_hdr("history", "Movement History")

    try:
        movements = sb.list_machine_movements(machine_id=selected_machine["id"])
    except Exception as exc:
        st.warning(f"Could not load movement history: {exc}")
        movements = []

    if not movements:
        st.markdown(
            "<div style='text-align:center;padding:32px 12px;"
            "color:#9CA3AF;font-size:13px;'>"
            "<span class='msr' style='font-size:32px;display:block;margin-bottom:8px;'>"
            "swap_vert</span>"
            "No movements recorded yet for this machine."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        df = pd.DataFrame(movements)

        # Keep only relevant columns (guard against missing ones)
        keep_cols = [c for c in
                     ["movement_code", "movement_type", "from_location",
                      "to_location", "movement_date", "comments"]
                     if c in df.columns]
        df = df[keep_cols].copy()

        # Rename for display
        rename_map = {
            "movement_code":  "Movement Code",
            "movement_type":  "Type",
            "from_location":  "From Location",
            "to_location":    "To Location",
            "movement_date":  "Date",
            "comments":       "Comments",
        }
        df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Movement Code": st.column_config.TextColumn("Movement Code", width="medium"),
                "Type":          st.column_config.TextColumn("Type",          width="small"),
                "From Location": st.column_config.TextColumn("From Location", width="medium"),
                "To Location":   st.column_config.TextColumn("To Location",   width="medium"),
                "Date":          st.column_config.DateColumn("Date",          width="small",
                                                             format="DD MMM YYYY"),
                "Comments":      st.column_config.TextColumn("Comments",      width="large"),
            },
        )
