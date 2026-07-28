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

/* ── Forgot-password link ────────────────────────────────────────────────── */
.forgot-link {
    text-align : right;
    margin-top : -10px;
    margin-bottom: 6px;
    font-size  : 12px;
}
.forgot-link a {
    color          : #E87722;
    text-decoration: none;
    font-weight    : 600;
    cursor         : pointer;
}
.forgot-link a:hover { text-decoration: underline; }

/* ── Style the Forgot/Back buttons as plain text links ───────────────────── */
[data-testid="stBaseButton-secondary"][kind="secondary"]:has(> p) {
    background : transparent !important;
    border     : none !important;
    padding    : 0 !important;
    color      : #E87722 !important;
    font-size  : 12px !important;
    font-weight: 600 !important;
    box-shadow : none !important;
    margin-top : 4px !important;
}
button[kind="secondary"][data-testid="stBaseButton-secondary"] {
    background : transparent !important;
    border     : none !important;
    box-shadow : none !important;
}
/* Specifically target the forgot / back buttons by key */
div[data-testid="element-container"]:has(button#goto_reset),
div[data-testid="element-container"]:has(button#back_to_login) {
    text-align: right;
}

/* ── Success banner ──────────────────────────────────────────────────────── */
.login-success {
    display      : flex;
    align-items  : flex-start;
    gap          : 10px;
    background   : #F0FDF4;
    border       : 1px solid #BBF7D0;
    border-left  : 4px solid #16A34A;
    border-radius: 8px;
    padding      : 11px 14px;
    margin-top   : 14px;
    font-size    : 13px;
    color        : #166534;
    line-height  : 1.5;
}

/* ── Password hint ───────────────────────────────────────────────────────── */
.pw-hint {
    font-size  : 11px;
    color      : #9CA3AF;
    margin-top : 4px;
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

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # ── Hash → query-param bridge ─────────────────────────────────────────────
    # Supabase password-reset links use a URL hash (#access_token=...).
    # Python / Streamlit cannot read hash fragments, so we inject a tiny JS
    # snippet that detects the recovery hash and replaces it with query params,
    # causing a page reload that Python CAN read.
    st.iframe("""
<script>
(function(){
    try {
        var h = window.parent.location.hash;
        if (!h || h.indexOf('access_token') === -1) return;
        var p = new URLSearchParams(h.replace(/^#/, ''));
        if (p.get('type') !== 'recovery') return;
        var u = new URL(window.parent.location.href);
        u.hash = '';
        u.searchParams.set('access_token', p.get('access_token') || '');
        u.searchParams.set('type', 'recovery');
        var rt = p.get('refresh_token');
        if (rt) u.searchParams.set('refresh_token', rt);
        window.parent.location.replace(u.toString());
    } catch(e) {}
})();
</script>
""", height=1)

    # Toggle between sign-in and forgot-password modes
    if "show_reset" not in st.session_state:
        st.session_state["show_reset"] = False

    _, col, _ = st.columns([1, 1, 1])

    with col:
        # ── Brand header ───────────────────────────────────────────────
        st.markdown(
            """
            <div class="login-brand">
              <div class="login-brand-icon">&#8679;</div>
              <div>
                <div class="login-brand-name">ERP Platform</div>
                <div class="login-brand-sub">Fleet Operations ERP</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ══════════════════════════════════════════════════════════════
        # SET NEW PASSWORD MODE  (user arrived via email reset link)
        # ══════════════════════════════════════════════════════════════
        _at = st.query_params.get("access_token", "")
        _rt = st.query_params.get("refresh_token", "")
        _tp = st.query_params.get("type", "")

        if _tp == "recovery" and _at:
            st.markdown(
                "<p class='login-heading'>Set a new password</p>"
                "<p class='login-sub'>Choose a strong password for your account.</p>"
                "<hr class='login-divider'>",
                unsafe_allow_html=True,
            )

            with st.form("set_password_form", clear_on_submit=False):
                new_pw  = st.text_input("New Password",     type="password", placeholder="Min. 8 characters")
                conf_pw = st.text_input("Confirm Password", type="password", placeholder="Repeat new password")
                set_submitted = st.form_submit_button("Update Password", use_container_width=True, type="primary")

            st.markdown("<p class='pw-hint'>Password must be at least 8 characters.</p>", unsafe_allow_html=True)

            if set_submitted:
                if not new_pw or not conf_pw:
                    st.markdown(
                        "<div class='login-error'><span class='login-error-icon'>&#9888;</span>"
                        "Please fill in both password fields.</div>",
                        unsafe_allow_html=True,
                    )
                elif new_pw != conf_pw:
                    st.markdown(
                        "<div class='login-error'><span class='login-error-icon'>&#9888;</span>"
                        "Passwords do not match.</div>",
                        unsafe_allow_html=True,
                    )
                elif len(new_pw) < 8:
                    st.markdown(
                        "<div class='login-error'><span class='login-error-icon'>&#9888;</span>"
                        "Password must be at least 8 characters.</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    try:
                        sb = SupabaseClient()
                        sb.set_recovery_session(_at, _rt)
                        sb.update_user_password(new_pw)
                        st.query_params.clear()
                        st.markdown(
                            "<div class='login-success'>&#10003;&nbsp; Password updated successfully! "
                            "You can now sign in with your new password.</div>",
                            unsafe_allow_html=True,
                        )
                        st.session_state["show_reset"] = False
                    except Exception as exc:
                        st.markdown(
                            f"<div class='login-error'><span class='login-error-icon'>&#9888;</span>"
                            f"Could not update password: {exc}</div>",
                            unsafe_allow_html=True,
                        )

        # ══════════════════════════════════════════════════════════════
        # FORGOT PASSWORD MODE  (user clicked "Forgot password?")
        # ══════════════════════════════════════════════════════════════
        elif st.session_state["show_reset"]:
            st.markdown(
                "<p class='login-heading'>Reset your password</p>"
                "<p class='login-sub'>Enter your email and we'll send you a reset link.</p>"
                "<hr class='login-divider'>",
                unsafe_allow_html=True,
            )

            with st.form("reset_form", clear_on_submit=False):
                reset_email = st.text_input(
                    "Email Address",
                    placeholder="you@example.com",
                    autocomplete="email",
                )
                reset_submitted = st.form_submit_button(
                    "Send Reset Link",
                    use_container_width=True,
                    type="primary",
                )

            if reset_submitted:
                email_clean = (reset_email or "").strip()
                if not email_clean:
                    st.markdown(
                        "<div class='login-error'>"
                        "<span class='login-error-icon'>&#9888;</span>"
                        "Please enter your email address."
                        "</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    try:
                        sb = SupabaseClient()
                        sb.send_password_reset_email(email_clean)
                        st.markdown(
                            "<div class='login-success'>"
                            "&#10003;&nbsp; Password reset email sent. "
                            "Check your inbox and follow the link to set a new password."
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    except Exception as exc:
                        st.markdown(
                            f"<div class='login-error'>"
                            f"<span class='login-error-icon'>&#9888;</span>"
                            f"Could not send reset email: {exc}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

            st.markdown("<div style='margin-top:16px;text-align:center;font-size:13px;color:#6B7280;'>", unsafe_allow_html=True)
            if st.button("← Back to Sign In", key="back_to_login", use_container_width=False):
                st.session_state["show_reset"] = False
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════
        # SIGN IN MODE
        # ══════════════════════════════════════════════════════════════
        else:
            st.markdown(
                "<p class='login-heading'>Sign in to your account</p>"
                "<p class='login-sub'>Enter your credentials to continue.</p>"
                "<hr class='login-divider'>",
                unsafe_allow_html=True,
            )

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

            # Forgot password link (below the form)
            if st.button("Forgot password?", key="goto_reset",
                         help="Send a password reset link to your email"):
                st.session_state["show_reset"] = True
                st.rerun()

            # Handle sign-in submission
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

                st.session_state["user"]    = user
                st.session_state["profile"] = profile
                if session:
                    st.session_state["_new_tokens"] = {
                        "at": session.access_token,
                        "rt": session.refresh_token,
                    }

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
