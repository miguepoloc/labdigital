<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import LdAppShell, { type NavItem } from '@/components/LdAppShell.vue'
import { t } from '@/i18n'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()

const nav = computed<NavItem[]>(() => [
  { label: t('nav.home'), to: { name: 'home' } },
  { label: t('nav.projects'), to: { name: 'projects' } },
  { label: t('nav.courses'), to: { name: 'courses' } },
  { label: t('nav.profile'), to: { name: 'profile' } },
  { label: t('nav.sessions'), to: { name: 'sessions' } },
])

async function logout() {
  await session.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <LdAppShell
    :user-name="session.me?.full_name"
    :user-email="session.me?.email"
    :nav="nav"
    @logout="logout"
  >
    <RouterView />
  </LdAppShell>
</template>
