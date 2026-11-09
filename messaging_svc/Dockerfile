FROM python:3.12-slim

RUN groupadd -r appuser && useradd -m -r -g appuser appuser
WORKDIR /home/appuser/app

COPY ./requirements.txt /home/appuser/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /home/appuser/requirements.txt

COPY . /home/appuser/app
COPY --from=shared . /home/appuser/app/frontend_shared
ENV FRONTEND_SHARED_PATH=/home/appuser/app/frontend_shared
RUN chown -R appuser:appuser /home/appuser/app

USER appuser

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "1", "--threads", "100", "app:create_app()"]