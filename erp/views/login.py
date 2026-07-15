"""
erp/views/login.py — Standalone login page for IRONLINE ACCESS ERP.

Rendered by app.py when no authenticated session exists.  The function
injects its own CSS (to override the global padding-top set for the
navbar) and uses st.columns for centering.
"""
from __future__ import annotations

import streamlit as st

from erp.supabase_client import SupabaseClient


_LOGIN_CSS = """<style>
/* ── Full-page dark gradient background ─────────────────────────────────── */
.stApp {
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%) !important;
    min-height: 100vh;
}

/* ── Hide default Streamlit chrome ──────────────────────────────────────── */
#MainMenu                  { visibility: hidden !important; }
footer                     { visibility: hidden !important; }
header                     { visibility: hidden !important; }
[data-testid="stToolbar"]  { display: none !important; }
.stDeployButton            { display: none !important; }

/* ── Page layout ─────────────────────────────────────────────────────────── */
.block-container {
    padding-top: 8vh !important;
    padding-bottom: 6vh !important;
    max-width: 100% !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

/* ── Login card: style the center column's vertical block ────────────────── */
/* Covers both data-testid variants used across Streamlit versions.          */
[data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"],
[data-testid="stColumns"]         > [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] {
    background    : #ffffff;
    border-radius : 16px;
    padding       : 40px 36px 32px !important;
    box-shadow    : 0 24px 64px rgba(0,0,0,.45), 0 4px 20px rgba(0,0,0,.22);
    animation     : cs-fadeup .40s ease;
    max-width     : 420px;
    margin        : 0 auto;
}

/* ── Brand block ─────────────────────────────────────────────────────────── */
.login-brand {
    display     : flex;
    align-items : center;
    gap         : 14px;
    margin-bottom: 28px;
}
.login-brand-icon {
    display         : inline-flex;
    align-items     : center;
    justify-content : center;
    width           : 48px;
    height          : 48px;
    background      : linear-gradient(135deg, #E87722 0%, #f09040 100%);
    border-radius   : 12px;
    font-size       : 26px;
    color           : #fff;
    flex-shrink     : 0;
    box-shadow      : 0 4px 14px rgba(232,119,34,.40);
}
.login-brand-name {
    font-size     : 17px;
    font-weight   : 800;
    color         : #111827;
    letter-spacing: 0.03em;
    line-height   : 1.2;
}
.login-brand-sub {
    font-size     : 11px;
    color         : #9CA3AF;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    margin-top    : 3px;
}

/* ── Heading + subtitle ──────────────────────────────────────────────────── */
.login-heading {
    font-size  : 22px;
    font-weight: 700;
    color      : #111827;
    margin     : 0 0 6px 0;
    line-height: 1.25;
}
.login-sub {
    font-size: 13px;
    color    : #6B7280;
    margin   : 0 0 22px 0;
}
.login-divider {
    border    : none;
    border-top: 1px solid #E2EBF0;
    margin    : 0 0 24px 0;
}

/* ── Styled error card ───────────────────────────────────────────────────── */
.login-error {
    display      : flex;
    align-items  : flex-start;
    gap          : 10px;
    background   : #FEF2F2;
    border       : 1px solid #FECACA;
    border-left  : 4px solid #EF4444;
    border-radius: 8px;
    padding      : 11px 14px;
    margin-top   : 14px;
    font-size    : 13px;
    color        : #991B1B;
    line-height  : 1.5;
}
.login-error-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }

/* ── Form submit button — orange brand ───────────────────────────────────── */
[data-testid="stFormSubmitButton"] > button {
    background    : linear-gradient(135deg, #E87722 0%, #d4651a 100%) !important;
    border        : none !important;
    color         : #fff !important;
    font-weight   : 700 !important;
    font-size     : 15px !important;
    letter-spacing: .02em !important;
    border-radius : 10px !important;
    height        : 46px !important;
    box-shadow    : 0 4px 14px rgba(232,119,34,.40) !important;
    transition    : opacity .18s, transform .15s !important;
}
[data-testid="stFormSubmitButton"] > button:hover  { opacity: .90 !important; transform: translateY(-1px) !important; }
[data-testid="stFormSubmitButton"] > button:active { transform: translateY(0) !important; }

/* ── Input focus ring in brand orange ────────────────────────────────────── */
[data-testid="stForm"] input:focus {
    border-color: #E87722 !important;
    box-shadow  : 0 0 0 3px rgba(232,119,34,.15) !important;
    outline     : none !important;
}

/* ── Footer ─────────────────────────────────────────────────────────────── */
.login-footer {
    text-align    : center;
    margin-top    : 28px;
    font-size     : 11px;
    color         : rgba(255,255,255,.30);
    letter-spacing: .05em;
}

/* ── Fade-up animation (shared with rest of the design system) ───────────── */
@keyframes cs-fadeup {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0);    }
}
</style>"""


def render() -> None:
    """Render the full-page login card."""

    # ------------------------------------------------------------------
    # CSS — dark background, card style, orange button, animations
    # ------------------------------------------------------------------
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Centre the card using three equal columns
    # ------------------------------------------------------------------
    _, col, _ = st.columns([1, 1, 1])

    with col:
        # Brand header
        st.markdown(
            """
            <div class="login-brand">
              <div class="login-brand-icon">&#8679;</div>
              <div>
                <div class="login-brand-name">ERP Platform</div>
                <div class="login-brand-sub">Fleet Operations ERP</div>
              </div>
            </div>
            <p class="login-heading">Sign in to your account</p>
            <p class="login-sub">Enter your credentials to continue.</p>
            <hr class="login-divider">
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
                st.markdown(
                    "<div class='login-error'>"
                    "<span class='login-error-icon'>&#9888;</span>"
                    "Please enter your email address and password."
                    "</div>",
                    unsafe_allow_html=True,
                )
                return

            try:
                sb = SupabaseClient()
                user, profile, session = sb.sign_in(email_clean, password)
            except Exception as exc:
                msg = str(exc)
                if any(k in msg.lower() for k in (
                    "invalid login", "invalid_credentials",
                    "wrong password", "email not confirmed",
                )):
                    err_txt = "Invalid email or password. Please try again."
                else:
                    err_txt = f"Sign-in failed: {msg}"
                st.markdown(
                    f"<div class='login-error'>"
                    f"<span class='login-error-icon'>&#9888;</span>"
                    f"{err_txt}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                return

            if not profile:
                st.markdown(
                    "<div class='login-error'>"
                    "<span class='login-error-icon'>&#9888;</span>"
                    "Your account profile was not found. "
                    "Contact your administrator."
                    "</div>",
                    unsafe_allow_html=True,
                )
                return

            if not profile.get("is_active", True):
                st.markdown(
                    "<div class='login-error'>"
                    "<span class='login-error-icon'>&#9888;</span>"
                    "Your account has been deactivated. "
                    "Contact your administrator."
                    "</div>",
                    unsafe_allow_html=True,
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

    # Footer sits on the dark background, below the card
    st.markdown(
        "<div class='login-footer'>"
        "&#169; 2025 Ironline Access &nbsp;&middot;&nbsp; Fleet Operations Platform"
        "</div>",
        unsafe_allow_html=True,
    )
