FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
COPY scripts ./scripts
COPY static ./static
COPY templates ./templates
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh \
    && mkdir -p data/uploads

ENV PORT=8000
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]