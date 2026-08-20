import re

import streamlit as st

from database import (
    get_user,
    get_user_by_email,
    check_password,
    register_user,
    username_exists,
    email_exists
)


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
        "login_email"
    ]:

        if key in st.session_state:

            del st.session_state[key]

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
                "👤 Username",
                key="login_username",
                placeholder="Enter your username"
            )

            is_email = False

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
                        "username."
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

            st.session_state.authenticated = True

            st.session_state.username = user["username"]

            st.session_state.role = user["role"]

            st.session_state.name = user["name"]

            st.session_state.email = user["email"]

            st.success(
                "✅ Login successful!"
            )

            st.rerun()

    return False
