FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
# pip is not needed once the app is installed; removing it drops its advisories from the
# running image (Codex release review, 18 Nov 2026).
RUN pip install --no-cache-dir . && pip uninstall -y pip
COPY . .
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8001
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8001", "--workers", "3"]
