# Plan — LabDigital GIDEAM: plataforma de laboratorios de la línea digital

## Contexto

Hoy JG FPGA (`/home/gideam/jg-fpga`, repo `mcangen/JG-FPGA`, publicado en `gideam…/fpga`, CD por runner self-hosted)
es un simulador/sintetizador VHDL para la Basys 3 **sin usuarios, sin base de datos y sin disco persistente**: el proyecto
vive en `localStorage` (`frontend/js/project/project.js:631-653`) y la identidad es un id aleatorio por navegador
(`hardware.js:33-46`). El docente quiere que los estudiantes **tengan cuenta, se inscriban a cursos y entreguen
laboratorios para revisión**, y que esto sea la base de una **plataforma de laboratorios de la línea digital** de
Ingeniería Electrónica (Unimagdalena): Circuitos Digitales (4.º sem.) → Diseño de Sistemas Digitales (5.º, FPGA) →
Microprocesamiento I (6.º, Arduino/ESP32 a futuro). Objetivo: **MVP completo en uso al inicio de 2027-I (febrero)**.

## Dos repositorios separados (decisión clave)

| Repositorio | Dueño | Contiene | Ruta pública |
|---|---|---|---|
| **`https://github.com/miguepoloc/LabDigital`** — **NUEVO, en tu cuenta** | Tú | **Todo lo de la plataforma**: landing, login/registro/JWT, recuperación de contraseña, usuarios, proyectos con versiones, cursos, labs, equipos, entregas, revisión y notas; frontend Vue; Postgres; worker de correo; nginx y CI/CD propios | `/labdigital/…` |
| `https://github.com/mcangen/JG-FPGA` — existente | José | **Solo la FPGA/Basys 3** (simulador, síntesis, agente). Sin login, sin BD, sin cursos | `/labdigital/fpga/…` (y `/fpga/` redirige ahí) |

- Cuando alguien entra a la FPGA, nginx primero pregunta a **LabDigital** si trae token válido: **sin token → redirige
  al login de LabDigital** y, tras entrar, vuelve a la FPGA. JG FPGA no sabe nada de usuarios.
- La relación entre ambos es solo: (1) esa protección por nginx y (2) una API JS pequeña que José expone en su app
  (`window.JGFPGA`) para que LabDigital lea/cargue proyectos y entregue. Todo lo demás vive en **tu** repo.
- Cada repo tiene su CI/CD y su runner self-hosted; desplegar uno no afecta al otro.
- Módulos futuros (circuitos tipo Logisim, Arduino/ESP32) = repos aparte con el mismo contrato.

## Decisiones tomadas (grill)

| Tema | Decisión |
|---|---|
| Nombre / ruta | **LabDigital GIDEAM**, en `https://gideam.unimagdalena.edu.co/labdigital/` |
| Arquitectura | **Plataforma nueva + módulos**. JG FPGA = primer módulo; se protege con la sesión común (nginx `auth_request`) |
| Repo | **Nuevo `miguepoloc/LabDigital` en tu cuenta** (plataforma), a partir de `miguepoloc/backend-architecture-standard`; JG-FPGA de José queda solo con la FPGA |
| Backend | FastAPI + SQLAlchemy 2 (sync) + Alembic + Pydantic v2, DDD hexagonal del estándar, `uv`/`ruff`/`mypy`/`import-linter` |
| BD | PostgreSQL en contenedor propio |
| Frontend | Vue 3 + TypeScript + Vite + Pinia + Vue Router; landing **prerenderizada**; tipos de la API generados del OpenAPI |
| Acceso | **Todo requiere cuenta**; la landing es la única parte pública. Registro abierto a **cualquier correo**, verificado |
| Roles | Global: `admin` / `user`. Por curso: `docente` (quien lo crea) / `estudiante`. Cualquier usuario puede crear cursos |
| Inscripción | Código del curso + **aprobación del docente** |
| Laboratorios | Definidos por el docente; individual o en equipo; **fecha configurable por lab** (cierre estricto / tardía marcada / sin fecha); **escala de nota definida por el docente** |
| Equipos | Los estudiantes se organizan (código de equipo, tamaño máx.) y el docente puede reasignar/fijar |
| Revisión | Abrir en el simulador, comentar, calificar, permitir re-entrega con historial |
| Entrega | Proyecto congelado + informe + `.bit` + archivos adicionales |
| Proyectos | Cada usuario guarda sus proyectos en la BD, **autoguardado con versiones** |
| Perfil | Correo, contraseña, **nombre completo** |
| Datos personales | Aceptar la **política de tratamiento de datos de Unimagdalena** al registrarse (Ley 1581/2012) |
| Correo | Proveedor gratuito con dominio `mcda.tools` verificado (SPF/DKIM). Recomendado **Brevo** (300/día, SMTP); remitente `no-responder@mcda.tools` |
| Marca | Paleta oficial del CDN de Unimagdalena + escudo del CDN, igual que el landing de GIDEAM ya lo usa |
| Ajustes al estándar | Rotación de refresh con detección de reuso, Argon2id, Docker (no Lambda), tokens en cookies HttpOnly |
| Avisos por correo extra | **Pendiente** ("luego vemos"): en el MVP solo verificación y recuperación |

## Mapa de rutas

```
https://gideam.unimagdalena.edu.co
├── /labdigital/                     Landing pública (prerender)          → labdigital-web (estático)
├── /labdigital/entrar               Login                                ┐
├── /labdigital/registro             Registro + aceptación de datos        │
├── /labdigital/verificar?t=…        Verificación de correo                │ SPA Vue (mismo build)
├── /labdigital/recuperar            Pedir enlace de recuperación          │
├── /labdigital/restablecer?t=…      Nueva contraseña                      │
├── /labdigital/sesion?next=…        Renueva la sesión y vuelve a `next`   │
└── /labdigital/app/…                Área privada:                         ┘
│     inicio · proyectos · cursos · cursos/:id (labs, miembros, solicitudes, notas)
│     labs/:id (enunciado, equipo, entregar) · entregas/:id (revisión) · perfil · sesiones · admin
├── /labdigital/api/v1/…             API de la plataforma                 → labdigital-api
│     auth/* · me · projects/* · courses/* · labs/* · teams/* · submissions/* · files/* · admin/*
│     .well-known/jwks.json (clave pública para módulos)
├── /labdigital/fpga/                Módulo JG FPGA (requiere sesión)     → jgfpga (127.0.0.1:8087)
├── /labdigital/circuitos/, /micro/  Módulos futuros (mismo patrón)
└── /fpga/…                          301 → /labdigital/fpga/  (no romper enlaces)
```

nginx (vhost `gideam`, mismo patrón que `/fpga` de hoy): `location /labdigital/fpga/` con
`auth_request /labdigital/_auth;` → subpetición interna a `GET /api/v1/auth/verify` (valida la cookie de acceso
**localmente**, sin BD). `401` → `error_page 401 = @renovar` → `302 /labdigital/sesion?next=$request_uri`.
`auth_request_set` reenvía `X-LabDigital-User` / `X-LabDigital-Email` al módulo; nginx **borra** esas cabeceras si
vienen del cliente. WebSocket (`/ws`, `/ws/hw`) igual que hoy.

## Autenticación (JWT access + refresh)

- **Access token**: JWT **RS256**, 15 min. Claims `iss=labdigital`, `aud=labdigital`, `sub` (user id), `sid` (sesión),
  `role`, `ver` (versión de credenciales del usuario), `iat`, `exp`, `jti`. Firma solo `identity`; los módulos pueden
  verificar con el JWKS (con `kid` para rotar claves).
- **Refresh token**: opaco `"<id>.<secreto>"`, solo se guarda el **SHA-256** (como en
  `identity/users/adapters/refresh_tokens.py` del estándar). 30 días; con "recordarme" desactivado es de sesión de navegador.
  - **Rotación**: cada `/auth/refresh` revoca el token usado y emite uno nuevo de la misma **familia** (`session_id`).
  - **Reuso**: si llega un refresh ya rotado, se revoca **toda la familia** (sesión robada) y se registra en auditoría.
  - Tabla `sessions` (familia): dispositivo/UA, IP, creada, último uso → pantalla "Sesiones activas" con "cerrar sesión" y "cerrar las demás".
- **Cookies** (no `localStorage`): `ld_access` (HttpOnly, Secure, SameSite=Lax, Path=`/labdigital/`) y
  `ld_refresh` (HttpOnly, Secure, SameSite=Strict, Path=`/labdigital/api/v1/auth/`). El JSON del estándar se adapta en
  la capa web: el servicio sigue devolviendo el par de tokens y el endpoint lo pone en cookies.
- **CSRF**: SameSite + comprobación de `Origin` en mutaciones + cabecera `X-Requested-With: labdigital` (la misma
  idea que `_same_site` de JG FPGA, `backend/app.py:336`).
- **Frontend**: interceptor que, ante `401`, llama una vez a `/auth/refresh` (con un candado para que no haya refrescos
  en paralelo) y repite la petición; si falla, va a `/entrar?next=`.
- **Contraseñas**: Argon2id (`argon2-cffi`) en `HashedPassword`; mínimo 10 caracteres + lista de contraseñas comunes; rehash transparente.
- **Verificación de correo y recuperación**: tokens de un solo uso guardados como hash (24 h / 30 min). "Si el correo existe,
  te enviamos un enlace" (no revela si la cuenta existe). Restablecer contraseña sube `ver` y **revoca todas las sesiones**.
- **Límites**: login 5/min por IP+correo con retardo creciente; recuperación 3/h por correo; registro 10/h por IP.
- **Admin**: `ADMIN_EMAILS` en el `.env` → rol `admin` al verificar el correo. Recomendado: 2FA TOTP para admin (fase posterior).
- `deactivate_user` del estándar se mantiene (revoca todas las familias).

## Modelo de datos (contextos acotados según el estándar)

- **identity**: `users` (email único normalizado, full_name, hashed_password, role, email_verified_at, credentials_version,
  is_active, accepted_data_policy_at + versión), `sessions`, `refresh_tokens` (session_id, hash, rotated_at, revoked_at,
  expires_at), `email_tokens` (purpose verify/reset, hash, expires_at, used_at).
- **projects**: `projects` (owner_id → users, module `fpga`|…, name, current_version_id, timestamps, deleted_at),
  `project_versions` (project_id, n, content JSONB = mismo formato que `snapshotProject()`/manifiesto `basys3-sim-project`
  de `basys_sim/project.py`, size, created_at, kind autosave|manual). Autoguardado con *debounce* (~5 s) que **sobrescribe
  la versión autosave abierta**; se crea versión nueva cada ~10 min de edición, al pulsar "Guardar versión" y al entregar.
  Límite 2 MB por versión (como `MAX_PROJECT_BYTES`).
- **courses**: `courses` (owner_id, nombre, periodo, descripción, join_code rotable, archived_at), `memberships`
  (course_id, user_id, role docente|estudiante, status pending|active|rejected|removed, timestamps).
- **labs**: `labs` (course_id, título, enunciado markdown, módulo, published_at, opens_at, due_at, deadline_policy
  strict|late_marked|none, team_mode individual|team, max_team_size, grade_scale {type numeric|pass_fail, min, max,
  decimals, pass_mark}, allow_resubmission), `teams` (lab_id, nombre, join_code, locked) + `team_members`.
- **submissions**: `submissions` (lab_id, student_id **o** team_id, attempt n, project_version_id congelada,
  submitted_at, is_late, status submitted|returned|graded), `submission_files` (kind report|bitstream|attachment,
  blob_id), `reviews` (submission_id, reviewer_id, grade, comment, returned_for_resubmission, created_at).
- **files**: `blobs` (sha256, size, mime, path en volumen `/data/blobs`, direccionado por contenido). Límites por
  defecto: 25 MB por archivo, 100 MB por entrega; tipos permitidos .bit, .pdf, .docx, .png/.jpg, .mp4.
- **commons**: outbox (del estándar) → worker que envía correos; `audit_log` (del estándar, §14.2).
- Autorización en servicios (no en la UI): solo el docente del curso ve las entregas; el estudiante ve las suyas/de su
  equipo; admin todo.

## Integración con JG FPGA (repo de José: cambios mínimos)

JG FPGA es de José; LabDigital es tuyo. Regla: **toda la lógica de plataforma vive en LabDigital** y JG FPGA solo
expone una API pequeña, genérica y estable.

- **Protección y redirección sin tocar JG FPGA**: nginx `auth_request` en `/labdigital/fpga/` (y `/fpga/` → 301 ahí).
  Sin token válido → `/labdigital/sesion?next=…` (intenta refresh) → si no hay sesión, `/labdigital/entrar?next=…`
  → tras el login vuelve a la ruta original.
- **Envoltorio en LabDigital** (`/labdigital/app/fpga/:proyecto?`): barra propia (usuario, guardado/estado,
  versiones, **Entregar**, volver) + JG FPGA en un **iframe del mismo origen** (`/labdigital/fpga/`). El autoguardado,
  las versiones, el diálogo de entrega (informe, `.bit`, adjuntos) y la revisión en solo lectura los hace el envoltorio.
- **Único PR a JG-FPGA** (~30-60 líneas, opcional para él, no rompe el modo local/`run.bat`):
  `window.JGFPGA = { version, getProject(), loadProject(p, {readOnly}), getReport(), getLastBitstream(), on("change", fn) }`
  sobre las funciones que ya existen (`snapshotProject()`/carga en `project.js:631-653,1001-1010`, informe en
  `project.report`, `.bit` en `hwBitHref` `hardware.js:347`); `readOnly` desactiva la edición pero deja simular.
  Textos nuevos (si los hay) en `i18n.js` ES/EN por `test_i18n_coverage.py`.
- **Opcional, segundo PR**: usar `X-LabDigital-User` (puesto por nginx) para aislar síntesis y límites por usuario en
  vez de `X-Client-Id`/IP (`app.py:57-83,340-360`). Hasta entonces sigue el aislamiento por navegador de hoy.
- Si José prefiere no aceptar el PR, el envoltorio puede usar directamente las funciones globales actuales del iframe
  (mismo origen) — funciona, pero es frágil ante sus cambios; por eso se propone la API estable.

## Design system y landing (antes de programar la UI)

1. Artifact **Design System "LabDigital GIDEAM"**: tokens claro/oscuro con la paleta oficial del CDN (base `#004B87`
   y tonos `#0183EF/#005CAB/#003A6B/#00294B`; complemento `#D17900`; secundarios `#A5CA00`, `#00A50B`, `#D1AE00`, `#D10500`),
   acentos de la app (placa `#0b6b3a`, LED), Open Sans (títulos) + Roboto (texto), escala, radios, componentes
   (botón, campo, tarjeta de curso/lab, estado de entrega, tabla de notas, avisos), escudo del CDN y logo de GIDEAM.
2. Artifact **Design** de la landing para tu aprobación: hero (qué es LabDigital), módulos (FPGA ahora; circuitos,
   micro próximamente), qué hace la app (simulación, placa, ondas, síntesis, IA, informe), sección **docentes**
   (curso → labs → revisión), **descarga del agente**, **equipo y GIDEAM**, pie con política de datos.
3. Los tokens se exportan a CSS variables que usan la SPA y (después) JG FPGA.

## Infraestructura y CI/CD (mismo patrón que JG FPGA)

- `/home/gideam/labdigital` con compose: `labdigital-db` (Postgres 16, volumen nombrado), `labdigital-api` (uvicorn,
  `127.0.0.1:8088`), `labdigital-worker` (outbox → SMTP de Brevo), `labdigital-web` (nginx con el build estático,
  `127.0.0.1:8089`); volumen `labdigital-blobs`. Secretos (claves RS256, SMTP, BD) en `.env` fuera de git.
- nginx: bloques `/labdigital/` y `/labdigital/api/`, `auth_request` para `/labdigital/fpga/`, 301 de `/fpga/`. Backup + `nginx -t` + reload, como ya hicimos.
- GitHub Actions en `miguepoloc/LabDigital`: `ruff`, `mypy`, `import-linter`, pytest unit + integración (testcontainers
  Postgres), build del frontend (`vue-tsc` + Vitest). Deploy en push a `main` con un **runner self-hosted nuevo** para ese
  repo: `pg_dump` previo → `alembic upgrade head` → build/up → health check → rollback de imagen (las migraciones deben ser compatibles hacia atrás).
- Correo: crear cuenta Brevo, verificar `mcda.tools` (SPF, DKIM, DMARC en el DNS de mcda.tools).
- Respaldos: `pg_dump` diario + blobs (ligado al pendiente A21 de observabilidad). Observabilidad: sondas blackbox
  para `/labdigital/`, `/api/v1/health` y `/labdigital/fpga/api/health`; Postgres en el exporter existente.
- Doc del servidor: anotar en `alunaia-cambios-*.md`.

## Fases hacia febrero 2027 (~11 semanas)

| Sem. | Fase | Entregable |
|---|---|---|
| 1–2 | F0 Base | Repo desde el template (ajustado a Docker), compose, CI/CD, design system + diseño de la landing aprobados |
| 2–4 | F1 Identidad | Registro, verificación, login/refresh/rotación, sesiones, recuperación, Argon2id, cookies, `auth_request`; páginas de cuenta |
| 4–6 | F2 Proyectos + módulo | Proyectos con versiones; PR a JG FPGA (modo plataforma, autoguardado); `/fpga` → `/labdigital/fpga` |
| 6–8 | F3 Cursos y labs | Cursos, código + aprobación, labs con fecha/escala, equipos |
| 8–10 | F4 Entregas y revisión | Entregar, archivos, abrir en simulador, comentar, calificar, re-entregar, tabla de notas (CSV) |
| 10–11 | F5 Endurecer | Landing final, límites, auditoría, respaldos, alertas, prueba piloto con un curso |

## Repos y reparto del trabajo con agentes

- **`mcangen/JG-FPGA`** (de José) queda **solo con la FPGA** (simulador, síntesis, agente); recibe únicamente el
  PR de la API de integración (sección anterior). **`miguepoloc/LabDigital`** (tuyo, nuevo) contiene todo lo demás:
  landing, cuentas, proyectos, cursos, labs, entregas, frontend Vue, infraestructura. Los módulos futuros (circuitos,
  micro) serán repos propios con el mismo contrato (`auth_request` + API `projects`/`submissions`).
- El contrato entre ambos (OpenAPI de `projects`, `submissions`, `me` + cabeceras de nginx) se fija **primero**, para
  que los agentes trabajen en paralelo sin bloquearse.
- Agentes en paralelo (cada uno en su rama/worktree, todo llega por **PR**, nada directo a `main`/`master`):
  1. **Backend plataforma**: repo desde el template (ajustes a Docker, Argon2id, rotación de refresh, cookies),
     contexto identity → projects → courses/labs → submissions, con tests.
  2. **Frontend plataforma**: Vue 3 + TS, páginas de cuenta y área privada contra el OpenAPI (mocks hasta que exista la API).
  3. **Integración FPGA**: envoltorio en LabDigital + PR pequeño de la API `window.JGFPGA` a JG-FPGA (para que José lo revise).
  - Yo coordino: design system + diseño de landing (artifacts), infraestructura (compose, nginx, runner, Brevo),
    revisión de cada PR y verificación end-to-end. Revisión por fase antes de pasar a la siguiente.
- **Lo que necesito de ti para arrancar**: crear el repo vacío `miguepoloc/LabDigital` y añadir una deploy key de
  escritura que te generaré (como en JG-FPGA); token del runner self-hosted de ese repo; cuenta Brevo + acceso al DNS
  de `mcda.tools` para SPF/DKIM; correo(s) de admin.

## Pendientes

- Avisos por correo extra (solicitudes, nuevo lab, calificación, recordatorios): decidir después del MVP.
- URL exacta de la política de tratamiento de datos de Unimagdalena para enlazarla en el registro.
- Confirmar que la autorización de marca de GIDEAM cubre LabDigital (comunicado de la Vicerrectoría de Investigación).
- Correo(s) de admin inicial para `ADMIN_EMAILS`.
- Visto bueno de José para el PR de la API de integración en JG-FPGA.

## Verificación

- **Auth** (pytest + e2e): registro → correo capturado en un SMTP falso → verificar → login → cookies correctas
  (flags, Path) → access caduca → refresh rota → **reusar el refresh viejo revoca la familia** → logout; recuperación
  revoca sesiones; respuestas iguales para correos inexistentes; límites de intentos.
- **Autorización**: un estudiante no puede ver entregas de otro curso/estudiante (tests por endpoint).
- **nginx**: sin cookie, `/labdigital/fpga/` → 302 a `/sesion`; con access caducado y refresh válido vuelve solo;
  cabecera `X-LabDigital-User` del cliente ignorada; WebSocket `101` por `/labdigital/fpga/ws`.
- **Flujo completo** en staging: docente crea curso y lab (equipo, tardía marcada, 0–5) → dos estudiantes se inscriben,
  forman equipo → trabajan en JG FPGA (autoguardado, restaurar versión) → entregan con informe y `.bit` → docente abre
  en el simulador, comenta, devuelve → re-entrega → nota → exportar CSV.
- CI verde en ambos repos; el despliegue por merge funciona con rollback probado; `pg_dump` restaurable.
