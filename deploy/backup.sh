#!/usr/bin/env bash
# Respaldo diario de LabDigital: base de datos (pg_dump) + archivos entregados (volumen de blobs).
# Cron (usuario gideam):  15 3 * * *  $HOME/labdigital-deploy/backup.sh >> $HOME/labdigital-deploy/backups/backup.log 2>&1
# Deja un latido para Prometheus en el textfile collector: labdigital_respaldo_ultimo_exito_timestamp.
set -euo pipefail

PROJECT="${LABDIGITAL_PROJECT:-labdigital}"
DEST="${LABDIGITAL_BACKUP_DIR:-$HOME/labdigital-deploy/backups}/diario"
KEEP_DAYS="${LABDIGITAL_BACKUP_KEEP_DAYS:-14}"
PROM_DIR="${LABDIGITAL_PROM_DIR:-$HOME/observabilidad/textfile_collector}"
DB="${PROJECT}-db-1"
BLOBS_VOL="${PROJECT}_blobs"

STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"
umask 077
echo "== $(date -Is) respaldo $STAMP"

# 1. Base de datos: formato custom (comprimido, restaurable con pg_restore) y verificación de que se puede leer
DUMP="$DEST/db-$STAMP.dump"
docker exec "$DB" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DUMP.part"
docker exec -i "$DB" pg_restore --list < "$DUMP.part" > /dev/null
mv "$DUMP.part" "$DUMP"

# 2. Archivos (blobs direccionados por contenido): tar del volumen en solo lectura
BLOBS="$DEST/blobs-$STAMP.tar.gz"
docker run --rm --user "$(id -u):$(id -g)" -v "$BLOBS_VOL":/data/blobs:ro -v "$DEST":/out alpine:3.20 \
  sh -c "tar -C /data -czf /out/.blobs-$STAMP.part blobs && tar -tzf /out/.blobs-$STAMP.part > /dev/null"
mv "$DEST/.blobs-$STAMP.part" "$BLOBS"

# 3. Retención
find "$DEST" -maxdepth 1 -type f \( -name 'db-*.dump' -o -name 'blobs-*.tar.gz' \) -mtime +"$KEEP_DAYS" -delete

DB_BYTES=$(stat -c %s "$DUMP"); BLOB_BYTES=$(stat -c %s "$BLOBS")
echo "   db: $DUMP ($DB_BYTES B) · blobs: $BLOBS ($BLOB_BYTES B)"

# 4. Latido para Prometheus (escritura atómica)
if [ -d "$PROM_DIR" ]; then
  TMP=$(mktemp "$PROM_DIR/.labdigital.prom.XXXXXX")
  {
    echo "# HELP labdigital_respaldo_ultimo_exito_timestamp Epoch del ultimo respaldo diario de LabDigital que termino bien."
    echo "# TYPE labdigital_respaldo_ultimo_exito_timestamp gauge"
    echo "labdigital_respaldo_ultimo_exito_timestamp $(date +%s)"
    echo "# HELP labdigital_respaldo_bytes Tamano del ultimo respaldo de LabDigital por parte."
    echo "# TYPE labdigital_respaldo_bytes gauge"
    echo "labdigital_respaldo_bytes{parte=\"db\"} $DB_BYTES"
    echo "labdigital_respaldo_bytes{parte=\"blobs\"} $BLOB_BYTES"
  } > "$TMP"
  chmod 644 "$TMP"
  mv "$TMP" "$PROM_DIR/labdigital.prom"
fi
echo "== $(date -Is) respaldo correcto"
