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
| `identity/entrypoints/web/admin.py` | `/v1/admin/users` (buscar, desactivar, activar, rol; rol admin comprobado en BD) |
| `projects/projects/` | Agregado `Project` con versiones (autosave/manual/submitted, `revision`, conflicto, restaurar, borrado lógico, versiones congeladas) |
| `teaching/` | Producto docente: `courses` (`Course`, `Membership`), `labs` (`Lab`, `Team`), `submissions` (`Submission` + `Review`); `teaching/commons` (ids, `Viewer`, `GradeScale`, puertos) y `teaching/services` (orquestadores con los permisos) |
| `files/blobs/` | Agregado `Blob` + almacenamiento en disco direccionado por SHA-256 (`BLOB_DIR`) |
| `orchestrators/ports.py` | Adaptadores de los puertos entre productos (directorio de usuarios, congelar proyecto, archivos, acceso a blobs) |
| `entrypoints/web/app.py` | App FastAPI única (`root_path=/labdigital/api`, rutas bajo `/v1`) |
| `entrypoints/worker/main.py` | Worker: outbox → correo SMTP (con reintentos), avisos de inscripción de `teaching` + limpieza horaria |

Contratos import-linter en `.importlinter` (pureza de dominio, capas, independencia
users/sessions, de los subcontextos de teaching y de los productos identity/projects/teaching/
files entre sí, commons, entrypoints y orquestadores delgados).

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
uv run pytest -m "integration or e2e"   # Postgres real (testcontainers, contenedor ld-test-pg-*; prefijo con LD_TEST_CONTAINER_PREFIX)
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
- **Avisos de inscripción (LD-17)**: `JoinRequested`/`MembershipStatusChanged` (ya en el outbox con la
  membresía) los traduce el worker (`teaching/services/notifications_orchestrator.py`) en `EmailRequested`
  por destinatario, que vuelven al outbox y entrega el handler de correo de siempre. Anti-spam: un correo
  por docente y curso cada 10 min (`course_join_notices`, `INSERT … ON CONFLICT … WHERE` atómico); las
  solicitudes dentro de la ventana cuentan en el «N pendientes» del siguiente. La maquetación HTML común
  vive en `commons/application/email_layout.py`.
- **Refresh**: `remember=false` ⇒ cookie de sesión y caducidad en servidor de 24 h sin uso;
  `remember=true` ⇒ 30 días deslizantes. Reuso de un refresh rotado ⇒ sesión revocada + auditoría.
- **`ver`**: `GET /me` y el refresh rechazan (401) si cambió `credentials_version`;
  `/auth/verify` no lo comprueba (sin BD por contrato).
- Imagen: `Dockerfile` (python:3.13-slim, uv, usuario no root 10001). La misma imagen sirve
  API (`CMD` por defecto), worker (`python -m backend.entrypoints.worker.main`) y migraciones
  (`alembic upgrade head`).
- **Producto `teaching`** (cursos, labs, equipos, entregas) separado de `projects` e
  `identity`: lo que necesita de ellos (nombres, congelar una versión, metadatos de archivos)
  lo pide por puertos (`teaching/commons/ports.py`); los adaptadores viven en
  `orchestrators/ports.py` y la app los inyecta con `dependency_overrides`. Cada producto
  confirma su propia transacción (§10.3).
- **Autorización en servicios**: el `Viewer` (sub + rol del access) llega a cada caso de uso.
  Sin relación con el curso ⇒ 404; estudiante haciendo algo de docente ⇒ 403; admin ve todo.
  Las rutas privadas comprueban además en BD que la sesión `sid` sigue viva y que `ver`
  coincide (un access robado muere al cerrar/revocar la sesión o desactivar al usuario).
- **Versión entregada inmutable**: entregar congela la versión en `projects`
  (`kind=submitted`, `locked`); el autosave nunca sobrescribe una versión bloqueada (crea otra),
  el repositorio sólo actualiza filas `locked = false` y un trigger de Postgres rechaza cambiar
  `content` o desbloquear. La entrega referencia esa versión con FK `RESTRICT`.
- **Notas CSV** (`GET /courses/{id}/grades.csv`): UTF-8 con BOM, `;`, coma decimal, CRLF;
  `Nombre;Correo;<lab>…`, una fila por estudiante activo con la última nota de cada lab;
  `pass_fail` ⇒ `Aprobado`/`No aprobado`; celdas que empiezan por `= + - @` con `'` delante.
- **Archivos**: 25 MB/archivo (el middleware de tamaño sube su límite sólo para
  `POST /v1/files`), 100 MB/entrega; extensión permitida por `kind` + firma mágica.
- **IP real**: uvicorn con `--proxy-headers` sólo confía en `FORWARDED_ALLOW_IPS` (por defecto
  `127.0.0.1`; en producción, el gateway del bridge donde está nginx). Login: 5/min por
  IP+correo, retardo creciente tras 3 fallos y 20/h por correo; recuperación/reenvío: 3/h por
  IP+correo, 20/h por IP, 10/h por correo.
