"""
erp/views/login.py — Standalone login page for IRONLINE ACCESS ERP.

Rendered by app.py when no authenticated session exists.  The function
injects its own CSS (to override the global padding-top set for the
navbar) and uses st.columns for centering.
"""
from __future__ import annotations

import streamlit as st

from erp.supabase_client import SupabaseClient


def render() -> None:
    """Render the full-page login card."""

    # ------------------------------------------------------------------
    # CSS overrides for the login page
    # ------------------------------------------------------------------
    st.markdown(
        """
        <style>
          /* No navbar on the login page — remove the top clearance and
             allow full-width layout so the card can be centred. */
          .block-container {
            padding-top: 3rem !important;
            padding-bottom: 3rem !important;
            max-width: 100% !important;
          }

          /* ── Login card ── */
          .login-brand {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 28px;
          }
          .login-brand-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 48px;
            height: 48px;
            background: #E87722;
            border-radius: 8px;
            font-size: 28px;
            font-weight: 900;
            color: #fff;
            transform: scaleX(0.80);
            flex-shrink: 0;
          }
          .login-brand-name {
            font-size: 14px;
            font-weight: 800;
            color: #1c1c2e;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            line-height: 1.25;
          }
          .login-brand-sub {
            font-size: 10px;
            color: #9ca3af;
            letter-spacing: 0.14em;
            text-transform: uppercase;
          }
          .login-heading {
            font-size: 22px;
            font-weight: 700;
            color: #111827;
            margin: 0 0 6px 0;
          }
          .login-sub {
            font-size: 13px;
            color: #6b7280;
            margin: 0 0 24px 0;
          }
          .login-divider {
            border: none;
            border-top: 1px solid #e5e7eb;
            margin: 24px 0;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # Centre the form using three equal columns
    # ------------------------------------------------------------------
    _, col, _ = st.columns([1, 1, 1])

    with col:
        # Brand header
        st.markdown(
            """
            <div class="login-brand">
              <div class="login-brand-icon">&#8679;</div>
              <div>
                <div class="login-brand-name">Ironline Access</div>
                <div class="login-brand-sub">Fleet Operations ERP</div>
              </div>
            </div>
            <p class="login-heading">Sign in to your account</p>
            <p class="login-sub">Enter your credentials to continue.</p>
            """,
            unsafe_allow_html=True,
        )

        # ------------------------------------------------------------------
        # Login form
        # ------------------------------------------------------------------
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input(
                "Email Address",
                placeholder="you@example.com",
                autocomplete="email",
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="••••••••",
                autocomplete="current-password",
            )
            submitted = st.form_submit_button(
                "Sign In",
                use_container_width=True,
                type="primary",
            )

        # ------------------------------------------------------------------
        # Handle submission (outside the form context so widgets are stable)
        # ------------------------------------------------------------------
        if submitted:
            email_clean = (email or "").strip()
            if not email_clean or not password:
                st.error("Please enter your email address and password.")
                return

            try:
                sb = SupabaseClient()
                user, profile, session = sb.sign_in(email_clean, password)
            except Exception as exc:
                msg = str(exc)
                if any(k in msg.lower() for k in ("invalid login", "invalid_credentials", "wrong password", "email not confirmed")):
                    st.error("Invalid email or password. Please try again.")
                else:
                    st.error(f"Sign-in failed: {msg}")
                return

            if not profile:
                st.error(
                    "Your account profile was not found. "
                    "Contact your administrator."
                )
                return

            if not profile.get("is_active", True):
                st.error(
                    "Your account has been deactivated. "
                    "Contact your administrator."
                )
                return

            # Store session
            st.session_state["user"] = user
            st.session_state["profile"] = profile
            # Stash tokens so app.py can save them to cookies
            if session:
                st.session_state["_new_tokens"] = {
                    "at": session.access_token,
                    "rt": session.refresh_token,
                }

            # Log the login event (non-fatal)
            try:
                sb.log_activity(
                    user_id=user.id,
                    user_email=profile.get("email", email_clean),
                    user_name=profile.get("full_name", ""),
                    action="LOGIN",
                    module="Auth",
                )
            except Exception:
                pass

            st.rerun()
