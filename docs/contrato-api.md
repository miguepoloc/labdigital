# Contrato LabDigital (v1) — fuente de verdad para backend, frontend y módulos

Plan completo: ver `docs/plan.md`. Este documento fija lo que **no** se cambia sin acuerdo entre las tres partes
(backend, frontend, módulo FPGA). Cambios = PR que edita este archivo primero.

## 1. Rutas públicas (todas bajo `https://gideam.unimagdalena.edu.co`)

| Ruta | Sirve | Notas |
|---|---|---|
| `/labdigital/` | landing (prerender) | pública |
| `/labdigital/entrar`, `/registro`, `/verificar?t=`, `/recuperar`, `/restablecer?t=`, `/sesion?next=` | SPA | públicas |
| `/labdigital/app/**` | SPA área privada | la SPA redirige a `/labdigital/entrar?next=` si `GET /me` da 401 tras intentar refresh |
| `/labdigital/app/fpga/:projectId?` | envoltorio del módulo FPGA (iframe a `/labdigital/fpga/`) | |
| `/labdigital/api/v1/**` | API (FastAPI, `root_path=/labdigital/api`) | JSON, errores §6 |
| `/labdigital/fpga/**` | módulo JG FPGA | protegido por nginx `auth_request` |

`next` sólo acepta rutas relativas que empiecen por `/labdigital/` (evitar open redirect).

## 2. Cookies y tokens

| Cookie | Contenido | Flags |
|---|---|---|
| `ld_access` | JWT RS256, 15 min | `HttpOnly; Secure; SameSite=Lax; Path=/labdigital/` |
| `ld_refresh` | opaco `<uuid>.<secreto>`, 30 días (o de sesión si `remember=false`) | `HttpOnly; Secure; SameSite=Strict; Path=/labdigital/api/v1/auth/` |

Claims del access: `iss="labdigital"`, `aud="labdigital"`, `sub` (user id UUIDv7), `sid` (session id), `role`
(`admin`|`user`), `ver` (int, versión de credenciales), `email`, `name`, `iat`, `exp`, `jti`. Cabecera `kid`.
JWKS público: `GET /api/v1/.well-known/jwks.json`.

Refresh: rotación obligatoria; reusar un refresh ya rotado ⇒ se revoca toda la sesión (familia) y responde 401.

**CSRF**: toda petición que no sea GET/HEAD debe llevar `X-Requested-With: labdigital` y un `Origin` igual al host;
si no ⇒ 403 `csrf_rejected`.

## 3. nginx ⇄ API ⇄ módulos

- `GET /api/v1/auth/verify` (interno, para `auth_request`): lee `ld_access`; **sin BD**. 204 si válido con cabeceras
  `X-LabDigital-User: <sub>`, `X-LabDigital-Email`, `X-LabDigital-Name` (URL-encoded), `X-LabDigital-Role`; 401 si no.
- nginx pasa esas cabeceras al módulo y **elimina** cualquier `X-LabDigital-*` que mande el cliente.
- 401 en un módulo ⇒ nginx `302 /labdigital/sesion?next=<uri original>`; `/sesion` intenta `POST /auth/refresh`;
  si funciona vuelve a `next`, si no va a `/entrar?next=`.

## 4. Endpoints v1 (resumen; el detalle lo da el OpenAPI generado, que debe respetar esto)

Auth (`/api/v1/auth`): `POST register {email, full_name, password, accept_data_policy:true}` → 202 (siempre igual,
exista o no el correo) · `POST verify-email {token}` → 204 · `POST login {email, password, remember}` → 200 `Me` + cookies ·
`POST refresh` → 204 + cookies · `POST logout` → 204 · `POST forgot-password {email}` → 202 (siempre) ·
`POST reset-password {token, password}` → 204 (revoca todas las sesiones) · `POST resend-verification {email}` → 202 ·
`GET sessions` → `[Session]` · `DELETE sessions/{id}` · `POST sessions/revoke-others`.

Me: `GET /api/v1/me` → `Me {id, email, full_name, role, email_verified, created_at}` · `PATCH /api/v1/me {full_name}` ·
`POST /api/v1/me/password {current, new}`.

Proyectos: `GET /projects?module=fpga` · `POST /projects {name, module, content}` → `Project` ·
`GET /projects/{id}` (incluye `content` de la versión actual) · `PATCH /projects/{id} {name}` · `DELETE /projects/{id}` (soft) ·
`PUT /projects/{id}/autosave {content, base_version}` → `{version_id, n}` (409 si `base_version` no es la actual) ·
`POST /projects/{id}/versions {label?}` → versión manual · `GET /projects/{id}/versions` · `GET /projects/{id}/versions/{vid}` ·
`POST /projects/{id}/versions/{vid}/restore`.

Cursos: `GET /courses` (los míos: como docente y como estudiante) · `POST /courses {name, period, description}` ·
`GET/PATCH /courses/{id}` · `POST /courses/{id}/join-code/rotate` · `POST /courses/join {code}` → membresía `pending` ·
`GET /courses/{id}/members?status=` · `POST /courses/{id}/members/{uid}/approve|reject|remove`.

Labs: `GET /courses/{id}/labs` · `POST /courses/{id}/labs {title, statement_md, module, opens_at?, due_at?,
deadline_policy: strict|late_marked|none, team_mode: individual|team, max_team_size?, grade_scale:{type: numeric|pass_fail,
min?, max?, decimals?, pass_mark?}, allow_resubmission}` · `GET/PATCH /labs/{id}` · `POST /labs/{id}/publish`.

Equipos: `GET /labs/{id}/teams` · `POST /labs/{id}/teams {name}` → `{join_code}` · `POST /labs/{id}/teams/join {code}` ·
`POST /teams/{id}/leave` · docente: `PUT /teams/{id}/members [uid]`, `POST /teams/{id}/lock`.

Entregas: `POST /labs/{id}/submissions {project_id, version_id?, file_ids:[...]}` (congela versión; marca `is_late`;
rechaza si `strict` y pasó `due_at`) · `GET /labs/{id}/submissions` (docente: todas; estudiante: las suyas/equipo) ·
`GET /submissions/{id}` (incluye `content` congelado y archivos) · `POST /submissions/{id}/reviews {grade?, comment,
return_for_resubmission}` · `GET /courses/{id}/grades.csv`.

Archivos: `POST /files` (multipart, campo `file`, `kind: report|bitstream|attachment`) → `{id, sha256, size, mime}` ·
`GET /files/{id}` (sólo si el usuario puede ver la entrega/proyecto que lo usa o es suyo). Límites: 25 MB/archivo,
100 MB/entrega; tipos `.bit .pdf .docx .png .jpg .jpeg .mp4`.

Admin: `GET /admin/users?q=` · `POST /admin/users/{id}/deactivate|activate|role`.

Salud: `GET /api/v1/health` → `{ok:true}`.

## 5. Contenido de proyecto FPGA (`content`)

El mismo objeto que produce JG FPGA (`snapshotProject()` en `frontend/js/project/project.js`):
`{ "format": "basys3-sim-project", "version": 1, "name", "top", "simTop", "files": [{"name","role","text"}], "report": {...}|null }`.
La API lo trata como JSON opaco validado por tamaño (≤ 2 MB) y por `format`.

## 6. Errores

`{ "error": { "code": "snake_case", "message": "texto en español", "details": {...}? } }` con el status HTTP adecuado.
Códigos fijos usados por el frontend: `invalid_credentials`, `email_not_verified`, `account_inactive`, `rate_limited`
(+ `Retry-After`), `csrf_rejected`, `token_invalid`, `version_conflict`, `deadline_passed`, `forbidden`, `not_found`,
`validation_error`, `payload_too_large`.

### 6.1 Precisiones (acordadas tras LD-7)

- **401 = sólo sesión ausente/caducada**, con código `unauthenticated` (el cliente lo usa para renovar). Credenciales
  equivocadas en `POST /me/password` ⇒ **400** `invalid_current_password` (nunca 401). Login fallido sigue 401
  `invalid_credentials` (no dispara renovación: el cliente lo excluye).
- **422 `validation_error`**: `details.fields = { "<campo>": "<mensaje en español>" }`.
- `Session = { id, user_agent, ip, created_at, last_used_at, current: bool }`.
- `PATCH /me` devuelve `Me`.
- `next` es siempre la ruta completa con prefijo (`/labdigital/app/...`, `/labdigital/fpga/...`).
- **Revisión de autosave** (tras LD-3): `Project` y la respuesta de `PUT /projects/{id}/autosave` incluyen `revision`
  (entero que sube en CADA guardado, también cuando el autosave sobrescribe la versión abierta). El autosave envía
  `{content, base_version, base_revision}`; si `base_revision` ≠ la actual ⇒ 409 `version_conflict` con
  `details: {current_version, current_revision}`.
- **Refresh concurrente**: reusar el refresh recién rotado dentro de **10 s** no revoca la familia (devuelve 204 con
  cookies nuevas de la misma familia); fuera de esa ventana sí (robo). El frontend además serializa la renovación entre
  pestañas con `navigator.locks.request("ld-refresh", …)` (si no existe, el candado por pestaña).
- `POST /projects/{id}/versions` acepta cuerpo vacío.
- **Formas de proyecto** (tras LD-8/9): `ProjectSummary = {id, name, module, current_version_id, current_version_n,
  revision, created_at, updated_at}`; `Project = ProjectSummary + {content}`; `ProjectVersion = {id, n, kind:
  autosave|manual|submitted, label|null, size (bytes), created_at, updated_at}`. `POST /projects/{id}/versions` y
  `POST .../restore` devuelven `Project` (con la `revision` nueva).
- `GET /submissions/{id}` incluye `content` (proyecto congelado) y `version_id`.
- **Formas de cursos y entregas** (tras LD-8b):
  `Course = {id, name, period, description, archived_at|null, owner_id, owner_name, my_role: docente|estudiante,
  my_status: pending|active|rejected|removed, join_code (sólo si my_role=docente), counts: {students, pending, labs}}`;
  `POST /courses/join` devuelve `Course`.
  `Lab = {…campos de creación, id, course_id, published_at|null, my_submission: SubmissionSummary|null}`.
  `Team = {id, lab_id, name, locked, members: [{id, full_name}], join_code (sólo miembros y docente)}`;
  docente: `POST /teams/{id}/unlock` además de `lock`.
  `SubmissionSummary = {id, attempt, status, is_late, submitted_at, grade|null}`;
  `Submission = SubmissionSummary + {lab_id, project_id, version_id, version_n, submitted_by: {id, full_name},
  team: {id, name}|null, members: [{id, full_name}], files: [{id, kind, name, size, mime}],
  reviews: [{id, reviewer_name, grade|null, comment, returned_for_resubmission, created_at}], content}`.
  `grade` es la de la última revisión con nota. En `pass_fail`, la nota es `1` (aprobado) o `0` (no aprobado).
- **Códigos 409 nuevos**: `deadline_passed`, `already_member`, `team_full`, `team_locked`, `already_in_team`,
  `team_required`, `resubmission_not_allowed`, `lab_not_open`; `invalid_code` es 404.
- **Cookie indicadora** `ld_session=1` (NO HttpOnly, `Secure; SameSite=Lax; Path=/labdigital/`, misma vida que
  `ld_refresh`): se pone en login/refresh y se borra en logout o al revocar. Sólo evita que páginas públicas pidan
  `/me` sin sesión; nunca se usa para autorizar.

## 7. API de integración del módulo FPGA (`window.JGFPGA`, PR a mcangen/JG-FPGA)

```js
window.JGFPGA = {
  version: "1",
  getProject(),                         // -> content (§5) del proyecto abierto
  loadProject(content, { readOnly }),   // reemplaza el proyecto abierto; readOnly: simular sí, editar no
  getReport(),                          // -> objeto del informe o null
  async getReportDocx(),                // -> Blob .docx del informe o null
  async getLastBitstream(),             // -> { name, blob } del último .bit generado o null
  on(event, fn) / off(event, fn),       // "change" (debounce interno 1 s), "ready"
};
```
Se dispara `window.parent.postMessage({ type: "jgfpga:ready", version: "1" }, location.origin)` al cargar.
El envoltorio de LabDigital (mismo origen) usa sólo esta API.

Precisiones (implementación en `mcangen/JG-FPGA` rama `feat/api-integracion`, `docs/EMBED.md`):
- `on("change", fn)`: `fn(content)` recibe el proyecto; se emite 1 s después de la última edición y sólo si cambió.
  `"ready"` también se entrega a quien se suscribe tarde. Extra: `readOnly()` → boolean.
- `loadProject` **lanza** si `format`/`version`/`files` no son válidos, devuelve la lista de archivos omitidos y no emite `change`.
- Embebido, JG FPGA guarda su caché en claves propias (`basys-project-embed`), así que **el envoltorio debe llamar siempre
  a `loadProject` al recibir `ready`** (si no, se vería la última caché, editable).
- `getLastBitstream()` devuelve el `.bit` más reciente **de ese navegador**, no necesariamente del proyecto abierto:
  el envoltorio debe mostrar su nombre y fecha para que el estudiante confirme antes de adjuntarlo.
- Errores de red/HTTP en `getLastBitstream`/`getReportDocx` se lanzan (no devuelven `null`): capturarlos.

## 8. Convenciones de repo

Ramas `miguel.polo/<tipo>/LD-<n>-<descripcion>`; commits `<tipo>(<scope>): #LD-<n> <descripción>`; todo por PR a
`main`; CI verde obligatorio. Tickets en `docs/backlog.md`.
