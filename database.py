import os
import re
import sqlite3
import pandas as pd
import hashlib
import secrets
from datetime import datetime

# ============================================================
# DATABASE CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_FOLDER = os.path.join(
    BASE_DIR,
    "database"
)

DATABASE_FILE = os.path.join(
    DATABASE_FOLDER,
    "candidates.db"
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    """
    Create and return SQLite database connection.
    """

    os.makedirs(
        DATABASE_FOLDER,
        exist_ok=True
    )

    conn = sqlite3.connect(
        DATABASE_FILE,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# PASSWORD HASHING
# ============================================================

def hash_password(password):
    """
    Hash a plain-text password using PBKDF2-SHA256
    with a random salt. Returns "pbkdf2$salt$digest".
    """

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        100_000
    ).hex()

    return f"pbkdf2${salt}${digest}"


def check_password(password, stored):
    """
    Verify a plain-text password against a stored
    hash. Returns False for legacy plain-text rows.
    """

    try:

        _, salt, expected = stored.split("$")

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            100_000
        ).hex()

        return digest == expected

    except Exception:

        return False


# ============================================================
# SEED DEMO USERS
# ============================================================

def seed_demo_users(cursor):
    """
    Insert demo recruiter and candidate accounts
    if they do not already exist. Passwords hashed.
    """

    demo_users = [
        (
            "recruiter",
            "recruiter123",
            "Demo Recruiter",
            "recruiter@example.com",
            "recruiter"
        ),
        (
            "candidate",
            "candidate123",
            "Demo Candidate",
            "candidate@example.com",
            "candidate"
        ),
        (
            "arun",
            "arun123",
            "Arun Kumar",
            "arun-kumar@email.com",
            "candidate"
        ),
        (
            "priya",
            "priya123",
            "Priya Sharma",
            "priya.sharma@email.com",
            "candidate"
        ),
        (
            "rahul",
            "rahul123",
            "Rahul Verma",
            "rahul.verma@email.com",
            "candidate"
        )
    ]

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    for (
        username,
        password,
        name,
        email,
        role
    ) in demo_users:

        cursor.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE LOWER(username) = LOWER(?)
               OR LOWER(email) = LOWER(?)
        """, (
            username,
            email
        ))

        if cursor.fetchone()[0] == 0:

            cursor.execute("""
                INSERT INTO users (
                    username,
                    password,
                    name,
                    email,
                    role,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                username,
                hash_password(password),
                name,
                email,
                role,
                created_at
            ))


# ============================================================
# CREATE / UPGRADE DATABASE
# ============================================================

def create_database():
    """
    Create candidates table if it does not exist.

    Also upgrades older database versions by adding
    missing columns automatically.
    """

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT DEFAULT 'Unknown Candidate',

            email TEXT DEFAULT 'Not Found',

            phone TEXT DEFAULT 'Not Found',

            skills TEXT DEFAULT '',

            resume_text TEXT DEFAULT '',

            filename TEXT DEFAULT '',

            score REAL DEFAULT 0,

            status TEXT DEFAULT 'Pending',

            job_role TEXT DEFAULT '',

            matched_skills TEXT DEFAULT '',

            missing_skills TEXT DEFAULT '',

            uploaded_by TEXT DEFAULT '',

            uploaded_at TEXT DEFAULT ''

        )
    """)

    # --------------------------------------------------------
    # Users table for candidate accounts
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            name TEXT DEFAULT '',

            email TEXT DEFAULT '',

            role TEXT DEFAULT 'candidate',

            created_at TEXT DEFAULT ''

        )
    """)

    # Unique email for user accounts
    try:

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_users_email ON users(email)"
        )

    except sqlite3.OperationalError:
        pass

    # --------------------------------------------------------
    # Interviews table (extra feature - Interview Scheduler)
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interviews (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            candidate_id INTEGER DEFAULT 0,

            candidate_name TEXT DEFAULT '',

            candidate_email TEXT DEFAULT '',

            job_role TEXT DEFAULT '',

            interview_date TEXT DEFAULT '',

            interview_time TEXT DEFAULT '',

            interview_type TEXT DEFAULT 'Online',

            location_or_link TEXT DEFAULT '',

            duration INTEGER DEFAULT 30,

            notes TEXT DEFAULT '',

            status TEXT DEFAULT 'Scheduled',

            created_at TEXT DEFAULT ''

        )
    """)

    conn.commit()

    # --------------------------------------------------------
    # Interview results table (extra feature -
    # AI Interview Simulator)
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interview_results (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            candidate_name TEXT DEFAULT '',

            candidate_email TEXT DEFAULT '',

            job_role TEXT DEFAULT '',

            difficulty TEXT DEFAULT '',

            technical_score INTEGER DEFAULT 0,

            communication_score INTEGER DEFAULT 0,

            problem_solving_score INTEGER DEFAULT 0,

            overall_score INTEGER DEFAULT 0,

            strengths TEXT DEFAULT '',

            weak_areas TEXT DEFAULT '',

            recommendation TEXT DEFAULT '',

            created_at TEXT DEFAULT ''

        )
    """)

    # --------------------------------------------------------
    # Notifications log table (extra feature -
    # Email Notifications)
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            recipient TEXT DEFAULT '',

            subject TEXT DEFAULT '',

            event_type TEXT DEFAULT '',

            status TEXT DEFAULT 'Pending',

            message TEXT DEFAULT '',

            created_at TEXT DEFAULT ''

        )
    """)

    conn.commit()

    seed_demo_users(cursor)

    conn.commit()

    # --------------------------------------------------------
    # Automatically upgrade old database
    # --------------------------------------------------------

    cursor.execute(
        "PRAGMA table_info(candidates)"
    )

    existing_columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    required_columns = {

        "name": "TEXT DEFAULT 'Unknown Candidate'",

        "email": "TEXT DEFAULT 'Not Found'",

        "phone": "TEXT DEFAULT 'Not Found'",

        "skills": "TEXT DEFAULT ''",

        "resume_text": "TEXT DEFAULT ''",

        "filename": "TEXT DEFAULT ''",

        "score": "REAL DEFAULT 0",

        "status": "TEXT DEFAULT 'Pending'",

        "job_role": "TEXT DEFAULT ''",

        "matched_skills": "TEXT DEFAULT ''",

        "missing_skills": "TEXT DEFAULT ''",

        "uploaded_by": "TEXT DEFAULT ''",

        "uploaded_at": "TEXT DEFAULT ''"
    }

    for column, definition in required_columns.items():

        if column not in existing_columns:

            try:

                cursor.execute(
                    f"""
                    ALTER TABLE candidates
                    ADD COLUMN {column} {definition}
                    """
                )

            except sqlite3.OperationalError:
                pass

    conn.commit()

    conn.close()


# ============================================================
# ADD CANDIDATE
# ============================================================

def add_candidate(
    candidate,
    filename,
    score,
    status,
    job_role,
    matched_skills,
    missing_skills,
    uploaded_by="recruiter"
):

    conn = get_connection()

    cursor = conn.cursor()

    uploaded_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor.execute("""
        INSERT INTO candidates (

            name,
            email,
            phone,
            skills,
            resume_text,
            filename,
            score,
            status,
            job_role,
            matched_skills,
            missing_skills,
            uploaded_by,
            uploaded_at

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        candidate.get(
            "name",
            "Unknown Candidate"
        ),

        candidate.get(
            "email",
            "Not Found"
        ),

        candidate.get(
            "phone",
            "Not Found"
        ),

        ", ".join(
            candidate.get(
                "skills",
                []
            )
        ),

        candidate.get(
            "resume_text",
            ""
        ),

        filename,

        float(score),

        status,

        job_role,

        ", ".join(
            matched_skills
        ),

        ", ".join(
            missing_skills
        ),

        uploaded_by,

        uploaded_at
    ))

    candidate_id = cursor.lastrowid

    conn.commit()

    conn.close()

    # Automatically create candidate login account
    # associated with the extracted resume email
    try:

        ensure_candidate_account(
            candidate.get(
                "name",
                "Unknown Candidate"
            ),
            candidate.get(
                "email",
                ""
            )
        )

    except Exception:
        pass

    return candidate_id


# ============================================================
# GET ALL CANDIDATES
# ============================================================
def get_candidates():
    conn = sqlite3.connect(DATABASE_FILE)

    query = """
        SELECT
            id,
            name,
            email,
            phone,
            skills,
            resume_text,
            filename,
            score,
            status,
            job_role,
            matched_skills,
            missing_skills,
            uploaded_by,
            uploaded_at
        FROM candidates
        ORDER BY score DESC
    """

    df = pd.read_sql_query(query, conn)

    conn.close()

    return df

# ============================================================
# GET CANDIDATES BY EMAIL
# ============================================================

def get_candidate_by_email(email):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM candidates
        WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))
        ORDER BY uploaded_at DESC
    """, (email,))

    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


# ============================================================
# GET CANDIDATE
# ============================================================

def get_candidate(candidate_id):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM candidates
        WHERE id = ?
    """, (candidate_id,))

    row = cursor.fetchone()

    conn.close()

    if row is None:

        return None

    return dict(row)


# ============================================================
# UPDATE STATUS
# ============================================================

def update_candidate_status(
    candidate_id,
    status
):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        UPDATE candidates
        SET status = ?
        WHERE id = ?
    """, (
        status,
        candidate_id
    ))

    conn.commit()

    conn.close()


# ============================================================
# DELETE CANDIDATE
# ============================================================

def delete_candidate(candidate_id):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM candidates
        WHERE id = ?
    """, (
        candidate_id,
    ))

    conn.commit()

    conn.close()


# ============================================================
# CLEAR ALL
# ============================================================

def clear_all_candidates():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM candidates"
    )

    conn.commit()

    conn.close()


# ============================================================
# DATABASE COUNT
# ============================================================

def get_candidate_count():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM candidates"
    )

    count = cursor.fetchone()[0]

    conn.close()

    return count


# ============================================================
# REGISTER USER
# ============================================================

def register_user(
    username,
    password,
    name,
    email,
    role="candidate"
):
    """
    Create a new user account. The plain-text
    password is hashed before being stored.
    """

    conn = get_connection()

    cursor = conn.cursor()

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor.execute("""
        INSERT INTO users (
            username,
            password,
            name,
            email,
            role,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        username,
        hash_password(password),
        name,
        email,
        role,
        created_at
    ))

    user_id = cursor.lastrowid

    conn.commit()

    conn.close()

    return user_id


# ============================================================
# GET USER BY USERNAME
# ============================================================

def get_user(username):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE LOWER(TRIM(username)) = LOWER(TRIM(?))
    """, (username,))

    row = cursor.fetchone()

    conn.close()

    if row is None:

        return None

    return dict(row)


# ============================================================
# GET USER BY EMAIL
# ============================================================

def get_user_by_email(email):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))
    """, (email,))

    row = cursor.fetchone()

    conn.close()

    if row is None:

        return None

    return dict(row)


# ============================================================
# CHECK USERNAME EXISTS
# ============================================================

def username_exists(username):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM users
        WHERE LOWER(TRIM(username)) = LOWER(TRIM(?))
    """, (username,))

    count = cursor.fetchone()[0]

    conn.close()

    return count > 0


# ============================================================
# CHECK EMAIL EXISTS
# ============================================================

def email_exists(email):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM users
        WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))
    """, (email,))

    count = cursor.fetchone()[0]

    conn.close()

    return count > 0


# ============================================================
# ENSURE CANDIDATE ACCOUNT
# ============================================================

def ensure_candidate_account(name, email):
    """
    Automatically create a candidate login account
    for an extracted resume email. Called after a
    recruiter processes a resume.

    Default password: candidate123
    Username: local part of the email.
    """

    if not email or "@" not in email:

        return None

    email = email.strip().lower()

    existing = get_user_by_email(email)

    if existing:

        return existing["id"]

    local = email.split("@")[0]

    username = local

    counter = 1

    while username_exists(username):

        username = f"{local}{counter}"

        counter += 1

    return register_user(
        username=username,
        password="candidate123",
        name=name,
        email=email,
        role="candidate"
    )


# ============================================================
# INTERVIEWS - SCHEDULE
# ============================================================

def add_interview(
    candidate_id,
    candidate_name,
    candidate_email,
    job_role,
    interview_date,
    interview_time,
    interview_type,
    location_or_link,
    duration,
    notes,
    status="Scheduled"
):

    conn = get_connection()

    cursor = conn.cursor()

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor.execute("""
        INSERT INTO interviews (
            candidate_id,
            candidate_name,
            candidate_email,
            job_role,
            interview_date,
            interview_time,
            interview_type,
            location_or_link,
            duration,
            notes,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        candidate_id,
        candidate_name,
        candidate_email,
        job_role,
        interview_date,
        interview_time,
        interview_type,
        location_or_link,
        duration,
        notes,
        status,
        created_at
    ))

    interview_id = cursor.lastrowid

    conn.commit()

    conn.close()

    return interview_id


# ============================================================
# INTERVIEWS - GET ALL
# ============================================================

def get_interviews(status=None):

    conn = get_connection()

    cursor = conn.cursor()

    if status:

        cursor.execute("""
            SELECT *
            FROM interviews
            WHERE LOWER(TRIM(status)) = LOWER(TRIM(?))
            ORDER BY interview_date DESC, interview_time DESC
        """, (status,))

    else:

        cursor.execute("""
            SELECT *
            FROM interviews
            ORDER BY interview_date DESC, interview_time DESC
        """)

    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


# ============================================================
# INTERVIEWS - GET BY ID
# ============================================================

def get_interview(interview_id):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM interviews
        WHERE id = ?
    """, (interview_id,))

    row = cursor.fetchone()

    conn.close()

    if row is None:

        return None

    return dict(row)


# ============================================================
# INTERVIEWS - UPDATE
# ============================================================

def update_interview(
    interview_id,
    candidate_name,
    candidate_email,
    job_role,
    interview_date,
    interview_time,
    interview_type,
    location_or_link,
    duration,
    notes,
    status
):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        UPDATE interviews
        SET candidate_name = ?,
            candidate_email = ?,
            job_role = ?,
            interview_date = ?,
            interview_time = ?,
            interview_type = ?,
            location_or_link = ?,
            duration = ?,
            notes = ?,
            status = ?
        WHERE id = ?
    """, (
        candidate_name,
        candidate_email,
        job_role,
        interview_date,
        interview_time,
        interview_type,
        location_or_link,
        duration,
        notes,
        status,
        interview_id
    ))

    conn.commit()

    conn.close()


# ============================================================
# INTERVIEWS - UPDATE STATUS
# ============================================================

def update_interview_status(
    interview_id,
    status
):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        UPDATE interviews
        SET status = ?
        WHERE id = ?
    """, (
        status,
        interview_id
    ))

    conn.commit()

    conn.close()


# ============================================================
# INTERVIEWS - DELETE
# ============================================================

def delete_interview(interview_id):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM interviews
        WHERE id = ?
    """, (interview_id,))

    conn.commit()

    conn.close()


# ============================================================
# INTERVIEW RESULTS - SAVE
# ============================================================

def save_interview_result(
    candidate_name="",
    candidate_email="",
    job_role="",
    difficulty="",
    technical_score=0,
    communication_score=0,
    problem_solving_score=0,
    overall_score=0,
    strengths="",
    weak_areas="",
    recommendation=""
):

    from datetime import datetime

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO interview_results (
            candidate_name,
            candidate_email,
            job_role,
            difficulty,
            technical_score,
            communication_score,
            problem_solving_score,
            overall_score,
            strengths,
            weak_areas,
            recommendation,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        candidate_name,
        candidate_email,
        job_role,
        difficulty,
        technical_score,
        communication_score,
        problem_solving_score,
        overall_score,
        strengths,
        weak_areas,
        recommendation,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()

    conn.close()


# ============================================================
# INTERVIEW RESULTS - GET
# ============================================================

def get_interview_results(
    candidate_email=None,
    limit=50
):

    conn = get_connection()

    cursor = conn.cursor()

    if candidate_email:

        cursor.execute("""
            SELECT * FROM interview_results
            WHERE LOWER(TRIM(candidate_email)) =
                  LOWER(TRIM(?))
            ORDER BY id DESC
            LIMIT ?
        """, (candidate_email, limit))

    else:

        cursor.execute("""
            SELECT * FROM interview_results
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()

    conn.close()

    return rows


# ============================================================
# NOTIFICATIONS - LOG
# ============================================================

def log_notification(
    recipient,
    subject,
    event_type,
    status,
    message=""
):

    from datetime import datetime

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO notifications (
            recipient,
            subject,
            event_type,
            status,
            message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        recipient,
        subject,
        event_type,
        status,
        message,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()

    conn.close()


# ============================================================
# NOTIFICATIONS - GET
# ============================================================

def get_notifications(limit=50):

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM notifications
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()

    conn.close()

    return rows


# ============================================================
# INITIALIZE DATABASE
# ============================================================

create_database()