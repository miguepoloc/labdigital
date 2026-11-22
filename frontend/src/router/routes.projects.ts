import type { RouteRecordRaw } from 'vue-router'

/**
 * Rutas de proyectos (LD-8a) y del envoltorio FPGA (LD-9). Se incluyen en `routes.ts` con un solo spread.
 * - `/app/proyectos/**` usa el mismo `AppLayout` que `/app` (mismo componente ⇒ Vue lo reutiliza, no remonta).
 * - `/app/fpga/:projectId?` va a pantalla completa, sin barra lateral (contrato §1).
 */
export const projectRoutes: RouteRecordRaw[] = [
  {
    path: '/app/proyectos',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'projects',
        component: () => import('@/pages/app/projects/ProjectsListPage.vue'),
        meta: { title: 'projects.list.title' },
      },
      {
        path: ':id',
        name: 'project',
        component: () => import('@/pages/app/projects/ProjectDetailPage.vue'),
        meta: { title: 'projects.detail.versionsTitle' },
      },
    ],
  },
  {
    path: '/app/fpga/:projectId?',
    name: 'fpga',
    component: () => import('@/pages/app/fpga/FpgaWrapperPage.vue'),
    meta: { requiresAuth: true, title: 'projects.fpga.title' },
  },
]
