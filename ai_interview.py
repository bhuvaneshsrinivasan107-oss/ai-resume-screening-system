"""
AI Interview Simulator
======================

Independent extra feature that generates interview
questions from a job description, evaluates typed
answers, scores each response and produces a final
performance report.

Works offline with a rule-based question bank and
keyword evaluation - no API key required. If an AI
API is added later, only `generate_questions` and
`evaluate_answer` need to change.
"""

import re
import random
import streamlit as st

from resume_parser import extract_skills


# ============================================================
# QUESTION BANK
# ============================================================

QUESTION_BANK = {

    "Technical": [
        {
            "q": "Explain the difference between INNER JOIN and LEFT JOIN in SQL.",
            "keywords": ["inner", "left", "unmatched", "null", "rows"]
        },
        {
            "q": "What is the difference between a list and a tuple in Python?",
            "keywords": ["mutable", "immutable", "change", "modify"]
        },
        {
            "q": "Explain what an index is in a database.",
            "keywords": ["speed", "query", "faster", "search", "performance"]
        },
        {
            "q": "What is normalization in databases?",
            "keywords": ["redundancy", "duplication", "data", "consistent", "forms"]
        },
        {
            "q": "What is a primary key in a database table?",
            "keywords": ["unique", "identify", "record", "row"]
        },
        {
            "q": "Explain Big O notation and why it matters.",
            "keywords": ["complexity", "performance", "growth", "algorithm"]
        },
        {
            "q": "What is a DataFrame in pandas?",
            "keywords": ["table", "rows", "columns", "tabular", "data"]
        },
        {
            "q": "Explain what version control (git) is and why teams use it.",
            "keywords": ["track", "changes", "branch", "merge", "collaborate"]
        }
    ],

    "Behavioral": [
        {
            "q": "Tell me about a time you worked successfully in a team.",
            "keywords": ["team", "collaborated", "together", "goal", "contributed"]
        },
        {
            "q": "Describe a time you had a conflict with a colleague. How did you handle it?",
            "keywords": ["conflict", "listened", "resolved", "solution", "calm"]
        },
        {
            "q": "Tell me about a time you failed at something. What did you learn?",
            "keywords": ["failed", "learned", "lesson", "improved", "reflected"]
        },
        {
            "q": "How do you handle tight deadlines and pressure?",
            "keywords": ["deadline", "prioritize", "plan", "calm", "focused"]
        }
    ],

    "Situational": [
        {
            "q": "You discover a bug in production. What is your first action?",
            "keywords": ["assess", "impact", "report", "fix", "test", "communicate"]
        },
        {
            "q": "Your manager assigns a task you have never done before. What do you do?",
            "keywords": ["ask", "learn", "research", "communicate", "steps"]
        },
        {
            "q": "A client changes requirements in the middle of a project. How do you respond?",
            "keywords": ["clarify", "communicate", "scope", "adapt", "plan"]
        }
    ],

    "HR": [
        {
            "q": "Tell me about yourself.",
            "keywords": ["experience", "skills", "role", "interest", "career"]
        },
        {
            "q": "Why do you want to work for this company?",
            "keywords": ["company", "growth", "culture", "opportunity", "learn"]
        },
        {
            "q": "What are your key strengths?",
            "keywords": ["strength", "skill", "example", "achievement"]
        },
        {
            "q": "Where do you see yourself in five years?",
            "keywords": ["growth", "career", "role", "learn", "goal"]
        }
    ]
}


# ============================================================
# ROLE-SPECIFIC QUESTIONS
# ============================================================

ROLE_QUESTIONS = {
    "sql": {
        "q": "Write/explain a query that finds duplicate records in a table.",
        "keywords": ["group by", "having", "count", "where", "duplicate"]
    },
    "python": {
        "q": "Explain list comprehension in Python with an example.",
        "keywords": ["expression", "loop", "concise", "iterate", "syntax"]
    },
    "excel": {
        "q": "Explain VLOOKUP / XLOOKUP and when you would use it.",
        "keywords": ["lookup", "column", "table", "match", "value"]
    },
    "power bi": {
        "q": "What is the difference between a measure and a calculated column in Power BI?",
        "keywords": ["measure", "calculated", "aggregation", "row", "filter"]
    },
    "machine learning": {
        "q": "Explain the difference between training, validation and test data.",
        "keywords": ["train", "validation", "test", "evaluate", "overfit"]
    },
    "deep learning": {
        "q": "What is a neural network and how does backpropagation work?",
        "keywords": ["layers", "weights", "error", "gradient", "backpropagation"]
    },
    "java": {
        "q": "Explain the difference between an interface and an abstract class in Java.",
        "keywords": ["interface", "abstract", "implements", "extends", "methods"]
    },
    "javascript": {
        "q": "Explain the difference between let, const and var in JavaScript.",
        "keywords": ["block", "scope", "reassign", "const", "hoisting"]
    },
    "statistics": {
        "q": "What is the difference between correlation and causation?",
        "keywords": ["correlation", "causation", "relationship", "confound"]
    },
    "git": {
        "q": "Explain how you would resolve a merge conflict in git.",
        "keywords": ["merge", "conflict", "resolve", "branch", "commit"]
    }
}


# ============================================================
# INTERVIEW GENERATION
# ============================================================

DIFFICULTY_COUNTS = {
    "Easy": 5,
    "Medium": 7,
    "Hard": 9
}


def generate_questions(job_role, job_description, difficulty):
    """
    Generate a question list for an interview.

    Returns a list of dicts:
        {category, question, keywords}
    """

    questions = []

    # 1. Role-specific questions from the job description
    skills = extract_skills(job_description)

    for skill in skills:

        if skill in ROLE_QUESTIONS and len(questions) < 3:

            item = dict(ROLE_QUESTIONS[skill])

            item["category"] = "Role-specific"

            questions.append(item)

    # 2. Fill from the generic bank by category
    count = DIFFICULTY_COUNTS.get(difficulty, 7)

    category_order = ["Technical", "Behavioral", "Situational", "HR"]

    rng = random.Random()

    for category in category_order:

        if len(questions) >= count:
            break

        pool = QUESTION_BANK.get(category, [])

        rng.shuffle(pool)

        for item in pool:

            if len(questions) >= count:
                break

            question = dict(item)

            question["category"] = category

            questions.append(question)

    return questions


# ============================================================
# ANSWER EVALUATION
# ============================================================

def evaluate_answer(answer, question):
    """
    Score a candidate answer 0-10 with feedback.

    Returns: (score, feedback)
    """

    answer_lower = answer.lower().strip()

    words = len(re.findall(r"\b\w+\b", answer_lower))

    keywords = question.get("keywords", [])

    hits = []

    for keyword in keywords:

        if keyword in answer_lower:

            hits.append(keyword)

    # Base score from keyword coverage
    # (full coverage of a small keyword set is
    #  worth 8 before any length bonus)
    score = min(8, 2 + len(hits) * 1.5)

    # Length bonus (a real answer needs some detail)
    if words >= 40:
        score += 2
    elif words >= 20:
        score += 1

    # Cap and round
    score = round(min(10, max(1, score)))

    # Feedback
    feedback = []

    if hits:

        feedback.append(
            "Good - you covered key points: "
            + ", ".join(hits)
            + "."
        )

    else:

        feedback.append(
            "Your answer was brief and missed the key "
            "concepts expected for this question."
        )

    missing = [k for k in keywords if k not in answer_lower]

    if missing:

        feedback.append(
            "Consider mentioning: "
            + ", ".join(missing[:4])
            + "."
        )

    if words < 20:

        feedback.append(
            "Provide more detail and a practical example."
        )

    elif words < 40:

        feedback.append(
            "Good length - add a concrete example "
            "to strengthen the answer."
        )

    return score, " ".join(feedback)


# ============================================================
# CATEGORY MAPPING
# ============================================================

def performance_area(category):
    """Map question category to a performance area."""

    mapping = {
        "Technical": "Technical",
        "Role-specific": "Technical",
        "Behavioral": "Communication",
        "HR": "Communication",
        "Situational": "Problem Solving"
    }

    return mapping.get(category, "Technical")


# ============================================================
# FINAL REPORT
# ============================================================

def build_report(answers):
    """
    Build the final performance report from the
    list of (question, answer, score) tuples.
    """

    areas = {}

    for question, answer, score in answers:

        area = performance_area(question.get("category", "Technical"))

        areas.setdefault(area, []).append(score)

    area_scores = {}

    for area, scores in areas.items():

        area_scores[area] = round(
            sum(scores) / len(scores) * 10
        )

    all_scores = [a[2] for a in answers]

    overall = (
        round(sum(all_scores) / len(all_scores) * 10)
        if all_scores else 0
    )

    # Strengths
    strengths = []

    for question, answer, score in answers:

        if score >= 8:

            strengths.append(
                question.get("q", "").split("?")[0][:60]
            )

    # Weak areas
    weak_areas = []

    for area, value in area_scores.items():

        if value < 70:

            weak_areas.append(area)

    # Improvement
    improvement = []

    for area, value in area_scores.items():

        if value < 75:

            improvement.append(
                f"Improve {area.lower()} skills with "
                "structured practice."
            )

    if len(all_scores) >= 3 and min(all_scores) <= 5:

        improvement.append(
            "Answer with examples and more structure "
            "to score higher."
        )

    # Recommendation
    if overall >= 80:

        recommendation = "Strong Hire - highly recommended."

    elif overall >= 65:

        recommendation = "Hire - good fit with minor development areas."

    elif overall >= 50:

        recommendation = "Consider - needs further evaluation."

    else:

        recommendation = "Not recommended at this stage."

    return {
        "area_scores": area_scores,
        "overall": overall,
        "strengths": strengths[:5],
        "weak_areas": weak_areas,
        "improvement": improvement,
        "recommendation": recommendation
    }


# ============================================================
# UI - SETUP
# ============================================================

def _setup_form():

    st.markdown(
        "### ⚙️ Configure Your Interview"
    )

    col1, col2 = st.columns(2)

    with col1:

        job_role = st.text_input(
            "💼 Job Role",
            placeholder="Example: Data Analyst",
            key="ai_interview_job_role_input"
        )

    with col2:

        difficulty = st.radio(
            "🎚 Interview Difficulty",
            ["Easy", "Medium", "Hard"],
            horizontal=True,
            key="ai_interview_difficulty"
        )

    job_description = st.text_area(
        "📝 Job Description",
        height=150,
        placeholder=(
            "Paste the job description. The simulator "
            "will generate role-specific questions "
            "from the required skills."
        ),
        key="ai_interview_job_description"
    )

    if st.button(
        "🚀 Start AI Interview",
        type="primary",
        use_container_width=True,
        key="ai_interview_start_btn"
    ):

        if not job_description.strip():

            st.warning(
                "⚠️ Please enter the job description."
            )

        else:

            questions = generate_questions(
                job_role,
                job_description,
                difficulty
            )

            if not questions:

                st.error(
                    "❌ Could not generate questions. "
                    "Please try again."
                )

            else:

                st.session_state["ai_questions"] = questions

                st.session_state["ai_index"] = 0

                st.session_state["ai_answers"] = []

                st.session_state["ai_done"] = False

                st.session_state["ai_job_role"] = job_role.strip()

                st.session_state["ai_difficulty"] = difficulty

                st.session_state["ai_saved"] = False

                st.rerun()


# ============================================================
# UI - INTERVIEW LOOP
# ============================================================

def _interview_loop():

    questions = st.session_state["ai_questions"]

    index = st.session_state["ai_index"]

    total = len(questions)

    st.progress(
        index / total
    )

    st.caption(
        f"Question {index + 1} of {total}"
    )

    question = questions[index]

    st.markdown(
        f"### 🤔 {question['q']}"
    )

    st.caption(
        f"Category: {question['category']}"
    )

    answer = st.text_area(
        "✍️ Your Answer",
        key=f"ai_answer_{index}",
        height=120,
        placeholder="Type your answer here..."
    )

    if st.button(
        "✅ Submit Answer",
        type="primary",
        key=f"ai_submit_{index}"
    ):

        if not answer.strip():

            st.warning(
                "⚠️ Please type an answer before continuing."
            )

        else:

            score, feedback = evaluate_answer(
                answer,
                question
            )

            st.session_state["ai_answers"].append(
                (question, answer, score)
            )

            st.info(
                f"**Score: {score}/10**"
            )

            st.success(
                f"**Feedback:** {feedback}"
            )

            if index + 1 >= total:

                st.session_state["ai_done"] = True

                st.rerun()

            else:

                st.session_state["ai_index"] = index + 1

                st.rerun()


# ============================================================
# UI - REPORT
# ============================================================

def _report():

    answers = st.session_state["ai_answers"]

    report = build_report(answers)

    st.markdown(
        "### 📊 Interview Performance"
    )

    area_scores = report["area_scores"]

    col1, col2, col3, col4 = st.columns(4)

    areas = [
        ("Technical", "Technical"),
        ("Communication", "Communication"),
        ("Problem Solving", "Problem Solving"),
        ("Overall", "Overall")
    ]

    with col1:

        st.metric(
            "🛠 Technical",
            f"{area_scores.get('Technical', 0)}%"
        )

    with col2:

        st.metric(
            "🗣 Communication",
            f"{area_scores.get('Communication', 0)}%"
        )

    with col3:

        st.metric(
            "🧩 Problem Solving",
            f"{area_scores.get('Problem Solving', 0)}%"
        )

    with col4:

        st.metric(
            "🎯 Overall",
            f"{report['overall']}%"
        )

    st.divider()

    st.markdown(
        "### 💪 Strengths"
    )

    if report["strengths"]:

        for strength in report["strengths"]:

            st.success(f"✅ {strength}")

    else:

        st.info(
            "Practice delivering more detailed answers."
        )

    st.markdown(
        "### 📈 Areas for Improvement"
    )

    if report["improvement"]:

        for item in report["improvement"]:

            st.warning(f"⚠️ {item}")

    else:

        st.success(
            "No major improvement areas identified."
        )

    st.markdown(
        "### 🎯 Final Recommendation"
    )

    st.info(
        f"**{report['recommendation']}**"
    )

    # ------------------------------------------------
    # SAVE RESULT TO DATABASE (once per interview)
    # ------------------------------------------------

    if not st.session_state.get("ai_saved"):

        st.session_state["ai_saved"] = True

        try:

            from database import save_interview_result

            save_interview_result(
                candidate_name=st.session_state.get(
                    "name", ""
                ),
                candidate_email=st.session_state.get(
                    "email", ""
                ),
                job_role=st.session_state.get(
                    "ai_job_role", ""
                ),
                difficulty=st.session_state.get(
                    "ai_difficulty", ""
                ),
                technical_score=area_scores.get(
                    "Technical", 0
                ),
                communication_score=area_scores.get(
                    "Communication", 0
                ),
                problem_solving_score=area_scores.get(
                    "Problem Solving", 0
                ),
                overall_score=report["overall"],
                strengths=", ".join(
                    report["strengths"]
                ),
                weak_areas=", ".join(
                    report["weak_areas"]
                ),
                recommendation=report["recommendation"]
            )

            st.success(
                "💾 Interview result saved to the "
                "system database."
            )

        except Exception as e:

            st.caption(
                f"ℹ️ Result could not be saved: {e}"
            )

    if st.button(
        "🔄 Start New Interview",
        use_container_width=True,
        key="ai_interview_restart_btn"
    ):

        for key in [
            "ai_questions",
            "ai_index",
            "ai_answers",
            "ai_done",
            "ai_job_role",
            "ai_difficulty",
            "ai_saved"
        ]:

            if key in st.session_state:

                del st.session_state[key]

        st.rerun()


# ============================================================
# MAIN PAGE
# ============================================================

def show():

    st.markdown(
        """
        <div class="main-title">
            🎤 AI Interview Simulator
        </div>

        <div class="main-subtitle">
            Generate interview questions, evaluate your
            answers and get a full performance report.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    if st.session_state.get("ai_done"):

        _report()

    elif st.session_state.get("ai_questions"):

        _interview_loop()

    else:

        _setup_form()
