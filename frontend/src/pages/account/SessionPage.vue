<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { refreshSession } from '@/api/client'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { safeNext } from '@/lib/next'
import { goToNext } from '@/router/guards'
import { useSessionStore } from '@/stores/session'

/**
 * `/sesion?next=` (contrato §3): nginx manda aquí cuando un módulo da 401.
 * Intenta `POST /auth/refresh`; si funciona vuelve a `next` (validado), si no va a `/entrar?next=`.
 */
const route = useRoute()
const router = useRouter()
const session = useSessionStore()

onMounted(async () => {
  const next = safeNext(route.query.next)
  const ok = await refreshSession()
  if (ok) {
    await session.load()
    await goToNext(router, next)
    return
  }
  session.clear()
  await router.replace({ name: 'login', query: next ? { next } : {} })
})
</script>

<template>
  <AuthLayout :title="t('session.title')">
    <div class="ld-row">
      <LdSpinner :label="t('session.renewing')" />
      <span aria-hidden="true">{{ t('session.renewing') }}</span>
    </div>
  </AuthLayout>
</template>
