# API y worker de LabDigital (misma imagen, distinto comando).
#   API:     docker run ... labdigital-api            (uvicorn en :8000 dentro del contenedor)
#   Worker:  docker run ... labdigital-api python -m backend.entrypoints.worker.main
#   Migrar:  docker run ... labdigital-api alembic upgrade head
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
RUN groupadd --system --gid 10001 labdigital \
    && useradd --system --uid 10001 --gid labdigital --no-create-home labdigital
WORKDIR /app
COPY --from=build --chown=labdigital:labdigital /app/.venv /app/.venv
COPY --chown=labdigital:labdigital src ./src
COPY --chown=labdigital:labdigital alembic.ini ./
COPY --chown=labdigital:labdigital migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER labdigital
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=4).status == 200 else 1)"
# --proxy-headers: la IP del cliente sale de X-Forwarded-For puesto por nginx. El puerto del
# contenedor sólo se publica en 127.0.0.1 del host, así que se confía en cualquier origen.
# `--proxy-headers` sólo confía en X-Forwarded-For de las IPs de FORWARDED_ALLOW_IPS (uvicorn
# la lee del entorno). NUNCA "*": cualquiera falsearía su IP y se saltaría los límites. El
# compose de producción la fija a la IP del gateway del bridge (donde llega nginx).
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["uvicorn", "backend.entrypoints.web.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers"]
