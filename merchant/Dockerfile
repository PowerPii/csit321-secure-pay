FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY . .
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8002
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8002", "--workers", "3"]
