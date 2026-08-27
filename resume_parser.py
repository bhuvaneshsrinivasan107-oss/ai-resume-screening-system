import os
import re
import io
import shutil
import logging
import tempfile

import pdfplumber
import pytesseract

from PIL import Image
from pypdf import PdfReader
from docx import Document

logger = logging.getLogger("resume_parser")


# ============================================================
# TESSERACT CONFIGURATION (cross-platform)
# ============================================================

def _find_tesseract():
    if os.name == "nt":
        win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.isfile(win_path):
            return win_path
    unix_path = shutil.which("tesseract")
    if unix_path:
        return unix_path
    return None

TESSERACT_PATH = _find_tesseract()

if TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    logger.info("Tesseract found at: %s", TESSERACT_PATH)
else:
    logger.warning("Tesseract binary not found on this system. OCR will be unavailable.")


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = text.replace("\x00", " ")

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# EXTRACT TEXT FROM NORMAL PDF
# ============================================================

def extract_pdf_text(file_bytes):

    text = ""

    # --------------------------------------------------------
    # Method 1: pdfplumber
    # --------------------------------------------------------

    try:

        with pdfplumber.open(
            io.BytesIO(file_bytes)
        ) as pdf:

            pages_text = []

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:

                    pages_text.append(
                        page_text
                    )

            text = "\n".join(
                pages_text
            )

    except Exception:
        text = ""

    if text.strip():

        return clean_text(text)

    # --------------------------------------------------------
    # Method 2: pypdf
    # --------------------------------------------------------

    try:

        reader = PdfReader(
            io.BytesIO(file_bytes)
        )

        pages_text = []

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:

                pages_text.append(
                    page_text
                )

        text = "\n".join(
            pages_text
        )

    except Exception:
        text = ""

    return clean_text(text)


# ============================================================
# OCR SCANNED PDF
# ============================================================

def extract_pdf_with_ocr(file_bytes):

    if not TESSERACT_PATH:
        logger.warning("OCR skipped: tesseract binary not available.")
        return ""

    # --------------------------------------------------------
    # Method 1: PyMuPDF (no Poppler needed)
    # --------------------------------------------------------

    try:

        import pymupdf

        doc = pymupdf.open(
            stream=file_bytes,
            filetype="pdf"
        )

        extracted_pages = []

        for page in doc:

            images = page.get_images(
                full=True
            )

            for img_index in images:

                xref = img_index[0]

                base_image = doc.extract_image(
                    xref
                )

                image_bytes = base_image[
                    "image"
                ]

                pil_image = Image.open(
                    io.BytesIO(
                        image_bytes
                    )
                )

                text = pytesseract.image_to_string(
                    pil_image
                )

                if text and text.strip():

                    extracted_pages.append(
                        text
                    )

        doc.close()

        if extracted_pages:

            return clean_text(
                "\n".join(
                    extracted_pages
                )
            )

    except Exception as e:

        logger.warning("PyMuPDF OCR method failed: %s", e)

    # --------------------------------------------------------
    # Method 2: pdf2image + tempfiles (needs Poppler)
    # --------------------------------------------------------

    try:

        from pdf2image import convert_from_bytes

        images = convert_from_bytes(
            file_bytes,
            dpi=200
        )

        extracted_pages = []

        for image in images:

            text = pytesseract.image_to_string(
                image
            )

            if text:

                extracted_pages.append(
                    text
                )

        return clean_text(
            "\n".join(
                extracted_pages
            )
        )

    except Exception as e:

        logger.warning("pdf2image OCR method failed: %s", e)

    return ""


# ============================================================
# EXTRACT DOCX TEXT
# ============================================================

def extract_docx_text(file_bytes):

    try:

        document = Document(
            io.BytesIO(file_bytes)
        )

        paragraphs = []

        for paragraph in document.paragraphs:

            if paragraph.text.strip():

                paragraphs.append(
                    paragraph.text
                )

        # Also extract tables
        for table in document.tables:

            for row in table.rows:

                row_text = []

                for cell in row.cells:

                    row_text.append(
                        cell.text
                    )

                paragraphs.append(
                    " ".join(row_text)
                )

        return clean_text(
            "\n".join(paragraphs)
        )

    except Exception as e:

        logger.error(
            "DOCX ERROR: %s",
            e,
        )

        return ""


# ============================================================
# MAIN TEXT EXTRACTION
# ============================================================

def extract_text(uploaded_file):

    try:

        file_name = uploaded_file.name.lower()

        file_bytes = uploaded_file.getvalue()

        if not file_bytes:

            return ""

        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

        if file_name.endswith(".pdf"):

            # First try normal PDF extraction
            text = extract_pdf_text(
                file_bytes
            )

            # If text exists, use it
            if text and len(text.strip()) >= 30:

                return text

            # Otherwise use OCR
            logger.info(
                "Normal PDF extraction yielded insufficient text for '%s'. Trying OCR...",
                uploaded_file.name,
            )

            ocr_text = extract_pdf_with_ocr(
                file_bytes
            )

            if ocr_text and ocr_text.strip():
                return ocr_text

            logger.error(
                "All extraction methods failed for '%s'. "
                "The file may be corrupted or contain only images "
                "and tesseract could not process it.",
                uploaded_file.name,
            )

            return ""

        # ----------------------------------------------------
        # DOCX
        # ----------------------------------------------------

        elif file_name.endswith(".docx"):

            return extract_docx_text(
                file_bytes
            )

        # ----------------------------------------------------
        # TXT
        # ----------------------------------------------------

        elif file_name.endswith(".txt"):

            try:

                return clean_text(
                    file_bytes.decode(
                        "utf-8",
                        errors="ignore"
                    )
                )

            except Exception:

                return ""

        # ----------------------------------------------------
        # Unsupported
        # ----------------------------------------------------

        return ""

    except Exception as e:

        logger.error(
            "TEXT EXTRACTION ERROR for '%s': %s",
            getattr(uploaded_file, 'name', 'unknown'),
            e,
        )

        return ""


# ============================================================
# EXTRACT EMAIL
# ============================================================

def extract_email(text):

    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"

    match = re.search(
        pattern,
        text
    )

    if match:

        email = match.group(0)

        # Remove OCR noise prefix like "W_" before the
        # real email address (e.g. "W_arun-kumar@email.com")
        email = re.sub(
            r"^[A-Za-z0-9]_(?=[A-Za-z0-9])",
            "",
            email
        )

        email = re.sub(
            r"^[^A-Za-z0-9]+",
            "",
            email
        )

        if email:

            return email

    return "Not Found"


# ============================================================
# EXTRACT PHONE
# ============================================================

def extract_phone(text):

    patterns = [

        r"\+91[\s-]?\d{10}",

        r"\b\d{10}\b",

        r"\+91[\s-]?\d{5}[\s-]?\d{5}"

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            return match.group(0)

    return "Not Found"


# ============================================================
# EXTRACT NAME
# ============================================================

def extract_name(text, filename=""):

    lines = [

        line.strip()

        for line in text.splitlines()

        if line.strip()
    ]

    # --------------------------------------------------------
    # Try first few lines
    # --------------------------------------------------------

    for line in lines[:15]:

        clean_line = re.sub(
            r"[^A-Za-z .'-]",
            "",
            line
        ).strip()

        words = clean_line.split()

        if 2 <= len(words) <= 4:

            lower_line = clean_line.lower()

            blocked = [

                "resume",
                "curriculum",
                "vitae",
                "email",
                "phone",
                "mobile",
                "address",
                "profile",
                "objective",
                "summary",
                "skills",
                "education",
                "experience",
                "contact"
            ]

            if not any(
                word in lower_line
                for word in blocked
            ):

                if all(
                    re.match(
                        r"^[A-Za-z][A-Za-z.'-]*$",
                        word
                    )
                    for word in words
                ):

                    return clean_line

    # --------------------------------------------------------
    # Try filename
    # --------------------------------------------------------

    if filename:

        name = os.path.splitext(
            os.path.basename(filename)
        )[0]

        name = re.sub(
            r"resume",
            "",
            name,
            flags=re.IGNORECASE
        )

        name = re.sub(
            r"[_\-]+",
            " ",
            name
        )

        name = name.strip()

        if name:

            return name.title()

    return "Unknown Candidate"


# ============================================================
# SKILL EXTRACTION
# ============================================================

def extract_skills(text):

    skill_dictionary = [

        "python",
        "java",
        "c++",
        "c#",
        "c",

        "sql",
        "mysql",
        "postgresql",
        "mongodb",

        "excel",
        "power bi",
        "tableau",

        "pandas",
        "numpy",
        "scikit-learn",
        "sklearn",

        "machine learning",
        "deep learning",
        "artificial intelligence",

        "data science",
        "data analysis",
        "data analytics",

        "nlp",
        "natural language processing",

        "computer vision",

        "tensorflow",
        "pytorch",

        "aws",
        "azure",
        "google cloud",

        "docker",

        "git",
        "github",

        "flask",
        "fastapi",
        "streamlit",

        "html",
        "css",
        "javascript",
        "react",
        "node.js",

        "matplotlib",
        "seaborn",

        "statistics",
        "statistical analysis",

        "powerpoint",
        "ms office"
    ]

    text_lower = text.lower()

    found = []

    for skill in skill_dictionary:

        # Short skills (e.g. "c", "c#") must appear as
        # standalone words - otherwise "c" matches inside
        # any word containing the letter (e.g. "excel").
        if len(skill) <= 2:

            pattern = (
                r"(?<![A-Za-z0-9])"
                + re.escape(skill)
                + r"(?![A-Za-z0-9])"
            )

            present = (
                re.search(
                    pattern,
                    text_lower
                )
                is not None
            )

        else:

            present = skill in text_lower

        if present:

            if skill not in found:

                found.append(
                    skill
                )

    return found


# ============================================================
# EXTRACT CANDIDATE DETAILS
# ============================================================

def extract_candidate_details(
    text,
    filename=""
):

    text = clean_text(
        text
    )

    name = extract_name(
        text,
        filename
    )

    email = extract_email(
        text
    )

    phone = extract_phone(
        text
    )

    skills = extract_skills(
        text
    )

    return {

        "name": name,

        "email": email,

        "phone": phone,

        "skills": skills,

        "resume_text": text

    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print(
        "Resume parser loaded successfully."
    )

    print(
        "Tesseract:",
        TESSERACT_PATH or "not found"
    )