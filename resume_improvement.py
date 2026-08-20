"""
AI Resume Improvement
=====================

Independent extra feature that analyzes an uploaded
resume, scores it, checks ATS compatibility, and
suggests improvements.

The original resume is NEVER overwritten - improved
sections and the analysis report can be downloaded.

Works offline with a rule-based analyzer. If an AI
API is added later, only the suggestion builders
need to change.
"""

import re
import streamlit as st

from resume_parser import (
    extract_text,
    extract_skills,
    extract_candidate_details
)


# ============================================================
# SECTION DETECTION
# ============================================================

SECTION_KEYWORDS = {
    "Summary": ["summary", "profile", "objective", "about"],
    "Skills": ["skills", "technical skills", "core competencies"],
    "Experience": ["experience", "employment", "work history", "work"],
    "Education": ["education", "academic", "qualification"],
    "Projects": ["projects", "project"],
    "Certifications": ["certification", "certifications", "courses"]
}


def detect_sections(text):
    """Return a dict of section -> bool (present or not)."""

    text_lower = text.lower()

    detected = {}

    for section, keywords in SECTION_KEYWORDS.items():

        detected[section] = any(
            keyword in text_lower
            for keyword in keywords
        )

    return detected


# ============================================================
# GRAMMAR / QUALITY CHECKS
# ============================================================

def grammar_checks(text):
    """Return a list of grammar and writing issues."""

    issues = []

    if re.search(r"\s{2,}", text):

        issues.append(
            "Multiple consecutive spaces found - use single spaces."
        )

    if re.search(r"\b(\w+) \1\b", text, re.IGNORECASE):

        issues.append(
            "Repeated words found (e.g. 'the the')."
        )

    if re.search(r"\bi\b(?!\w)", text):

        issues.append(
            "The pronoun 'i' should be capitalized as 'I'."
        )

    if re.search(r"\bcant\b|\bdont\b|\bwont\b|\bisnt\b|\bdoesnt\b",
                 text, re.IGNORECASE):

        issues.append(
            "Missing apostrophes found (e.g. 'dont' -> \"don't\")."
        )

    if re.search(r"\bteh\b|\brecieve\b|\bseperat\b|\baccomodate\b|\bdefinately\b",
                 text, re.IGNORECASE):

        issues.append(
            "Possible spelling mistakes found."
        )

    if not issues:

        issues.append(
            "No obvious grammar issues detected."
        )

    return issues


def formatting_checks(text):
    """Return a list of formatting suggestions."""

    suggestions = []

    lines = text.splitlines()

    long_lines = [
        line for line in lines
        if len(line) > 100
    ]

    if len(long_lines) > len(lines) * 0.3:

        suggestions.append(
            "Keep lines under 100 characters for readability."
        )

    bullets = sum(
        1 for line in lines
        if line.strip().startswith(("-", "*", "•"))
    )

    if bullets < 5:

        suggestions.append(
            "Use bullet points for skills and achievements "
            "to improve ATS readability."
        )

    if len(text.split()) < 300:

        suggestions.append(
            "Consider expanding the resume - one page may be "
            "too short for detailed experience."
        )

    if not suggestions:

        suggestions.append(
            "Formatting looks good."
        )

    return suggestions


# ============================================================
# MAIN ANALYSIS
# ============================================================

def analyze_resume(text, job_description=""):
    """
    Analyze a resume and return a full report dict.
    """

    text_clean = " ".join(text.split())

    sections = detect_sections(text)

    skills = extract_skills(text)

    issues = grammar_checks(text)

    formatting = formatting_checks(text)

    # ------------------------------------------------
    # RESUME SCORE (presence + content quality)
    # ------------------------------------------------

    present = sum(1 for v in sections.values() if v)

    structure_score = round(present / len(sections) * 45)

    quality_score = 0

    if len(text.split()) > 300:
        quality_score += 10
    elif len(text.split()) > 150:
        quality_score += 5

    if len(skills) >= 6:
        quality_score += 15
    elif len(skills) >= 3:
        quality_score += 8

    if issues == ["No obvious grammar issues detected."]:
        quality_score += 15
    else:
        quality_score += min(10, max(0, 15 - 3 * len(issues)))

    if bullets_score(text) >= 5:
        quality_score += 10
    else:
        quality_score += 5

    if any(k in text.lower() for k in
           ["achieved", "increased", "reduced", "improved", "managed"]):
        quality_score += 5

    resume_score = min(100, structure_score + quality_score)

    # ------------------------------------------------
    # ATS / JOB DESCRIPTION MATCH
    # ------------------------------------------------

    ats_score = None

    matched = []

    missing = []

    jd_skills = []

    if job_description.strip():

        jd_skills = extract_skills(job_description)

        resume_skills = set(skills)

        for skill in jd_skills:

            if skill in resume_skills:

                matched.append(skill)

            else:

                missing.append(skill)

        if jd_skills:

            ats_score = round(
                len(matched) / len(jd_skills) * 100
            )

    else:

        missing = [
            s for s in [
                "tableau", "statistics", "deep learning", "docker",
                "fastapi", "react", "powerpoint", "aws"
            ]
            if s not in skills
        ][:6]

    # ------------------------------------------------
    # MISSING / KEYWORD SUGGESTIONS
    # ------------------------------------------------

    keyword_suggestions = []

    suggested = [
        "machine learning", "data analysis", "statistics", "sql",
        "python", "excel", "power bi", "tableau", "git", "docker"
    ]

    for skill in suggested:

        if skill not in skills:

            keyword_suggestions.append(skill)

    keyword_suggestions = keyword_suggestions[:6]

    # ------------------------------------------------
    # WEAK SECTIONS
    # ------------------------------------------------

    weak_sections = [
        section
        for section, present in sections.items()
        if not present
    ]

    if not weak_sections:

        weak_sections = ["Projects"]

    # ------------------------------------------------
    # SUGGESTIONS
    # ------------------------------------------------

    suggestions = []

    if "achieved" not in text.lower() and \
       "increased" not in text.lower():

        suggestions.append(
            "Add measurable achievements with numbers "
            "(e.g. 'Increased sales by 20%')."
        )

    if not sections.get("Summary"):

        suggestions.append(
            "Add a professional summary at the top "
            "of the resume."
        )

    if not sections.get("Skills"):

        suggestions.append(
            "Add a dedicated skills section."
        )

    if len(skills) < 6:

        suggestions.append(
            "Include relevant technical keywords for "
            "better ATS matching."
        )

    if missing and jd_skills:

        suggestions.append(
            "Add missing job-description keywords: "
            + ", ".join(missing[:5])
            + "."
        )

    return {
        "sections": sections,
        "skills": skills,
        "issues": issues,
        "formatting": formatting,
        "resume_score": resume_score,
        "ats_score": ats_score,
        "matched": matched,
        "missing": missing,
        "jd_skills": jd_skills,
        "keyword_suggestions": keyword_suggestions,
        "weak_sections": weak_sections,
        "suggestions": suggestions
    }


def bullets_score(text):
    """Count bullet-point style lines."""

    return sum(
        1 for line in text.splitlines()
        if line.strip().startswith(("-", "*", "•"))
    )


# ============================================================
# IMPROVED SECTIONS
# ============================================================

def build_improved_sections(report):
    """
    Build suggested improved text for key resume
    sections. Does NOT modify the original resume.
    """

    sections = report["sections"]

    parts = []

    # Summary
    if sections.get("Summary"):

        parts.append(
            "PROFESSIONAL SUMMARY (Suggested)\n"
            "------------------------------\n"
            "Results-driven professional with a strong record of "
            "delivering measurable outcomes. Combine technical "
            "expertise with strong communication to drive business "
            "value. Proven ability to [add your key achievement here], "
            "e.g. 'increased efficiency by 25%'.\n"
        )

    else:

        parts.append(
            "PROFESSIONAL SUMMARY (Add this section)\n"
            "--------------------------------------\n"
            "Add a 3-4 line summary at the top: your role, years of "
            "experience, core strengths, and a measurable achievement.\n"
        )

    # Skills
    skills_list = report["skills"]

    if skills_list:

        parts.append(
            "SKILLS (Suggested organization)\n"
            "-------------------------------\n"
            "Programming: "
            + ", ".join(s for s in skills_list if s in
                        ["python", "java", "c", "c++", "c#", "sql",
                         "javascript", "react", "node.js"])
            + "\n"
            "Data & Analytics: "
            + ", ".join(s for s in skills_list if s in
                        ["excel", "power bi", "tableau", "pandas",
                         "numpy", "sql", "statistics"])
            + "\n"
            "Tools & Platforms: "
            + ", ".join(s for s in skills_list if s in
                        ["git", "github", "docker", "aws", "azure",
                         "tensorflow", "pytorch", "flask", "fastapi"])
            + "\n"
        )

    # Experience
    if sections.get("Experience"):

        parts.append(
            "EXPERIENCE (Improvement guide)\n"
            "------------------------------\n"
            "For each role: use 'Action + Result' bullets. "
            "Start with a strong verb (Led, Built, Improved, Reduced). "
            "Add numbers: 'Reduced processing time by 30%'. "
            "Keep each bullet to one line.\n"
        )

    else:

        parts.append(
            "EXPERIENCE (Add this section)\n"
            "----------------------------\n"
            "List roles in reverse-chronological order with "
            "company, title, dates, and 2-3 achievement bullets "
            "with measurable results.\n"
        )

    # Education
    if sections.get("Education"):

        parts.append(
            "EDUCATION (Suggestion)\n"
            "----------------------\n"
            "Include degree, institution, year, and any relevant "
            "coursework or GPA if strong (3.5+).\n"
        )

    else:

        parts.append(
            "EDUCATION (Add this section)\n"
            "----------------------------\n"
            "Add your degrees with institution names and "
            "graduation years.\n"
        )

    # Keywords
    if report["keyword_suggestions"]:

        parts.append(
            "KEYWORDS TO ADD\n"
            "---------------\n"
            + ", ".join(report["keyword_suggestions"])
            + "\n"
        )

    return "\n".join(parts)


def build_report_text(report, filename):
    """Build the plain-text analysis report for download."""

    lines = []

    lines.append(f"AI RESUME IMPROVEMENT REPORT - {filename}")
    lines.append("=" * 50)

    lines.append(f"Resume Score: {report['resume_score']}/100")

    if report["ats_score"] is not None:

        lines.append(f"ATS Match Score: {report['ats_score']}%")

        lines.append(f"Matched Skills: {', '.join(report['matched']) or 'None'}")

        lines.append(f"Missing Skills: {', '.join(report['missing']) or 'None'}")

    lines.append("")
    lines.append("Sections Detected:")
    lines.append("-" * 50)

    for section, present in report["sections"].items():

        lines.append(f"  {section}: {'Present' if present else 'MISSING'}")

    lines.append("")
    lines.append("Weak Sections: " + ", ".join(report["weak_sections"]))

    lines.append("")
    lines.append("Grammar Issues:")
    lines.append("-" * 50)

    for issue in report["issues"]:

        lines.append(f"  - {issue}")

    lines.append("")
    lines.append("Formatting Suggestions:")
    lines.append("-" * 50)

    for suggestion in report["formatting"]:

        lines.append(f"  - {suggestion}")

    lines.append("")
    lines.append("Improvement Suggestions:")
    lines.append("-" * 50)

    for suggestion in report["suggestions"]:

        lines.append(f"  - {suggestion}")

    lines.append("")
    lines.append("Detected Skills:")
    lines.append("-" * 50)

    lines.append("  " + ", ".join(report["skills"]))

    return "\n".join(lines)


# ============================================================
# UI
# ============================================================

def show():

    st.markdown(
        """
        <div class="main-title">
            ✨ AI Resume Improvement
        </div>

        <div class="main-subtitle">
            Analyze your resume, get an ATS score and
            download improved section suggestions.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:

        uploaded_file = st.file_uploader(
            "📎 Upload Resume",
            type=["pdf", "docx", "txt"],
            key="improve_resume"
        )

    with col2:

        job_description = st.text_area(
            "📝 Optional Job Description",
            height=150,
            placeholder=(
                "Paste the job description to get "
                "an ATS match score..."
            ),
            key="improve_jd_textarea"
        )

    if st.button(
        "🔍 Analyze Resume",
        type="primary",
        use_container_width=True,
        key="analyze_resume_btn"
    ):

        if uploaded_file is None:

            st.warning(
                "⚠️ Please upload a resume first."
            )

        else:

            with st.spinner(
                "🔎 Analyzing resume..."
            ):

                try:

                    text = extract_text(uploaded_file)

                    if not text or not text.strip():

                        st.error(
                            "❌ No readable text found in "
                            "the uploaded file."
                        )

                        st.stop()

                    report = analyze_resume(
                        text,
                        job_description
                    )

                    st.session_state["improve_report"] = report

                    st.session_state["improve_text"] = text

                    st.session_state["improve_filename"] = (
                        uploaded_file.name
                    )

                except Exception as e:

                    st.error(
                        f"❌ Could not analyze the resume: {e}"
                    )

    report = st.session_state.get("improve_report")

    if report is None:

        st.info(
            "Upload a resume and click Analyze to "
            "see the improvement report."
        )

        return

    # ------------------------------------------------
    # SCORES
    # ------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "📄 Resume Score",
            f"{report['resume_score']}/100"
        )

    with col2:

        if report["ats_score"] is not None:

            st.metric(
                "🎯 ATS Match Score",
                f"{report['ats_score']}%"
            )

        else:

            st.metric(
                "🎯 ATS Match Score",
                "N/A (add JD)"
            )

    # ------------------------------------------------
    # SECTION STATUS
    # ------------------------------------------------

    st.markdown(
        "### 📑 Resume Sections"
    )

    cols = st.columns(3)

    section_items = list(report["sections"].items())

    for index, (section, present) in enumerate(section_items):

        with cols[index % 3]:

            if present:

                st.success(f"✅ {section}")

            else:

                st.error(f"❌ {section} missing")

    st.markdown(
        f"**Weak sections:** "
        + ", ".join(report["weak_sections"])
    )

    # ------------------------------------------------
    # ATS MATCH
    # ------------------------------------------------

    if report["ats_score"] is not None:

        st.markdown(
            "### 🎯 Job Description Match"
        )

        st.write(
            "**Matched Skills:** "
            + ", ".join(report["matched"]) or "None"
        )

        if report["matched"]:

            st.success(
                ", ".join(report["matched"])
            )

        st.write(
            "**Missing Skills:** "
        )

        if report["missing"]:

            st.warning(
                ", ".join(report["missing"])
            )

        else:

            st.success(
                "All job skills found!"
            )

    # ------------------------------------------------
    # ISSUES AND SUGGESTIONS
    # ------------------------------------------------

    st.markdown(
        "### 🧠 Grammar & Formatting"
    )

    for issue in report["issues"]:

        st.warning(issue)

    for suggestion in report["formatting"]:

        st.info(suggestion)

    st.markdown(
        "### 💡 Improvement Suggestions"
    )

    for suggestion in report["suggestions"]:

        st.info(suggestion)

    if report["keyword_suggestions"]:

        st.markdown(
            "### 🔑 Suggested Keywords to Add"
        )

        st.success(
            ", ".join(report["keyword_suggestions"])
        )

    # ------------------------------------------------
    # IMPROVED SECTIONS + DOWNLOAD
    # ------------------------------------------------

    st.markdown(
        "### ✨ Improved Section Suggestions"
    )

    improved = build_improved_sections(report)

    st.text(improved)

    col1, col2 = st.columns(2)

    with col1:

        st.download_button(
            "📥 Download Analysis Report",
            data=build_report_text(
                report,
                st.session_state.get(
                    "improve_filename",
                    "resume"
                )
            ),
            file_name="resume_analysis_report.txt",
            mime="text/plain"
        )

    with col2:

        st.download_button(
            "📥 Download Improved Sections",
            data=improved,
            file_name="resume_improved_sections.txt",
            mime="text/plain"
        )

    st.caption(
        "Note: Your original resume is never modified. "
        "Downloads are separate files."
    )
