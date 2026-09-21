import os
import re
import io
import shutil
import logging
import tempfile

import pdfplumber
import pytesseract

from PIL import Image, ImageOps, ImageFilter
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
# TEXT RELIABILITY VALIDATION
# ============================================================
# A PDF can contain a "text layer" that is long enough to pass a
# simple length check but is actually corrupted or garbled (e.g. a
# broken font encoding that maps glyphs to the wrong characters).
# Example of such garbage: "SHLONIAYLS AA" / "SHLDNAUYLS AIX Ps".
#
# `is_text_reliable` decides whether extracted text actually looks
# like readable resume content before any candidate details are
# pulled from it. It is deliberately generic (no hardcoded special
# cases) and combines several independent signals.


_COMMON_ENGLISH = frozenset("""
the a an and or for with without by at in on to of from into within
between across through during after before about according among around
against along other another others these those this that they them their
there here where when which who whom what while will would can could should
must may might shall has have had been being is are was were be do does did
done not nor no but if as than so then also very most more less many much
some any all each few both because since until such only own same over under
above below up down out off we you your our its us years year month months
day date time work worked working works project projects team company
companies experience experienced education degree bachelor master mba btech
diploma engineering engineer developer development developing developed
design designing designed software hardware system systems application
applications technology technologies technical data analysis analytics
analyst scientist researcher management manage managed manager lead leader
skills skill quality testing test tested support supporting customer clients
service services business sales marketing product products operations
processes process improvement strong good excellent proficient knowledge
ability communicate communication written verbal interpersonal leadership
teamwork collaboration solving analytical summary objective career
professional academic university college school student internship
certification certificate training responsible duties responsibilities
including include includes using used users provide provides provided
deliver delivering deployed deployment implemented implementing maintained
maintaining requirements requirement specification database databases
python sql excel word powerpoint outlook office microsoft successfully
throughout various multiple report reports reporting candidate required
position role assistance activities planning organization organized
""".split())

_RESUME_KEYWORDS = frozenset([
    "experience", "education", "skills", "project", "work", "summary",
    "objective", "contact", "email", "phone", "degree", "technical",
    "professional", "career", "university", "computer", "data",
    "engineering", "management", "certificate", "training",
    "responsibilities", "company", "position", "profile",
])


def _count_unusual_chars(text):
    """Count replacement / control / private-use characters."""
    count = 0
    for ch in text:
        code = ord(ch)
        if ch == "\ufffd":
            count += 1
        elif 0xE000 <= code <= 0xF8FF:
            count += 1
        elif 0xF0000 <= code <= 0xFFFFD:
            count += 1
        elif code < 0x20 and ch not in "\n\r\t":
            count += 1
    return count


def _readable_words(text):
    """Tokens that plausibly read as words (letters + at least one vowel)."""
    return [
        w for w in re.findall(r"[A-Za-z]{3,25}", text)
        if re.search(r"[aeiouyAEIOUY]", w)
    ]


def _real_word_hits(text):
    """How many distinct tokens also appear in a common-English set."""
    tokens = {
        w.lower()
        for w in re.findall(r"[A-Za-z]{3,20}", text)
    }
    return len(tokens.intersection(_COMMON_ENGLISH))


def _suspicious_tokens(text):
    """Tokens that look like decoding/scrambling noise rather than words.

    Catches: tokens built from almost no distinct letters, 3+ repeated
    characters, 3+ consecutive consonants in a row, and long consonant-only
    runs - all typical of a corrupted font map.
    """
    suspicious = []
    for tok in re.findall(r"[A-Za-z]{2,}", text):
        lower = tok.lower()
        distinct = set(lower)

        if len(distinct) <= 2 and len(tok) >= 4:
            suspicious.append(tok)
            continue

        if re.search(r"(.)\1{2}", tok):
            suspicious.append(tok)
            continue

        if re.search(r"[bcdfghjklmnpqrstvwxyz]{3,}", lower):
            suspicious.append(tok)
            continue

        if len(tok) >= 8 and not re.search(r"[aeiouy]", lower):
            suspicious.append(tok)

    return suspicious


def is_text_reliable(text):
    """Return True when `text` looks like readable resume content.

    Combines multiple signals instead of relying on a bare length check:
    1. Amount of alphabetic characters
    2. Ratio of alphabetic to printable characters
    3. Readable English word count
    4. Suspicious/random token ratio
    5. Replacement / unusual characters
    6. Repetition patterns
    7. Presence of resume keywords and contact information
    8. Natural-language flow (multiple words)
    """

    if not text:
        return False

    text = clean_text(text)

    if len(text) < 30:
        return False

    alpha = sum(1 for ch in text if ch.isalpha())
    if alpha < 24:
        return False

    printable = sum(
        1 for ch in text
        if ch.isprintable() and not ch.isspace()
    )
    if printable and (alpha / printable) < 0.5:
        return False

    if _count_unusual_chars(text) > 0:
        logger.info("Text rejected: contains unusual / replacement characters.")
        return False

    text_lower = text.lower()

    ascii_letters = sum(
        1 for ch in text
        if ch.isalpha() and ord(ch) <= 127
    )
    non_ascii_letters = alpha - ascii_letters

    # ------------------------------------------------------------
    # Non-Latin scripts (Hindi, Arabic, CJK, ...): the ASCII English
    # word checks do not apply. Validate structure + contact info.
    # ------------------------------------------------------------
    if non_ascii_letters > ascii_letters:
        has_contact = (
            extract_email(text) != "Not Found"
            or extract_phone(text) != "Not Found"
        )
        structural = (
            len(text) >= 60
            and len(text.split()) >= 8
            and (
                has_contact
                or len(re.findall(r"\d", text)) >= 3
            )
        )
        return structural

    # ------------------------------------------------------------
    # Latin text path
    # ------------------------------------------------------------

    tokens = re.findall(r"[A-Za-z]{2,}", text)
    if not tokens:
        return False

    suspicious = _suspicious_tokens(text)
    suspicious_ratio = len(suspicious) / len(tokens)

    if suspicious_ratio > 0.35:
        logger.info(
            "Text rejected: suspicious token ratio too high (%.2f).",
            suspicious_ratio,
        )
        return False

    readable = _readable_words(text)
    real_hits = _real_word_hits(text)

    resume_hits = sum(
        1 for kw in _RESUME_KEYWORDS
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower)
    )

    has_email = extract_email(text) != "Not Found"
    has_phone = extract_phone(text) != "Not Found"
    has_digits = len(re.findall(r"[0-9]", text)) >= 2
    multiple_words = text.count(" ") >= 20

    signals = sum([
        1 if len(readable) >= 6 else 0,
        1 if real_hits >= 8 else 0,
        1 if resume_hits >= 2 else 0,
        1 if (has_email or has_phone or has_digits) else 0,
        1 if multiple_words else 0,
    ])

    if signals >= 3:
        return True

    logger.info(
        "Text rejected: not enough reliability signals (%d/5).",
        signals,
    )
    return False


# ============================================================
# EXTRACT TEXT FROM NORMAL PDF
# ============================================================

def _extract_with_pymupdf(file_bytes):
    """Extract text using PyMuPDF (fitz) - fastest and most reliable."""

    try:

        # Prefer the modern `pymupdf` import; fall back to the
        # classic `fitz` name for older versions of the package.
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        doc = fitz.open(
            stream=file_bytes,
            filetype="pdf"
        )

        pages_text = []

        for page in doc:

            page_text = page.get_text(
                "text",
                sort=True
            )

            if page_text:

                pages_text.append(
                    page_text
                )

        doc.close()

        if pages_text:

            return "\n".join(pages_text)

    except Exception as e:

        logger.warning("PyMuPDF extraction failed: %s", e)

    return ""


def _extract_with_pdfplumber(file_bytes):
    """Extract text using pdfplumber (fallback)."""

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

            return "\n".join(pages_text)

    except Exception as e:

        logger.warning("pdfplumber extraction failed: %s", e)

    return ""


def _extract_with_pypdf(file_bytes):
    """Extract text using pypdf (final fallback)."""

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

        return "\n".join(pages_text)

    except Exception as e:

        logger.warning("pypdf extraction failed: %s", e)

    return ""


def extract_pdf_text(file_bytes):

    text = ""

    # --------------------------------------------------------
    # Method 1: PyMuPDF (fitz) - primary
    # --------------------------------------------------------

    text = _extract_with_pymupdf(file_bytes)

    if text.strip():

        return clean_text(text)

    # --------------------------------------------------------
    # Method 2: pdfplumber
    # --------------------------------------------------------

    text = _extract_with_pdfplumber(file_bytes)

    if text.strip():

        return clean_text(text)

    # --------------------------------------------------------
    # Method 3: pypdf
    # --------------------------------------------------------

    text = _extract_with_pypdf(file_bytes)

    return clean_text(text)


# ============================================================
# TESSERACT VALIDATION
# ============================================================

def tesseract_available():
    """Return True if the Tesseract OCR engine is usable.

    This is a development-side check: it verifies the binary is
    reachable. On Render the Dockerfile installs tesseract-ocr,
    so this should return True inside the container.
    """
    if not TESSERACT_PATH:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


# ============================================================
# OCR IMAGE PREPROCESSING
# ============================================================

def _ocrize(pil_image):
    """Preprocess a page image to improve OCR accuracy.

    Converts to grayscale, enhances contrast and lightly denoises
    so Tesseract can read scanned resumes more reliably. The result
    is derived from the original image - the source is never
    destroyed and no hard thresholding is applied (which could
    erase light text).
    """
    try:
        gray = pil_image.convert("L")
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.MedianFilter(3))
        return gray
    except Exception as e:
        logger.debug("Image preprocessing failed: %s", e)
        try:
            return pil_image.convert("L")
        except Exception:
            return pil_image


def _ocr_readability_score(text):
    """Heuristic score for comparing OCR results."""
    if not text:
        return 0
    tokens = re.findall(r"[A-Za-z]{3,}", text)
    readable = [
        t for t in tokens
        if re.search(r"[aeiouyAEIOUY]", t)
    ]
    lines = [
        ln for ln in text.splitlines()
        if ln.strip()
    ]
    return len(readable) + min(len(lines), 30)


def _ocr_image_best(pil_image):
    """Run OCR on an image with a sensible, bounded fallback strategy.

    Fast path (the common case): OCR the image as-is with the default
    page segmentation (psm 3) and return immediately if the output is
    reliable. Only if that fails do we try OCR again on the rotated
    variants (scanned pages are sometimes rotated 90/180/270 degrees)
    and finally a --psm 6 retry on the winning rotation. This keeps the
    number of OCR passes small instead of running every configuration.
    """

    def _run(image, angle, psm):
        try:
            img = (
                image.rotate(angle, expand=True)
                if angle
                else image
            )
            processed = _ocrize(img)
            text = pytesseract.image_to_string(
                processed,
                config=psm
            )
            return clean_text(text)
        except Exception as e:
            logger.warning(
                "OCR (psm=%s angle=%s) failed: %s",
                psm,
                angle,
                e,
            )
            return ""

    candidate = _run(
        pil_image,
        0,
        "--psm 3"
    )

    if is_text_reliable(candidate):
        return candidate

    best_text = candidate
    best_score = _ocr_readability_score(best_text)
    best_angle = 0

    for angle in [180, 90, 270]:

        text = _run(
            pil_image,
            angle,
            "--psm 3"
        )

        if is_text_reliable(text):
            return text

        score = _ocr_readability_score(text)

        if score > best_score:

            best_score = score

            best_text = text

            best_angle = angle

    # A single uniform text block can be read better with psm 6.
    psm6 = _run(
        pil_image,
        best_angle,
        "--psm 6"
    )

    if _ocr_readability_score(psm6) > best_score:

        return psm6

    return best_text


# ============================================================
# OCR SCANNED PDF
# ============================================================

def extract_pdf_with_ocr(file_bytes):

    if not TESSERACT_PATH:
        logger.warning("OCR skipped: tesseract binary not available.")
        return ""

    # --------------------------------------------------------
    # Method 1: pdf2image + Tesseract (uses Poppler to render
    # each PDF page to a Pillow image, then OCRs it). This is
    # the most reliable general-purpose OCR path for scanned
    # and image-based PDFs.
    # --------------------------------------------------------

    tmp_dir = None

    try:

        from pdf2image import convert_from_bytes

        # Render with a temp dir so `pdftoppm` does not leak
        # any files into the repo or working directory.
        tmp_dir = tempfile.mkdtemp(
            prefix="resume_pdf_ocr_"
        )

        images = convert_from_bytes(
            file_bytes,
            dpi=300,
            output_folder=tmp_dir
        )

        extracted_pages = []

        for image in images:

            text = _ocr_image_best(
                image
            )

            if text:

                extracted_pages.append(
                    text
                )

        if extracted_pages:

            return clean_text(
                "\n".join(
                    extracted_pages
                )
            )

    except Exception as e:

        logger.warning("pdf2image OCR method failed: %s", e)

    finally:

        if tmp_dir and os.path.isdir(tmp_dir):

            shutil.rmtree(tmp_dir, ignore_errors=True)

    # --------------------------------------------------------
    # Method 2: PyMuPDF page rendering + Tesseract (no Poppler)
    #
    # If Poppler is unavailable, render each page directly to
    # a high-resolution image with PyMuPDF and OCR it.
    # --------------------------------------------------------

    try:

        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        doc = fitz.open(
            stream=file_bytes,
            filetype="pdf"
        )

        extracted_pages = []

        for page in doc:

            # Render the page to a high-resolution pixmap
            # (300 DPI gives Tesseract more detail to work with).
            page_image = page.get_pixmap(
                dpi=300
            )

            pil_image = Image.open(
                io.BytesIO(
                    page_image.tobytes(
                        "png"
                    )
                )
            )

            text = _ocr_image_best(
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
    """Compatibility wrapper: return extracted text as a string.

    Returns "" (empty) when no text can be extracted. Prefer
    `extract_resume_with_result` when a per-file error reason is
    needed for the UI.
    """
    text, _ = extract_resume_with_result(uploaded_file)
    return text


def extract_resume_with_result(uploaded_file):
    """Extract resume text and return (text, reason).

    reason is a dict with keys: 'filename', 'ok', 'message',
    'suggested_action'. This is used by the UI to report failures
    per file without crashing the whole screening run.
    """

    filename = getattr(
        uploaded_file,
        'name',
        'unknown'
    )

    def _result(
        filename,
        ok,
        message="",
        suggested_action="",
        method="",
        reliability="",
        error="",
        warnings=None
    ):
        return {
            "filename": filename,
            "ok": ok,
            "success": ok,
            "message": message,
            "suggested_action": suggested_action,
            "method": method,
            "reliability": reliability,
            "error": error,
            "warnings": warnings or [],
        }

    def _fail(reason, action, method="", reliability="unreliable", warnings=None):
        return "", _result(
            filename,
            False,
            reason,
            action,
            method=method,
            reliability=reliability,
            error=reason,
            warnings=warnings,
        )

    try:

        file_name = filename.lower()

        file_bytes = uploaded_file.getvalue()

        if not file_bytes:

            return _fail(
                "The file is empty.",
                "Please upload a non-empty resume.",
            )

        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

        if file_name.endswith(".pdf"):

            # ------------------------------------------------
            # Step 1-2: normal extraction, then validate it.
            # ------------------------------------------------

            text = extract_pdf_text(
                file_bytes
            )

            cleaned = clean_text(text)

            if is_text_reliable(cleaned):

                return cleaned, _result(
                    filename,
                    True,
                    method="pdf",
                    reliability="reliable",
                )

            if cleaned:

                logger.warning(
                    "Normal PDF extraction for '%s' produced text "
                    "but it failed reliability validation (%d chars). "
                    "Falling back to OCR.",
                    filename,
                    len(cleaned),
                )

            else:

                logger.info(
                    "Normal PDF extraction for '%s' yielded no "
                    "useful text. Falling back to OCR.",
                    filename,
                )

            # ------------------------------------------------
            # Step 3-4: OCR fallback, then validate OCR output.
            # ------------------------------------------------

            if not tesseract_available():

                logger.warning(
                    "OCR requested for '%s' but Tesseract binary is "
                    "unavailable (found: %s).",
                    filename,
                    TESSERACT_PATH or "none",
                )

                return _fail(
                    "OCR engine (Tesseract) is not available on "
                    "the server, so this image-based resume could "
                    "not be read.",
                    "The server needs tesseract-ocr installed. "
                    "The Docker deployment installs it automatically.",
                    method="ocr (tesseract)",
                    warnings=["Tesseract binary not found on server."],
                )

            logger.info(
                "Starting OCR for '%s'.",
                filename,
            )

            ocr_text = extract_pdf_with_ocr(
                file_bytes
            )

            ocr_cleaned = clean_text(ocr_text)

            if is_text_reliable(ocr_cleaned):

                logger.info(
                    "OCR extraction for '%s' produced reliable text.",
                    filename,
                )

                return ocr_cleaned, _result(
                    filename,
                    True,
                    method="ocr (tesseract)",
                    reliability="reliable",
                )

            if ocr_cleaned:

                logger.warning(
                    "OCR output for '%s' failed reliability "
                    "validation (%d chars). Extraction rejected "
                    "rather than saving garbled text.",
                    filename,
                    len(ocr_cleaned),
                )

                return _fail(
                    "The PDF text layer is corrupted/unreadable. "
                    "OCR was attempted automatically, but its "
                    "result was still unreadable, so no candidate "
                    "data could be extracted.",
                    "Try a clearer scan of the resume, or upload "
                    "it as DOCX/TXT.",
                    method="ocr (tesseract)",
                    warnings=[
                        "Normal PDF text and OCR output both "
                        "failed the readability check."
                    ],
                )

            return _fail(
                "The PDF appears to contain no readable text and "
                "OCR could not extract any either.",
                "The PDF may be corrupted or contain an unsupported "
                "image format. Try a clearer scan.",
                method="pdf + ocr",
                warnings=["OCR produced no usable text."],
            )

        # ----------------------------------------------------
        # DOCX
        # ----------------------------------------------------

        elif file_name.endswith(".docx"):

            docx_text = extract_docx_text(
                file_bytes
            )

            if docx_text:

                return docx_text, _result(
                    filename,
                    True,
                    method="docx",
                    reliability="reliable",
                )

            return _fail(
                "This DOCX document did not yield any readable text.",
                "The document may be empty or password-protected.",
                method="docx",
            )

        # ----------------------------------------------------
        # TXT
        # ----------------------------------------------------

        elif file_name.endswith(".txt"):

            try:

                txt_text = clean_text(
                    file_bytes.decode(
                        "utf-8",
                        errors="ignore"
                    )
                )

                if txt_text:

                    return txt_text, _result(
                        filename,
                        True,
                        method="txt",
                        reliability="reliable",
                    )

                logger.warning(
                    "TXT extraction for '%s' produced no readable "
                    "content.",
                    filename,
                )

            except Exception as e:

                logger.warning(
                    "TXT decoding failed for '%s': %s",
                    filename,
                    e,
                )

            return _fail(
                "This text file yielded no readable content.",
                "The file may be empty.",
                method="txt",
            )

        # ----------------------------------------------------
        # Unsupported format
        # ----------------------------------------------------

        return _fail(
            "Unsupported file format.",
            "Please upload a PDF or DOCX resume.",
        )

    except Exception as e:

        logger.error(
            "TEXT EXTRACTION ERROR for '%s': %s",
            filename,
            e,
        )

        return _fail(
            "The resume could not be read due to an unexpected "
            "processing error.",
            "The file may be corrupted. Please try another resume.",
        )


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

    # --------------------------------------------------------
    # Fallback: OCR sometimes splits edges of the email with
    # extra symbols (e.g. "W_arun@g_mail.com"->"arun@gmail.com"
    # or "arun@gmail_com"). Find a clean @-based match.
    # --------------------------------------------------------

    at_match = re.search(
        r"[A-Za-z0-9][A-Za-z0-9._%+-]*(?:@|…|→)\s*"
        r"[A-Za-z0-9][A-Za-z0-9.-]*(?:\.|\.\.|…)\s*"
        r"[A-Za-z]{2,}",
        text
    )

    if at_match:

        email = at_match.group(0)

        email = email.replace(
            " ", ""
        )

        email = email.replace(
            "…", ""
        )

        email = email.replace(
            "→", "@"
        )

        email = re.sub(
            r"\.+",
            ".",
            email
        )

        email = re.sub(
            r"[^A-Za-z0-9@._%-]",
            "",
            email
        )

        if "@" in email and "." in email:

            return email

    return "Not Found"


# ============================================================
# EXTRACT PHONE
# ============================================================

def extract_phone(text):

    patterns = [

        r"\+91[\s-]?\d{10}",

        r"\+91[\s-]?\d{5}[\s-]?\d{5}",

        r"\+\d{1,3}[\s-]?\(\d{2,4}\)[\s-]?\d{3,4}[\s-]?\d{4}",

        r"\(\d{3}\)[\s-]?\d{3}[\s-]?\d{4}",

        r"\b\d{5}[\s-]\d{5}\b",

        r"\b\d{10}\b",

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
# NAME VALIDATION HELPERS
# ============================================================

def _looks_like_name_word(word):
    """Return True if word has a human-name capitalization pattern.

    Rejects OCR noise like "woIsioag" (uppercase in the middle),
    "wajqoid" (no capitals) and "yigy" - while accepting real
    names like John, SMITH, Mcdonald, O'Brien, Jean-Pierre.
    """
    if not word or len(word) < 2 or len(word) > 12:
        return False

    if word.isupper():
        return True

    caps = [i for i, ch in enumerate(word) if ch.isupper()]

    if len(caps) == 1:
        return caps[0] == 0

    if len(caps) == 2:
        return caps[0] == 0

    return False


def _is_garbled_word(word):
    """Generic guard against treating decoding/OCR noise as a name word.

    Flags tokens that look like output from a corrupted font map or
    OCR garbage: almost no distinct letters, tripled characters, long
    consecutive-consonant runs, or long vowel-less tokens. It is generic
    (no hardcoded resume names) so real human names pass untouched.
    """
    if not word or len(word) < 2:
        return False

    if len(word) == 2:
        return False

    lower = word.lower()

    distinct = set(lower)

    if len(distinct) <= 2 and len(word) >= 4:
        return True

    if re.search(r"(.)\1{2}", word):
        return True

    if re.search(r"[bcdfghjklmnpqrstvwxyz]{3,}", lower):
        return True

    if len(word) >= 8 and not re.search(r"[aeiouy]", lower):
        return True

    return False


def _is_valid_name(name):
    """Check if a name looks like a real person name."""
    if not name or len(name) < 3:
        return False
    words = name.split()
    if len(words) < 2 or len(words) > 5:
        return False
    for word in words:
        if not word or len(word) < 2 or len(word) > 20:
            return False
        if not word[0].isupper():
            return False
        if len(word) > 12:
            return False
        if _is_garbled_word(word):
            return False
    return True


def _name_from_email(email):
    """Derive a candidate name from an email address."""
    if not email or "@" not in email:
        return ""
    local = email.split("@")[0]
    local = re.sub(
        r'^(info|admin|contact|support|hello|hi|mail|email|user|test)',
        '', local, flags=re.IGNORECASE
    )
    parts = re.split(r'[._\-+]', local)
    parts = [p for p in parts if p and len(p) >= 2 and p.isalpha()]
    if len(parts) >= 2:
        return " ".join(p.capitalize() for p in parts[:3])
    return ""


# ============================================================
# EXTRACT NAME
# ============================================================

def extract_name(text, filename=""):
    """Extract candidate name using multiple strategies.

    Priority:
    1. Labeled patterns (Name:, Full Name:, etc.)
    2. Email-derived name
    3. Strict heuristic (first lines)
    4. Filename-based
    5. "Unknown Candidate"
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # --------------------------------------------------------
    # Strategy 1: Labeled patterns
    # --------------------------------------------------------

    labeled_patterns = [
        r'(?:candidate\s+name|full\s+name|name)\s*[:\-=]\s*(.+?)(?:\n|$)',
        r'(?:applicant|person)\s*[:\-=]\s*(.+?)(?:\n|$)',
    ]

    for pattern in labeled_patterns:
        match = re.search(
            pattern, text,
            re.IGNORECASE | re.MULTILINE
        )
        if match:
            name = match.group(1).strip()
            name = re.sub(
                r"[^A-Za-z .'-]", "", name
            ).strip()
            if _is_valid_name(name):
                return name

    # --------------------------------------------------------
    # Strategy 2: Email-derived name
    # --------------------------------------------------------

    email = extract_email(text)
    if email and email != "Not Found":
        name_from_email = _name_from_email(email)
        if name_from_email:
            return name_from_email

    # --------------------------------------------------------
    # Strategy 3: Strict heuristic (first lines)
    # --------------------------------------------------------

    blocked = [
        "resume", "curriculum", "vitae", "email",
        "phone", "mobile", "address", "profile",
        "objective", "summary", "skills", "education",
        "experience", "contact", "certification",
        "project", "reference", "date", "birth",
        "age", "gender", "nationality", "religion",
        "marital", "declaration", "career",
        "professional", "personal", "academic",
        "award", "achievement", "language", "interest",
        "hobby", "detail", "information", "about",
        "engineer", "developer", "analyst", "manager",
        "designer", "architect", "consultant",
        "scientist", "researcher", "recruiter",
        "intern", "freelancer", "lead", "senior",
        "junior", "associate", "specialist",
        "coordinator", "executive", "officer",
        "technician", "software", "web", "cloud",
        "devops", "administrator", "professional",
    ]

    for line in lines[:15]:
        clean_line = re.sub(
            r"[^A-Za-z .'-]", "", line
        ).strip()
        words = clean_line.split()

        if 2 <= len(words) <= 4:
            lower_line = clean_line.lower()

            if not any(
                word in lower_line for word in blocked
            ):
                if all(
                    _looks_like_name_word(word)
                    for word in words
                ):
                    if all(
                        not _is_garbled_word(word)
                        for word in words
                    ):
                        if all(
                            len(word) >= 2 for word in words
                        ):
                            return clean_line

    # --------------------------------------------------------
    # Strategy 4: Filename
    # --------------------------------------------------------

    if filename:
        name = os.path.splitext(
            os.path.basename(filename)
        )[0]
        name = re.sub(
            r'resume|cv', '', name,
            flags=re.IGNORECASE
        )
        name = re.sub(r'[_\-]+', ' ', name).strip()
        if name and len(name) >= 3 and len(name) <= 50:
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
        "javascript",
        "typescript",
        "go",
        "rust",
        "ruby",
        "php",
        "swift",
        "kotlin",
        "scala",
        "r",
        "matlab",
        "sas",
        "perl",
        "lua",
        "sql",

        "mysql",
        "postgresql",
        "mongodb",
        "oracle",
        "sql server",
        "redis",
        "cassandra",
        "dynamodb",
        "elasticsearch",
        "neo4j",
        "sqlite",
        "db2",

        "excel",
        "power bi",
        "tableau",
        "looker",
        "qlik",

        "pandas",
        "numpy",
        "scipy",
        "scikit-learn",
        "sklearn",
        "xgboost",
        "lightgbm",

        "machine learning",
        "deep learning",
        "artificial intelligence",

        "data science",
        "data analysis",
        "data analytics",
        "data visualization",

        "nlp",
        "natural language processing",

        "computer vision",

        "tensorflow",
        "pytorch",
        "keras",

        "aws",
        "azure",
        "google cloud",
        "gcp",

        "docker",
        "kubernetes",
        "terraform",
        "ansible",
        "jenkins",
        "ci/cd",
        "devops",

        "git",
        "github",
        "gitlab",

        "flask",
        "fastapi",
        "streamlit",
        "django",
        "spring",
        "angular",
        "vue.js",
        "react",
        "node.js",
        "next.js",

        "html",
        "css",
        "sass",
        "bootstrap",

        "matplotlib",
        "seaborn",
        "plotly",
        "bokeh",

        "statistics",
        "statistical analysis",
        "regression",
        "classification",
        "clustering",
        "a/b testing",

        "powerpoint",
        "word",
        "ms office",
        "google sheets",
        "google docs",

        "communication",
        "leadership",
        "teamwork",
        "problem solving",
        "analytical thinking",
        "project management",
        "time management",
        "presentation",
        "negotiation",
        "critical thinking",
        "strategic planning",

        "agile",
        "scrum",
        "kanban",
        "six sigma",
        "pmp",
        "itil",

        "data engineering",
        "etl",
        "big data",
        "spark",
        "hadoop",
        "kafka",
        "airflow",
        "hive",

        "blockchain",
        "cybersecurity",
        "networking",
        "linux",
        "windows server",

        "sales",
        "marketing",
        "seo",
        "sem",
        "social media",
        "content writing",
        "copywriting",

        "financial analysis",
        "accounting",
        "tally",
        "sap",
        "erp",

        "java spring boot",
        "microservices",
        "rest api",
        "graphql",
        "web scraping",
        "beautifulsoup",
        "selenium",

        "jira",
        "confluence",
        "slack",
        "trello",
        "notion",

        "photoshop",
        "illustrator",
        "figma",
        "adobe xd",
        "canva",

        "video editing",
        "premiere pro",
        "after effects",

        "technical writing",
        "report writing",
        "data entry",
        "typing",

        "quality assurance",
        "qa testing",
        "selenium testing",
        "automation testing",
        "manual testing",
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
# EXTRACT EDUCATION
# ============================================================

def _extract_education(text):
    """Best-effort extraction of education snippets."""

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    keywords = [
        "b.tech", "b.e", "m.tech", "b.sc", "m.sc", "ba ",
        "ma ", "phd", "mba", "bca", "mca", "bcom", "mcom",
        "bachelor", "master", "degree", "diploma",
        "engineering", "university", "college", "school",
        "intermediate", "high school", "ssc", "hsc",
    ]

    found = []

    for i, line in enumerate(lines[:80]):

        lower = line.lower()

        if any(k in lower for k in keywords):

            snippet = " ".join(lines[i:i + 2])
            snippet = " ".join(snippet.split())
            if snippet not in found:
                found.append(snippet)

        if len(found) >= 3:
            break

    return found


# ============================================================
# EXTRACT EXPERIENCE
# ============================================================

def _extract_experience(text):
    """Best-effort extraction of experience snippets."""

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    keywords = [
        "experience", "work history", "employment",
        "professional experience", "job", "intern",
        "worked at", "worked as", "years of",
    ]

    found = []

    for i, line in enumerate(lines[:80]):

        lower = line.lower()

        if any(k in lower for k in keywords):

            snippet = " ".join(lines[i:i + 2])
            snippet = " ".join(snippet.split())
            if snippet not in found:
                found.append(snippet)

        if len(found) >= 3:
            break

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

    education = _extract_education(
        text
    )

    experience = _extract_experience(
        text
    )

    # --------------------------------------------------------
    # Gemini fallback for missing critical fields
    # --------------------------------------------------------

    need_gemini = (
        (name == "Unknown Candidate" or email == "Not Found")
        and len(text) > 50
    )

    if need_gemini:
        try:
            from gemini_service import ask_gemini
            prompt = (
                "Extract the following from this resume text.\n"
                "Return ONLY a valid JSON object, nothing else.\n\n"
                "Fields: name, email, phone, skills (as comma-separated string)\n\n"
                "Resume text:\n"
                + text[:3000] + "\n\n"
                'JSON format: {"name":"...","email":"...","phone":"...","skills":"..."}'
            )
            response, error = ask_gemini(prompt)
            if response and not error:
                import json as _json
                json_match = re.search(
                    r'\{[^{}]*\}', response, re.DOTALL
                )
                if json_match:
                    data = _json.loads(json_match.group())
                    if (
                        name == "Unknown Candidate"
                        and data.get("name", "").strip()
                    ):
                        extracted = data["name"].strip()
                        if _is_valid_name(extracted):
                            name = extracted
                    if (
                        email == "Not Found"
                        and data.get("email", "").strip()
                    ):
                        em = data["email"].strip()
                        if re.search(
                            r'@', em
                        ):
                            email = em
                    if (
                        phone == "Not Found"
                        and data.get("phone", "").strip()
                    ):
                        phone = data["phone"].strip()
                    if not skills and data.get("skills"):
                        raw = data["skills"]
                        if isinstance(raw, str):
                            skills = [
                                s.strip()
                                for s in raw.split(",")
                                if s.strip()
                            ]
                        elif isinstance(raw, list):
                            skills = [
                                s.strip()
                                for s in raw
                                if s and s.strip()
                            ]
        except Exception as e:

            logger.warning(
                "Gemini fallback extraction failed: %s",
                e,
            )

    return {

        "name": name,

        "email": email,

        "phone": phone,

        "skills": skills,

        "education": education,

        "experience": experience,

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