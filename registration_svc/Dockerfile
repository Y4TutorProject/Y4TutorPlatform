FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY users_svc/requirements.txt ./users_svc/requirements.txt
COPY registration_svc/requirements.txt ./registration_svc/requirements.txt
RUN pip install --no-cache-dir -r registration_svc/requirements.txt

RUN useradd --create-home appuser

COPY --chown=appuser:appuser users_svc ./users_svc
COPY --chown=appuser:appuser registration_svc ./registration_svc

USER appuser

EXPOSE 5000

CMD ["flask", "--app", "registration_svc:create_app", "run", "--host=0.0.0.0", "--port=5000"]
