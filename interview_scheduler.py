""""
Interview Scheduler
===================

Independent extra feature for scheduling and
managing candidate interviews.

Uses the separate `interviews` table (see database.py).
Sends email notifications via email_service.py.
"""

import streamlit as st

from database import (
    add_interview,
    get_interviews,
    get_interview,
    update_interview,
    update_interview_status,
    delete_interview,
    get_candidates
)

from email_service import (
    send_interview_scheduled_email,
    send_interview_rescheduled_email,
    send_interview_cancelled_email,
    send_interview_reminder,
    email_configured
)

STATUSES = [
    "Scheduled",
    "Completed",
    "Cancelled",
    "Rescheduled"
]

INTERVIEW_TYPES = [
    "Online",
    "Offline",
    "Phone"
]


# ============================================================
# HELPERS
# ============================================================

def _candidate_options():
    """Build name/email options from the candidates table."""

    options = {}

    try:

        candidates = get_candidates()

        # get_candidates() returns a pandas DataFrame;
        # normalize to plain dict records
        if hasattr(candidates, "to_dict"):

            candidates = candidates.to_dict("records")

        for candidate in candidates:

            name = str(
                candidate.get("name", "Unknown Candidate")
            )

            email = str(
                candidate.get("email", "Not Found")
            )

            key = f"{name} - {email}"

            if key not in options:

                options[key] = {
                    "name": name,
                    "email": email,
                    "id": candidate.get("id", 0)
                }

    except Exception:
        pass

    return options


def _send_emails(record, email_type):
    """Send the relevant email and show the result."""

    details = {
        "job_role": record.get("job_role", ""),
        "interview_date": record.get("interview_date", ""),
        "interview_time": record.get("interview_time", ""),
        "interview_type": record.get("interview_type", "Online"),
        "location_or_link": record.get("location_or_link", ""),
        "duration": record.get("duration", ""),
        "notes": record.get("notes", "")
    }

    if email_type == "scheduled":

        ok, msg = send_interview_scheduled_email(
            record.get("candidate_name", "Candidate"),
            record.get("candidate_email", ""),
            details
        )

    elif email_type == "rescheduled":

        ok, msg = send_interview_rescheduled_email(
            record.get("candidate_name", "Candidate"),
            record.get("candidate_email", ""),
            details
        )

    elif email_type == "cancelled":

        ok, msg = send_interview_cancelled_email(
            record.get("candidate_name", "Candidate"),
            record.get("candidate_email", ""),
            details
        )

    else:

        ok, msg = send_interview_reminder(
            record.get("candidate_name", "Candidate"),
            record.get("candidate_email", ""),
            details
        )

    if ok:

        st.success(f"📧 {msg}")

    else:

        st.warning(f"📧 {msg}")


def _show_interview_row(record, with_actions=True):
    """Render a single interview record."""

    status = record.get("status", "Scheduled")

    st.markdown(
        f"**{record.get('job_role', 'Job Role')}** "
        f"- {record.get('candidate_name', 'Unknown')}"
    )

    st.caption(
        f"📅 {record.get('interview_date', '')} "
        f"| ⏰ {record.get('interview_time', '')} "
        f"| {record.get('interview_type', 'Online')}"
    )

    if record.get("location_or_link"):

        st.caption(
            f"📍 {record['location_or_link']}"
        )

    if record.get("duration"):

        st.caption(
            f"⏱ {record['duration']} minutes"
        )

    if record.get("notes"):

        st.caption(
            f"📝 {record['notes']}"
        )

    if status == "Scheduled":

        st.success("🟢 Scheduled")

    elif status == "Rescheduled":

        st.warning("🟡 Rescheduled")

    elif status == "Completed":

        st.info("🔵 Completed")

    else:

        st.error("🔴 Cancelled")

    if with_actions:

        col1, col2, col3, col4 = st.columns(4)

        with col1:

            if st.button(
                "✏️ Edit",
                key=f"edit_{record['id']}"
            ):

                st.session_state[f"editing_{record['id']}"] = True

        with col2:

            if st.button(
                "🔄 Reschedule",
                key=f"resched_{record['id']}"
            ):

                st.session_state[f"rescheduling_{record['id']}"] = True

        with col3:

            if st.button(
                "✅ Complete",
                key=f"complete_{record['id']}"
            ):

                update_interview_status(
                    record["id"],
                    "Completed"
                )

                st.success(
                    "✅ Interview marked as completed."
                )

                st.rerun()

        with col4:

            if st.button(
                "❌ Cancel",
                key=f"cancel_{record['id']}"
            ):

                update_interview_status(
                    record["id"],
                    "Cancelled"
                )

                _send_emails(record, "cancelled")

                st.rerun()


# ============================================================
# SCHEDULE FORM
# ============================================================

def _schedule_form():

    st.markdown(
        "### 🗓 Schedule a New Interview"
    )

    options = _candidate_options()

    selected = st.selectbox(
        "Select Candidate",
        [""] + list(options.keys()),
        key="interview_scheduler_candidate"
    )

    candidate_id = 0
    candidate_name = ""
    candidate_email = ""

    if selected:

        info = options[selected]

        candidate_id = info["id"]
        candidate_name = info["name"]
        candidate_email = info["email"]

    col1, col2 = st.columns(2)

    with col1:

       job_role = st.text_input(
    "💼 Job Role",
    placeholder="Example: Data Analyst",
    key="interview_scheduler_job_role"
    )

    with col2:

        interview_type = st.selectbox(
            "🎤 Interview Type",
            INTERVIEW_TYPES,
            key="interview_scheduler_interview_type"
        )

    col1, col2 = st.columns(2)

    with col1:

        interview_date = st.date_input(
            "📅 Interview Date",
            key="interview_scheduler_date"
        ).strftime("%Y-%m-%d")

    with col2:

        interview_time = st.time_input(
            "⏰ Interview Time",
            key="interview_scheduler_time"
        ).strftime("%H:%M")

    col1, col2 = st.columns(2)

    with col1:

        location_or_link = st.text_input(
            "📍 Location / Meeting Link",
            placeholder="Office address or video meeting link",
            key="interview_scheduler_location"
        )

    with col2:

        duration = st.number_input(
            "⏱ Duration (minutes)",
            min_value=15,
            max_value=240,
            value=30,
            step=15,
            key="interview_scheduler_duration"
        )

    notes = st.text_area(
        "📝 Interview Notes",
        placeholder="Any instructions for the candidate...",
        key="interview_scheduler_notes"
    )

    st.write("")

    if st.button(
        "📧 Schedule Interview",
        type="primary",
        use_container_width=True,
        key="interview_scheduler_schedule_button"
    ):

        if not candidate_name:

            st.warning(
                "⚠️ Please select a candidate."
            )

        elif not job_role.strip():

            st.warning(
                "⚠️ Please enter the job role."
            )

        elif not location_or_link.strip():

            st.warning(
                "⚠️ Please enter a location or meeting link."
            )

        else:

            interview_id = add_interview(
                candidate_id=candidate_id,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                job_role=job_role.strip(),
                interview_date=interview_date,
                interview_time=interview_time,
                interview_type=interview_type,
                location_or_link=location_or_link.strip(),
                duration=int(duration),
                notes=notes.strip(),
                status="Scheduled"
            )

            st.success(
                f"✅ Interview scheduled! (ID: {interview_id})"
            )

            record = dict(
                get_interview(interview_id)
            )

            _send_emails(record, "scheduled")


# ============================================================
# EDIT / RESCHEDULE FORMS
# ============================================================

def _edit_form(record):

    st.markdown(
        f"### ✏️ Edit Interview #{record['id']}"
    )

    col1, col2 = st.columns(2)

    with col1:

        new_role = st.text_input(
            "💼 Job Role",
            value=record.get("job_role", ""),
            key=f"erole_{record['id']}"
        )

    with col2:

        new_type = st.selectbox(
            "🎤 Interview Type",
            INTERVIEW_TYPES,
            index=INTERVIEW_TYPES.index(
                record.get("interview_type", "Online")
            ) if record.get("interview_type") in INTERVIEW_TYPES else 0,
            key=f"etype_{record['id']}"
        )

    col1, col2 = st.columns(2)

    with col1:

        new_date = st.date_input(
            "📅 Interview Date",
            key=f"edate_{record['id']}"
        ).strftime("%Y-%m-%d")

    with col2:

        new_time = st.time_input(
            "⏰ Interview Time",
            key=f"etime_{record['id']}"
        ).strftime("%H:%M")

    col1, col2 = st.columns(2)

    with col1:

        new_location = st.text_input(
            "📍 Location / Meeting Link",
            value=record.get("location_or_link", ""),
            key=f"eloc_{record['id']}"
        )

    with col2:

        new_duration = st.number_input(
            "⏱ Duration (minutes)",
            min_value=15,
            max_value=240,
            value=int(record.get("duration", 30) or 30),
            step=15,
            key=f"edur_{record['id']}"
        )

    new_notes = st.text_area(
        "📝 Interview Notes",
        value=record.get("notes", ""),
        key=f"enotes_{record['id']}"
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "💾 Save Changes",
            type="primary",
            key=f"esave_{record['id']}"
        ):

            update_interview(
                interview_id=record["id"],
                candidate_name=record.get("candidate_name", ""),
                candidate_email=record.get("candidate_email", ""),
                job_role=new_role.strip(),
                interview_date=new_date,
                interview_time=new_time,
                interview_type=new_type,
                location_or_link=new_location.strip(),
                duration=int(new_duration),
                notes=new_notes.strip(),
                status=record.get("status", "Scheduled")
            )

            st.success("✅ Interview updated.")

            st.session_state.pop(
                f"editing_{record['id']}",
                None
            )

            st.rerun()

    with col2:

        if st.button(
            "Cancel",
            key=f"ecancel_{record['id']}"
        ):

            st.session_state.pop(
                f"editing_{record['id']}",
                None
            )

            st.rerun()


def _reschedule_form(record):

    st.markdown(
        f"### 🔄 Reschedule Interview #{record['id']}"
    )

    col1, col2 = st.columns(2)

    with col1:

        new_date = st.date_input(
            "📅 New Interview Date",
            key=f"rdate_{record['id']}"
        ).strftime("%Y-%m-%d")

    with col2:

        new_time = st.time_input(
            "⏰ New Interview Time",
            key=f"rtime_{record['id']}"
        ).strftime("%H:%M")

    notes = st.text_input(
        "📝 Reason / Note",
        placeholder="Optional note for the candidate",
        key=f"rnotes_{record['id']}"
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "🔄 Confirm Reschedule",
            type="primary",
            key=f"rsave_{record['id']}"
        ):

            update_interview(
                interview_id=record["id"],
                candidate_name=record.get("candidate_name", ""),
                candidate_email=record.get("candidate_email", ""),
                job_role=record.get("job_role", ""),
                interview_date=new_date,
                interview_time=new_time,
                interview_type=record.get("interview_type", "Online"),
                location_or_link=record.get("location_or_link", ""),
                duration=int(record.get("duration", 30) or 30),
                notes=notes.strip(),
                status="Rescheduled"
            )

            updated = dict(
                get_interview(record["id"])
            )

            _send_emails(updated, "rescheduled")

            st.session_state.pop(
                f"rescheduling_{record['id']}",
                None
            )

            st.success("🔄 Interview rescheduled.")

            st.rerun()

    with col2:

        if st.button(
            "Cancel",
            key=f"rcancel_{record['id']}"
        ):

            st.session_state.pop(
                f"rescheduling_{record['id']}",
                None
            )

            st.rerun()


# ============================================================
# INTERVIEW LIST
# ============================================================

def _interview_list(status):

    records = get_interviews(status=status)

    if not records:

        st.info(
            f"No {status.lower()} interviews found."
        )

        return

    for record in records:

        # sqlite3.Row -> dict so .get() works everywhere
        record = dict(record)

        with st.container():

            _show_interview_row(record)

            if st.session_state.get(
                f"editing_{record['id']}"
            ):

                _edit_form(record)

            if st.session_state.get(
                f"rescheduling_{record['id']}"
            ):

                _reschedule_form(record)

            st.divider()


# ============================================================
# REMINDERS
# ============================================================

def _reminder_section():

    st.markdown(
        "### ⏰ Interview Reminders"
    )

    st.caption(
        "Send a reminder email to all candidates with "
        "upcoming (Scheduled/Rescheduled) interviews."
    )

    if st.button(
        "📧 Send Reminders to All Upcoming Interviews",
        type="primary",
        key="interview_scheduler_reminders_button"
    ):

        upcoming = (
            get_interviews(status="Scheduled")
            + get_interviews(status="Rescheduled")
        )

        if not upcoming:

            st.info(
                "No upcoming interviews to remind."
            )

        else:

            sent = 0

            for record in upcoming:

                record = dict(record)

                if record.get("candidate_email"):

                    _send_emails(record, "reminder")

                    sent += 1

            if sent:

                st.success(
                    f"📧 Reminders processed for "
                    f"{sent} interview(s)."
                )

    if not email_configured():

        st.caption(
            "Email service is not configured."
        )


# ============================================================
# MAIN PAGE
# ============================================================

def show():

    st.markdown(
        """
        <div class="main-title">
            🗓 Interview Scheduler
        </div>

        <div class="main-subtitle">
            Schedule, edit, cancel and reschedule
            candidate interviews.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "🗓 Schedule",
            "🟢 Upcoming",
            "🔵 Completed",
            "🔴 Cancelled",
            "⏰ Reminders"
        ]
    )

    with tab1:

        _schedule_form()

    with tab2:

        st.subheader(
            "📌 Upcoming / Scheduled Interviews"
        )

        _interview_list("Scheduled")

        st.subheader(
            "🔄 Rescheduled Interviews"
        )

        _interview_list("Rescheduled")

    with tab3:

        st.subheader(
            "✅ Completed Interviews"
        )

        _interview_list("Completed")

    with tab4:

        st.subheader(
            "🚫 Cancelled Interviews"
        )

        _interview_list("Cancelled")

    with tab5:

        _reminder_section()
