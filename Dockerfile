FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

ARG INCLUDE_ML_DEPS=0

# Install system tool for legacy DOC extraction.
RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword \
    && rm -rf /var/lib/apt/lists/*

# Create cache dir and non-root user early to keep layers stable.
RUN useradd -m -u 10001 appuser \
    && mkdir -p "${HF_HOME}" \
    && chown -R appuser:appuser /app "${HF_HOME}"

COPY requirements.txt ./requirements.txt
COPY requirements-ml.txt ./requirements-ml.txt

# Install the core app dependencies (small by default).
RUN pip install -r requirements.txt

# Optional ML dependencies to reduce default image size and build time.
RUN if [ "$INCLUDE_ML_DEPS" = "1" ]; then \
            pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 && \
            pip install -r requirements-ml.txt; \
        fi

COPY . .

USER appuser

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
