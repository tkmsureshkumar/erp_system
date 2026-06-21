# CTO ERP – Python (Streamlit + Pydantic)

A faithful Python port of the React/TypeScript frontend. The browser app can't
run "as Python", so the equivalent stack is **Streamlit** (UI + state) and
**Pydantic v2** (the typed schema + validation). Same three views, same workflow
guards, same in-memory store and live cross-view updates.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # optional
pip install -r requirements.txt
streamlit run app.py                                  # opens http://localhost:8501
```

It boots on in-memory seed data — no backend needed. Try:

- **Fleet Status** — KPI tiles, fleet-by-status utilization bar, search + status
  filter, badge table (overdue returns flagged in red).
- **New Work Order** — pick CUST-001; the Site select unlocks and lists only its
  sites. Add machine lines (the “useFieldArray” stand-in); picking a machine
  prefills its rental; the indicative total updates live.
- **Dispatch Machine** — CUST-001 → WO-2026-0001 → line `SL-260` → Dispatch.
  Go back to Fleet Status: `SL-260` is now **On Rent**. Selecting `SL-190`
  (Breakdown) blocks dispatch with a reason.

## File mapping (React → Python)

| React / TS | Python | Role |
|---|---|---|
| `types.ts` | `erp/models.py` | ENUMs (`str, Enum`) + Pydantic table models + option models + `FleetStatusRow` |
| `lib/validation.ts` (Zod) | `erp/validation.py` | Pydantic form payloads + `model_validator` cross-field rules + `machine_dispatchable` guard |
| `lib/format.ts` | `erp/format.py` | INR (lakh/crore) currency, dates, days-until |
| `components/ui/StatusBadge.tsx` | `erp/components.py` | `badge_html` signature element + tone palettes |
| `mockData.ts` + `App.tsx` store + `data/supabase.ts` | `erp/store.py` | seed data, derived options, `vw_fleet_status`, mutations + side effects |
| `FleetDashboardView.tsx` | `erp/views/fleet_dashboard.py` | KPIs, utilization bar, filters, table |
| `WorkOrderForm.tsx` | `erp/views/work_order_form.py` | header + dynamic line items, customer-filtered sites |
| `DeploymentForm.tsx` | `erp/views/deployment_form.py` | Active-WO + Available-machine guards, state transition |
| `App.tsx` shell | `app.py` | page config, sidebar nav, routing |
| `ErrorBoundary.tsx` | Streamlit shows tracebacks; wrap blocks in `try/except` + `st.error` for prod |

## Workflow guards → DB backing

| Guard | Where | DB constraint mirrored |
|---|---|---|
| Site select disabled until a customer is chosen; lists only that customer's sites | both forms | `trg_validate_wo_site_customer` |
| Only `status = Active` work orders offered for the customer | deployment form | `trg_validate_deployment_wo` |
| Machine dispatchable only when Available and not Breakdown/BER | deployment form (`machine_dispatchable`) | `deployments_one_active_per_machine` |
| ≥1 line, no duplicate machine per WO, date ordering | `validation.py` (`model_validator`) | line-item integrity / invariants |

Client guards are convenience; the database stays authoritative. Swap the
methods in `erp/store.py` for real Supabase/Postgres calls — the views only touch
the public `Store` methods, so nothing else changes.

## Notes

- `st.session_state` is the in-memory store; the `Store` object persists across
  reruns, so mutations (e.g. dispatch flipping a machine to On Rent) show up
  everywhere immediately.
- Dynamic line items use a session-state row-id list as the Streamlit equivalent
  of React Hook Form's `useFieldArray`.
- Requires Streamlit ≥ 1.36 for `st.selectbox(index=None, placeholder=...)` and
  `st.date_input(value=None)`.
```
cto-erp-py/
├─ app.py
├─ requirements.txt · README.md
└─ erp/
   ├─ models.py · validation.py · format.py · components.py · store.py
   └─ views/ fleet_dashboard.py · work_order_form.py · deployment_form.py
```
