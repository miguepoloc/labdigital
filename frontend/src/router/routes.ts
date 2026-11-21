import type { RouteRecordRaw } from 'vue-router'
import type { MessageKey } from '@/i18n'
import LandingPage from '@/pages/LandingPage.vue'
import { courseRoutes } from './routes.courses'

declare module 'vue-router' {
  interface RouteMeta {
    /** Requiere sesión: la guardia redirige a `/entrar?next=`. */
    requiresAuth?: boolean
    /** Sólo para visitantes: con sesión se redirige a `next` o a `/app`. */
    guestOnly?: boolean
    /** Clave i18n del título de la pestaña. */
    title?: MessageKey
  }
}

/** Rutas relativas a `base` (`/labdigital/`). Textos de las rutas en español (contrato §1). */
export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'landing', component: LandingPage },
  {
    path: '/entrar',
    name: 'login',
    component: () => import('@/pages/account/LoginPage.vue'),
    meta: { guestOnly: true, title: 'login.title' },
  },
  {
    path: '/registro',
    name: 'register',
    component: () => import('@/pages/account/RegisterPage.vue'),
    meta: { guestOnly: true, title: 'register.title' },
  },
  {
    path: '/verificar',
    name: 'verify',
    component: () => import('@/pages/account/VerifyPage.vue'),
    meta: { title: 'verify.title' },
  },
  {
    path: '/recuperar',
    name: 'forgot',
    component: () => import('@/pages/account/ForgotPage.vue'),
    meta: { guestOnly: true, title: 'forgot.title' },
  },
  {
    path: '/restablecer',
    name: 'reset',
    component: () => import('@/pages/account/ResetPage.vue'),
    meta: { title: 'reset.title' },
  },
  {
    path: '/sesion',
    name: 'session',
    component: () => import('@/pages/account/SessionPage.vue'),
    meta: { title: 'session.title' },
  },
  {
    // Cascarón prerenderizado que nginx sirve para /labdigital/app/** (ver nginx.conf).
    path: '/_shell',
    name: 'shell',
    component: () => import('@/pages/ShellPage.vue'),
  },
  {
    path: '/app',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/pages/app/HomePage.vue'),
        meta: { title: 'nav.home' },
      },
      {
        path: 'perfil',
        name: 'profile',
        component: () => import('@/pages/app/ProfilePage.vue'),
        meta: { title: 'profile.title' },
      },
      {
        path: 'sesiones',
        name: 'sessions',
        component: () => import('@/pages/app/SessionsPage.vue'),
        meta: { title: 'sessions.title' },
      },
      ...courseRoutes,
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/pages/NotFoundPage.vue'),
    meta: { title: 'notFound.title' },
  },
]
