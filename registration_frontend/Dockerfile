FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY registration_frontend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY --chown=appuser:appuser frontend_shared ./frontend_shared
COPY --chown=appuser:appuser registration_frontend ./registration_frontend
USER appuser
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "registration_frontend.app:create_app()"]
