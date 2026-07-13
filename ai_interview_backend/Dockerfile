FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_NO_CACHE_DIR 1

RUN set -eux; \
    for attempt in 1 2 3 4 5; do \
        apt-get update -o Acquire::Retries=3 && \
        apt-get install -y --no-install-recommends \
            build-essential \
            curl \
            ffmpeg \
            pkg-config \
            libmariadb-dev \
            && break; \
        if [ "$attempt" -eq 5 ]; then \
            exit 1; \
        fi; \
        sleep 5; \
    done; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir gunicorn && pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "ai_interview_backend.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
