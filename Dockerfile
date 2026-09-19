FROM python:3.11-slim

# Install OCR and PDF tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Streamlit health check
HEALTHCHECK CMD curl --fail http://localhost:${PORT:-10000}/_stcore/health || exit 1

# Start Streamlit
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-10000} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]