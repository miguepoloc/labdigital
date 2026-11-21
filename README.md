# LabDigital GIDEAM

Plataforma de laboratorios de la línea digital (Ingeniería Electrónica, Universidad del Magdalena — grupo GIDEAM):
cuentas, cursos, laboratorios y entregas, con módulos de simulación. Primer módulo: JG FPGA (Basys 3), en su propio repo.

- `backend/` — API (FastAPI + SQLAlchemy + Alembic, DDD hexagonal según `docs/ARCHITECTURE-estandar.md`).
- `frontend/` — SPA Vue 3 + TypeScript + landing.
- `deploy/` — compose, nginx, scripts de despliegue.
- `docs/contrato-api.md` — contrato entre backend, frontend y módulos (**leer primero**). `docs/plan.md`, `docs/backlog.md`.

Producción: https://gideam.unimagdalena.edu.co/labdigital/
