#!/usr/bin/env bash
# Despliegue de LabDigital (lo ejecuta el runner self-hosted al hacer merge a main; también a mano).
#   1. pg_dump de respaldo   2. build de imágenes   3. alembic upgrade head   4. up   5. health   6. rollback si falla
# Configuración fuera de git: $LABDIGITAL_ENV_FILE (por defecto ~/labdigital-deploy/.env).
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="${LABDIGITAL_PROJECT:-labdigital}"
ENV_FILE="${LABDIGITAL_ENV_FILE:-$HOME/labdigital-deploy/.env}"
BACKUP_DIR="${LABDIGITAL_BACKUP_DIR:-$HOME/labdigital-deploy/backups}"
API_HEALTH="${LABDIGITAL_API_HEALTH:-http://127.0.0.1:8088/v1/health}"
WEB_HEALTH="${LABDIGITAL_WEB_HEALTH:-http://127.0.0.1:8089/labdigital/}"
SERVICES=(api worker web)

[ -f "$ENV_FILE" ] || { echo "Falta el archivo de entorno: $ENV_FILE" >&2; exit 1; }
compose() { docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f docker-compose.yml "$@"; }

wait_ok() { local url=$1 i; for i in $(seq 1 60); do curl -fsS --max-time 5 "$url" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }

REV=$(git rev-parse --short HEAD)
echo "==> LabDigital $REV"

# 1. Base de datos arriba y respaldo previo
compose up -d db
for i in $(seq 1 30); do compose exec -T db pg_isready -q && break; sleep 2; done
mkdir -p "$BACKUP_DIR"
DUMP="$BACKUP_DIR/pre-deploy-$(date +%Y%m%d-%H%M%S)-$REV.sql.gz"
compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$DUMP"
echo "==> Respaldo: $DUMP ($(du -h "$DUMP" | cut -f1))"
ls -1t "$BACKUP_DIR"/pre-deploy-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f   # conservar 14

# 2. Etiquetar imágenes actuales para rollback y construir
for s in "${SERVICES[@]}"; do
  img="labdigital-$s"
  docker image inspect "$img:latest" >/dev/null 2>&1 && docker tag "$img:latest" "$img:previous" || true
done
compose build

# 3. Migraciones (deben ser compatibles hacia atrás: la versión anterior sigue funcionando con el esquema nuevo)
compose run --rm api alembic upgrade head

# 4-5. Levantar y comprobar
compose up -d "${SERVICES[@]}"
if wait_ok "$API_HEALTH" && wait_ok "$WEB_HEALTH"; then
  echo "==> Despliegue correcto ($REV)"
  docker image prune -f >/dev/null 2>&1 || true
  exit 0
fi

# 6. Rollback de imágenes (el esquema queda migrado; restaurar $DUMP a mano solo si hiciera falta)
echo "!! No quedó sano. Registro reciente:" >&2
compose logs --tail 40 api web >&2 || true
for s in "${SERVICES[@]}"; do
  img="labdigital-$s"
  docker image inspect "$img:previous" >/dev/null 2>&1 && docker tag "$img:previous" "$img:latest"
done
compose up -d --no-build --force-recreate "${SERVICES[@]}"
wait_ok "$API_HEALTH" && echo "!! Revertido a la versión anterior" >&2 || echo "!! La versión anterior tampoco responde; respaldo en $DUMP" >&2
exit 1
