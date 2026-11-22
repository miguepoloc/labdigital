# Despliegue de LabDigital

Servidor `alunaia` (mismo host que JG FPGA). Todo detrás del nginx del host en `gideam.unimagdalena.edu.co`.

| Servicio | Contenedor | Puerto local |
|---|---|---|
| Postgres 16 | `labdigital-db-1` | (sin publicar) |
| API FastAPI | `labdigital-api-1` | `127.0.0.1:8088` |
| Worker (outbox → correo) | `labdigital-worker-1` | — |
| Web (landing + SPA, nginx) | `labdigital-web-1` | `127.0.0.1:8089` |
| JG FPGA (otro repo) | `jgfpga-jgfpga-1` | `127.0.0.1:8087` |

## Configuración (`~/labdigital-deploy/.env`, permisos 600, fuera de git)

```
POSTGRES_USER=labdigital
POSTGRES_PASSWORD=<aleatoria>
POSTGRES_DB=labdigital
JWT_KID=2027-01
JWT_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----\n..."
JWT_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----\n..."
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=<usuario Brevo>
SMTP_PASSWORD=<clave SMTP Brevo>
MAIL_FROM=LabDigital GIDEAM <no-responder@mcda.tools>
ADMIN_EMAILS=<correo1>,<correo2>
```

## CI/CD

- `CI` (push y PR): backend (ruff, mypy, import-linter, pytest con Postgres) y frontend (lint, tests, build).
- `CD` (`.github/workflows/cd.yml`): cuando `CI` termina bien en un push a `main`, el runner self-hosted
  (etiquetas `alunaia,labdigital`) ejecuta `deploy/deploy.sh`: respaldo `pg_dump` → build → `alembic upgrade head`
  → up → health → rollback de imágenes si falla. Las migraciones deben ser compatibles hacia atrás.

## nginx

`deploy/nginx/labdigital.locations.conf` se copia a `/etc/nginx/snippets/labdigital.conf` y se incluye en el server
443 de `/etc/nginx/sites-available/gideam` (backup + `nginx -t` + reload). **Orden de salida a producción**:
1. Plataforma arriba y probada en `/labdigital/` (con `/labdigital/fpga/` protegido).
2. Recién entonces activar el 301 de `/fpga/` → `/labdigital/fpga/` y quitar el bloque `/fpga/` actual del vhost
   (hasta ese día, JG FPGA sigue abierto en `/fpga/`).
3. Quitar los bloques estáticos temporales `/labdigital/design-system/` y `/labdigital/preview/` cuando la web los sirva.

## Respaldos

- Antes de cada despliegue: `deploy.sh` deja un `pg_dump` (se guardan 14).
- **Diario 03:15** (cron de `gideam`): `deploy/backup.sh` (copiado a `~/labdigital-deploy/backup.sh`) guarda
  `db-<fecha>.dump` (`pg_dump -Fc`, verificado con `pg_restore --list`) y `blobs-<fecha>.tar.gz` (volumen de
  archivos, verificado con `tar -t`) en `~/labdigital-deploy/backups/diario/`, 14 días de retención, y escribe el
  latido `labdigital_respaldo_ultimo_exito_timestamp` en `~/observabilidad/textfile_collector/labdigital.prom`.
- Restaurar: `docker exec -i labdigital-db-1 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists'
  < db-<fecha>.dump` y descomprimir el tar en el volumen `labdigital_blobs` (con la API detenida). Probado
  restaurando en una BD temporal.
- **Pendiente**: copia fuera del servidor (hoy todo vive en el mismo disco).

## Alertas (Prometheus, `~/observabilidad/prometheus/rules/labdigital.yml`)

A39 web caída · A40 API caída · A41 módulo FPGA caído · **A42 `/labdigital/fpga/` sin sesión no redirige al login**
(detecta el módulo abierto sin autenticación; módulo blackbox `http_redirect_login`) · A43 respaldo > 26 h ·
A44 sin latido de respaldo. Los contenedores `labdigital-*` quedan cubiertos por las alertas genéricas de contenedores.
