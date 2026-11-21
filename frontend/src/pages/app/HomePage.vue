<script setup lang="ts">
import { computed } from 'vue'
import LdAlert from '@/components/LdAlert.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import { t } from '@/i18n'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const firstName = computed(() => session.me?.full_name.split(/\s+/)[0] ?? '')
</script>

<template>
  <div class="ld-stack">
    <header>
      <h1>{{ t('home.title', { name: firstName }) }}</h1>
      <p class="ld-muted">{{ t('home.subtitle') }}</p>
    </header>
    <LdAlert v-if="session.me && !session.me.email_verified" variant="warning">
      {{ t('home.emailUnverified') }}
    </LdAlert>
    <div class="ld-home__grid">
      <LdCard :title="t('home.projectsTitle')">
        <LdEmptyState :title="t('nav.soon')" :body="t('home.projectsEmpty')" />
      </LdCard>
      <LdCard :title="t('home.coursesTitle')">
        <LdEmptyState :title="t('nav.soon')" :body="t('home.coursesEmpty')" />
      </LdCard>
    </div>
  </div>
</template>

<style scoped>
.ld-home__grid {
  display: grid;
  gap: var(--ld-space-4);
}

@media (min-width: 900px) {
  .ld-home__grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
