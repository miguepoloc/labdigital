# LabDigital — backend

API de la plataforma (FastAPI + SQLAlchemy 2 síncrono + Alembic + Pydantic v2), DDD hexagonal
según `../docs/ARCHITECTURE-estandar.md`. Contrato obligatorio: `../docs/contrato-api.md`.
Despliegue en Docker siempre encendido (uvicorn); sin Lambda/Mangum/SNS/SQS.

## Paquetes (`src/backend/`)

| Paquete | Qué |
|---|---|
| `commons/` | Núcleo compartido: entidades/VO base, UoW, outbox + despachador, auditoría, rate limiting (Postgres), JWT RS256 + JWKS, `Settings` único, logger JSON, middlewares (CSRF, tamaño de cuerpo), errores §6, puerto `Mailer` + adaptador SMTP |
| `identity/commons/` | `UserId` (UUIDv7) y `Role`, compartidos por los subcontextos de identity |
| `identity/users/` | Agregados `User` (Argon2id, política de contraseñas, verificación, admin por `ADMIN_EMAILS`) y `EmailToken` (un solo uso, hash SHA-256) |
| `identity/sessions/` | Agregado `Session` = familia de refresh tokens: rotación y detección de reuso |
| `identity/services/` | Orquestadores: login, refresh, reset de contraseña, cambio de contraseña, desactivar |
| `identity/entrypoints/` | Rutas `/v1/auth/*`, `/v1/me`, JWKS; housekeeping |
| `projects/projects/` | Agregado `Project` con versiones (autosave/manual, conflicto, restaurar, borrado lógico) |
| `entrypoints/web/app.py` | App FastAPI única (`root_path=/labdigital/api`, rutas bajo `/v1`) |
| `entrypoints/worker/main.py` | Worker: outbox → correo SMTP (con reintentos) + limpieza horaria |

Contratos import-linter en `.importlinter` (pureza de dominio, capas, independencia
users/sessions e identity/projects, commons, entrypoints y orquestadores delgados).

## Desarrollo

```bash
cp .env.example .env        # claves RS256 de desarrollo, ver comentario
make install                 # uv sync --all-extras (Python 3.13 lo descarga uv)
make dev-up && make migrate  # Postgres en 127.0.0.1:18432
make run                     # API en http://127.0.0.1:18000/v1/...
make worker                  # worker del outbox
make migration m="..."       # autogenerate (nunca a mano, §18)
```

## Tests y calidad

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest -m unit         # fakes, sin I/O
uv run pytest -m "integration or e2e"   # Postgres real (testcontainers, contenedor ld-test-pg-*)
```

Los tests generan sus propias claves RS256, usan Argon2 barato y migran con
`alembic upgrade head`. El correo se captura con un `Mailer` falso; `SmtpMailer` se prueba
contra un SMTP local (aiosmtpd).

## Decisiones

- **Rate limiting en Postgres** (`rate_limits`, ventana fija con `INSERT … ON CONFLICT`):
  la API corre con varios workers de uvicorn y los límites deben ser globales y sobrevivir a
  reinicios. El intento se cuenta en su propia transacción antes del caso de uso.
- **Outbox con lease**: el worker reclama filas (`FOR UPDATE SKIP LOCKED` + `next_attempt_at`),
  envía sin transacción abierta y marca entregado; reintentos con espera exponencial
  (8 intentos). Tras enviar, el cuerpo del correo (con el enlace/token) se borra del payload.
- **Refresh**: `remember=false` ⇒ cookie de sesión y caducidad en servidor de 24 h sin uso;
  `remember=true` ⇒ 30 días deslizantes. Reuso de un refresh rotado ⇒ sesión revocada + auditoría.
- **`ver`**: `GET /me` y el refresh rechazan (401) si cambió `credentials_version`;
  `/auth/verify` no lo comprueba (sin BD por contrato).
- Imagen: `Dockerfile` (python:3.13-slim, uv, usuario no root 10001). La misma imagen sirve
  API (`CMD` por defecto), worker (`python -m backend.entrypoints.worker.main`) y migraciones
  (`alembic upgrade head`).
