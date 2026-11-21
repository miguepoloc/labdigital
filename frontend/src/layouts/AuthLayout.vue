<script setup lang="ts">
import { RouterLink } from 'vue-router'
import LdEscudo from '@/components/LdEscudo.vue'
import LdThemeToggle from '@/components/LdThemeToggle.vue'
import { config } from '@/config'
import { t } from '@/i18n'

defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <div class="ld-auth">
    <a class="ld-skip-link" href="#ld-main">{{ t('app.skipToContent') }}</a>
    <header class="ld-auth__top">
      <RouterLink class="ld-auth__brand" :to="{ name: 'landing' }">
        <LdEscudo :size="36" />
        <span>
          <strong>{{ t('app.name') }}</strong>
          <small>GIDEAM</small>
        </span>
      </RouterLink>
      <LdThemeToggle />
    </header>
    <main id="ld-main" class="ld-auth__main" tabindex="-1">
      <div class="ld-auth__card">
        <h1 class="ld-auth__title">{{ title }}</h1>
        <p v-if="subtitle" class="ld-auth__subtitle">{{ subtitle }}</p>
        <slot />
      </div>
      <div v-if="$slots.below" class="ld-auth__below"><slot name="below" /></div>
    </main>
    <footer class="ld-auth__footer">
      <span>{{ t('app.org') }}</span>
      <a :href="config.dataPolicyUrl" target="_blank" rel="noopener">{{
        t('landing.footerPolicy')
      }}</a>
    </footer>
  </div>
</template>

<style scoped>
.ld-auth {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(
      60rem 30rem at 100% -10%,
      color-mix(in srgb, var(--um-blue-300) 16%, transparent),
      transparent
    ),
    var(--ld-color-bg);
}

.ld-auth__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--ld-space-3) var(--ld-space-4);
}

.ld-auth__brand {
  display: flex;
  align-items: center;
  gap: var(--ld-space-2);
  color: var(--ld-color-text);
  text-decoration: none;
  font-family: var(--ld-font-heading);
}

.ld-auth__brand span {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.ld-auth__brand small {
  font-size: var(--ld-text-xs);
  letter-spacing: 0.08em;
  color: var(--ld-color-text-muted);
}

.ld-auth__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--ld-space-4);
}

.ld-auth__main:focus {
  outline: none;
}

.ld-auth__card {
  width: 100%;
  max-width: 28rem;
  padding: var(--ld-space-5) var(--ld-space-4);
  background: var(--ld-color-surface);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-lg);
  box-shadow: var(--ld-shadow-md);
  border-top: 4px solid var(--ld-color-primary);
}

.ld-auth__title {
  font-size: var(--ld-text-2xl);
}

.ld-auth__subtitle {
  color: var(--ld-color-text-muted);
  margin-bottom: var(--ld-space-5);
}

.ld-auth__below {
  margin-top: var(--ld-space-4);
  text-align: center;
  font-size: var(--ld-text-sm);
}

.ld-auth__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--ld-space-2) var(--ld-space-4);
  padding: var(--ld-space-4);
  font-size: var(--ld-text-xs);
  color: var(--ld-color-text-muted);
}

@media (min-width: 600px) {
  .ld-auth__main {
    justify-content: center;
    padding-bottom: var(--ld-space-7);
  }

  .ld-auth__card {
    padding: var(--ld-space-6);
  }
}
</style>
