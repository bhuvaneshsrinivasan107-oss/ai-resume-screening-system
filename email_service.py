"""
Email Notification Service
===========================

Sends professional emails for interview and
application-status events using SMTP.

Configuration is read securely from environment
variables or Streamlit secrets - NEVER from the UI
and NEVER hardcoded in source code.

The sender address always comes from SENDER_EMAIL.

If the email service is not configured, emails are
logged as Failed and the caller receives a simple
friendly message.
"""

import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

# Load SMTP credentials from the local .env file.
# Never hardcode credentials in Python code.
load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("email_service")


# ============================================================
# CONFIGURATION
# ============================================================

def _get_secret(key, default=""):
    """Read from Streamlit secrets, then environment."""

    try:

        import streamlit as st

        if st.secrets is not None:

            value = st.secrets.get(key, None)

            if value:
                return value

    except Exception:
        pass

    return os.environ.get(key, default)


def get_smtp_config():
    """
    Return SMTP configuration as a dict.
    Empty values mean SMTP is not configured.
    """

    return {
        "server": _get_secret("SMTP_SERVER"),
        "port": _get_secret("SMTP_PORT", "587"),
        "username": _get_secret("SMTP_USERNAME"),
        "password": _get_secret("SMTP_PASSWORD"),
        "sender": _get_secret("SENDER_EMAIL")
    }


# Placeholder values mean the .env file was not
# filled in yet - treat them as "not configured".
_PLACEHOLDERS = {
    "your_email@gmail.com",
    "your.email@gmail.com",
    "your_gmail_app_password",
    "your_app_password",
    "change_me",
    "change-me",
    "smtp.yourprovider.com",
}


def email_configured():
    """Check whether real email (SMTP) credentials exist.

    Returns False when .env / secrets are missing, values
    are empty, or the user has only left the placeholders.

    This is a developer/admin check only - its result is
    never shown as a detailed SMTP status in the UI.
    """

    config = get_smtp_config()

    required = [
        config["server"],
        config["username"],
        config["password"],
        config["sender"]
    ]

    if any(not v for v in required):

        return False

    cleaned = [
        str(v).strip().lower()
        for v in required
    ]

    return not any(
        v in _PLACEHOLDERS
        for v in cleaned
    )


# Backwards-compatible alias
smtp_configured = email_configured


# ============================================================
# FORMATTING HELPERS
# ============================================================

def format_date(date_str):
    """'2026-08-25' -> '25 August 2026' (best effort)."""

    if not date_str:
        return "TBD"

    for fmt in [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d"
    ]:

        try:

            return datetime.strptime(
                date_str,
                fmt
            ).strftime("%d %B %Y")

        except (ValueError, TypeError):
            continue

    return str(date_str)


def format_time(time_str):
    """'10:30' -> '10:30 AM' (best effort)."""

    if not time_str:
        return "TBD"

    for fmt in [
        "%H:%M",
        "%I:%M %p",
        "%I:%M%p",
        "%H:%M:%S"
    ]:

        try:

            return datetime.strptime(
                time_str,
                fmt
            ).strftime("%I:%M %p")

        except (ValueError, TypeError):
            continue

    return str(time_str)


# ============================================================
# CORE SEND
# ============================================================

def _friendly_error(error):
    """Map an SMTP exception to a useful, safe message.

    Never includes the password or raw credentials.
    """

    import socket

    if isinstance(
        error,
        smtplib.SMTPAuthenticationError
    ):

        return "SMTP authentication failed (check SMTP_USERNAME and SMTP_PASSWORD)"

    if isinstance(
        error,
        (
            smtplib.SMTPConnectError,
            ConnectionRefusedError,
            socket.gaierror,
            socket.timeout,
            TimeoutError
        )
    ):

        return "SMTP server connection failed (server unreachable or refused)"

    if isinstance(
        error,
        smtplib.SMTPRecipientsRefused
    ):

        return "Recipient address is invalid or rejected by the server"

    if isinstance(
        error,
        smtplib.SMTPSenderRefused
    ):

        return "Sender address was rejected by the server"

    if isinstance(
        error,
        smtplib.SMTPServerDisconnected
    ):

        return "SMTP server disconnected unexpectedly"

    if isinstance(
        error,
        ValueError
    ):

        return "SMTP configuration error (invalid server or port)"

    return f"Email sending failed ({type(error).__name__})"


def get_sender_email():
    """Return the configured sender email (SENDER_EMAIL)."""

    return _get_secret("SENDER_EMAIL")


def send_email(to_email, subject, body, event_type="email"):
    """
    Send an email. Returns (success, message).

    Never raises - returns a friendly message
    when the email service is missing or sending fails.

    The result is always logged in the
    notifications table (guarded - a logging
    failure never breaks sending).
    """

    def log_status(status, message=""):

        try:

            from database import log_notification

            log_notification(
                recipient=to_email,
                subject=subject,
                event_type=event_type,
                status=status,
                message=message
            )

        except Exception:

            pass

    if not to_email:

        log_status(
            "Failed",
            "Recipient address is invalid"
        )

        return False, "Recipient address is invalid"

    if "@" not in str(to_email):

        log_status(
            "Failed",
            "Recipient address is invalid"
        )

        return False, "Recipient address is invalid"

    if not email_configured():

        logger.info(
            "Email service not configured - email NOT sent to %s "
            "(subject: %s)",
            to_email,
            subject
        )

        log_status(
            "Skipped",
            "Email service is not configured."
        )

        return False, "Email service is not configured."

    config = get_smtp_config()

    try:

        message = MIMEMultipart("alternative")

        message["From"] = config["sender"]

        message["To"] = to_email

        message["Subject"] = subject

        message.attach(
            MIMEText(body, "plain", "utf-8")
        )

        port = int(config["port"])

        if port == 465:

            server = smtplib.SMTP_SSL(
                config["server"],
                port,
                timeout=30
            )

        else:

            server = smtplib.SMTP(
                config["server"],
                port,
                timeout=30
            )

            server.ehlo()

            server.starttls()

            server.ehlo()

        server.login(
            config["username"],
            config["password"]
        )

        server.sendmail(
            config["sender"],
            [to_email],
            message.as_string()
        )

        server.quit()

        logger.info("Email sent to %s (subject: %s)", to_email, subject)

        log_status("Sent")

        return True, f"Email sent successfully to {to_email}"

    except Exception as e:

        logger.error("Email failed for %s: %s", to_email, e)

        reason = _friendly_error(e)

        log_status(
            "Failed",
            reason
        )

        return False, reason


def _template(candidate_name, details_lines, closing="Please be available at the scheduled time."):
    """Build the common professional email body."""

    body = f"Dear {candidate_name},\n\n"

    body += details_lines

    if closing:

        body += f"\n\n{closing}"

    body += (
        "\n\nRegards,\n"
        "AI Recruiter Team"
    )

    return body


# ============================================================
# INTERVIEW EMAILS
# ============================================================

def send_interview_scheduled_email(candidate_name, candidate_email, details):
    """
    details keys: job_role, interview_date, interview_time,
                  interview_type, location_or_link, duration, notes
    """

    subject = (
        f"Interview Scheduled - "
        f"{details.get('job_role', 'Job Role')}"
    )

    lines = (
        "Your interview has been scheduled.\n\n"
        f"Candidate Name: {candidate_name}\n"
        f"Job Role: {details.get('job_role', 'Job Role')}\n"
        f"Interview Date: {format_date(details.get('interview_date'))}\n"
        f"Interview Time: {format_time(details.get('interview_time'))}\n"
        f"Interview Type: {details.get('interview_type', 'Online')}\n"
    )

    if details.get("location_or_link"):

        lines += f"Meeting/Interview Link: {details['location_or_link']}\n"

    if details.get("interviewer"):

        lines += f"Interviewer: {details['interviewer']}\n"

    if details.get("duration"):

        lines += f"Duration: {details['duration']} minutes\n"

    if details.get("notes"):

        lines += f"Additional Instructions: {details['notes']}\n"

    return send_email(
        candidate_email,
        subject,
        _template(candidate_name, lines),
        event_type="Interview Scheduled"
    )


def send_interview_rescheduled_email(candidate_name, candidate_email, details):
    """details keys: job_role, interview_date, interview_time, notes"""

    subject = (
        f"Interview Rescheduled - "
        f"{details.get('job_role', 'Job Role')}"
    )

    lines = (
        f"Your interview for the {details.get('job_role', 'position')} "
        "position has been rescheduled.\n\n"
        f"Candidate Name: {candidate_name}\n"
        f"Job Role: {details.get('job_role', 'Job Role')}\n"
        f"New Date: {format_date(details.get('interview_date'))}\n"
        f"New Time: {format_time(details.get('interview_time'))}\n"
        f"Interview Type: {details.get('interview_type', 'Online')}\n"
    )

    if details.get("location_or_link"):

        lines += f"Meeting Link: {details['location_or_link']}\n"

    if details.get("interviewer"):

        lines += f"Interviewer: {details['interviewer']}\n"

    if details.get("notes"):

        lines += f"Notes: {details['notes']}\n"

    return send_email(
        candidate_email,
        subject,
        _template(candidate_name, lines),
        event_type="Interview Rescheduled"
    )


def send_interview_cancelled_email(candidate_name, candidate_email, details):
    """details keys: job_role, interview_date, interview_time"""

    subject = (
        f"Interview Cancelled - "
        f"{details.get('job_role', 'Job Role')}"
    )

    lines = (
        f"Your interview for the {details.get('job_role', 'position')} "
        "position has been cancelled.\n\n"
        f"Candidate Name: {candidate_name}\n"
        f"Job Role: {details.get('job_role', 'Job Role')}\n"
        f"Original Date: {format_date(details.get('interview_date'))}\n"
        f"Original Time: {format_time(details.get('interview_time'))}\n"
    )

    return send_email(
        candidate_email,
        subject,
        _template(
            candidate_name,
            lines,
            closing="If you have any questions, please contact the "
            "recruitment team."
        ),
        event_type="Interview Cancelled"
    )


def send_interview_reminder(candidate_name, candidate_email, details):
    """details keys: job_role, interview_date, interview_time,
       interview_type, location_or_link, duration"""

    subject = (
        f"Interview Reminder - "
        f"{details.get('job_role', 'Job Role')}"
    )

    lines = (
        f"This is a friendly reminder about your interview "
        f"for the {details.get('job_role', 'position')} position.\n\n"
        f"Interview Date: {format_date(details.get('interview_date'))}\n"
        f"Interview Time: {format_time(details.get('interview_time'))}\n"
        f"Interview Type: {details.get('interview_type', 'Online')}\n"
    )

    if details.get("location_or_link"):

        lines += f"Meeting Link: {details['location_or_link']}\n"

    if details.get("duration"):

        lines += f"Duration: {details['duration']} minutes\n"

    return send_email(
        candidate_email,
        subject,
        _template(candidate_name, lines),
        event_type="Interview Reminder"
    )


# ============================================================
# INTERVIEW EMAIL DISPATCHER
# ============================================================

def send_interview_email(event, candidate_name, candidate_email, details):
    """
    Send the right interview email for the given event.

    event: "scheduled" | "rescheduled" | "cancelled" | "reminder"

    Returns (success, message).
    """

    if event == "rescheduled":

        return send_interview_rescheduled_email(
            candidate_name,
            candidate_email,
            details
        )

    if event == "cancelled":

        return send_interview_cancelled_email(
            candidate_name,
            candidate_email,
            details
        )

    if event == "reminder":

        return send_interview_reminder(
            candidate_name,
            candidate_email,
            details
        )

    return send_interview_scheduled_email(
        candidate_name,
        candidate_email,
        details
    )


# ============================================================
# STATUS EMAILS
# ============================================================

def send_status_email(candidate_name, candidate_email, job_role, status):
    """
    Send an application status email.

    status: Approved | Pending | Rejected

    The candidate's email always comes from the
    candidates table - never re-entered by the recruiter.
    """

    subject = (
        f"Application Update - "
        f"{job_role}"
    )

    if status == "Approved":

        status_line = (
            "Congratulations! The recruiter has "
            "approved your application."
        )

    elif status == "Rejected":

        status_line = (
            "After careful review, your application "
            "was not selected at this stage. We "
            "appreciate your time and interest."
        )

    else:

        status_line = (
            "Your application is still under review. "
            "We will update you as soon as a decision "
            "is made."
        )

    lines = (
        f"Your application for the {job_role} position "
        "has been reviewed.\n\n"
        f"Current Status: {status}\n\n"
        f"{status_line}"
    )

    return send_email(
        candidate_email,
        subject,
        _template(
            candidate_name,
            lines,
            closing=""
        ),
        event_type="Application Update"
    )


# ============================================================
# DIRECT CANDIDATE EMAIL
# ============================================================

def send_candidate_email(
    candidate_name,
    candidate_email,
    subject,
    message
):
    """Send a direct email to a candidate.

    Recipient: the candidate's email stored in the
    candidates database (never typed by the recruiter).

    Sender: the recruiter's configured SENDER_EMAIL.

    Returns (success, message). Never raises.
    """

    body = (
        f"Dear {candidate_name},\n\n"
        f"{message}\n\n"
        "Regards,\n"
        "AI Recruiter Team"
    )

    return send_email(
        candidate_email,
        subject,
        body,
        event_type="Email to Candidate"
    )


# Backwards-compatible alias
send_candidate_status_email = send_status_email
