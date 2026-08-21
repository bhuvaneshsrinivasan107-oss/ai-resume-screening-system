"""
Authentication module for the AI Resume Screening
and Candidate Ranking System.

Handles:
- Recruiter and Candidate login (email/username + password)
- Account creation
- End-to-end Forgot Password (secure, single-use,
  time-limited reset LINKS sent by email)

Everything runs inside the SAME Streamlit application -
there is no second app and no second server.

Passwords are stored as secure hashes only (PBKDF2),
never as plain text. Reset tokens are stored as hashes
only and expire after 30 minutes.
"""

import os
import re
import hashlib
import secrets
import logging
from datetime import datetime, timedelta

import streamlit as st

from database import (
    get_user,
    get_user_by_email,
    check_password,
    hash_password,
    register_user,
    username_exists,
    email_exists,
    update_user_password,
    create_password_reset_token,
    get_password_reset_token,
    mark_password_reset_token_used
)

import email_service


logger = logging.getLogger("auth")


# Lifetime of a password-reset link, in minutes.
RESET_LINK_VALID_MINUTES = 30


# ============================================================
# INITIALIZE SESSION
# ============================================================

def initialize_session():

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if "username" not in st.session_state:
        st.session_state.username = ""

    if "role" not in st.session_state:
        st.session_state.role = ""

    if "name" not in st.session_state:
        st.session_state.name = ""

    if "email" not in st.session_state:
        st.session_state.email = ""

    # Which sub-view of the auth page is active:
    # login | register | forgot_request | forgot_sent |
    # reset_new_password | reset_invalid | reset_done
    if "auth_view" not in st.session_state:
        st.session_state.auth_view = "login"


# ============================================================
# START SESSION (shared by all login methods)
# ============================================================

def _start_session(user):

    st.session_state.authenticated = True

    st.session_state.username = user["username"]

    st.session_state.role = user["role"]

    st.session_state.name = user["name"]

    st.session_state.email = user["email"]


# ============================================================
# LOGOUT
# ============================================================

def logout():

    # Remove all authentication-related session variables
    for key in [
        "authenticated",
        "username",
        "role",
        "name",
        "email",
        "recruiter_login_identifier",
        "recruiter_login_password",
        "candidate_login_identifier",
        "candidate_login_password",
        "reset_token",
        "reset_user_role",
        "pw_link_reason",
        "rp_show_password"
    ]:

        if key in st.session_state:

            del st.session_state[key]

    # Always land back on the normal login form.
    st.session_state["auth_view"] = "login"

    st.rerun()


# ============================================================
# AUTHENTICATE USER
# ============================================================

def authenticate_user(
    identifier,
    password,
    role,
    is_email
):

    # Find the user record
    if role == "recruiter":

        # Recruiters may log in with username OR email
        if is_email:

            user = get_user_by_email(identifier)

        else:

            user = get_user(identifier)

    elif is_email:

        user = get_user_by_email(identifier)

    else:

        user = get_user(identifier)

    if user is None:

        return None, "❌ Account not found."

    if user["role"] != role:

        return None, (
            "❌ Incorrect account type. "
            f"'{identifier}' is registered as a "
            f"{user['role'].title()} account."
        )

    # Verify password (hash-aware, with legacy fallback)
    if not check_password(password, user["password"]):

        if password != user["password"]:

            return None, "❌ Incorrect password."

    return user, ""


# ============================================================
# CREATE ACCOUNT FORM
# ============================================================

def _register_form():
    """Registration form for new recruiter/candidate accounts."""

    st.markdown("### 📝 Create Account")

    st.caption(
        "Create a new recruiter or candidate account. "
        "Passwords are stored as secure hashes only."
    )

    # ------------------------------------------------
    # FORM FIELDS
    # ------------------------------------------------

    name = st.text_input(
        "👤 Full Name",
        key="reg_name",
        placeholder="Enter your full name"
    )

    email = st.text_input(
        "📧 Email Address",
        key="reg_email",
        placeholder="Enter your email address"
    )

    username = st.text_input(
        "👤 Username",
        key="reg_username",
        placeholder="Choose a username"
    )

    password = st.text_input(
        "🔑 Password",
        type="password",
        key="reg_password",
        placeholder="Minimum 6 characters"
    )

    confirm_password = st.text_input(
        "🔑 Confirm Password",
        type="password",
        key="reg_confirm_password",
        placeholder="Re-enter your password"
    )

    account_type = st.radio(
        "Account Type",
        [
            "👔 Recruiter",
            "👤 Candidate"
        ],
        horizontal=True,
        key="reg_account_type"
    )

    st.write("")

    # ------------------------------------------------
    # CREATE ACCOUNT BUTTON
    # ------------------------------------------------

    if st.button(
        "Create Account",
        type="primary",
        use_container_width=True,
        key="reg_submit_button"
    ):

        name = name.strip()

        email = email.strip().lower()

        username = username.strip().lower()

        password = password.strip()

        # ----------------------------------------
        # VALIDATION
        # ----------------------------------------

        if not all(
            [name, email, username, password, confirm_password]
        ):

            st.error(
                "❌ All fields are required."
            )

            return False

        if not re.match(
            r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
            email
        ):

            st.error(
                "❌ Please enter a valid email address."
            )

            return False

        if username_exists(username):

            st.error(
                "❌ This username is already taken. "
                "Please choose another."
            )

            return False

        if email_exists(email):

            st.error(
                "❌ An account with this email "
                "already exists."
            )

            return False

        if len(password) < 6:

            st.error(
                "❌ Password must be at least "
                "6 characters long."
            )

            return False

        if password != confirm_password.strip():

            st.error(
                "❌ Passwords do not match."
            )

            return False

        # ----------------------------------------
        # CREATE THE ACCOUNT (password is hashed
        # inside register_user - never stored
        # as plain text)
        # ----------------------------------------

        role = (
            "recruiter"
            if account_type == "👔 Recruiter"
            else "candidate"
        )

        register_user(
            username,
            password,
            name,
            email,
            role
        )

        st.session_state["account_created"] = True

        st.session_state["auth_view"] = "login"

        st.rerun()

    # ------------------------------------------------
    # BACK TO LOGIN
    # ------------------------------------------------

    st.write("")

    if st.button(
        "← Back to Login",
        key="reg_back_to_login"
    ):

        st.session_state["auth_view"] = "login"

        st.rerun()

    return False


# ============================================================
# FORGOT PASSWORD - HELPERS
# ============================================================

def _clear_reset_state():
    """Remove every password-reset related session key."""

    for key in [
        "reset_token",
        "reset_user_role",
        "pw_link_reason",
        "rp_show_password",
        "recruiter_forgot_email",
        "candidate_forgot_email",
        "recruiter_new_password",
        "recruiter_confirm_password",
        "candidate_new_password",
        "candidate_confirm_password"
    ]:

        if key in st.session_state:

            del st.session_state[key]


def _hash_reset_token(token):
    """
    SHA-256 hash of the raw reset token.

    Only this hash is stored in the database - the raw
    token exists solely inside the emailed link.
    """

    return hashlib.sha256(
        str(token).encode("utf-8")
    ).hexdigest()


def _get_app_base_url():
    """
    Build the application base URL dynamically so reset
    links work locally AND after deployment.

    Priority:
      1. APP_BASE_URL override (env var or secret)
      2. Host header of the CURRENT request
      3. http://localhost:8501 fallback
    """

    override = ""

    try:

        override = str(
            st.secrets.get("APP_BASE_URL", "") or ""
        ).strip().rstrip("/")

    except Exception:

        override = ""

    if not override:

        override = str(
            os.environ.get("APP_BASE_URL", "") or ""
        ).strip().rstrip("/")

    if override:

        return override

    # Derive from the CURRENT request - works for any
    # host/port the app is actually served on.
    try:

        headers = st.context.headers

        host = (
            headers.get("Host")
            or headers.get("host")
            or ""
        )

        if host:

            proto = (
                headers.get("X-Forwarded-Proto")
                or headers.get("x-forwarded-proto")
                or ""
            ).lower()

            if not proto:

                proto = (
                    "https"
                    if "localhost" not in host
                    and "127.0.0.1" not in host
                    else "http"
                )

            return f"{proto}://{host}"

    except Exception:

        pass

    return "http://localhost:8501"


def _handle_reset_token_param():
    """
    Detect ?reset_token=... in the URL (opened from the
    reset email), validate it ONCE, store the outcome in
    session state and clean the address bar.

    Runs on every authentication() call BEFORE anything
    renders, so the reset screen always opens - even
    after Streamlit reruns.
    """

    try:

        token = str(
            st.query_params.get("reset_token", "") or ""
        ).strip()

    except Exception:

        token = ""

    if not token:

        return

    result = get_password_reset_token(
        _hash_reset_token(token)
    )

    if result["status"] == "valid":

        st.session_state["reset_token"] = token

        st.session_state["reset_user_role"] = (
            result["user"].get("role", "candidate")
        )

        # Back to Login must open the portal that owns
        # this account.
        st.session_state["login_role"] = (
            "👔 Recruiter"
            if result["user"].get("role") == "recruiter"
            else "👤 Candidate"
        )

        st.session_state["auth_view"] = "reset_new_password"

    else:

        st.session_state["pw_link_reason"] = (
            result["status"]
        )

        st.session_state["auth_view"] = "reset_invalid"

    try:

        st.query_params.clear()

    except Exception:

        pass

    st.rerun()


# ============================================================
# FORGOT PASSWORD - STAGE 1: REQUEST RESET LINK
# ============================================================

def _render_forgot_request_stage(selected_role):

    if selected_role == "recruiter":

        st.markdown("### 🤖 AI Recruiter")

        st.markdown("#### Forgot Recruiter Password")

        email_key = "recruiter_forgot_email"

    else:

        st.markdown("### 👤 Candidate Portal")

        st.markdown("#### Forgot Candidate Password")

        email_key = "candidate_forgot_email"

    st.caption(
        "Enter your registered email address and we "
        "will send you a secure reset link."
    )

    email = st.text_input(
        "📧 Registered Email",
        key=email_key,
        placeholder="Enter your registered email"
    )

    if st.button(
        "📧 Send Reset Link",
        type="primary",
        use_container_width=True,
        key=f"{selected_role}_send_reset_button"
    ):

        cleaned = email.strip().lower()

        if not cleaned:

            st.error(
                "❌ Please enter your email address."
            )

        elif not re.match(
            r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
            cleaned
        ):

            st.error(
                "❌ Please enter a valid email address."
            )

        else:

            # ----------------------------------------
            # Service-status notice - shown for ANY
            # submitted address, so it never reveals
            # whether a particular email is registered.
            # ----------------------------------------

            smtp_ready = (
                email_service.email_configured()
            )

            if not smtp_ready:

                st.warning(
                    "⚠️ The email service is currently "
                    "not available. Please contact the "
                    "administrator."
                )

            db_error = False

            user = None

            if smtp_ready:

                try:

                    user = get_user_by_email(cleaned)

                except Exception:

                    logger.exception(
                        "Database error during "
                        "password-reset lookup"
                    )

                    db_error = True

            if db_error:

                st.error(
                    "❌ Something went wrong. "
                    "Please try again later."
                )

            else:

                # Only an account belonging to THIS portal
                # (recruiter/candidate) receives a link.
                if (
                    user is not None
                    and user.get("role") != selected_role
                ):

                    user = None

                if user is not None:

                    try:

                        token = secrets.token_urlsafe(32)

                        expires_at = (
                            datetime.now()
                            + timedelta(
                                minutes=RESET_LINK_VALID_MINUTES
                            )
                        ).strftime("%Y-%m-%d %H:%M:%S")

                        # Store only the HASH of the token -
                        # never the raw token itself.
                        stored = create_password_reset_token(
                            user["id"],
                            user["email"],
                            _hash_reset_token(token),
                            expires_at
                        )

                        if stored is not None:

                            reset_link = (
                                f"{_get_app_base_url()}"
                                f"/?reset_token={token}"
                            )

                            sent, reason = (
                                email_service.send_password_reset_email(
                                    user.get("name") or "User",
                                    user["email"],
                                    reset_link
                                )
                            )

                            if not sent:

                                # Never expose the reason in
                                # the UI - log it for the
                                # administrator only.
                                logger.error(
                                    "Password reset email could "
                                    "not be sent to a registered "
                                    "account: %s",
                                    reason
                                )

                    except Exception:

                        logger.exception(
                            "Failed to create password "
                            "reset token"
                        )

                # Same neutral confirmation for every input
                # (no account enumeration).
                st.session_state["auth_view"] = "forgot_sent"

                st.rerun()

    _render_back_to_login_button(
        f"{selected_role}_forgot_back"
    )


# ============================================================
# FORGOT PASSWORD - STAGE 2: LINK SENT
# ============================================================

def _render_forgot_sent_stage():

    st.markdown("### 📧 Check Your Email")

    st.info(
        "📧 If an account exists for this email, "
        "a password reset link has been sent."
    )

    st.caption(
        f"The link expires in {RESET_LINK_VALID_MINUTES} "
        "minutes and can be used only once. Remember to "
        "check your spam folder."
    )

    _render_back_to_login_button("forgot_sent_back")


# ============================================================
# FORGOT PASSWORD - STAGE 3: NEW PASSWORD (FROM LINK)
# ============================================================

def _render_reset_new_password_stage():

    role_prefix = st.session_state.get(
        "reset_user_role",
        "candidate"
    )

    st.markdown("### 🔐 Reset Your Password")

    st.caption(
        "Choose a strong new password for your account."
    )

    show_password = st.checkbox(
        "👁 Show passwords",
        key="rp_show_password"
    )

    pw_type = "default" if show_password else "password"

    new_password = st.text_input(
        "New Password",
        type=pw_type,
        key=f"{role_prefix}_new_password",
        placeholder="Minimum 6 characters"
    )

    confirm_password = st.text_input(
        "Confirm New Password",
        type=pw_type,
        key=f"{role_prefix}_confirm_password",
        placeholder="Re-enter your new password"
    )

    if st.button(
        "🔐 Reset Password",
        type="primary",
        use_container_width=True,
        key=f"{role_prefix}_reset_submit_button"
    ):

        token = st.session_state.get("reset_token", "")

        # Re-validate the token - it may have been used
        # or expired while this form was open.
        result = (
            get_password_reset_token(
                _hash_reset_token(token)
            )
            if token
            else {"status": "invalid"}
        )

        if result["status"] != "valid":

            st.session_state["pw_link_reason"] = (
                result["status"]
            )

            st.session_state["auth_view"] = "reset_invalid"

            st.rerun()

        new_pw = new_password.strip()

        confirm_pw = confirm_password.strip()

        if not new_pw:

            st.error(
                "❌ Please enter a new password."
            )

        elif len(new_pw) < 6:

            st.error(
                "❌ Password must be at least "
                "6 characters long."
            )

        elif new_pw != confirm_pw:

            st.error(
                "❌ Passwords do not match."
            )

        else:

            try:

                # Store only the HASH - plain-text
                # passwords are never persisted.
                update_user_password(
                    result["user"]["id"],
                    hash_password(new_pw)
                )

                # One-time usage: mark the token used so
                # it can never be reused.
                mark_password_reset_token_used(
                    result["token_id"]
                )

                st.session_state["auth_view"] = "reset_done"

                st.rerun()

            except Exception:

                logger.exception(
                    "Failed to update password"
                )

                st.error(
                    "❌ Something went wrong while updating "
                    "your password. Please try again."
                )

    _render_back_to_login_button(
        f"{role_prefix}_reset_back"
    )


# ============================================================
# FORGOT PASSWORD - STAGE 4: INVALID LINK
# ============================================================

def _render_reset_invalid_stage():

    reason = st.session_state.get(
        "pw_link_reason",
        "invalid"
    )

    messages = {
        "expired": (
            "❌ This reset link has expired. "
            "Please request a new one."
        ),
        "used": (
            "❌ This reset link has already been used."
        ),
    }

    st.error(
        messages.get(
            reason,
            "❌ This reset link is invalid or has expired."
        )
    )

    st.caption(
        "For security reasons, reset links stop working "
        "after 30 minutes or after a single use."
    )

    _render_back_to_login_button("reset_invalid_back")


# ============================================================
# FORGOT PASSWORD - STAGE 5: SUCCESS
# ============================================================

def _render_reset_done_stage():

    st.success(
        "✅ Password reset successfully."
    )

    st.caption(
        "You can now log in using your new password."
    )

    if st.button(
        "Back to Login",
        type="primary",
        use_container_width=True,
        key="reset_done_back"
    ):

        _clear_reset_state()

        st.session_state["auth_view"] = "login"

        st.rerun()


# ============================================================
# BACK TO LOGIN (shared by every sub-view)
# ============================================================

def _render_back_to_login_button(key):

    st.write("")

    if st.button(
        "← Back to Login",
        key=key
    ):

        _clear_reset_state()

        # login_role (the portal radio) is untouched, so
        # the user returns to the SAME portal they came
        # from - recruiter stays recruiter, candidate
        # stays candidate.
        st.session_state["auth_view"] = "login"

        st.rerun()


# ============================================================
# AUTH SUB-VIEW DISPATCHER
# ============================================================

def _render_auth_subview(selected_role):
    """
    Render whichever sub-view is active.

    Returns True when a sub-view rendered (caller stops),
    False when the normal login form should render.
    """

    view = st.session_state.get("auth_view", "login")

    if view == "forgot_request":

        _render_forgot_request_stage(selected_role)

        return True

    if view == "forgot_sent":

        _render_forgot_sent_stage()

        return True

    if view == "reset_new_password":

        _render_reset_new_password_stage()

        return True

    if view == "reset_invalid":

        _render_reset_invalid_stage()

        return True

    if view == "reset_done":

        _render_reset_done_stage()

        return True

    if view == "register":

        _register_form()

        return True

    return False


# ============================================================
# LOGIN PAGE
# ============================================================

def authentication():

    initialize_session()

    # --------------------------------------------------------
    # Already logged in
    # --------------------------------------------------------

    if st.session_state.authenticated:
        return True

    # --------------------------------------------------------
    # PASSWORD RESET LINK (?reset_token=...) - checked
    # before anything renders so the reset screen always
    # opens, regardless of the previous view.
    # --------------------------------------------------------

    _handle_reset_token_param()

    # --------------------------------------------------------
    # PAGE STYLE
    # --------------------------------------------------------

    st.markdown(
        """
        <style>

        .login-title {
            text-align: center;
            font-size: 38px;
            font-weight: 800;
            margin-top: 40px;
        }

        .login-subtitle {
            text-align: center;
            color: #6b7280;
            font-size: 17px;
            margin-bottom: 30px;
        }

        </style>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    st.markdown(
        """
        <div class="login-title">
            🔐 AI Recruitment Portal
        </div>

        <div class="login-subtitle">
            AI Resume Screening & Candidate Ranking System
        </div>
        """,
        unsafe_allow_html=True
    )

    # --------------------------------------------------------
    # LOGIN FORM
    # --------------------------------------------------------

    left, center, right = st.columns(
        [1, 2, 1]
    )

    with center:

        # Success message shown after account creation
        if st.session_state.pop(
            "account_created",
            False
        ):

            st.success(
                "✅ Account created successfully! "
                "Please log in with your new "
                "credentials."
            )

        # ------------------------------------------------
        # PORTAL SELECTOR (persisted as login_role)
        # ------------------------------------------------

        account_type = st.radio(
            "Select Login Type",
            [
                "👔 Recruiter",
                "👤 Candidate"
            ],
            horizontal=True,
            key="login_role"
        )

        if account_type == "👔 Recruiter":
            selected_role = "recruiter"
        else:
            selected_role = "candidate"

        # ------------------------------------------------
        # SUB-VIEWS (forgot password / reset / register)
        # ------------------------------------------------

        if _render_auth_subview(selected_role):
            return False

        # ------------------------------------------------
        # ROLE-SPECIFIC LOGIN HEADING
        # ------------------------------------------------

        if selected_role == "recruiter":

            st.markdown("### 🤖 AI Recruiter")

            st.markdown("#### Recruiter Login")

            identifier = st.text_input(
                "👤 Username or Email",
                key="recruiter_login_identifier",
                placeholder="Enter your username or email"
            )

        else:

            st.markdown("### 👤 Candidate Portal")

            st.markdown("#### Candidate Login")

            identifier = st.text_input(
                "📧 Email or Username",
                key="candidate_login_identifier",
                placeholder="Enter your email address or username"
            )

        is_email = "@" in identifier.strip()

        # ------------------------------------------------
        # PASSWORD
        # ------------------------------------------------

        password = st.text_input(
            "🔑 Password",
            type="password",
            key=f"{selected_role}_login_password",
            placeholder="Enter your password"
        )

        st.write("")

        # ------------------------------------------------
        # FORGOT PASSWORD (BEFORE the Login button)
        # ------------------------------------------------

        col_left, col_center, col_right = st.columns(
            [1, 2, 1]
        )

        with col_center:

            if st.button(
                "Forgot Password?",
                key=f"{selected_role}_forgot_password_button"
            ):

                st.session_state["auth_view"] = "forgot_request"

                st.rerun()

        st.write("")

        # ------------------------------------------------
        # LOGIN BUTTON
        # ------------------------------------------------

        login_clicked = st.button(
            "🚀 Login",
            type="primary",
            use_container_width=True,
            key=f"{selected_role}_login_button"
        )

        if login_clicked:

            identifier = identifier.strip().lower()

            password = password.strip()

            if not identifier:

                st.error(
                    "❌ Please enter your "
                    + (
                        "username or email."
                        if selected_role == "recruiter"
                        else "email or username."
                    )
                )

                return False

            if not password:

                st.error(
                    "❌ Please enter your password."
                )

                return False

            user, error = authenticate_user(
                identifier,
                password,
                selected_role,
                is_email
            )

            if user is None:

                st.error(error or "Invalid username or password.")

                return False

            # ----------------------------------------
            # LOGIN SUCCESS
            # ----------------------------------------

            _start_session(user)

            st.success(
                "✅ Login successful!"
            )

            st.rerun()

        st.write("")

        # ------------------------------------------------
        # CREATE ACCOUNT
        # ------------------------------------------------

        if st.button(
            "📝 Create Account",
            use_container_width=True,
            key=f"{selected_role}_create_account_button"
        ):

            st.session_state["auth_view"] = "register"

            st.rerun()

    return False
