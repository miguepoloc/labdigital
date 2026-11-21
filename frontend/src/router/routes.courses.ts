import type { RouteRecordRaw } from 'vue-router'

/** Rutas de cursos, labs y entregas (LD-8b). Hijas de `/app` (ver `routes.ts`). */
export const courseRoutes: RouteRecordRaw[] = [
  {
    path: 'cursos',
    name: 'courses',
    component: () => import('@/pages/app/courses/CoursesPage.vue'),
    meta: { title: 'courses.title' },
  },
  {
    path: 'cursos/:id',
    name: 'course',
    component: () => import('@/pages/app/courses/CoursePage.vue'),
    meta: { title: 'courses.title' },
  },
  {
    path: 'cursos/:id/labs/nuevo',
    name: 'lab-new',
    component: () => import('@/pages/app/labs/LabEditorPage.vue'),
    meta: { title: 'labEditor.createTitle' },
  },
  {
    path: 'labs/:id',
    name: 'lab',
    component: () => import('@/pages/app/labs/LabPage.vue'),
    meta: { title: 'labs.listTitle' },
  },
  {
    path: 'labs/:id/editar',
    name: 'lab-edit',
    component: () => import('@/pages/app/labs/LabEditorPage.vue'),
    meta: { title: 'labEditor.editTitle' },
  },
  {
    path: 'entregas/:id',
    name: 'submission',
    component: () => import('@/pages/app/submissions/SubmissionPage.vue'),
    meta: { title: 'review.title' },
  },
]
