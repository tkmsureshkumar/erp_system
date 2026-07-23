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


def _secret(key: str, default: str = "") -> str:
    """Read a secret from os.environ first, then st.secrets (Streamlit Cloud)."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st  # noqa: PLC0415
        return str(st.secrets.get(key, default))
    except Exception:
        return default


class SupabaseClient:
    def __init__(self) -> None:
        url = _secret('SUPABASE_URL')
        key = _secret('SUPABASE_KEY')
        if not url or not key:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in secrets or .env")
        if create_client is None:
            raise RuntimeError("supabase package not installed. Run: pip install supabase")
        self.client = create_client(url, key)

        # Admin client uses the service-role key (bypasses RLS, needed for
        # auth.admin.create_user and user_profiles writes).
        service_key = _secret('SUPABASE_SERVICE_KEY')
        if service_key:
            self.admin_client = create_client(url, service_key)
        else:
            self.admin_client = self.client  # fallback — admin ops will fail

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

    def delete_worklog(self, work_order_id: str, machine_id: str, billing_month: str) -> None:
        self.client.table("work_logs") \
            .delete() \
            .eq("work_order_id", work_order_id) \
            .eq("machine_id", machine_id) \
            .eq("year", billing_month) \
            .execute()

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

    # ── Auth / User profiles ──────────────────────────────────────────────

    def sign_in(self, email: str, password: str) -> tuple:
        """
        Authenticate with Supabase, then fetch the matching user_profiles row.

        Returns:
            (user, profile_dict, session) — session carries access/refresh tokens.
        """
        resp = self.client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        user    = resp.user
        session = resp.session
        profile = self.get_user_profile(str(user.id))
        return user, profile, session

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """SELECT * FROM user_profiles WHERE id = user_id (single row)."""
        resp = (
            self.admin_client.table("user_profiles")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        data = resp.data if hasattr(resp, "data") else (
            resp.get("data") if isinstance(resp, dict) else None
        )
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def list_user_profiles(self) -> List[Dict[str, Any]]:
        """SELECT * FROM user_profiles ORDER BY created_at DESC."""
        resp = (
            self.admin_client.table("user_profiles")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        data = resp.data if hasattr(resp, "data") else (
            resp.get("data") if isinstance(resp, dict) else None
        )
        return data if isinstance(data, list) else []

    def admin_create_user(
        self,
        email: str,
        password: str,
        full_name: str,
        role: str,
        page_access: List[str],
    ) -> Dict[str, Any]:
        """
        1. Create a Supabase Auth user (email pre-confirmed).
        2. Insert a matching row into user_profiles.

        Returns the inserted user_profiles row.
        """
        auth_resp = self.admin_client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
            }
        )
        new_user = auth_resp.user

        profile_payload: Dict[str, Any] = {
            "id": str(new_user.id),
            "email": email,
            "full_name": full_name,
            "role": role,
            "page_access": page_access,
            "is_active": True,
        }
        resp = (
            self.admin_client.table("user_profiles")
            .insert(profile_payload)
            .execute()
        )
        data = resp.data if hasattr(resp, "data") else (
            resp.get("data") if isinstance(resp, dict) else None
        )
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return profile_payload

    def update_user_profile(
        self, user_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """UPDATE user_profiles SET ... WHERE id = user_id."""
        from datetime import datetime, timezone  # noqa: PLC0415
        update_payload = {
            **payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = (
            self.admin_client.table("user_profiles")
            .update(update_payload)
            .eq("id", user_id)
            .execute()
        )
        data = resp.data if hasattr(resp, "data") else (
            resp.get("data") if isinstance(resp, dict) else None
        )
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    # ── Machine movements ─────────────────────────────────────────────────

    def insert_machine_movement(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.admin_client.table("machine_movements").insert(payload).execute()
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

    def list_machine_movements(self, machine_id: str = None) -> List[Dict[str, Any]]:
        query = (
            self.admin_client.table("machine_movements")
            .select("*")
            .order("movement_date", desc=True)
            .limit(200)
        )
        if machine_id:
            query = query.eq("machine_id", machine_id)
        resp = query.execute()
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

    def update_machine_movement(self, movement_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = (
            self.admin_client.table("machine_movements")
            .update(payload)
            .eq("id", movement_id)
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

    # ── Activity logging ──────────────────────────────────────────────────

    def log_activity(
        self,
        user_id: Any,
        user_email: str,
        user_name: str,
        action: str,
        module: str,
        record_id: Any = None,
        record_label: Any = None,
        details: Any = None,
    ) -> None:
        """
        Insert a row into activity_logs.

        This method NEVER raises — any error is silently swallowed so that
        a logging failure cannot break normal application flow.
        """
        try:
            payload: Dict[str, Any] = {
                "user_id": str(user_id) if user_id is not None else None,
                "user_email": user_email,
                "user_name": user_name,
                "action": action,
                "module": module,
                "record_id": str(record_id) if record_id is not None else None,
                "record_label": str(record_label) if record_label is not None else None,
                "details": details,
            }
            self.admin_client.table("activity_logs").insert(payload).execute()
        except Exception:  # noqa: BLE001
            pass

    def list_activity_logs(
        self,
        module: Any = None,
        action: Any = None,
        user_name: Any = None,
        date_from: Any = None,
        date_to: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        SELECT * FROM activity_logs with optional filters.
        Returns up to 500 rows ordered by created_at DESC.
        """
        from datetime import timedelta  # noqa: PLC0415

        query = (
            self.admin_client.table("activity_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(500)
        )
        if module:
            query = query.eq("module", module)
        if action:
            query = query.eq("action", action)
        if user_name:
            query = query.ilike("user_name", f"%{user_name}%")
        if date_from:
            # gte on an ISO date string works with TIMESTAMPTZ columns
            query = query.gte("created_at", str(date_from))
        if date_to:
            # Make upper bound inclusive by querying up to start of next day
            next_day = date_to + timedelta(days=1)
            query = query.lt("created_at", str(next_day))

        resp = query.execute()
        data = resp.data if hasattr(resp, "data") else (
            resp.get("data") if isinstance(resp, dict) else None
        )
        return data if isinstance(data, list) else []

    # ── Invoice methods ────────────────────────────────────────────────────────

    def invoice_number_exists(self, invoice_number: str) -> bool:
        resp = self.client.table("invoices").select("id").eq(
            "invoice_number", invoice_number
        ).limit(1).execute()
        data = resp.data if hasattr(resp, "data") else (
            resp.get("data") if isinstance(resp, dict) else None
        )
        return bool(data)

    def insert_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.client.table("invoices").insert(payload).execute()
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

    def list_invoices_for_wo(self, work_order_id: str) -> List[Dict[str, Any]]:
        resp = (
            self.client.table("invoices")
            .select("*")
            .eq("work_order_id", work_order_id)
            .order("invoice_date", desc=True)
            .execute()
        )
        data = resp.data if hasattr(resp, "data") else (
            resp.get("data") if isinstance(resp, dict) else None
        )
        return data if isinstance(data, list) else []
