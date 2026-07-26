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
            fonts-noto-cjk \
            pkg-config \
            && break; \
        if [ "$attempt" -eq 5 ]; then \
            exit 1; \
        fi; \
        sleep 5; \
    done; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir gunicorn && pip install --no-cache-dir -r requirements.txt

# RenderCV has a newer CLI dependency set than Docling. Keep the pinned
# renderer in its own virtual environment so document ingestion stays stable.
RUN python -m venv /opt/rendercv && \
    /opt/rendercv/bin/pip install --no-cache-dir "rendercv[full]==2.8" && \
    mkdir -p /opt/rendercv/home /opt/rendercv/cache /tmp/rendercv-prefetch && \
    cd /tmp/rendercv-prefetch && \
    HOME=/opt/rendercv/home XDG_CACHE_HOME=/opt/rendercv/cache \
        /opt/rendercv/bin/rendercv new "iFaceOff Prefetch" --theme classic --locale english && \
    HOME=/opt/rendercv/home XDG_CACHE_HOME=/opt/rendercv/cache \
        /opt/rendercv/bin/rendercv render iFaceOff_Prefetch_CV.yaml \
        --pdf-path prefetch.pdf --png-path prefetch.png \
        --dont-generate-html --dont-generate-markdown && \
    rm -rf /tmp/rendercv-prefetch

COPY . .
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV RESUME_RENDER_EXECUTABLE=/opt/rendercv/bin/rendercv
ENV RESUME_RENDER_CACHE_DIR=/opt/rendercv/cache

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "ai_interview_backend.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
