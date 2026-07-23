"""
erp/views/invoice.py
GST Tax Invoice generation — CTO Logistics & Infra format.

Run this SQL once in Supabase before using:
    CREATE TABLE invoices (
        id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        invoice_number TEXT UNIQUE NOT NULL,
        work_order_id  UUID,
        invoice_date   DATE NOT NULL,
        customer_id    UUID,
        site_id        UUID,
        tax_type       TEXT DEFAULT 'CGST/SGST',
        line_items     JSONB,
        subtotal       NUMERIC(14,2) DEFAULT 0,
        tax_amount     NUMERIC(14,2) DEFAULT 0,
        round_off      NUMERIC(6,2)  DEFAULT 0,
        grand_total    NUMERIC(14,2) DEFAULT 0,
        status         TEXT DEFAULT 'Draft',
        notes          TEXT,
        created_at     TIMESTAMPTZ DEFAULT NOW()
    );
"""
from __future__ import annotations

import json
import calendar
from datetime import date, datetime

import streamlit as st
import streamlit.components.v1 as components

from ..supabase_client import SupabaseClient

# ── Fixed company / bank constants ────────────────────────────────────────────
_CO = {
    "name":       "CTO LOGISTICS & INFRA",
    "gstin":      "27AASFC8920H1Z1",
    "state":      "Maharashtra",
    "state_code": "27",
    "email":      "ctologinfra@gmail.com",
    "tel":        "022-4215 6953",
    "addr1":      "B-202, Second, Steel Chambers,",
    "addr2":      "Steel Market Road, Plot No. 514,",
    "addr3":      "Varsha Cranes Pvt. Ltd. Kalamboli,",
    "addr4":      "Navi Mumbai - 410218",
}
_BANK = {
    "holder":  "CTO Logistics & Infra",
    "bank":    "ICICI Bank",
    "account": "109805002451",
    "ifsc":    "ICIC0001098",
}


# ── Utility helpers ────────────────────────────────────────────────────────────

def _fy_str(d: date | None = None) -> str:
    d = d or date.today()
    y = d.year if d.month >= 4 else d.year - 1
    return f"{str(y)[2:]}-{str(y + 1)[2:]}"


_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty",
         "Sixty", "Seventy", "Eighty", "Ninety"]


def _w2(n: int) -> str:
    return _ONES[n] if n < 20 else _TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")


def _w3(n: int) -> str:
    if n < 100:
        return _w2(n)
    return _ONES[n // 100] + " Hundred" + (" " + _w2(n % 100) if n % 100 else "")


def _num_to_words_inr(amount: float) -> str:
    n = int(round(max(0.0, amount)))
    if n == 0:
        return "Zero Rupees Only"
    parts: list[str] = []
    if n >= 1_00_00_000:
        parts.append(_w3(n // 1_00_00_000) + " Crore"); n %= 1_00_00_000
    if n >= 1_00_000:
        parts.append(_w3(n // 1_00_000) + " Lakh"); n %= 1_00_000
    if n >= 1_000:
        parts.append(_w3(n // 1_000) + " Thousand"); n %= 1_000
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred"); n %= 100
    if n:
        parts.append(_w2(n))
    return " ".join(parts) + " Rupees Only"


def _fmt_inr(n: float) -> str:
    """Format float in Indian comma style: 2,64,883.20"""
    neg = n < 0
    n = abs(n)
    int_part = int(round(n * 100)) // 100
    frac = int(round(n * 100)) % 100
    s = str(int_part)
    if len(s) <= 3:
        fmt = s
    else:
        fmt = s[-3:]
        s = s[:-3]
        while s:
            chunk = s[-2:] if len(s) >= 2 else s
            fmt = chunk + "," + fmt
            s = s[:-len(chunk)]
    result = f"{fmt}.{frac:02d}"
    return f"-{result}" if neg else result


# ── Billing computation ────────────────────────────────────────────────────────

def _parse_rows(raw) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict) and data.get("shift_type") == "double":
            return (data.get("shift1") or []) + (data.get("shift2") or [])
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _compute_billing(wl: dict, mc: dict) -> dict:
    rows      = _parse_rows(wl.get("schedule_data"))
    shift_hr  = float(mc.get("machine_shift_hour") or 8)
    no_days   = float(mc.get("no_of_days") or 26)
    rental    = float(mc.get("rental_per_month") or 0)
    ot_rate   = float(wl.get("ot_rate") or 0)
    deduction = float(wl.get("deduction") or 0)

    work_hrs   = no_days * shift_hr
    actual_hrs = sum(float(r.get("net_time") or 0) for r in rows)
    qty        = round(actual_hrs / work_hrs, 3) if work_hrs > 0 else 0.0
    hiring     = round(rental * qty, 2)
    ot_hrs     = round(sum(float(r.get("ot") or 0) for r in rows), 3)
    ot_amt     = round(ot_hrs * ot_rate, 2)
    return {
        "qty": qty, "rate": rental, "hiring": hiring,
        "ot_hrs": ot_hrs, "ot_rate": ot_rate, "ot_amt": ot_amt,
        "deduction": deduction,
        "net": max(0.0, hiring + ot_amt - deduction),
    }


def _period_str(billing_month: str) -> str:
    try:
        dt = datetime.strptime(billing_month.strip(), "%B %Y")
        _, last = calendar.monthrange(dt.year, dt.month)
        return f"{dt.day} {dt.strftime('%b %Y')} to {last} {dt.strftime('%b %Y')}"
    except Exception:
        return billing_month


# ── HTML invoice template ──────────────────────────────────────────────────────

_CSS = """
<style>
@page{size:A4;margin:12mm 10mm;}
@media print{.no-print{display:none!important;}}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:Arial,Helvetica,sans-serif;font-size:8.5pt;color:#111;
     background:#ddd;padding:16px;}
.wrapper{width:190mm;margin:0 auto;background:#fff;border:1.5px solid #333;}
/* header */
.hdr{display:flex;align-items:stretch;border-bottom:1.5px solid #333;}
.hdr-left{flex:1;padding:8px 10px;display:flex;flex-direction:column;justify-content:center;}
.co-name{font-size:17pt;font-weight:900;color:#B22222;letter-spacing:.5px;line-height:1;}
.co-sub{font-size:7pt;color:#444;margin-top:2px;}
.co-addr{font-size:7pt;color:#333;font-weight:600;margin-top:6px;text-align:center;}
.hdr-right{width:130px;display:flex;align-items:center;justify-content:center;
           border-left:1.5px solid #333;padding:8px;}
.ti-box{font-size:11pt;font-weight:900;letter-spacing:2px;border:1.5px solid #333;
        padding:4px 10px;text-align:center;}
/* two-col sections */
.two-col{display:flex;border-bottom:1px solid #888;}
.two-col .left{flex:1;padding:6px 10px;border-right:1px solid #888;font-size:8pt;}
.two-col .right{flex:1;padding:6px 10px;font-size:8pt;}
.sec-lbl{font-weight:700;text-decoration:underline;margin-bottom:3px;font-size:8pt;}
.fr{display:flex;gap:4px;margin:1px 0;}
.fk{font-weight:700;min-width:100px;flex-shrink:0;}
/* table */
table.inv{width:100%;border-collapse:collapse;font-size:8pt;}
table.inv th{border:1px solid #aaa;padding:4px 5px;background:#eef2f7;
             text-align:center;font-size:7.5pt;font-weight:700;line-height:1.3;}
table.inv td{border:1px solid #aaa;padding:3px 5px;vertical-align:top;}
tr.eq-hdr td{background:#e4ecf5;font-weight:700;font-size:8.5pt;}
tr.subtotal td{font-weight:700;background:#f5f5f5;}
tr.grand td{font-weight:900;font-size:9.5pt;background:#dfe8f4;}
/* footer */
.words{border-top:1px solid #888;padding:5px 10px;font-size:8pt;}
.foot{display:flex;border-top:1px solid #888;}
.foot-left{flex:1;padding:8px 10px;border-right:1px solid #888;font-size:8pt;}
.foot-right{width:160px;padding:8px 10px;font-size:8pt;text-align:right;}
/* print btn */
.pbtn{position:fixed;top:20px;right:20px;background:#2563EB;color:#fff;
      border:none;padding:9px 22px;border-radius:8px;font-size:13px;
      font-weight:700;cursor:pointer;box-shadow:0 4px 12px rgba(37,99,235,.35);}
.pbtn:hover{background:#1D4ED8;}
</style>
"""


def _build_html(
    *,
    inv_no: str,
    inv_date: date,
    wo: dict,
    customer: dict,
    site: dict,
    groups: list[dict],
    tax_type: str,
    tax_on: bool,
    hsn_on: bool,
    hsn_code: str,
    item_code_on: bool,
    notes: str,
) -> str:

    # ── address blocks ─────────────────────────────────────────────────────────
    cname     = customer.get("customer_name", "")
    bill_addr = customer.get("billing_address") or site.get("address") or ""
    bill_city = ", ".join(filter(None, [
        customer.get("city") or site.get("city"),
        customer.get("state") or site.get("state"),
        customer.get("pincode") or site.get("pincode"),
    ]))
    bill_gst  = customer.get("gst_number") or "—"
    bill_state = customer.get("state") or site.get("state") or "—"

    ship_addr = site.get("address") or ""
    ship_city = ", ".join(filter(None, [
        site.get("city"), site.get("state"), site.get("pincode"),
    ]))
    ship_gst  = site.get("gst_number") or customer.get("gst_number") or "—"
    ship_state = site.get("state") or "—"

    wo_num    = wo.get("wo_number", "—")
    client_wo = wo.get("client_work_ordernumber") or wo_num
    wo_date   = wo.get("start_date", "—")

    # ── totals ─────────────────────────────────────────────────────────────────
    subtotal = sum(sum(it["amount"] for it in g["items"]) for g in groups)
    tax_rate = 0.18 if tax_on else 0.0
    tax_tot  = round(subtotal * tax_rate, 2)
    grand_ex = subtotal + tax_tot
    grand    = round(grand_ex)
    rnd_off  = round(grand - grand_ex, 2)

    cgst = sgst = igst = 0.0
    if tax_on:
        if tax_type == "CGST/SGST":
            cgst = sgst = round(tax_tot / 2, 2)
        else:
            igst = tax_tot

    # ── column count for colspan ───────────────────────────────────────────────
    n_cols   = 7 + (1 if item_code_on else 0) + (1 if hsn_on else 0)
    span_pre = n_cols - 1   # colspan for all cols before Amount

    # ── line items HTML ────────────────────────────────────────────────────────
    rows_html = ""
    for grp in groups:
        label = grp["machine_label"]
        if grp.get("make") or grp.get("model"):
            label += f" — {' '.join(filter(None,[grp.get('make',''),grp.get('model','')]))}"
        if grp.get("serial"):
            label += f" S/N - {grp['serial']}"

        rows_html += (
            f"<tr class='eq-hdr'><td colspan='{n_cols}' "
            f"style='padding:4px 6px;'>{label}</td></tr>"
        )

        sl = grp["sl_no"]
        for idx, it in enumerate(grp["items"]):
            sl_cell  = str(sl) if idx == 0 else ""
            ic_cell  = (grp.get("item_code") or "") if idx == 0 and item_code_on else ""
            hsn_cell = hsn_code if hsn_on else ""
            tax_cell = "18%" if tax_on else ""
            desc_h   = it["desc"].replace("\n", "<br>")
            amt_fmt  = _fmt_inr(it["amount"])

            ic_td  = f"<td style='border:1px solid #aaa;padding:3px 5px;text-align:center;'>{ic_cell}</td>" if item_code_on else ""
            hsn_td = f"<td style='border:1px solid #aaa;padding:3px 5px;text-align:center;'>{hsn_cell}</td>" if hsn_on else ""

            rows_html += f"""<tr>
  <td style='border:1px solid #aaa;padding:3px 5px;text-align:center;vertical-align:top;'>{sl_cell}</td>
  {ic_td}
  <td style='border:1px solid #aaa;padding:3px 6px;'>{desc_h}</td>
  {hsn_td}
  <td style='border:1px solid #aaa;padding:3px 5px;text-align:center;'>{tax_cell}</td>
  <td style='border:1px solid #aaa;padding:3px 5px;text-align:center;'>{it['uom']}</td>
  <td style='border:1px solid #aaa;padding:3px 5px;text-align:right;'>{it['qty']}</td>
  <td style='border:1px solid #aaa;padding:3px 5px;text-align:right;'>{_fmt_inr(it['rate'])}</td>
  <td style='border:1px solid #aaa;padding:3px 5px;text-align:right;'>{amt_fmt}</td>
</tr>"""

    # ── tax + totals rows ──────────────────────────────────────────────────────
    tax_rows = ""
    if tax_on:
        if tax_type == "CGST/SGST":
            tax_rows = (
                f"<tr><td colspan='{span_pre}' style='border:1px solid #aaa;'></td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;'>CGST 9%</td></tr>"
                .replace("</td></tr>", f"<td style='border:1px solid #aaa;padding:3px 6px;text-align:right;'>{_fmt_inr(cgst)}</td></tr>")
            )
            # Simpler direct approach:
            tax_rows = (
                f"<tr><td colspan='{span_pre}' style='border:1px solid #aaa;padding:3px 6px;'></td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;text-align:right;'></td></tr>"
            )
            tax_rows = (
                f"<tr><td colspan='{span_pre-1}' style='border:1px solid #aaa;'></td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;font-size:8pt;'>CGST 9%</td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;text-align:right;'>{_fmt_inr(cgst)}</td></tr>"
                f"<tr><td colspan='{span_pre-1}' style='border:1px solid #aaa;'></td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;font-size:8pt;'>SGST 9%</td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;text-align:right;'>{_fmt_inr(sgst)}</td></tr>"
            )
        else:
            tax_rows = (
                f"<tr><td colspan='{span_pre-1}' style='border:1px solid #aaa;'></td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;font-size:8pt;'>IGST @ 18%</td>"
                f"<td style='border:1px solid #aaa;padding:3px 6px;text-align:right;'>{_fmt_inr(igst)}</td></tr>"
            )

    rnd_disp = _fmt_inr(rnd_off) if rnd_off != 0 else "—"

    # ── column headers ─────────────────────────────────────────────────────────
    ic_th  = "<th style='width:7%;'>Item<br>code</th>" if item_code_on else ""
    hsn_th = "<th style='width:7%;'>HSN/S<br>AC</th>" if hsn_on else ""

    # ── notes ─────────────────────────────────────────────────────────────────
    notes_html = (
        f"<div style='border-top:1px solid #888;padding:5px 10px;font-size:7.5pt;color:#555;'>"
        f"<b>Notes:</b> {notes}</div>"
    ) if notes else ""

    inv_date_str = inv_date.strftime("%d-%B-%Y") if isinstance(inv_date, date) else str(inv_date)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Tax Invoice — {inv_no}</title>
{_CSS}
</head>
<body>
<button class="pbtn no-print" onclick="window.print()">🖨 Print / Save PDF</button>
<div class="wrapper">

<!-- ── Company header ── -->
<div class="hdr">
  <div class="hdr-left">
    <div class="co-name">CTO LOGISTICS &amp; INFRA</div>
    <div class="co-sub">(CTO GROUP) &nbsp;&nbsp; (LOGISTICS &amp; INFRA EQUIPMENTS)</div>
    <div class="co-addr">
      B-202, STEEL CHAMBERS, STEEL MARKET ROAD, PLOT NO. 514, KALAMBOLI - 410 208, DIST. RAIGAD
      &nbsp; Tel.: {_CO['tel']} &nbsp; E-mail: {_CO['email']}
    </div>
  </div>
  <div class="hdr-right"><div class="ti-box">TAX<br>INVOICE</div></div>
</div>

<!-- ── Company details | Invoice meta ── -->
<div class="two-col">
  <div class="left">
    <b>{_CO['name']}</b><br>
    {_CO['addr1']}<br>{_CO['addr2']}<br>{_CO['addr3']}<br>{_CO['addr4']}<br>
    <div class="fr"><span class="fk">GSTIN/UIN:</span><span>{_CO['gstin']}</span></div>
    <div class="fr"><span class="fk">State Name :</span>
      <span>{_CO['state']}, Code : {_CO['state_code']}</span></div>
    <div class="fr"><span class="fk">E-Mail :</span><span>{_CO['email']}</span></div>
  </div>
  <div class="right">
    <div class="fr"><span class="fk">Invoice No. :-</span><span><b>{inv_no}</b></span></div>
    <div class="fr"><span class="fk">Dated :-</span><span>{inv_date_str}</span></div>
    <br>
    <div class="fr"><span class="fk">Work Order No. -</span><span>{client_wo}</span></div>
    <div class="fr"><span class="fk">Word Order Dt. -</span><span>{wo_date}</span></div>
  </div>
</div>

<!-- ── Ship to | Bill to ── -->
<div class="two-col">
  <div class="left">
    <div class="sec-lbl">Consignee (Ship to)</div>
    <b>{cname}</b><br>
    {ship_addr}<br>{ship_city}<br>
    <div class="fr"><span class="fk">GSTIN/UIN :</span><span>{ship_gst}</span></div>
    <div class="fr"><span class="fk">State Name :</span><span>{ship_state}</span></div>
  </div>
  <div class="right">
    <div class="sec-lbl">Buyer (Bill to)</div>
    <b>{cname}</b><br>
    {bill_addr}<br>{bill_city}<br>
    <div class="fr"><span class="fk">GSTIN/UIN :</span><span>{bill_gst}</span></div>
    <div class="fr"><span class="fk">State Name :</span><span>{bill_state}</span></div>
  </div>
</div>

<!-- ── Line items ── -->
<table class="inv">
<thead>
  <tr>
    <th style='width:4%;'>Sl<br>No.</th>
    {ic_th}
    <th>Description of Services</th>
    {hsn_th}
    <th style='width:5%;'>Tax<br>rate</th>
    <th style='width:6%;'>UOM</th>
    <th style='width:8%;'>Quantity</th>
    <th style='width:11%;'>Rate</th>
    <th style='width:12%;'>Amount (INR)</th>
  </tr>
</thead>
<tbody>
{rows_html}
<!-- subtotal -->
<tr class="subtotal">
  <td colspan='{span_pre}' style='border:1px solid #aaa;padding:4px 6px;'>Total taxable vale</td>
  <td style='border:1px solid #aaa;padding:4px 6px;text-align:right;'>{_fmt_inr(subtotal)}</td>
</tr>
{tax_rows}
<!-- round off -->
<tr>
  <td colspan='{span_pre}' style='border:1px solid #aaa;padding:3px 6px;'>Round Off</td>
  <td style='border:1px solid #aaa;padding:3px 6px;text-align:right;'>{rnd_disp}</td>
</tr>
<!-- grand total -->
<tr class="grand">
  <td colspan='{span_pre}' style='border:1px solid #aaa;padding:5px 6px;'>Grand total</td>
  <td style='border:1px solid #aaa;padding:5px 6px;text-align:right;'>{_fmt_inr(grand)}</td>
</tr>
</tbody>
</table>

<!-- ── Amount in words ── -->
<div class="words">
  <b>Amount Chargeable (in words)</b> - INR {_num_to_words_inr(grand)}
</div>

{notes_html}

<!-- ── Bank details + signature ── -->
<div class="foot">
  <div class="foot-left">
    <b>Company Bank Details</b><br><br>
    <div class="fr"><span class="fk">A/c Holder Name :</span><span>{_BANK['holder']}</span></div>
    <div class="fr"><span class="fk">Bank Name :</span><span>{_BANK['bank']}</span></div>
    <div class="fr"><span class="fk">A/c No. :</span><span>{_BANK['account']}</span></div>
    <div class="fr"><span class="fk">Branch &amp; IFSC Code :</span><span>{_BANK['ifsc']}</span></div>
  </div>
  <div class="foot-right">
    For {_CO['name']}<br><br><br><br><br>
    Authorised Signatory
  </div>
</div>

</div><!-- /wrapper -->
</body></html>"""


# ── Main view ──────────────────────────────────────────────────────────────────

def render() -> None:
    st.markdown(
        "<div class='page-eyebrow'>// Finance</div>"
        "<div class='page-title'>Invoice</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)

    try:
        sb = SupabaseClient()
    except Exception as exc:
        st.error(f"Supabase connection failed: {exc}")
        return

    try:
        work_orders = sb.list_work_orders()
    except Exception as exc:
        st.error(f"Failed to load work orders: {exc}"); return

    customers = []
    sites     = []
    try: customers = sb.list_customers()
    except Exception: pass
    try: sites = sb.list_sites()
    except Exception: pass

    customer_map = {c["id"]: c for c in customers if c.get("id")}
    site_map     = {s["id"]: s for s in sites     if s.get("id")}
    wo_map       = {w["id"]: w for w in work_orders if w.get("id")}

    # ── Selectors ─────────────────────────────────────────────────────────────
    cids = sorted(
        {wo.get("customer_id") for wo in work_orders if wo.get("customer_id")},
        key=lambda c: customer_map.get(c, {}).get("customer_name", ""),
    )
    c1, c2 = st.columns(2)
    with c1:
        sel_cid = st.selectbox(
            "Customer",
            [""] + cids,
            format_func=lambda x: "Select customer" if not x
                else customer_map.get(x, {}).get("customer_name", x),
            key="inv_cid",
        )

    if st.session_state.get("_inv_prev_cid") != sel_cid:
        st.session_state["_inv_prev_cid"] = sel_cid
        st.session_state["inv_wo"] = ""

    wo_ids = sorted(
        [wid for wid, wo in wo_map.items() if wo.get("customer_id") == sel_cid],
        key=lambda wid: wo_map[wid].get("wo_number", ""),
    ) if sel_cid else []

    with c2:
        sel_wo_id = st.selectbox(
            "Work Order",
            [""] + wo_ids,
            format_func=lambda x: "Select work order" if not x
                else wo_map[x].get("wo_number", "Unknown"),
            key="inv_wo",
            disabled=not sel_cid,
        )

    if not sel_cid or not sel_wo_id:
        st.markdown(
            "<div style='margin-top:32px;padding:40px;background:#f8fafc;"
            "border:1px dashed #d1d5db;border-radius:10px;text-align:center;'>"
            "<div style='font-size:32px;'>🧾</div>"
            "<div style='font-size:14px;font-weight:600;color:#374151;margin-top:10px;'>"
            "Select a Customer and Work Order to begin.</div></div>",
            unsafe_allow_html=True,
        )
        return

    sel_wo       = wo_map[sel_wo_id]
    sel_customer = customer_map.get(sel_wo.get("customer_id", ""), {})
    sel_site     = site_map.get(sel_wo.get("site_id", ""), {})

    raw_mc = sel_wo.get("machine_config")
    mc_list: list[dict] = []
    if raw_mc:
        try:
            recs = json.loads(raw_mc) if isinstance(raw_mc, str) else raw_mc
            mc_list = [r for r in (recs if isinstance(recs, list) else []) if r.get("machine_label")]
        except Exception:
            pass

    if not mc_list:
        st.warning("No machines configured on this work order.")
        return

    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

    # ── Two-panel layout ───────────────────────────────────────────────────────
    left_col, right_col = st.columns([4, 7], gap="large")

    # ── LEFT: charge selection + config ───────────────────────────────────────
    with left_col:
        st.markdown(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
            "color:#E87722;text-transform:uppercase;margin-bottom:10px;'>"
            "Select Charges to Invoice</div>",
            unsafe_allow_html=True,
        )

        selected_items: list[dict] = []

        for i, mc in enumerate(mc_list):
            mid  = mc.get("machine_id") or str(i)
            mlbl = mc.get("machine_label", f"Machine {i+1}")

            with st.expander(f"🔧 {mlbl}", expanded=(i == 0)):
                # Completed worklogs
                wls: list[dict] = []
                try:
                    all_wls = sb.list_worklogs_for_machine(sel_wo_id, mid)
                    wls = [w for w in all_wls if not w.get("is_draft", True)]
                except Exception:
                    pass

                if wls:
                    st.markdown(
                        "<div style='font-size:9px;font-weight:700;color:#6B7280;"
                        "text-transform:uppercase;margin-bottom:6px;'>Completed Worklogs</div>",
                        unsafe_allow_html=True,
                    )
                    for wl in wls:
                        bm      = wl.get("year", "—")
                        billing = _compute_billing(wl, mc)
                        period  = _period_str(bm)
                        wl_key  = f"inv_wl_{sel_wo_id}_{mid}_{bm}"
                        if st.checkbox(
                            f"{bm} — ₹ {_fmt_inr(billing['net'])}", key=wl_key, value=True
                        ):
                            selected_items.append({
                                "type": "worklog", "mc": mc, "wl": wl,
                                "billing": billing, "period": period, "sl": i + 1,
                            })
                else:
                    st.caption("No completed worklogs for this machine.")

                mob  = float(mc.get("mobilization_cost") or 0)
                demob = float(mc.get("demobilization_cost") or 0)
                if mob > 0 and st.checkbox(
                    f"Mobilisation — ₹ {_fmt_inr(mob)}",
                    key=f"inv_mob_{sel_wo_id}_{mid}",
                ):
                    selected_items.append({"type": "mob", "mc": mc, "amount": mob, "sl": i + 1})

                if demob > 0 and st.checkbox(
                    f"Demobilisation — ₹ {_fmt_inr(demob)}",
                    key=f"inv_demob_{sel_wo_id}_{mid}",
                ):
                    selected_items.append({"type": "demob", "mc": mc, "amount": demob, "sl": i + 1})

        # ── Invoice config ─────────────────────────────────────────────────────
        st.markdown("<div style='margin-top:14px'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
            "color:#E87722;text-transform:uppercase;margin-bottom:10px;'>"
            "Invoice Configuration</div>",
            unsafe_allow_html=True,
        )

        prefix   = f"BL/CLI/{_fy_str()}/"
        inv_input = st.text_input(
            "Invoice Number",
            placeholder=f"{prefix}204",
            key="inv_number",
            help=f"Format: {prefix}NNN — enter just the number or the full invoice number",
        )
        inv_no = (
            inv_input.strip()
            if "/" in inv_input.strip()
            else f"{prefix}{inv_input.strip()}"
        ) if inv_input.strip() else ""

        inv_date  = st.date_input("Invoice Date", value=date.today(), key="inv_date")
        tax_on    = st.checkbox("Apply GST (18%)", value=True, key="inv_tax")
        tax_type  = "CGST/SGST"
        if tax_on:
            tax_type = st.radio(
                "Tax Type", ["CGST/SGST", "IGST"],
                key="inv_tax_type", horizontal=True,
                help="CGST/SGST = intra-state · IGST = inter-state",
            )
        hsn_on   = st.checkbox("Include HSN/SAC code", value=False, key="inv_hsn")
        hsn_code = st.text_input("HSN/SAC", placeholder="997319", key="inv_hsn_val") if hsn_on else ""
        ic_on    = st.checkbox("Include Item Codes", value=False, key="inv_ic")
        notes    = st.text_area("Notes (optional)", key="inv_notes", height=60)

        # duplicate check
        dup = False
        if inv_no:
            try:
                dup = sb.invoice_number_exists(inv_no)
                if dup:
                    st.error(f"Invoice number **{inv_no}** already exists.")
            except Exception:
                pass

        can_gen = bool(inv_no) and not dup and bool(selected_items)
        if not selected_items:
            st.warning("Select at least one charge above.")

        gen_btn = st.button(
            "🧾  Generate Invoice",
            type="primary",
            disabled=not can_gen,
            use_container_width=True,
            key="inv_gen",
        )

    # ── RIGHT: preview ─────────────────────────────────────────────────────────
    with right_col:
        st.markdown(
            "<div style='font-size:10px;font-weight:700;letter-spacing:.12em;"
            "color:#E87722;text-transform:uppercase;margin-bottom:10px;'>"
            "Invoice Preview</div>",
            unsafe_allow_html=True,
        )

        if not selected_items:
            st.markdown(
                "<div style='padding:60px;background:#f8fafc;border:1px dashed #d1d5db;"
                "border-radius:10px;text-align:center;'>"
                "<div style='font-size:40px;'>🧾</div>"
                "<div style='font-size:13px;color:#6B7280;margin-top:10px;'>"
                "Select charges on the left to preview the invoice.</div></div>",
                unsafe_allow_html=True,
            )
        else:
            # Build line groups
            grp_map: dict[str, dict] = {}
            sl_seen: dict[str, int]  = {}

            for item in selected_items:
                mc   = item["mc"]
                mid  = mc.get("machine_id") or str(item["sl"] - 1)
                mlbl = mc.get("machine_label", "")
                mtype = mlbl.split("—")[0].strip() if "—" in mlbl else mlbl

                if mid not in grp_map:
                    sl_seen[mid] = len(sl_seen) + 1
                    grp_map[mid] = {
                        "machine_label": mlbl,
                        "make":   mc.get("make", ""),
                        "model":  mc.get("model", ""),
                        "serial": mc.get("serial_number", ""),
                        "sl_no":  sl_seen[mid],
                        "item_code": "",
                        "items": [],
                    }

                grp = grp_map[mid]

                if item["type"] == "worklog":
                    b = item["billing"]
                    p = item["period"]
                    grp["items"].append({
                        "desc":   f"Hiring charges - {mtype}\nPeriod - {p}",
                        "uom":    "Month",
                        "qty":    f"{b['qty']:.3f}",
                        "rate":   b["rate"],
                        "amount": b["hiring"],
                    })
                    if b["ot_hrs"] > 0:
                        grp["items"].append({
                            "desc":   f"OT charges - {mtype}\nPeriod - {p}",
                            "uom":    "Hourly",
                            "qty":    f"{b['ot_hrs']:.3f}",
                            "rate":   b["ot_rate"],
                            "amount": b["ot_amt"],
                        })
                    if b["deduction"] > 0:
                        grp["items"].append({
                            "desc":   "Deduction",
                            "uom":    "—",
                            "qty":    "—",
                            "rate":   0,
                            "amount": -b["deduction"],
                        })
                elif item["type"] == "mob":
                    grp["items"].append({
                        "desc":   "Mobilisation charges",
                        "uom":    "Nos",
                        "qty":    "1.000",
                        "rate":   item["amount"],
                        "amount": item["amount"],
                    })
                elif item["type"] == "demob":
                    grp["items"].append({
                        "desc":   "Demobilisation charges",
                        "uom":    "Nos",
                        "qty":    "1.000",
                        "rate":   item["amount"],
                        "amount": item["amount"],
                    })

            groups = list(grp_map.values())

            inv_html = _build_html(
                inv_no=inv_no or f"{prefix}???",
                inv_date=inv_date,
                wo=sel_wo,
                customer=sel_customer,
                site=sel_site,
                groups=groups,
                tax_type=tax_type,
                tax_on=tax_on,
                hsn_on=hsn_on,
                hsn_code=hsn_code,
                item_code_on=ic_on,
                notes=notes.strip() if notes else "",
            )

            components.html(inv_html, height=960, scrolling=True)

            # ── Action row ─────────────────────────────────────────────────────
            a1, a2 = st.columns(2)
            with a1:
                st.download_button(
                    "⬇  Download Invoice (HTML)",
                    data=inv_html.encode("utf-8"),
                    file_name=f"{inv_no.replace('/', '_') if inv_no else 'invoice'}.html",
                    mime="text/html",
                    use_container_width=True,
                )
            with a2:
                if gen_btn and can_gen:
                    subtotal = sum(sum(it["amount"] for it in g["items"]) for g in groups)
                    tax_tot  = round(subtotal * 0.18, 2) if tax_on else 0.0
                    grand    = round(subtotal + tax_tot)
                    rnd_off  = round(grand - (subtotal + tax_tot), 2)
                    try:
                        sb.insert_invoice({
                            "invoice_number": inv_no,
                            "work_order_id":  sel_wo_id,
                            "invoice_date":   inv_date.isoformat(),
                            "customer_id":    sel_wo.get("customer_id"),
                            "site_id":        sel_wo.get("site_id"),
                            "tax_type":       tax_type,
                            "line_items":     json.dumps(groups),
                            "subtotal":       subtotal,
                            "tax_amount":     tax_tot,
                            "round_off":      rnd_off,
                            "grand_total":    grand,
                            "status":         "Draft",
                            "notes":          notes.strip() or None,
                        })
                        st.success(f"✔ Invoice **{inv_no}** saved.")
                    except Exception as exc:
                        st.warning(f"Preview ready — could not save to DB: {exc}")
