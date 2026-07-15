# Small, non-root image for the FastAPI service. No secrets are baked in —
# everything the app and the deploy scripts need comes from environment
# variables supplied at runtime (see docs/deploy.md).
FROM python:3.12-slim

WORKDIR /app

# Copy the installable unit (pyproject.toml + the bella package itself —
# setuptools needs both present to build) before anything else, then
# install. Source-only edits below this line don't bust the dependency layer.
COPY pyproject.toml ./
COPY bella ./bella
RUN pip install --no-cache-dir .

# Content and the presentation asset are baked in for now; the Enrollment
# Card/Knowledge Base/canned replies aren't read by any code yet (tickets
# 04+). Never copy the *.docx Source Documents — ADR-0001 keeps them out of
# anything the bot or an operator-facing surface can reach, deploy image
# included.
COPY content ./content
COPY whatsapp_profile_picture.png ./

# Pin the asset location rather than letting bella/config.py infer it from
# __file__ — the inferred path only happens to be right when the app is run
# as `python -m bella.app` from this WORKDIR.
ENV PROFILE_PICTURE_PATH=/app/whatsapp_profile_picture.png

# Runs as an unprivileged user; the process never needs root.
RUN useradd --create-home --uid 1000 bella && chown -R bella:bella /app
USER bella

EXPOSE 8000

# Redundant with Coolify's own HTTP healthcheck (wired to GET /health in
# docs/deploy.md) — this one covers `docker inspect`/plain `docker run`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u, sys; sys.exit(0 if u.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"

CMD ["python", "-m", "bella.app"]
