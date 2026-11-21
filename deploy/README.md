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

`deploy.sh` deja un `pg_dump` antes de cada despliegue (se guardan 14). Falta el respaldo diario y de `blobs`
(cron + copia fuera del servidor) — pendiente A21.
