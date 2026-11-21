<script setup lang="ts">
import { t } from '@/i18n'

withDefaults(
  defineProps<{
    variant?: 'info' | 'success' | 'warning' | 'danger'
    title?: string
    dismissible?: boolean
  }>(),
  { variant: 'info', title: undefined },
)

const emit = defineEmits<{ dismiss: [] }>()
// danger/warning interrumpen al lector de pantalla (role=alert); el resto es informativo (status).
</script>

<template>
  <div
    class="ld-alert"
    :class="`ld-alert--${variant}`"
    :role="variant === 'danger' || variant === 'warning' ? 'alert' : 'status'"
  >
    <div class="ld-alert__body">
      <p v-if="title" class="ld-alert__title">{{ title }}</p>
      <div class="ld-alert__content"><slot /></div>
      <div v-if="$slots.actions" class="ld-alert__actions"><slot name="actions" /></div>
    </div>
    <button
      v-if="dismissible"
      type="button"
      class="ld-alert__close"
      :aria-label="t('common.close')"
      @click="emit('dismiss')"
    >
      ×
    </button>
  </div>
</template>

<style scoped>
.ld-alert {
  --alert-fg: var(--ld-color-info);
  --alert-bg: var(--ld-color-info-bg);
  display: flex;
  gap: var(--ld-space-3);
  padding: var(--ld-space-3) var(--ld-space-4);
  border-left: 4px solid var(--alert-fg);
  border-radius: var(--ld-radius-md);
  background: var(--alert-bg);
  color: var(--ld-color-text);
  font-size: var(--ld-text-sm);
}

.ld-alert--success {
  --alert-fg: var(--ld-color-success);
  --alert-bg: var(--ld-color-success-bg);
}

.ld-alert--warning {
  --alert-fg: var(--ld-color-warning);
  --alert-bg: var(--ld-color-warning-bg);
}

.ld-alert--danger {
  --alert-fg: var(--ld-color-danger);
  --alert-bg: var(--ld-color-danger-bg);
}

.ld-alert__body {
  flex: 1;
  min-width: 0;
}

.ld-alert__title {
  margin: 0 0 var(--ld-space-1);
  font-weight: 700;
  color: var(--alert-fg);
}

.ld-alert__content :deep(p:last-child) {
  margin-bottom: 0;
}

.ld-alert__actions {
  margin-top: var(--ld-space-2);
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-2);
}

.ld-alert__close {
  flex: none;
  width: 2rem;
  height: 2rem;
  border: 0;
  border-radius: var(--ld-radius-sm);
  background: transparent;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
}

.ld-alert__close:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}
</style>
