FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 DATABASE_URL=sqlite:////data/pereryv.db
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home app && mkdir /data && chown app:app /data
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
USER app
EXPOSE 8080
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
