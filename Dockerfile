FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# Create cache dir and non-root user early to keep layers stable.
RUN useradd -m -u 10001 appuser \
    && mkdir -p "${HF_HOME}" \
    && chown -R appuser:appuser /app "${HF_HOME}"

COPY requirements.txt ./requirements.txt

# Install heavy torch dependency in its own layer for better reuse.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1

# Install the rest of the app dependencies.
RUN pip install -r requirements.txt

COPY . .

USER appuser

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
