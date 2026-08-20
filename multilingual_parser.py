"""
Multi-language Resume Parsing
=============================

Independent extra feature that detects the language
of an uploaded resume (English, Tamil, Hindi, Telugu,
Kannada, Malayalam, Gujarati, Bengali, Punjabi,
French, German, Spanish), preserves the original text,
extracts candidate details and normalizes skills to
English for ranking against a job description.

Works offline with Unicode range detection and a
built-in translation dictionary. Adding a new language
is just adding an entry to LANGUAGE_DATA.
"""

import re
import streamlit as st

from resume_parser import (
    extract_text,
    extract_email,
    extract_phone,
    extract_skills
)

from ranking_engine import rank_candidate


# ============================================================
# LANGUAGE DATA
# ============================================================

# Unicode ranges for native scripts
SCRIPT_RANGES = {
    "Hindi": [(0x0900, 0x097F)],        # Devanagari
    "Bengali": [(0x0980, 0x09FF)],
    "Punjabi": [(0x0A00, 0x0A7F)],      # Gurmukhi
    "Gujarati": [(0x0A80, 0x0AFF)],
    "Tamil": [(0x0B80, 0x0BFF)],
    "Telugu": [(0x0C00, 0x0C7F)],
    "Kannada": [(0x0C80, 0x0CFF)],
    "Malayalam": [(0x0D00, 0x0D7F)]
}

# Language metadata: section keywords, stopwords for
# Latin-script languages, and name title hints
LANGUAGE_DATA = {

    "English": {
        "section_keywords": {
            "Summary": ["summary", "profile", "objective"],
            "Skills": ["skills", "technical skills"],
            "Experience": ["experience", "employment", "work history"],
            "Education": ["education", "qualification"],
            "Projects": ["projects"],
            "Certifications": ["certifications", "courses"]
        },
        "stopwords": ["the", "and", "with", "for", "from"],
        "titles": ["mr.", "ms.", "mrs.", "dr."]
    },

    "Tamil": {
        "section_keywords": {
            "Summary": ["சுருக்கம்", "தொழில்முறை சுயவிவரம்"],
            "Skills": ["திறன்கள்", "திறமைகள்"],
            "Experience": ["அனுபவம்", "பணி அனுபவம்"],
            "Education": ["கல்வி", "கல்வி தகுதி"],
            "Projects": ["திட்டங்கள்"],
            "Certifications": ["சான்றிதழ்கள்", "சான்றிதழ்"]
        },
        "stopwords": [],
        "titles": ["திரு.", "திருமதி."]
    },

    "Hindi": {
        "section_keywords": {
            "Summary": ["सारांश", "प्रोफाइल"],
            "Skills": ["कौशल", "कौशल्य"],
            "Experience": ["अनुभव", "कार्य अनुभव"],
            "Education": ["शिक्षा", "शैक्षिक योग्यता"],
            "Projects": ["परियोजनाएं", "प्रोजेक्ट"],
            "Certifications": ["प्रमाणपत्र", "प्रमाणपत्रों"]
        },
        "stopwords": [],
        "titles": ["श्री.", "श्रीमती."]
    },

    "Telugu": {
        "section_keywords": {
            "Summary": ["సారాంశం", "ప్రొఫైల్"],
            "Skills": ["నైపుణ్యాలు", "నైపుణ్యాలు"],
            "Experience": ["అనుభవం", "పని అనుభవం"],
            "Education": ["విద్య", "అర్హత"],
            "Projects": ["ప్రాజెక్టులు", "ప్రాజెక్ట్స్"],
            "Certifications": ["సర్టిఫికేట్లు"]
        },
        "stopwords": [],
        "titles": ["శ్రీ.", "శ్రీమతి."]
    },

    "Kannada": {
        "section_keywords": {
            "Summary": ["ಸಾರಾಂಶ", "ಪ್ರೊಫೈಲ್"],
            "Skills": ["ಕೌಶಲ್ಯ", "ಕೌಶಲ್ಯಗಳು"],
            "Experience": ["ಅನುಭವ", "ಕೆಲಸದ ಅನುಭವ"],
            "Education": ["ಶಿಕ್ಷಣ", "ಶೈಕ್ಷಣಿಕ"],
            "Projects": ["ಯೋಜನೆಗಳು", "ಪ್ರಾಜೆಕ್ಟ್"],
            "Certifications": ["ಪ್ರಮಾಣಪತ್ರಗಳು"]
        },
        "stopwords": [],
        "titles": ["ಶ್ರೀ.", "ಶ್ರೀಮತಿ."]
    },

    "Malayalam": {
        "section_keywords": {
            "Summary": ["സംഗ്രഹം", "പ്രൊഫൈൽ"],
            "Skills": ["കഴിവുകൾ", "വൈദഗ്ധ്യം"],
            "Experience": ["അനുഭവം", "ജോലി പരിചയം"],
            "Education": ["വിദ്യാഭ്യാസം", "യോഗ്യത"],
            "Projects": ["പ്രോജക്ടുകൾ", "പദ്ധതികൾ"],
            "Certifications": ["സർട്ടിഫിക്കറ്റുകൾ"]
        },
        "stopwords": [],
        "titles": ["ശ്രീ.", "ശ്രീമതി."]
    },

    "Gujarati": {
        "section_keywords": {
            "Summary": ["સારાંશ", "પ્રોફાઇલ"],
            "Skills": ["કૌશલ્ય", "કુશળતા"],
            "Experience": ["અનુભવ", "કાર્ય અનુભવ"],
            "Education": ["શિક્ષણ", "લાયકાત"],
            "Projects": ["પ્રોજેક્ટ્સ", "પ્રોજેક્ટ"],
            "Certifications": ["પ્રમાણપત્રો"]
        },
        "stopwords": [],
        "titles": ["શ્રી.", "શ્રીમતી."]
    },

    "Bengali": {
        "section_keywords": {
            "Summary": ["সারসংক্ষেপ", "প্রোফাইল"],
            "Skills": ["দক্ষতা"],
            "Experience": ["অভিজ্ঞতা", "কর্ম অভিজ্ঞতা"],
            "Education": ["শিক্ষা", "যোগ্যতা"],
            "Projects": ["প্রকল্প"],
            "Certifications": ["সার্টিফিকেট"]
        },
        "stopwords": [],
        "titles": ["শ্রী.", "শ্রীমতী."]
    },

    "Punjabi": {
        "section_keywords": {
            "Summary": ["ਸਾਰਾਂਸ਼", "ਪ੍ਰੋਫਾਈਲ"],
            "Skills": ["ਹੁਨਰ", "ਕਾਬਲੀਅਤ"],
            "Experience": ["ਤਜਰਬਾ", "ਕੰਮ ਦਾ ਤਜਰਬਾ"],
            "Education": ["ਸਿੱਖਿਆ", "ਯੋਗਤਾ"],
            "Projects": ["ਪ੍ਰੋਜੈਕਟ"],
            "Certifications": ["ਸਰਟੀਫਿਕੇਟ"]
        },
        "stopwords": [],
        "titles": ["ਸ੍ਰੀ.", "ਸ਼੍ਰੀਮਤੀ."]
    },

    "French": {
        "section_keywords": {
            "Summary": ["résumé", "profil", "objectif"],
            "Skills": ["compétences", "aptitudes"],
            "Experience": ["expérience", "emploi"],
            "Education": ["formation", "éducation"],
            "Projects": ["projets"],
            "Certifications": ["certifications", "certificats"]
        },
        "stopwords": ["le", "la", "les", "et", "pour", "avec", "une", "des"],
        "titles": ["m.", "mme", "dr."]
    },

    "German": {
        "section_keywords": {
            "Summary": ["zusammenfassung", "profil"],
            "Skills": ["fähigkeiten", "kenntnisse"],
            "Experience": ["erfahrung", "berufserfahrung"],
            "Education": ["ausbildung", "bildung"],
            "Projects": ["projekte"],
            "Certifications": ["zertifikate", "zertifizierung"]
        },
        "stopwords": ["und", "der", "die", "das", "mit", "für", "eine"],
        "titles": ["herr", "frau", "dr."]
    },

    "Spanish": {
        "section_keywords": {
            "Summary": ["resumen", "perfil", "objetivo"],
            "Skills": ["habilidades", "competencias"],
            "Experience": ["experiencia", "empleo"],
            "Education": ["educación", "formación"],
            "Projects": ["proyectos"],
            "Certifications": ["certificaciones", "certificados"]
        },
        "stopwords": ["el", "la", "los", "las", "y", "para", "con", "una"],
        "titles": ["sr.", "sra.", "dr."]
    }
}


# ============================================================
# LANGUAGE DETECTION
# ============================================================

def _in_ranges(char, ranges):

    code = ord(char)

    for start, end in ranges:

        if start <= code <= end:

            return True

    return False


def detect_language(text):
    """
    Detect the language of a resume text.

    Returns (language, confidence) where confidence
    is a percentage.
    """

    if not text or not text.strip():

        return "English", 0.0

    sample = text[:3000]

    total = len(re.findall(r"\S", sample))

    if total == 0:

        return "English", 0.0

    # 1. Native script detection
    script_counts = {}

    for char in sample:

        for language, ranges in SCRIPT_RANGES.items():

            if _in_ranges(char, ranges):

                script_counts[language] = (
                    script_counts.get(language, 0) + 1
                )

                break

    for language, count in sorted(
        script_counts.items(),
        key=lambda item: item[1],
        reverse=True
    ):

        if count >= 5:

            confidence = round(min(100, count / max(1, total) * 200))

            return language, confidence

    # 2. Latin script: stopword frequency + accent signals
    words = re.findall(r"[a-zà-ÿÀ-ß]+", sample.lower())

    ACCENTS = {
        "French": "éèêàçùîïôœ",
        "German": "äöüß",
        "Spanish": "ñáéíóú"
    }

    best_language = "English"

    best_score = 0

    for language, data in LANGUAGE_DATA.items():

        if language in SCRIPT_RANGES:

            continue

        stopwords = data.get("stopwords", [])

        score = sum(1 for word in words if word in stopwords)

        # Accent characters are a strong signal
        accent_set = ACCENTS.get(language, "")

        accent_score = sum(
            1 for char in sample.lower()
            if char in accent_set
        )

        score += accent_score * 2

        if score > best_score:

            best_score = score

            best_language = language

    if best_score >= 4:

        confidence = round(min(100, best_score / max(1, len(words)) * 300))

        return best_language, confidence

    return "English", 50.0


# ============================================================
# NATIVE SKILL TRANSLATIONS (normalize to English)
# ============================================================

SKILL_TRANSLATIONS = {
    # Hindi
    "डेटा विश्लेषण": "data analysis",
    "सांख्यिकी": "statistics",
    "मशीन लर्निंग": "machine learning",
    "सॉफ्टवेयर विकास": "software development",
    "वेब विकास": "web development",
    # Tamil
    "தரவு பகுப்பாய்வு": "data analysis",
    "புள்ளியியல்": "statistics",
    "இயந்திர கற்றல்": "machine learning",
    "மென்பொருள் மேம்பாடு": "software development",
    "வலை மேம்பாடு": "web development",
    # Telugu
    "డేటా విశ్లేషణ": "data analysis",
    "గణాంకాలు": "statistics",
    "మెషిన్ లెర్నింగ్": "machine learning",
    "సాఫ్ట్వేర్ అభివృద్ధి": "software development",
    "వెబ్ డెవలప్మెంట్": "web development",
    # Kannada
    "ಡೇಟಾ ವಿಶ್ಲೇಷಣೆ": "data analysis",
    "ಅಂಕಿಅಂಶ": "statistics",
    "ಯಂತ್ರ ಕಲಿಕೆ": "machine learning",
    "ಸಾಫ್ಟ್ವೇರ್ ಅಭಿವೃದ್ಧಿ": "software development",
    "ವೆಬ್ ಅಭಿವೃದ್ಧಿ": "web development",
    # Malayalam
    "ഡാറ്റ വിശകലനം": "data analysis",
    "സ്ഥിതിവിവരക്കണക്ക്": "statistics",
    "മെഷീൻ ലേണിംഗ്": "machine learning",
    "സോഫ്റ്റ്വെയർ വികസനം": "software development",
    "വെബ് വികസനം": "web development",
    # Gujarati
    "ડેટા વિશ્લેષણ": "data analysis",
    "આંકડાશાસ્ત્ર": "statistics",
    "મશીન લર્નિંગ": "machine learning",
    # Bengali
    "ডেটা বিশ্লেষণ": "data analysis",
    "পরিসংখ্যান": "statistics",
    "মেশিন লার্নিং": "machine learning",
    # Punjabi
    "ਡਾਟਾ ਵਿਸ਼ਲੇਸ਼ਣ": "data analysis",
    "ਅੰਕੜੇ": "statistics",
    "ਮਸ਼ੀਨ ਲਰਨਿੰਗ": "machine learning",
    # French
    "analyse de données": "data analysis",
    "statistiques": "statistics",
    "apprentissage automatique": "machine learning",
    "développement logiciel": "software development",
    # German
    "datenanalyse": "data analysis",
    "statistik": "statistics",
    "maschinelles lernen": "machine learning",
    "softwareentwicklung": "software development",
    # Spanish
    "análisis de datos": "data analysis",
    "estadísticas": "statistics",
    "aprendizaje automático": "machine learning",
    "desarrollo de software": "software development"
}


def normalize_skills(text):
    """
    Extract and normalize skills to English names.

    Tech terms usually stay in Latin script even in
    native-language resumes, so latin extraction is
    combined with translation of native skill phrases.
    """

    text_lower = text.lower()

    skills = extract_skills(text)

    normalized = set(skills)

    for native, english in SKILL_TRANSLATIONS.items():

        if native in text_lower:

            normalized.add(english)

    return sorted(normalized)


# ============================================================
# SECTION DETECTION (per language)
# ============================================================

def detect_sections(text, language):
    """Return dict of section -> bool for the detected language."""

    data = LANGUAGE_DATA.get(language, LANGUAGE_DATA["English"])

    keywords = data.get("section_keywords", {})

    text_lower = text.lower()

    detected = {}

    for section, words in keywords.items():

        detected[section] = any(
            word in text_lower
            for word in words
        )

    return detected


# ============================================================
# DETAIL EXTRACTION
# ============================================================

def extract_native_name(text, language):
    """Best-effort name extraction from the first lines."""

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:

        return ""

    # Skip lines that look like emails, phones or headers
    for line in lines[:5]:

        if re.search(r"@|http|\b\d{3,}\b", line):

            continue

        if len(line) < 2 or len(line) > 60:

            continue

        return line

    return lines[0][:60]


def parse_resume(text, filename=""):
    """
    Full multilingual parse of a resume.

    Returns a report dict:
        language, confidence, sections, skills,
        email, phone, name, text (preserved),
        education, experience, projects,
        certifications (present + snippets)
    """

    language, confidence = detect_language(text)

    sections = detect_sections(text, language)

    skills = normalize_skills(text)

    email = extract_email(text)

    phone = extract_phone(text)

    name = extract_native_name(text, language)

    # Section snippets (first matching line, max 3 lines)
    snippets = {}

    text_lower = text.lower()

    data = LANGUAGE_DATA.get(language, LANGUAGE_DATA["English"])

    keywords = data.get("section_keywords", {})

    for section, words in keywords.items():

        for word in words:

            match = re.search(
                re.escape(word) + r"[^\n]*",
                text_lower,
                re.IGNORECASE
            )

            if match:

                start = match.start()

                snippet = text[start:start + 300]

                snippets[section] = " ".join(
                    snippet.split()
                )[:280]

                break

    return {
        "language": language,
        "confidence": confidence,
        "sections": sections,
        "skills": skills,
        "email": email,
        "phone": phone,
        "name": name,
        "text": text,
        "snippets": snippets
    }


# ============================================================
# UI
# ============================================================

def show():

    st.markdown(
        """
        <div class="main-title">
            🌐 Multi-language Resume Parsing
        </div>

        <div class="main-subtitle">
            Detect the resume language, extract details
            and rank against a job description - with
            skills normalized to English.
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
            key="ml_resume"
        )

    with col2:

        job_description = st.text_area(
            "📝 Optional Job Description",
            height=150,
            placeholder=(
                "Paste the job description to "
                "rank this resume against it..."
            ),
            key="ml_jd_textarea"
        )

    if st.button(
        "🔍 Parse & Analyze",
        type="primary",
        use_container_width=True,
        key="ml_parse_btn"
    ):

        if uploaded_file is None:

            st.warning(
                "⚠️ Please upload a resume first."
            )

        else:

            with st.spinner(
                "🌐 Detecting language and parsing..."
            ):

                try:

                    text = extract_text(uploaded_file)

                    if not text or not text.strip():

                        st.error(
                            "❌ No readable text found "
                            "in the uploaded file."
                        )

                        st.stop()

                    report = parse_resume(
                        text,
                        uploaded_file.name
                    )

                    st.session_state["ml_report"] = report

                    st.session_state["ml_jd"] = job_description

                except Exception as e:

                    st.error(
                        f"❌ Could not parse the resume: {e}"
                    )

    report = st.session_state.get("ml_report")

    if report is None:

        st.info(
            "Upload a resume and click Parse & Analyze "
            "to see the extracted details."
        )

        return

    # ------------------------------------------------
    # LANGUAGE BADGE
    # ------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "🌐 Detected Language",
            report["language"]
        )

    with col2:

        st.metric(
            "📊 Confidence",
            f"{report['confidence']}%"
        )

    # ------------------------------------------------
    # EXTRACTED DETAILS
    # ------------------------------------------------

    st.markdown(
        "### 👤 Extracted Candidate Details"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.write("**Name**")

        st.write(report["name"] or "Not found")

    with col2:

        st.write("**Email**")

        st.write(report["email"] or "Not found")

    with col3:

        st.write("**Phone**")

        st.write(report["phone"] or "Not found")

    # ------------------------------------------------
    # SECTIONS
    # ------------------------------------------------

    st.markdown(
        "### 📑 Sections Detected"
    )

    cols = st.columns(3)

    section_items = list(report["sections"].items())

    for index, (section, present) in enumerate(section_items):

        with cols[index % 3]:

            if present:

                st.success(f"✅ {section}")

            else:

                st.error(f"❌ {section}")

    # ------------------------------------------------
    # SKILLS
    # ------------------------------------------------

    st.markdown(
        "### 🛠 Skills (Normalized to English)"
    )

    skills = report["skills"]

    if skills:

        st.success(", ".join(skills))

    else:

        st.warning(
            "No skills detected - the resume may "
            "need OCR-friendly formatting."
        )

    # ------------------------------------------------
    # SECTION SNIPPETS
    # ------------------------------------------------

    if report["snippets"]:

        st.markdown(
            "### 🔎 Section Previews (Original Language)"
        )

        for section, snippet in report["snippets"].items():

            with st.expander(
                f"{section}"
            ):

                st.write(snippet)

    # ------------------------------------------------
    # ORIGINAL TEXT (preserved)
    # ------------------------------------------------

    with st.expander(
        "📄 Original Resume Text (Preserved)"
    ):

        st.text(report["text"])

    # ------------------------------------------------
    # RANKING
    # ------------------------------------------------

    job_description = st.session_state.get("ml_jd", "")

    if job_description.strip() and skills:

        st.markdown(
            "### 🏆 Ranking vs Job Description"
        )

        required_skills = extract_skills(job_description)

        if not required_skills:

            st.info(
                "No skills recognized in the job "
                "description - add skill keywords."
            )

        else:

            ranking = rank_candidate(
                skills,
                required_skills
            )

            col1, col2, col3 = st.columns(3)

            with col1:

                st.metric(
                    "🎯 Match Score",
                    f"{ranking['score']}%"
                )

            with col2:

                st.metric(
                    "📋 Status",
                    ranking["status"]
                )

            with col3:

                st.metric(
                    "🔗 Matched",
                    str(len(ranking["matched_skills"]))
                )

            if ranking["matched_skills"]:

                st.success(
                    "Matched: "
                    + ", ".join(ranking["matched_skills"])
                )

            if ranking["missing_skills"]:

                st.warning(
                    "Missing: "
                    + ", ".join(ranking["missing_skills"])
                )

    else:

        st.caption(
            "Add a job description to rank this resume "
            "against required skills."
        )
