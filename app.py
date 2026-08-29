# ============================================================
# app.py
# AI Resume Screening & Candidate Ranking System
# Single Streamlit Application
# ============================================================

import os
import logging
from datetime import datetime

import pandas as pd
import streamlit as st

# Log to the console so technical errors are visible in Render
# Logs without confusing end users.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ============================================================
# EXISTING PROJECT MODULES
# ============================================================

from auth import authentication, logout

from resume_parser import (
    extract_text,
    extract_resume_with_result,
    extract_candidate_details,
    extract_skills
)

from ranking_engine import rank_candidate

from database import (
    create_database,
    check_database,
    add_candidate,
    get_candidates,
    get_candidate,
    update_candidate_status,
    delete_candidate,
    clear_all_candidates
)

from gemini_service import ask_gemini

# ============================================================
# EXTRA FEATURES (reusable modules - NOT separate
# Streamlit apps; all rendered inside this app)
# ============================================================

import interview_scheduler
import email_service
import ai_interview
import resume_improvement
import multilingual_parser

logger = logging.getLogger("app")

df = get_candidates()

# ============================================================
# GEMINI
# ============================================================

try:
    from google import genai
except ImportError:
    genai = None


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Resume Screening & Candidate Ranking",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

create_database()


# ============================================================
# DATABASE CONNECTION CHECK
# (safe - technical details are logged to the terminal only,
#  normal users see a friendly message)
# ============================================================

db_logger = logging.getLogger("app.database")


def verify_database_connection():

    result = check_database()

    if not result["ok"]:

        db_logger.error(
            "Database check failed: %s",
            "; ".join(result["issues"])
        )

        st.error(
            "⚠️ The application could not connect to its "
            "database. Please try again later or contact "
            "the administrator."
        )

        st.stop()


verify_database_connection()


# ============================================================
# CUSTOM CSS
# ============================================================

def apply_custom_css():

    st.markdown(
        """
        <style>

        .main {
            background-color: #f7f9fc;
        }

        /* ----------------------------------------------------
           Modern professional background (AI Recruiter theme)
           Soft gradient + gentle abstract glow shapes.
           Visual styling only - no logic changes.
        ---------------------------------------------------- */

        [data-testid="stAppViewContainer"] {
            background:
                linear-gradient(
                    135deg,
                    #f4f7fd 0%,
                    #eaeff9 45%,
                    #eef3fa 100%
                );
        }

        [data-testid="stAppViewContainer"]::before {
            content: "";
            position: fixed;
            top: -18%;
            right: -12%;
            width: 55vw;
            height: 55vw;
            max-width: 720px;
            max-height: 720px;
            background: radial-gradient(
                circle at center,
                rgba(88, 118, 208, 0.14) 0%,
                rgba(88, 118, 208, 0.0) 70%
            );
            pointer-events: none;
            z-index: 0;
        }

        [data-testid="stAppViewContainer"]::after {
            content: "";
            position: fixed;
            bottom: -22%;
            left: -14%;
            width: 60vw;
            height: 60vw;
            max-width: 780px;
            max-height: 780px;
            background: radial-gradient(
                circle at center,
                rgba(64, 156, 196, 0.13) 0%,
                rgba(64, 156, 196, 0.0) 70%
            );
            pointer-events: none;
            z-index: 0;
        }

        [data-testid="stAppViewContainer"] .block-container {
            position: relative;
            z-index: 1;
        }

        [data-testid="stSidebar"] {
            background:
                linear-gradient(
                    180deg,
                    #ffffff 0%,
                    #f1f5fc 100%
                );
        }

        [data-testid="stSidebar"] .block-container {
            position: relative;
            z-index: 1;
        }

        /* Soft glass-style surface for content cards */
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.88);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            border: 1px solid rgba(229, 233, 240, 0.9);
        }

        .metric-card {
            background: rgba(255, 255, 255, 0.88);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
        }

        .info-box {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
        }

        .main-header {
            font-size: 34px;
            font-weight: 800;
            color: #172033;
            margin-bottom: 5px;
        }

        .main-title {
            font-size: 30px;
            font-weight: 800;
            color: #172033;
            margin-bottom: 5px;
        }

        .main-subtitle {
            color: #687386;
            font-size: 16px;
            margin-bottom: 25px;
        }

        /* Native Streamlit metric cards */
        [data-testid="stMetric"] {
            background: white;
            padding: 18px;
            border-radius: 14px;
            border: 1px solid #e5e9f0;
            box-shadow: 0 3px 12px rgba(0,0,0,0.04);
        }

        [data-testid="stMetricLabel"] {
            color: #697586;
            font-size: 14px;
        }

        [data-testid="stMetricValue"] {
            font-size: 30px;
            font-weight: 800;
            color: #172033;
        }

        .metric-card {
            background: white;
            padding: 20px;
            border-radius: 15px;
            border: 1px solid #e5e9f0;
            box-shadow: 0 3px 12px rgba(0,0,0,0.04);
            text-align: center;
        }

        .metric-title {
            color: #697586;
            font-size: 14px;
        }

        .metric-number {
            font-size: 30px;
            font-weight: 800;
            color: #172033;
        }

        .info-box {
            background: white;
            padding: 20px;
            border-radius: 15px;
            border: 1px solid #e5e9f0;
            margin-bottom: 20px;
        }

        </style>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# GEMINI CLIENT
# ============================================================

def get_gemini_client():

    if genai is None:
        return None, (
            "Gemini package is not installed. "
            "Run: pip install google-genai"
        )

    api_key = None

    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        pass

    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return None, (
            "Gemini API key is not configured. "
            "Add GEMINI_API_KEY to .streamlit/secrets.toml."
        )

    try:
        client = genai.Client(
            api_key=api_key
        )

        return client, None

    except Exception as e:

        return None, str(e)


# ============================================================
# GEMINI AI RESUME ANALYSIS
# ============================================================

def ai_resume_analysis(
    resume_text,
    job_description
):

    client, error = get_gemini_client()

    if error:

        st.error(
            f"Gemini configuration error: {error}"
        )

        return

    prompt = f"""
You are an expert AI recruitment assistant.

Analyze the candidate resume against the job description.

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{resume_text}

Provide a professional recruitment analysis with the following sections:

1. Overall Candidate Suitability
2. Match Percentage Estimate
3. Key Strengths
4. Matching Skills
5. Missing or Weak Skills
6. Relevant Experience
7. Education Relevance
8. Potential Concerns
9. Interview Recommendation
10. Resume Improvement Suggestions

Important:
- Do not invent information.
- Use only information present in the resume.
- Clearly mention when information is unavailable.
- Keep the analysis concise and professional.
"""

    try:

        with st.spinner(
            "🤖 Gemini is analyzing the resume..."
        ):

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

        if response and response.text:

            st.markdown(
                "### 🤖 Gemini AI Resume Analysis"
            )

            st.markdown(
                response.text
            )

        else:

            st.warning(
                "Gemini returned an empty response."
            )

    except Exception as e:

        st.error(
            f"Gemini analysis failed: {e}"
        )


# ============================================================
# SIDEBAR
# ============================================================

def clean_display_name(name):
    """Remove a leading 'Demo' word from seeded account names.

    Only affects the visible label - the stored database
    value (used for login) is left untouched.
    """

    if not name:
        return name

    name = str(name).strip()

    for prefix in ("Demo ", "demo "):

        if name.startswith(prefix):

            cleaned = name[len(prefix):].strip()

            if cleaned:

                return cleaned

    return name


def show_sidebar():

    with st.sidebar:

        st.markdown(
            "# 🤖 AI Recruiter"
        )

        st.caption(
            "AI Resume Screening & Candidate Ranking"
        )

        st.divider()

        user_name = clean_display_name(
            st.session_state.get(
                "name",
                "User"
            )
        )

        user_role = st.session_state.get(
            "role",
            ""
        )

        st.markdown(
            f"""
            ### 👋 Welcome

            **{user_name}**

            Role:

            `{user_role.title()}`
            """
        )

        st.divider()

        if user_role == "recruiter":

            st.markdown(
                "### 📌 Recruiter Portal"
            )

            st.markdown(
                """
                - 📊 Dashboard
                - 📄 Resume Screening
                - 👥 Candidates
                - 🤖 AI Analysis
                - 📈 Analytics
                - 🚀 AI Tools & Extra Features
                """

            )

        elif user_role == "candidate":

            st.markdown(
                "### 📌 Candidate Portal"
            )

            st.markdown(
                """
                - 👤 My Profile
                - 📊 Screening Result
                - 🤖 AI Interview Simulator
                - 📝 AI Resume Improvement
                """
            )

        st.divider()

        if st.button(
            "🚪 Logout",
            use_container_width=True
        ):

            logout()
            st.rerun()


# ============================================================
# RECRUITER HEADER
# ============================================================

def recruiter_header():

    st.markdown(
        """
        <div class="main-header">
            🤖 AI Resume Screening
            & Candidate Ranking System
        </div>

        <div class="main-subtitle">
            Intelligent recruitment platform for
            resume analysis, candidate matching,
            ranking and AI-powered recruitment.
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# EXTRA FEATURES - AI TOOLS (integrated, same app)
# ============================================================

def extra_features_header():

    st.markdown(
        """
        <div class="main-title">
            🚀 AI Tools & Extra Features
        </div>

        <div class="main-subtitle">
            Interview scheduling, email notifications
            and multi-language parsing - all inside
            the same application.
        </div>
        """,
        unsafe_allow_html=True
    )


def recruiter_ai_tools():

    tabs = st.tabs(
        [
            "📅 Interview Scheduler",
            "📧 Email Notifications",
            "🌐 Multi-language Resume Parsing"
        ]
    )

    with tabs[0]:

        interview_scheduler.show()

    with tabs[1]:

        _email_notifications_page()

    with tabs[2]:

        multilingual_parser.show()


def candidate_ai_tools():

    st.markdown(
        "### 🚀 AI Tools"
    )

    tabs = st.tabs(
        [
            "🤖 AI Interview Simulator",
            "✨ AI Resume Improvement"
        ]
    )

    with tabs[0]:

        ai_interview.show()

    with tabs[1]:

        resume_improvement.show()


def _email_notifications_page():

    st.markdown(
        """
        <div class="main-title">
            📧 Email Notifications
        </div>

        <div class="main-subtitle">
            Candidate notifications are automatically sent
            from the recruiter's configured email address.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    # --------------------------------------------------------
    # EMAIL SERVICE STATUS CARD
    # (only shows whether SMTP is configured - the sender
    #  address and all credentials stay hidden)
    # --------------------------------------------------------

    if email_service.email_configured():

        st.metric(
            "SMTP Status",
            "🟢 Configured"
        )

        st.caption(
            "Email service is ready to send "
            "candidate notifications."
        )

    else:

        st.metric(
            "SMTP Status",
            "🔴 Not Configured"
        )

        st.caption(
            "Email service is not configured. "
            "Candidate notifications cannot be sent."
        )

    st.divider()

    # --------------------------------------------------------
    # SEND EMAIL TO CANDIDATE
    # --------------------------------------------------------

    st.markdown(
        "### 📧 Send Email to Candidate"
    )

    st.caption(
        "Send an email directly to the selected candidate "
        "using the recruiter's configured email address."
    )

    try:

        from database import get_candidates

        candidates_df = get_candidates()

        if candidates_df is None or candidates_df.empty:

            st.info(
                "No candidates available. Screen some resumes "
                "first to send emails."
            )

        else:

            candidate_options = {}

            for _, row in candidates_df.iterrows():

                name = str(
                    row.get("name", "Unknown Candidate")
                )

                email = str(
                    row.get("email", "")
                )

                if "@" in email:

                    label = f"{name} — {email}"

                    if label not in candidate_options:

                        candidate_options[label] = {
                            "name": name,
                            "email": email
                        }

            if not candidate_options:

                st.info(
                    "No candidates with a valid email address "
                    "are available."
                )

            else:

                selected = st.selectbox(
                    "Select Candidate",
                    list(candidate_options.keys()),
                    key="direct_email_candidate"
                )

                candidate_name = candidate_options[
                    selected
                ]["name"]

                candidate_email = candidate_options[
                    selected
                ]["email"]

                col1, col2 = st.columns(2)

                with col1:

                    st.metric(
                        "👤 Selected Candidate",
                        candidate_name
                    )

                with col2:

                    st.metric(
                        "📧 Candidate Email",
                        candidate_email
                    )

                subject = st.text_input(
                    "📝 Subject",
                    placeholder="Enter the email subject",
                    key="direct_email_subject"
                )

                message = st.text_area(
                    "✉️ Email Message",
                    height=180,
                    placeholder=(
                        "Write your message to the candidate..."
                    ),
                    key="direct_email_message"
                )

                if st.button(
                    "📧 Send Email to Candidate",
                    type="primary",
                    use_container_width=True,
                    key="direct_email_send_button"
                ):

                    if not subject.strip():

                        st.warning(
                            "⚠️ Please enter a subject."
                        )

                    elif not message.strip():

                        st.warning(
                            "⚠️ Please enter the email message."
                        )

                    else:

                        with st.spinner(
                            "📨 Sending email..."
                        ):

                            ok, reason = (
                                email_service.send_candidate_email(
                                    candidate_name,
                                    candidate_email,
                                    subject.strip(),
                                    message.strip()
                                )
                            )

                        if ok:

                            st.success(
                                f"✅ Email sent successfully to "
                                f"{candidate_name} "
                                f"({candidate_email})"
                            )

                        else:

                            st.error(
                                "❌ Email could not be sent. "
                                "Please check the SMTP "
                                "configuration."
                            )

                            if reason and (
                                reason
                                != "Email service is not configured."
                            ):

                                st.caption(
                                    f"ℹ️ Reason: {reason}"
                                )

    except Exception as e:

        st.caption(
            f"Candidate list unavailable: {e}"
        )

    st.divider()

    # --------------------------------------------------------
    # NOTIFICATION LOG
    # --------------------------------------------------------

    st.markdown(
        "### 📜 Notification Log"
    )

    try:

        from database import (
            get_notifications,
            get_candidate_by_email
        )

        log_rows = get_notifications(limit=200)

        if log_rows:

            # ------------------------------------------------
            # FILTER OPTIONS
            # ------------------------------------------------

            status_options = [
                "All",
                "Sent",
                "Failed",
                "Skipped"
            ]

            type_options = ["All"]

            for row in log_rows:

                event_type = str(
                    row.get("event_type", "")
                ).strip()

                if event_type and event_type not in type_options:

                    type_options.append(event_type)

            col1, col2 = st.columns(2)

            with col1:

                filter_status = st.selectbox(
                    "Filter by Status",
                    status_options,
                    key="log_filter_status"
                )

            with col2:

                filter_type = st.selectbox(
                    "Filter by Type",
                    type_options,
                    key="log_filter_type"
                )

            # ------------------------------------------------
            # RESOLVE CANDIDATE NAME + JOB ROLE FROM DB
            # ------------------------------------------------

            def _lookup_candidate(email):

                try:

                    records = get_candidate_by_email(email)

                    if records:

                        record = records[0]

                        return str(
                            record.get("name", "")
                        ), str(
                            record.get("job_role", "")
                        )

                except Exception:

                    pass

                return "", ""

            table_rows = []

            for row in log_rows:

                status = str(
                    row.get("status", "Failed")
                )

                event_type = str(
                    row.get("event_type", "")
                ).strip() or "Notification"

                recipient = str(
                    row.get("recipient", "")
                )

                if (
                    filter_status != "All"
                    and status != filter_status
                ):

                    continue

                if (
                    filter_type != "All"
                    and event_type != filter_type
                ):

                    continue

                subject = str(
                    row.get("subject", "")
                )

                role_from_subject = ""

                if " - " in subject:

                    _, _, role_from_subject = (
                        subject.partition(" - ")
                    )

                role_from_subject = role_from_subject.strip()

                candidate_name = ""

                job_role = ""

                if "@" in recipient:

                    candidate_name, job_role = (
                        _lookup_candidate(recipient)
                    )

                if not candidate_name:

                    candidate_name = (
                        recipient or "Unknown"
                    )

                if not job_role:

                    job_role = role_from_subject

                created_at = str(
                    row.get("created_at", "")
                )

                date_part = (
                    created_at.split(" ")[0]
                    if created_at
                    else ""
                )

                time_part = (
                    created_at.split(" ")[1]
                    if created_at and " " in created_at
                    else ""
                )

                dt_display = ""

                if date_part:

                    dt_display = email_service.format_date(
                        date_part
                    )

                if time_part:

                    dt_display += (
                        f", {email_service.format_time(time_part)}"
                    )

                status_icon = {
                    "Sent": "✅ Sent",
                    "Failed": "❌ Failed",
                    "Skipped": "🟡 Skipped"
                }.get(status, status)

                table_rows.append(
                    {
                        "Type": event_type,
                        "Candidate": candidate_name,
                        "Candidate Email": recipient,
                        "Subject": str(
                            row.get("subject", "")
                        ),
                        "Job Role": job_role,
                        "Date/Time": dt_display,
                        "Status": status_icon
                    }
                )

            if table_rows:

                st.dataframe(
                    pd.DataFrame(table_rows),
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "No notifications match the selected filters."
                )

        else:

            st.info(
                "No notification activity yet. Scheduling an "
                "interview or updating a candidate status will "
                "appear here."
            )

    except Exception as e:

        st.caption(
            f"Notification log unavailable: {e}"
        )


# ============================================================
# DASHBOARD METRICS
# ============================================================

def show_metrics(df):

    if df is None or df.empty:

        total = 0
        approved = 0
        pending = 0
        rejected = 0

    else:

        total = len(df)

        approved = len(
            df[
                df["status"] == "Approved"
            ]
        )

        pending = len(
            df[
                df["status"] == "Pending"
            ]
        )

        rejected = len(
            df[
                df["status"] == "Rejected"
            ]
        )

    col1, col2, col3, col4 = st.columns(4)

    metrics = [
        ("Total Candidates", total),
        ("✅ Approved", approved),
        ("⏳ Pending", pending),
        ("❌ Rejected", rejected)
    ]

    for col, (title, value) in zip(
        [col1, col2, col3, col4],
        metrics
    ):

        with col:

            st.metric(
                title,
                f"{value}"
            )


# ============================================================
# SAVE JOB DESCRIPTION
# ============================================================

def save_job_context(
    job_role,
    job_description
):

    st.session_state[
        "current_job_role"
    ] = job_role

    st.session_state[
        "current_job_description"
    ] = job_description


# ============================================================
# RESUME SCREENING
# ============================================================

def resume_screening():

    st.subheader(
        "📄 Resume Screening"
    )

    st.markdown(
        """
        <div class="info-box">

        Upload multiple resumes and compare them
        against the selected job description.

        <b>Supported:</b> PDF • DOCX • TXT

        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)

    with col1:

        job_role = st.text_input(
            "💼 Job Role",
            placeholder="Example: Data Analyst"
        )

    with col2:

        uploaded_files = st.file_uploader(
            "📎 Upload Resumes",
            type=[
                "pdf",
                "docx",
                "txt"
            ],
            accept_multiple_files=True
        )

    job_description = st.text_area(
        "📝 Job Description",
        height=180,
        placeholder=(
            "Example:\n"
            "Looking for a Data Analyst with Python, "
            "SQL, Excel, Power BI and Pandas."
        )
    )

    if st.button(
        "🚀 Screen Resumes",
        type="primary",
        use_container_width=True
    ):

        if not job_role.strip():

            st.warning(
                "Please enter the job role."
            )

            return

        if not job_description.strip():

            st.warning(
                "Please enter the job description."
            )

            return

        if not uploaded_files:

            st.warning(
                "Please upload at least one resume."
            )

            return

        # ----------------------------------------------------
        # SAVE JOB DESCRIPTION FOR GEMINI
        # ----------------------------------------------------

        save_job_context(
            job_role,
            job_description
        )

        results = []

        failed_files = []

        progress = st.progress(0)

        status_text = st.empty()

        total_files = len(
            uploaded_files
        )

        for index, uploaded_file in enumerate(
            uploaded_files
        ):

            status_text.write(
                f"Processing {uploaded_file.name}..."
            )

            try:

                # --------------------------------------------
                # EXTRACT RESUME TEXT
                # --------------------------------------------

                text, result_info = extract_resume_with_result(
                    uploaded_file
                )

                if not text:

                    # Track the failure (with a friendly reason)
                    # and continue with the next resume.
                    reason = result_info.get(
                        "message",
                        "The resume could not be read.",
                    )

                    action = result_info.get(
                        "suggested_action",
                        "",
                    )

                    failed_files.append(
                        {
                            "filename": uploaded_file.name,
                            "message": reason,
                            "suggested_action": action,
                        }
                    )

                    progress.progress(
                        (index + 1) / total_files
                    )

                    continue

                # --------------------------------------------
                # EXTRACT CANDIDATE DETAILS
                # --------------------------------------------

                candidate = extract_candidate_details(
                    text,
                    uploaded_file.name
                )

                if not candidate:

                    candidate = {}

                candidate[
                    "resume_text"
                ] = text

                # --------------------------------------------
                # RANK CANDIDATE
                # --------------------------------------------

                try:

                    ranking_result = rank_candidate(
                        candidate.get(
                            "skills",
                            []
                        ),
                        extract_skills(
                            job_description
                        )
                    )

                except TypeError:

                    try:

                        ranking_result = rank_candidate(
                            candidate.get(
                                "skills",
                                []
                            ),
                            extract_skills(
                                job_description
                            )
                        )

                    except Exception:

                        ranking_result = None

                # --------------------------------------------
                # HANDLE RANKING RESULT
                # --------------------------------------------

                score = 0

                matched_skills = []

                missing_skills = []

                status = "Pending"

                if isinstance(
                    ranking_result,
                    dict
                ):

                    score = float(
                        ranking_result.get(
                            "score",
                            ranking_result.get(
                                "match_score",
                                0
                            )
                        )
                    )

                    matched_skills = ranking_result.get(
                        "matched_skills",
                        []
                    )

                    missing_skills = ranking_result.get(
                        "missing_skills",
                        []
                    )

                    status = ranking_result.get(
                        "status",
                        "Pending"
                    )

                elif isinstance(
                    ranking_result,
                    (int, float)
                ):

                    score = float(
                        ranking_result
                    )

                # --------------------------------------------
                # FALLBACK STATUS
                # --------------------------------------------

                if status not in [
                    "Approved",
                    "Pending",
                    "Rejected"
                ]:

                    if score >= 75:
                        status = "Approved"

                    elif score >= 45:
                        status = "Pending"

                    else:
                        status = "Rejected"

                # --------------------------------------------
                # SAVE TO DATABASE
                # --------------------------------------------

                add_candidate(
                    candidate=candidate,
                    filename=uploaded_file.name,
                    score=score,
                    status=status,
                    job_role=job_role,
                    matched_skills=matched_skills,
                    missing_skills=missing_skills
                )

                results.append(
                    {
                        "Candidate":
                            candidate.get(
                                "name",
                                "Unknown Candidate"
                            ),

                        "Email":
                            candidate.get(
                                "email",
                                "Not Found"
                            ),

                        "Score":
                            score,

                        "Status":
                            status,

                        "Matched Skills":
                            ", ".join(
                                matched_skills
                            )
                    }
                )

            except Exception as e:

                # Log technical details for developers; show the
                # user only a friendly per-file message.
                logger.error(
                    "Error processing %s: %s",
                    uploaded_file.name,
                    e,
                )

                failed_files.append(
                    {
                        "filename": uploaded_file.name,
                        "message": (
                            "The resume could not be processed "
                            "due to an unexpected error."
                        ),
                        "suggested_action": (
                            "The file may be corrupted. "
                            "Please try another resume."
                        ),
                    }
                )

            progress.progress(
                (index + 1) / total_files
            )

        status_text.empty()

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        success_count = len(results)

        fail_count = len(failed_files)

        if success_count > 0:

            if fail_count > 0:

                st.success(
                    f"{success_count} resume(s) processed "
                    f"successfully. {fail_count} resume(s) "
                    f"could not be processed."
                )

            else:

                st.success(
                    f"Successfully screened "
                    f"{success_count} resume(s)."
                )

            results_df = pd.DataFrame(
                results
            )

            st.dataframe(
                results_df,
                use_container_width=True,
                hide_index=True
            )

        elif fail_count > 0:

            st.error(
                "No resumes could be processed."
            )

        # ----------------------------------------------------
        # FAILED RESUMES (friendly, per-file)
        # ----------------------------------------------------

        if failed_files:

            st.warning(
                "⚠️ " + f"{fail_count} resume(s) could not be read:"
            )

            for failed in failed_files:

                st.markdown(
                    f"**{failed['filename']}**"
                )

                st.write(
                    failed.get("message", "Could not be read.")
                )

                action = failed.get(
                    "suggested_action",
                    "",
                )

                if action:

                    st.caption(
                        f"💡 {action}"
                    )


# ============================================================
# CANDIDATE TABLE
# ============================================================

def candidate_table(df):

    st.subheader(
        "👥 Candidate Ranking"
    )

    if df is None or df.empty:

        st.info(
            "No candidates available."
        )

        return

    search = st.text_input(
        "🔎 Search Candidate",
        placeholder="Search by name, email or job role..."
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        status_filter = st.selectbox(
            "Filter by Status",
            [
                "All",
                "Approved",
                "Pending",
                "Rejected"
            ]
        )

    with col2:

        job_roles = [
            "All"
        ] + sorted(
            df["job_role"]
            .astype(str)
            .dropna()
            .unique()
            .tolist()
        )

        job_role_filter = st.selectbox(
            "Filter by Job Role",
            job_roles
        )

    with col3:

        min_score = st.slider(
            "Minimum Match Score",
            min_value=0,
            max_value=100,
            value=0,
            step=5
        )

    filtered_df = df.copy()

    if search:

        search_lower = search.lower()

        filtered_df = filtered_df[
            filtered_df.apply(
                lambda row:
                search_lower in str(
                    row.get("name", "")
                ).lower()
                or
                search_lower in str(
                    row.get("email", "")
                ).lower()
                or
                search_lower in str(
                    row.get("job_role", "")
                ).lower(),
                axis=1
            )
        ]

    if status_filter != "All":

        filtered_df = filtered_df[
            filtered_df["status"]
            ==
            status_filter
        ]

    if job_role_filter != "All":

        filtered_df = filtered_df[
            filtered_df["job_role"]
            .astype(str)
            ==
            job_role_filter
        ]

    filtered_df = filtered_df[
        filtered_df["score"] >= min_score
    ]

    if filtered_df.empty:

        st.info(
            "No candidates match the selected filters."
        )

        return

    st.caption(
        f"Showing {len(filtered_df)} candidate(s)."
    )

    columns = [
        "id",
        "name",
        "email",
        "job_role",
        "score",
        "status",
        "matched_skills"
    ]

    available_columns = [
        column
        for column in columns
        if column in filtered_df.columns
    ]

    display_df = filtered_df[
        available_columns
    ].copy()

    rename_map = {
        "id": "ID",
        "name": "Candidate",
        "email": "Email",
        "job_role": "Job Role",
        "score": "Score",
        "status": "Status",
        "matched_skills": "Matched Skills"
    }

    display_df.rename(
        columns=rename_map,
        inplace=True
    )

    if "Score" in display_df.columns:

        display_df["Score"] = display_df[
            "Score"
        ].apply(
            lambda x: f"{float(x):.1f}%"
        )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# CANDIDATE DETAILS
# ============================================================

def candidate_details(df):

    st.subheader(
        "🔍 Candidate Details"
    )

    if df is None or df.empty:

        st.info(
            "No candidate records available."
        )

        return

    # --------------------------------------------------------
    # CANDIDATE SELECTOR
    # --------------------------------------------------------

    candidate_options = {}

    for _, row in df.iterrows():

        name = row.get(
            "name",
            "Unknown Candidate"
        )

        email = row.get(
            "email",
            "Not Found"
        )

        candidate_options[
            f"{name} — {email}"
        ] = int(
            row["id"]
        )

    selected = st.selectbox(
        "Select Candidate",
        list(
            candidate_options.keys()
        )
    )

    candidate_id = candidate_options[
        selected
    ]

    candidate_data = get_candidate(
        candidate_id
    )

    if candidate_data is None:

        st.error(
            "Candidate not found."
        )

        return

    # --------------------------------------------------------
    # BASIC DETAILS
    # --------------------------------------------------------

    st.divider()

    status_value = str(
        candidate_data.get(
            "status",
            "Pending"
        )
    )

    status_badge = {
        "Approved": "🟢 Approved",
        "Pending": "🟡 Pending",
        "Rejected": "🔴 Rejected"
    }.get(
        status_value,
        status_value
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "🎯 AI Match Score",
            f"{float(candidate_data['score']):.1f}%"
        )

    with col2:

        st.metric(
            "📊 Application Status",
            status_badge
        )

    with col3:

        st.metric(
            "💼 Job Role",
            candidate_data.get(
                "job_role",
                ""
            )
        )

    with col4:

        st.metric(
            "📱 Phone",
            candidate_data.get(
                "phone",
                "Not Found"
            )
        )

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "👤 Candidate Name",
            candidate_data.get(
                "name",
                "Unknown"
            )
        )

    with col2:

        st.metric(
            "📧 Email",
            candidate_data.get(
                "email",
                ""
            )
        )

    with col3:

        st.metric(
            "📄 Resume",
            candidate_data.get(
                "filename",
                ""
            )
        )

    with st.expander(
        "🧠 Skill Analysis"
    ):

        st.write(
            "**Matched Skills:**"
        )

        matched = candidate_data.get(
            "matched_skills",
            ""
        )

        if matched:

            st.success(
                matched
            )

        else:

            st.info(
                "No matched skills."
            )

        st.write(
            "**Missing Skills:**"
        )

        missing = candidate_data.get(
            "missing_skills",
            ""
        )

        if missing:

            st.warning(
                missing
            )

        else:

            st.success(
                "No major missing skills."
            )

    # ========================================================
    # GEMINI AI ANALYSIS
    # ========================================================

    st.divider()

    st.markdown(
        "### 🤖 AI-Powered Resume Analysis"
    )

    st.caption(
        "Use Gemini AI to analyze this candidate "
        "against the job requirements."
    )

    # --------------------------------------------------------
    # GET CURRENT JOB DESCRIPTION
    # --------------------------------------------------------

    job_description = st.session_state.get(
        "current_job_description",
        ""
    )

    if not job_description:

        st.info(
            "The job description for this candidate "
            "is not currently available in this session."
        )

        with st.expander(
            "📝 Enter Job Description for AI Analysis"
        ):

            manual_job_description = st.text_area(
                "Job Description",
                height=180,
                key=f"manual_job_description_{candidate_id}"
            )

            if st.button(
                "💾 Use This Job Description",
                key=f"save_job_description_{candidate_id}"
            ):

                if manual_job_description.strip():

                    st.session_state[
                        "current_job_description"
                    ] = manual_job_description

                    st.success(
                        "Job description saved."
                    )

                    st.rerun()

                else:

                    st.warning(
                        "Please enter a job description."
                    )

    else:

        st.success(
            "✅ Job description available for AI analysis."
        )

    # --------------------------------------------------------
    # GEMINI BUTTON
    # --------------------------------------------------------

    if st.button(
        "🤖 Analyze Resume with Gemini",
        type="primary",
        use_container_width=True,
        key=f"gemini_analysis_{candidate_id}"
    ):

        current_job_description = st.session_state.get(
            "current_job_description",
            ""
        )

        resume_text = candidate_data.get(
            "resume_text",
            ""
        )

        if not current_job_description:

            st.warning(
                "⚠️ Job description is not available."
            )

        elif not resume_text:

            st.warning(
                "⚠️ Resume text is not available."
            )

        else:

            ai_resume_analysis(
                resume_text,
                current_job_description
            )

    # --------------------------------------------------------
    # VIEW RESUME
    # --------------------------------------------------------

    st.divider()

    with st.expander(
        "📄 View Extracted Resume Text"
    ):

        st.text(
            candidate_data.get(
                "resume_text",
                "No resume text available."
            )
        )

    # ========================================================
    # UPDATE STATUS
    # ========================================================

    st.divider()

    st.markdown(
        "### ⚙️ Update Candidate Status"
    )

    current_status = candidate_data[
        "status"
    ]

    statuses = [
        "Approved",
        "Pending",
        "Rejected"
    ]

    if current_status not in statuses:

        current_status = "Pending"

    new_status = st.selectbox(
        "Status",
        statuses,
        index=statuses.index(
            current_status
        ),
        key=f"status_{candidate_id}"
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "💾 Update Status",
            type="primary",
            use_container_width=True,
            key=f"update_{candidate_id}"
        ):

            update_candidate_status(
                candidate_id,
                new_status
            )

            st.success(
                f"Candidate status updated to {new_status}."
            )

            # ----------------------------------------
            # NOTIFY CANDIDATE BY EMAIL
            # (email comes from the existing
            #  candidate database record)
            # ----------------------------------------

            candidate_name = candidate_data.get(
                "name",
                "Candidate"
            )

            candidate_email = candidate_data.get(
                "email",
                ""
            )

            job_role = candidate_data.get(
                "job_role",
                ""
            )

            if candidate_email:

                ok, message = email_service.send_status_email(
                    candidate_name,
                    candidate_email,
                    job_role,
                    new_status
                )

                if ok:

                    st.success(
                        f"📧 {message}"
                    )

                else:

                    st.warning(
                        f"📧 {message}"
                    )

            st.rerun()

    with col2:

        if st.button(
            "🗑️ Delete Candidate",
            use_container_width=True,
            key=f"delete_{candidate_id}"
        ):

            delete_candidate(
                candidate_id
            )

            st.success(
                "Candidate deleted successfully."
            )

            st.rerun()


# ============================================================
# ANALYTICS
# ============================================================

def analytics(df):

    st.subheader(
        "📈 Recruitment Analytics"
    )

    if df is None or df.empty:

        st.info(
            "Upload resumes to generate analytics."
        )

        return

    col1, col2 = st.columns(2)

    with col1:

        status_counts = (
            df["status"]
            .value_counts()
            .reset_index()
        )

        status_counts.columns = [
            "Status",
            "Count"
        ]

        st.bar_chart(
            status_counts.set_index(
                "Status"
            )
        )

    with col2:

        score_data = df[
            ["name", "score"]
        ].copy()

        score_data = score_data.set_index(
            "name"
        )

        st.bar_chart(
            score_data
        )

    st.divider()

    st.markdown(
        "### 🏆 Top Candidates"
    )

    top_candidates = df[
        [
            "name",
            "email",
            "score",
            "status"
        ]
    ].head(10).copy()

    top_candidates["score"] = (
        top_candidates["score"]
        .apply(
            lambda x:
            f"{float(x):.1f}%"
        )
    )

    st.dataframe(
        top_candidates,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# DATA MANAGEMENT
# ============================================================

def data_management(df):

    st.subheader(
        "🛠️ Data Management"
    )

    st.warning(
        "Deleting candidate data cannot be undone."
    )

    if df is None or df.empty:

        st.info(
            "There are no candidate records."
        )

        return

    if st.button(
        "🗑️ Clear All Candidate Data",
        use_container_width=True
    ):

        st.session_state[
            "confirm_clear"
        ] = True

    if st.session_state.get(
        "confirm_clear",
        False
    ):

        st.warning(
            "Are you sure you want to delete "
            "all candidate records?"
        )

        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "✅ Yes, Delete All",
                use_container_width=True
            ):

                clear_all_candidates()

                st.session_state[
                    "confirm_clear"
                ] = False

                st.success(
                    "All candidate data deleted."
                )

                st.rerun()

        with col2:

            if st.button(
                "❌ Cancel",
                use_container_width=True
            ):

                st.session_state[
                    "confirm_clear"
                ] = False

                st.rerun()


# ============================================================
# CANDIDATE PORTAL
# ============================================================

def candidate_portal():

    st.markdown(
        """
        <div class="main-header">
            👤 Candidate Portal
        </div>

        <div class="main-subtitle">
            View your recruitment application
            and screening result.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    candidate_email = st.session_state.get(
        "email",
        ""
    )

    candidate_name = clean_display_name(
        st.session_state.get(
            "name",
            "Candidate"
        )
    )

    st.markdown(
        "### 👤 My Profile"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            f"**Name:** {candidate_name}"
        )

    with col2:

        st.write(
            f"**Email:** {candidate_email}"
        )

    st.divider()

    st.markdown(
        "### 📊 My Screening Result"
    )

    # --------------------------------------------------------
    # FIND CANDIDATE USING EMAIL
    # --------------------------------------------------------

    df = get_candidates()

    if df is None or df.empty:

        st.info(
            "Your resume has not been screened yet."
        )

    elif not candidate_email:

        st.warning(
            "Candidate email is not available."
        )

    else:

        email_matches = df[
            df["email"]
            .astype(str)
            .str.lower()
            ==
            str(candidate_email).lower()
        ]

        if email_matches.empty:

            st.info(
                "No screening result is available "
                "for your email yet."
            )

        else:

            # Show latest/highest matching records
            email_matches = email_matches.sort_values(
                by="score",
                ascending=False
            )

            for _, row in email_matches.iterrows():

                col1, col2, col3 = st.columns(3)

                with col1:

                    st.metric(
                        "Job Role",
                        row.get(
                            "job_role",
                            "Not Available"
                        )
                    )

                with col2:

                    st.metric(
                        "AI Match Score",
                        f"{float(row.get('score', 0)):.1f}%"
                    )

                with col3:

                    status = row.get(
                        "status",
                        "Pending"
                    )

                    st.metric(
                        "Application Status",
                        status
                    )

                st.markdown(
                    f"""
                    **Matched Skills:**  
                    {row.get("matched_skills", "None")}

                    **Missing Skills:**  
                    {row.get("missing_skills", "None")}
                    """
                )

                st.divider()

    # ========================================================
    # MY INTERVIEW INFORMATION
    # (only this candidate's interviews - filtered by
    #  the email of the logged-in candidate)
    # ========================================================

    st.divider()

    st.markdown(
        "### 🗓 My Interview Information"
    )

    try:

        from database import get_interviews

        interviews = get_interviews()

        my_interviews = [
            interview
            for interview in interviews
            if str(
                interview.get("candidate_email", "")
            ).strip().lower()
            == str(candidate_email).strip().lower()
        ]

        if my_interviews:

            for interview in my_interviews:

                col1, col2, col3 = st.columns(3)

                with col1:

                    st.metric(
                        "Job Role",
                        interview.get(
                            "job_role",
                            "Not Available"
                        )
                    )

                with col2:

                    st.metric(
                        "Interview Date",
                        interview.get(
                            "interview_date",
                            "TBD"
                        )
                    )

                with col3:

                    st.metric(
                        "Interview Time",
                        interview.get(
                            "interview_time",
                            "TBD"
                        )
                    )

                st.markdown(
                    f"""
                    **Interview Type:**
                    {interview.get("interview_type", "Online")}

                    **Location / Meeting Link:**
                    {interview.get("location_or_link", "") or "Not provided"}

                    **Status:** {interview.get("status", "Scheduled")}
                    """
                )

                if interview.get("notes"):

                    st.caption(
                        f"📝 {interview['notes']}"
                    )

                st.divider()

        else:

            st.info(
                "No interviews have been scheduled for you yet."
            )

    except Exception as e:

        st.caption(
            f"Interview information unavailable: {e}"
        )

    # ========================================================
    # AI TOOLS (for candidates - practice + improvement)
    # ========================================================

    st.divider()

    candidate_ai_tools()


# ============================================================
# RECRUITER APPLICATION
# ============================================================

def recruiter_application():

    recruiter_header()

    st.divider()

    # --------------------------------------------------------
    # GET DATABASE
    # --------------------------------------------------------

    try:

        df = get_candidates()

    except Exception as e:

        st.error(
            "Unable to load candidate database."
        )

        st.code(
            str(e)
        )

        st.info(
            "Check your database.py and candidates.db."
        )

        return

    if df is None:

        df = pd.DataFrame()

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    show_metrics(
        df
    )

    st.divider()

    # --------------------------------------------------------
    # TABS
    # --------------------------------------------------------

    tabs = st.tabs(
        [
            "📊 Dashboard",
            "📄 Screen Resumes",
            "👥 Candidates",
            "🔍 Candidate Details",
            "📈 Analytics",
            "🛠️ Data Management",
            "🚀 AI Tools & Extra Features"
        ]
    )

    # ========================================================
    # DASHBOARD
    # ========================================================

    with tabs[0]:

        st.subheader(
            "📊 Recruitment Dashboard"
        )

        if df.empty:

            st.info(
                "Welcome! Start by opening "
                "'Screen Resumes' and upload candidate resumes."
            )

            st.markdown(
                """
                ### 🚀 Recruitment Workflow

                **1.** Enter Job Role

                **2.** Enter Job Description

                **3.** Upload Multiple Resumes

                **4.** Screen Resumes

                **5.** AI extracts candidate information

                **6.** Candidate receives a matching score

                **7.** Candidate becomes Approved,
                Pending or Rejected

                **8.** Open Candidate Details

                **9.** Use Gemini AI for detailed analysis

                **10.** Update final candidate status
                """

            )

        else:

            st.markdown(
                "### 🏆 Top Ranked Candidates"
            )

            top = df.head(5)

            for _, row in top.iterrows():

                col1, col2, col3 = st.columns(
                    [4, 2, 2]
                )

                with col1:

                    st.write(
                        f"**{row.get('name', 'Unknown Candidate')}**"
                    )

                    st.caption(
                        row.get(
                            "email",
                            "Not Found"
                        )
                    )

                with col2:

                    st.metric(
                        "Score",
                        f"{float(row.get('score', 0)):.1f}%"
                    )

                with col3:

                    st.write(
                        row.get(
                            "status",
                            "Pending"
                        )
                    )

                st.divider()

    # ========================================================
    # RESUME SCREENING
    # ========================================================

    with tabs[1]:

        resume_screening()

    # ========================================================
    # CANDIDATES
    # ========================================================

    with tabs[2]:

        candidate_table(
            df
        )

    # ========================================================
    # DETAILS
    # ========================================================

    with tabs[3]:

        candidate_details(
            df
        )

    # ========================================================
    # ANALYTICS
    # ========================================================

    with tabs[4]:

        analytics(
            df
        )

    # ========================================================
    # DATA MANAGEMENT
    # ========================================================

    with tabs[5]:

        data_management(
            df
        )

    # ========================================================
    # AI TOOLS & EXTRA FEATURES
    # ========================================================

    with tabs[6]:

        extra_features_header()

        st.divider()

        recruiter_ai_tools()


# ============================================================
# APPLICATION START
# ============================================================

apply_custom_css()


# ============================================================
# LOGIN
# ============================================================

if not authentication():

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

show_sidebar()


# ============================================================
# ROLE-BASED PORTAL
# ============================================================

user_role = st.session_state.get(
    "role"
)

if user_role == "recruiter":

    recruiter_application()

elif user_role == "candidate":

    candidate_portal()

else:

    st.error(
        "Invalid user role."
    )

    logout()
    st.rerun()