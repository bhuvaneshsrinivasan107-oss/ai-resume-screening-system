import re
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
    store_reset_code,
    invalidate_reset_code,
    update_user_password,
    create_google_user
)

import email_service


logger = logging.getLogger("auth")


# Lifetime of a password-reset code, in minutes.
RESET_CODE_VALID_MINUTES = 10


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


# ============================================================
# START SESSION (shared by password + Google login)
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
        "login_username",
        "login_password",
        "login_email",
        "google_pending_user",
        "pw_reset_stage",
        "pw_reset_email",
        "pw_reset_notice",
        "rp_email",
        "rp_code",
        "rp_new_password",
        "rp_confirm_password"
    ]:

        if key in st.session_state:

            del st.session_state[key]

    # Also end the Google OIDC session (clears the signed
    # auth cookie) so the next visit starts fresh.
    try:

        st.logout()

        return

    except Exception:

        pass

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

        st.session_state["switch_to_login"] = True

        st.rerun()

    return False


# ============================================================
# FORGOT PASSWORD - HELPERS
# ============================================================

def _clear_reset_state():
    """Remove every password-reset related session key."""

    for key in [
        "pw_reset_stage",
        "pw_reset_email",
        "pw_reset_notice",
        "rp_email",
        "rp_code",
        "rp_new_password",
        "rp_confirm_password"
    ]:

        if key in st.session_state:

            del st.session_state[key]


def _generate_reset_code():
    """
    Cryptographically secure random 6-digit code.
    """

    return f"{secrets.randbelow(1000000):06d}"


def _parse_reset_expiry(expires_raw):
    """
    Parse the stored expiry timestamp.
    Returns None when missing/corrupt.
    """

    if not expires_raw:

        return None

    try:

        return datetime.strptime(
            str(expires_raw),
            "%Y-%m-%d %H:%M:%S"
        )

    except (ValueError, TypeError):

        return None


def _reset_code_is_valid(user):
    """
    Check whether the user holds a usable
    (not used, not expired) reset code.
    """

    if user is None:

        return False

    stored_hash = user.get("reset_code_hash", "")

    if not stored_hash:

        return False

    if user.get("reset_code_used"):

        return False

    expires_at = _parse_reset_expiry(
        user.get("reset_code_expires", "")
    )

    if expires_at is None:

        return False

    if datetime.now() > expires_at:

        return False

    return True


# ============================================================
# FORGOT PASSWORD - STAGE 1: REQUEST CODE
# ============================================================

def _render_reset_request_stage():

    st.markdown("### 🔐 Reset Password")

    st.caption(
        "Enter your registered email address."
    )

    email = st.text_input(
        "📧 Email Address",
        key="rp_email",
        placeholder="Enter your registered email"
    )

    if st.button(
        "Send Reset Code",
        type="primary",
        use_container_width=True,
        key="rp_send_button"
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
            # Uniform service-status notice - shown for
            # ANY submitted address, so it never reveals
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

            # ----------------------------------------
            # Only REGISTERED accounts receive a code.
            # Unregistered addresses are silently
            # ignored - the response below is identical
            # either way (no account enumeration).
            # ----------------------------------------

            user = get_user_by_email(cleaned)

            if user and smtp_ready:

                code = _generate_reset_code()

                expires_at = (
                    datetime.now()
                    + timedelta(
                        minutes=RESET_CODE_VALID_MINUTES
                    )
                ).strftime("%Y-%m-%d %H:%M:%S")

                # Store only the HASH of the code -
                # never the raw code itself.
                store_reset_code(
                    user["id"],
                    hash_password(code),
                    expires_at
                )

                sent, reason = (
                    email_service.send_password_reset_email(
                        user.get("name") or "User",
                        user["email"],
                        code
                    )
                )

                if not sent:

                    # Never expose the reason in the UI -
                    # log it for the administrator only.
                    logger.error(
                        "Password reset email could not be "
                        "sent to a registered account: %s",
                        reason
                    )

            # Same neutral confirmation for every input.
            st.session_state["pw_reset_email"] = cleaned

            st.session_state["pw_reset_notice"] = True

            st.session_state["pw_reset_stage"] = "verify"

            st.rerun()

    _render_back_to_login_button("rp_request_back")


# ============================================================
# FORGOT PASSWORD - STAGE 2: VERIFY CODE
# ============================================================

def _render_reset_verify_stage():

    if st.session_state.pop("pw_reset_notice", False):

        st.info(
            "📧 If an account exists for this email, "
            "a reset code has been sent."
        )

    st.markdown("### 🔑 Verify Reset Code")

    st.caption(
        "Enter the 6-digit code sent to your "
        "registered email."
    )

    code = st.text_input(
        "🔢 Verification Code",
        key="rp_code",
        max_chars=6,
        placeholder="Enter the 6-digit code"
    )

    if st.button(
        "Verify Code",
        type="primary",
        use_container_width=True,
        key="rp_verify_button"
    ):

        cleaned = code.strip()

        user = get_user_by_email(
            st.session_state.get("pw_reset_email", "")
        )

        stored_hash = (
            user.get("reset_code_hash", "")
            if user
            else ""
        )

        if not user or not stored_hash:

            st.error(
                "❌ This reset code is no longer valid."
            )

        elif user.get("reset_code_used"):

            st.error(
                "❌ This reset code is no longer valid."
            )

        else:

            expires_at = _parse_reset_expiry(
                user.get("reset_code_expires", "")
            )

            if expires_at is None or (
                datetime.now() > expires_at
            ):

                st.error(
                    "❌ Reset code has expired. "
                    "Please request a new code."
                )

            elif not cleaned or not check_password(
                cleaned,
                stored_hash
            ):

                st.error(
                    "❌ Invalid reset code. "
                    "Please try again."
                )

            else:

                st.session_state[
                    "pw_reset_stage"
                ] = "new_password"

                st.rerun()

    _render_back_to_login_button("rp_verify_back")


# ============================================================
# FORGOT PASSWORD - STAGE 3: NEW PASSWORD
# ============================================================

def _render_reset_new_password_stage():

    st.markdown("### 🔐 Create New Password")

    st.caption(
        "Choose a strong new password for your account."
    )

    new_password = st.text_input(
        "New Password",
        type="password",
        key="rp_new_password",
        placeholder="Minimum 8 characters"
    )

    confirm_password = st.text_input(
        "Confirm New Password",
        type="password",
        key="rp_confirm_password",
        placeholder="Re-enter your new password"
    )

    if st.button(
        "Reset Password",
        type="primary",
        use_container_width=True,
        key="rp_reset_button"
    ):

        user = get_user_by_email(
            st.session_state.get("pw_reset_email", "")
        )

        # Re-validate the code (it may have been used or
        # expired while this form was open).
        if not _reset_code_is_valid(user):

            st.error(
                "❌ This reset code is no longer valid."
            )

        else:

            new_pw = new_password.strip()

            confirm_pw = confirm_password.strip()

            if len(new_pw) < 8:

                st.error(
                    "❌ Password must contain at least "
                    "8 characters."
                )

            elif new_pw != confirm_pw:

                st.error(
                    "❌ Passwords do not match."
                )

            else:

                # Store only the HASH - plain-text
                # passwords are never persisted.
                update_user_password(
                    user["id"],
                    hash_password(new_pw)
                )

                # One-time usage: invalidate the code so
                # it can never be reused.
                invalidate_reset_code(user["id"])

                st.session_state[
                    "pw_reset_stage"
                ] = "done"

                st.rerun()

    _render_back_to_login_button("rp_new_back")


# ============================================================
# FORGOT PASSWORD - STAGE 4: SUCCESS
# ============================================================

def _render_reset_done_stage():

    st.success(
        "✅ Password reset successfully."
    )

    st.caption(
        "You can now log in with your new password."
    )

    if st.button(
        "Back to Login",
        type="primary",
        use_container_width=True,
        key="rp_done_back"
    ):

        _clear_reset_state()

        st.rerun()


# ============================================================
# FORGOT PASSWORD - FLOW DISPATCHER
# ============================================================

def _render_back_to_login_button(key):

    st.write("")

    if st.button(
        "← Back to Login",
        key=key
    ):

        _clear_reset_state()

        st.rerun()


def _forgot_password_flow():

    stage = st.session_state.get(
        "pw_reset_stage",
        "request"
    )

    if stage == "verify":

        _render_reset_verify_stage()

    elif stage == "new_password":

        _render_reset_new_password_stage()

    elif stage == "done":

        _render_reset_done_stage()

    else:

        _render_reset_request_stage()


# ============================================================
# CONTINUE WITH GOOGLE (Streamlit built-in OIDC)
# ============================================================

_GOOGLE_UNCONFIGURED_MESSAGE = (
    "⚠️ Google login is currently unavailable.\n\n"
    "Please configure Google OAuth credentials in:\n"
    "`.streamlit/secrets.toml`"
)

# Placeholder values mean the [auth] configuration has not
# been filled in yet - treat them as "not configured".
_AUTH_PLACEHOLDERS = {
    "",
    "your_google_client_id",
    "your_google_client_secret",
    "change_me",
    "change-me"
}


def _google_auth_configured():
    """
    True only when the [auth] section in
    .streamlit/secrets.toml contains real-looking
    credentials. Secrets are never displayed anywhere.
    """

    try:

        auth_config = st.secrets.get("auth", None)

        if auth_config is None:

            return False

        client_id = str(
            auth_config.get("client_id", "") or ""
        ).strip().lower()

        client_secret = str(
            auth_config.get("client_secret", "") or ""
        ).strip().lower()

    except Exception:

        return False

    if client_id in _AUTH_PLACEHOLDERS:

        return False

    if client_secret in _AUTH_PLACEHOLDERS:

        return False

    return bool(client_id) and bool(client_secret)


def _get_google_oidc_user():
    """
    Return the VERIFIED Google identity from Streamlit's
    built-in OIDC login, or None.

    The email comes from Google's ID token via st.user -
    never from manual user input.
    """

    try:

        if not st.user.is_logged_in:

            return None

        email = str(st.user.email or "").strip().lower()

        if not email:

            return None

        return {
            "email": email,
            "name": str(st.user.name or "").strip()
        }

    except Exception:

        return None


def _render_google_button():
    """
    Render the REAL 'Continue with Google' Streamlit
    button. Clicking it redirects the browser to Google's
    official sign-in page via st.login() - users NEVER
    enter their Google password inside this application.
    """

    if st.button(
        "🔵 Continue with Google",
        use_container_width=True,
        key="google_login_button"
    ):

        if not _google_auth_configured():

            st.warning(
                _GOOGLE_UNCONFIGURED_MESSAGE
            )

            return

        try:

            # Redirects to Google's authentication page;
            # Google then redirects back to /oauth2callback.
            st.login()

        except Exception:

            st.warning(
                _GOOGLE_UNCONFIGURED_MESSAGE
            )


def _google_account_setup(pending_user):
    """
    Explicit account-type selection for a NEW Google user.

    Google-authenticated users NEVER automatically become
    recruiters - they must explicitly choose their role.
    """

    st.markdown("### Create Account")

    st.info(
        f"Continue as **{pending_user['email']}** "
        "(verified by Google)"
    )

    st.caption(
        "No account exists for this Google email yet. "
        "Please choose your account type explicitly - "
        "roles are never assigned automatically."
    )

    account_type = st.radio(
        "Continue with:",
        [
            "👤 Candidate",
            "👔 Recruiter"
        ],
        horizontal=True,
        key="google_account_type_radio"
    )

    st.write("")

    if st.button(
        "Continue",
        type="primary",
        use_container_width=True,
        key="google_create_account_button"
    ):

        role = (
            "recruiter"
            if account_type == "👔 Recruiter"
            else "candidate"
        )

        name = (
            pending_user.get("name")
            or pending_user["email"].split("@")[0]
        )

        # Creates the account only if it does not
        # already exist (no duplicates).
        create_google_user(
            name,
            pending_user["email"],
            role
        )

        user = get_user_by_email(
            pending_user["email"]
        )

        if user is not None:

            if "google_pending_user" in st.session_state:

                del st.session_state["google_pending_user"]

            _start_session(user)

            st.success(
                "✅ Account created successfully!"
            )

            st.rerun()

        else:

            st.error(
                "❌ Account could not be created. "
                "Please try again."
            )

    if st.button(
        "Cancel",
        key="google_cancel_button"
    ):

        if "google_pending_user" in st.session_state:

            del st.session_state["google_pending_user"]

        # End the Google OIDC session so the user returns
        # to the normal login page instead of looping back
        # into this account-type selection.
        try:

            st.logout()

            return

        except Exception:

            pass

        st.rerun()


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
    # After account creation, switch back to the login form.
    # This must happen BEFORE the mode radio widget renders.
    # --------------------------------------------------------

    if st.session_state.pop(
        "switch_to_login",
        False
    ):

        st.session_state["auth_mode_radio"] = "🔐 Login"

    # --------------------------------------------------------
    # GOOGLE OIDC SIGN-IN RESULT
    # (Streamlit's built-in mechanism - after Google redirects
    #  back to /oauth2callback, st.user holds the VERIFIED
    #  Google email)
    # --------------------------------------------------------

    google_user = _get_google_oidc_user()

    if google_user is not None:

        existing_google_account = get_user_by_email(
            google_user["email"]
        )

        if existing_google_account is not None:

            # Log into the EXISTING account - its stored
            # role decides which portal opens. No
            # duplicates are ever created.
            _start_session(existing_google_account)

            st.success(
                "✅ Login successful!"
            )

            return True

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

        .login-or-divider {
            text-align: center;
            color: #6b7280;
            font-size: 13px;
            margin: 8px 0;
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

        # ------------------------------------------------
        # LOGIN / CREATE ACCOUNT TOGGLE
        # ------------------------------------------------

        auth_mode = st.radio(
            "Choose an Option",
            [
                "🔐 Login",
                "📝 Create Account"
            ],
            horizontal=True,
            key="auth_mode_radio"
        )

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

        if auth_mode == "📝 Create Account":

            _register_form()

            return False

        # ------------------------------------------------
        # GOOGLE: NEW USER MUST CHOOSE ACCOUNT TYPE
        # (explicit role selection - never automatic)
        # ------------------------------------------------

        if google_user is not None:

            _google_account_setup(google_user)

            return False

        st.markdown("### 🔐 Login")

        # ------------------------------------------------
        # LOGIN TYPE
        # ------------------------------------------------

        account_type = st.radio(
            "Select Login Type",
            [
                "👔 Recruiter",
                "👤 Candidate"
            ],
            horizontal=True
        )

        if account_type == "👔 Recruiter":
            selected_role = "recruiter"
        else:
            selected_role = "candidate"

        # ------------------------------------------------
        # IDENTIFIER
        # ------------------------------------------------

        if selected_role == "recruiter":

            identifier = st.text_input(
                "👤 Username or Email",
                key="login_username",
                placeholder="Enter your username or email"
            )

        else:

            identifier = st.text_input(
                "📧 Email or Username",
                key="login_email",
                placeholder="Enter your email address or username"
            )

        is_email = "@" in identifier.strip()

        # ------------------------------------------------
        # PASSWORD
        # ------------------------------------------------

        password = st.text_input(
            "🔑 Password",
            type="password",
            key="login_password",
            placeholder="Enter your password"
        )

        st.write("")

        # ------------------------------------------------
        # LOGIN BUTTON
        # ------------------------------------------------

        login_clicked = st.button(
            "🚀 Login",
            type="primary",
            use_container_width=True
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

                st.error(
                    "Invalid username or password."
                )

                return False

            # ----------------------------------------
            # LOGIN SUCCESS
            # ----------------------------------------

            _start_session(user)

            st.success(
                "✅ Login successful!"
            )

            st.rerun()

        # ------------------------------------------------
        # CONTINUE WITH GOOGLE
        # (always visible; shows a friendly warning if
        #  OAuth credentials are not configured yet)
        # ------------------------------------------------

        st.markdown(
            '<div class="login-or-divider">'
            "──────── OR ────────"
            "</div>",
            unsafe_allow_html=True
        )

        _render_google_button()

        # ------------------------------------------------
        # FORGOT PASSWORD
        # ------------------------------------------------

        col_left, col_center, col_right = st.columns(
            [1, 2, 1]
        )

        with col_center:

            if st.button(
                "Forgot Password?",
                key="forgot_password_button"
            ):

                st.session_state[
                    "pw_reset_stage"
                ] = "request"

                st.rerun()

    return False
