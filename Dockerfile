# Build stage: install dependencies in a full Python environment.
FROM python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28 AS builder
WORKDIR /build
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --target /build/deps -r requirements.lock

# Runtime stage: minimal final image with app code and dependencies.
FROM python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28
WORKDIR /app

# Copy pre-installed dependencies from builder.
COPY --from=builder --chown=1000:1000 /build/deps /usr/local/lib/python3.12/site-packages

# Create unprivileged user early; COPY --chown handles subsequent files.
RUN useradd --create-home --uid 1000 bella

# Copy application code and content.
COPY --chown=1000:1000 bella ./bella
COPY --chown=1000:1000 content ./content
COPY --chown=1000:1000 whatsapp_profile_picture.png ./

# Pin asset locations; these must match COPY destinations.
ENV PROFILE_PICTURE_PATH=/app/whatsapp_profile_picture.png
ENV CANNED_REPLIES_PATH=/app/content/canned_replies.yaml
ENV KNOWLEDGE_BASE_PATH=/app/content/knowledge_base.md
ENV ENROLLMENT_CARD_PATH=/app/content/enrollment_card.yaml

USER bella

EXPOSE 8000

# Matches the Compose dependency-aware readiness check and also covers plain
# `docker run`/`docker inspect` outside Coolify.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u, sys; sys.exit(0 if u.urlopen('http://localhost:8000/ready', timeout=3).status == 200 else 1)"

CMD ["python", "-m", "bella.app"]
