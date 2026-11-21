# Backlog LabDigital (tickets LD-n)

| Ticket | Fase | Qué | Estado |
|---|---|---|---|
| LD-1 | F0 | Backend base: template → LabDigital (quitar ejemplo `commerce`, Docker/uvicorn en vez de Lambda, settings, health, CI) | en curso |
| LD-2 | F1 | Identidad: registro, verificación, login, refresh rotativo + reuso, sesiones, recuperación, Argon2id, cookies, CSRF, `auth/verify`, JWKS, límites | en curso |
| LD-3 | F2 | Proyectos con versiones (autosave + manuales, restaurar) | en curso |
| LD-4 | F3 | Cursos + membresías (código + aprobación) | pendiente |
| LD-5 | F3 | Labs (fechas, escala) + equipos | pendiente |
| LD-6 | F4 | Entregas, archivos (blobs), revisiones, notas CSV | pendiente |
| LD-7 | F0-F1 | Frontend base: Vue 3 + TS + Vite, tokens del design system, layout, cliente API con refresh, páginas de cuenta | en curso |
| LD-8 | F2-F4 | Frontend área privada: proyectos, cursos, labs, equipos, entregas, revisión, notas | pendiente |
| LD-9 | F2 | Envoltorio FPGA (`/app/fpga`) sobre `window.JGFPGA` | pendiente |
| LD-10 | F2 | PR a mcangen/JG-FPGA: API `window.JGFPGA` (contrato §7) | en curso |
| LD-11 | F0-F5 | Infra: compose, nginx (`/labdigital`, `auth_request`), runner, Brevo, respaldos, alertas | pendiente |
| LD-12 | F0 | Design system + diseño de la landing | en curso |
