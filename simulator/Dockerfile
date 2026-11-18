FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
# Exact versions with hashes, so every build installs the same files (SEC-14). The app runs
# from /app, so the project itself is not installed. pip is not needed afterwards; removing
# it drops its advisories from the running image (Codex release review, 18 Nov 2026).
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock \
    && pip uninstall -y pip
COPY . .
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8001
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8001", "--workers", "3"]
