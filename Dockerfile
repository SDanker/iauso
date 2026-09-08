FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-server.txt ./
COPY LICENSE LICENSE-CODENOTCH ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements-server.txt \
    && groupadd --gid 1000 monitor \
    && useradd --uid 1000 --gid 1000 --create-home monitor
COPY iauso/ ./iauso/
COPY docker/config.collector.json ./docker/config.collector.json
USER 1000:1000
# --access-logfile - envia a stdout quien consulta y con que resultado, para
# poder diagnosticar una pantalla que no actualiza. El formato por defecto de
# Gunicorn no incluye cabeceras, asi que la clave del panel nunca se registra.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "2", "--timeout", "20", "--worker-tmp-dir", "/tmp", "--access-logfile", "-", "iauso.api:create_app()"]
