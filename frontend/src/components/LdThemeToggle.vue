<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { t } from '@/i18n'
import { applyTheme, nextTheme, readTheme, type ThemeChoice } from '@/lib/theme'

const choice = ref<ThemeChoice>('system')
onMounted(() => {
  choice.value = readTheme()
})

const label = computed(() =>
  choice.value === 'light'
    ? t('theme.light')
    : choice.value === 'dark'
      ? t('theme.dark')
      : t('theme.system'),
)
const icon = computed(() => (choice.value === 'light' ? '☀' : choice.value === 'dark' ? '☾' : '◐'))

function toggle() {
  choice.value = nextTheme(choice.value)
  applyTheme(choice.value)
}
</script>

<template>
  <button type="button" class="ld-theme" :title="`${t('theme.toggle')}: ${label}`" @click="toggle">
    <span aria-hidden="true">{{ icon }}</span>
    <span class="ld-visually-hidden">{{ t('theme.toggle') }}: {{ label }}</span>
  </button>
</template>

<style scoped>
.ld-theme {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: 1px solid color-mix(in srgb, currentColor 35%, transparent);
  border-radius: var(--ld-radius-full);
  background: transparent;
  color: inherit;
  font-size: 1.1rem;
  cursor: pointer;
}

.ld-theme:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}
</style>
