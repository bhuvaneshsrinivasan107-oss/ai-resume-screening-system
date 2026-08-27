# ============================================================
# AI Resume Screening & Candidate Ranking System
# Render deployment image
#
# The native (nim) Python runtime on Render does NOT include
# the system packages required for OCR-based PDF extraction:
#   - tesseract-ocr  (OCR engine used by pytesseract)
#   - poppler-utils  (PDF -> image rendering used by pdf2image)
#
# This Dockerfile builds a custom image that installs those
# packages so scanned/image PDF resumes can be processed.
# ============================================================

FROM python:3.11-slim

# ------------------------------------------------------------
# System packages needed by the resume parser (OCR path).
#   - tesseract-ocr : OCR text extraction for scanned PDFs
#   - poppler-utils : `pdftoppm` used by pdf2image
#   - build tools   : needed to compile some pip wheels
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Working directory
# ------------------------------------------------------------
WORKDIR /app

# ------------------------------------------------------------
# Install Python dependencies (cached per requirements change)
# ------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------
# Copy the application source into the image
# ------------------------------------------------------------
COPY . .

# ------------------------------------------------------------
# Streamlit configuration for headless deployment
# ------------------------------------------------------------
EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# ------------------------------------------------------------
# Launch the Streamlit application
# ------------------------------------------------------------
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
