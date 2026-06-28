"""Simple Supabase helper for inserting/listing customers.

Reads `SUPABASE_URL` and `SUPABASE_KEY` from environment variables.
"""
from __future__ import annotations

import calendar
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

try:
    from supabase import create_client  # type: ignore
except Exception:  # pragma: no cover - import may fail if package missing
    create_client = None

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


class SupabaseClient:
    def __init__(self) -> None:
        url = os.getenv('SUPABASE_URL') or 'https://gsafyjbpucgbhtvvbfue.supabase.co'
        key = os.getenv('SUPABASE_KEY') or 'sb_publishable_Ixq1xmRqsLVavcvL-wpguQ_v3JSxlhS'
        if not url or not key:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY environment variables")
        if create_client is None:
            raise RuntimeError("supabase package not installed. Run: pip install supabase")
        self.client = create_client(url, key)

    def insert_customer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("customers").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def list_customers(self) -> List[Dict[str, Any]]:
        resp = self.client.table("customers").select("*").execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list):
            return data
        return []

    def update_customer(self, customer_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("customers").update(payload).eq("id", customer_id).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def delete_customer(self, customer_id: str) -> None:
        resp = self.client.table("customers").delete().eq("id", customer_id).execute()
        error = None
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))

    def insert_site(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("sites").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def list_sites(self) -> List[Dict[str, Any]]:
        resp = self.client.table("sites").select("*").execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list):
            return data
        return []

    def update_site(self, site_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("sites").update(payload).eq("id", site_id).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def delete_site(self, site_id: str) -> None:
        resp = self.client.table("sites").delete().eq("id", site_id).execute()
        error = None
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))

    def insert_operator(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("operators").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def list_operators(self) -> List[Dict[str, Any]]:
        resp = self.client.table("operators").select("*").execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list):
            return data
        return []

    def update_operator(self, operator_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("operators").update(payload).eq("id", operator_id).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def delete_operator(self, operator_id: str) -> None:
        resp = self.client.table("operators").delete().eq("id", operator_id).execute()
        error = None
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))

    def insert_machine(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("machines").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def list_machines(self) -> List[Dict[str, Any]]:
        resp = self.client.table("machines").select("*").execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list):
            return data
        return []

    def update_machine(self, machine_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("machines").update(payload).eq("id", machine_id).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def delete_machine(self, machine_id: str) -> None:
        resp = self.client.table("machines").delete().eq("id", machine_id).execute()
        error = None
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))

    def insert_work_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("work_orders").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def list_work_orders(self) -> List[Dict[str, Any]]:
        resp = self.client.table("work_orders").select("*").execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list):
            return data
        return []

    def update_work_order(self, work_order_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("work_orders").update(payload).eq("id", work_order_id).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def list_assets(self) -> List[Dict[str, Any]]:
        resp = self.client.table("asset_master").select("*").order("asset_name").execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        return data if isinstance(data, list) else []

    def insert_asset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("asset_master").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def update_asset(self, asset_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("asset_master").update(payload).eq("id", asset_id).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def insert_work_order_line(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("work_order_lines").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    # ── Deployments ───────────────────────────────────────────────────────────

    def list_deployments(self) -> List[Dict[str, Any]]:
        resp = (
            self.client.table("deployments")
            .select("*")
            .execute()
        )
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list):
            return data
        return []

    def get_deployment_by_wo(self, work_order_id: str) -> Dict[str, Any]:
        resp = (
            self.client.table("deployments")
            .select("*")
            .eq("work_order_id", work_order_id)
            .limit(1)
            .execute()
        )
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def insert_deployment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("deployments").insert(payload).execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def update_deployment(self, deployment_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = (
            self.client.table("deployments")
            .update(payload)
            .eq("id", deployment_id)
            .execute()
        )
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    # ── Worklogs ──────────────────────────────────────────────────────────────

    def get_worklog_by_month(
        self, work_order_id: str, machine_id: str, year: int, month: int
    ) -> Dict[str, Any]:
        billing_month = f"{calendar.month_name[month]} {year}"
        resp = (
            self.client.table("work_logs")
            .select("*")
            .eq("work_order_id", work_order_id)
            .eq("machine_id", machine_id)
            .eq("year", billing_month)
            .limit(1)
            .execute()
        )
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def upsert_worklog(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Look up existing record by work_order_id + machine_id + year (billing month string)
        fb = (
            self.client.table("work_logs")
            .select("id")
            .eq("work_order_id", payload["work_order_id"])
            .eq("machine_id", payload["machine_id"])
            .eq("year", payload["year"])
            .limit(1)
            .execute()
        )
        fb_data = fb.data if hasattr(fb, "data") else (fb.get("data") if isinstance(fb, dict) else None)
        lookup = fb_data[0] if isinstance(fb_data, list) and fb_data else {}

        if lookup.get("id"):
            resp = (
                self.client.table("work_logs")
                .update(payload)
                .eq("id", lookup["id"])
                .execute()
            )
        else:
            resp = self.client.table("work_logs").insert(payload).execute()

        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    def list_all_worklogs(self) -> List[Dict[str, Any]]:
        resp = self.client.table("work_logs").select("*").execute()
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        return data if isinstance(data, list) else []

    def list_worklogs_for_machine(
        self, work_order_id: str, machine_id: str
    ) -> List[Dict[str, Any]]:
        resp = (
            self.client.table("work_logs")
            .select("*")
            .eq("work_order_id", work_order_id)
            .eq("machine_id", machine_id)
            .order("year")
            .order("month")
            .execute()
        )
        data = None
        error = None
        if hasattr(resp, "data"):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data")
        if hasattr(resp, "error"):
            error = resp.error
        elif isinstance(resp, dict):
            error = resp.get("error")
        if error:
            raise RuntimeError(str(error))
        return data if isinstance(data, list) else []
