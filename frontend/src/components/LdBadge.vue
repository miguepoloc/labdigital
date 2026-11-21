<script setup lang="ts">
/** Etiqueta de estado (entregado, tardía, calificado, borrador…). El color nunca va solo: siempre hay texto. */
withDefaults(
  defineProps<{ tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'accent' }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <span class="ld-badge" :class="`ld-badge--${tone}`"><slot /></span>
</template>

<style scoped>
.ld-badge {
  --badge-fg: var(--ld-color-text-muted);
  --badge-bg: var(--ld-color-surface-2);
  display: inline-flex;
  align-items: center;
  gap: var(--ld-space-1);
  padding: 0.1rem var(--ld-space-2);
  border-radius: var(--ld-radius-full);
  background: var(--badge-bg);
  color: var(--badge-fg);
  font-size: var(--ld-text-xs);
  font-weight: 600;
  line-height: 1.6;
  white-space: nowrap;
}

.ld-badge--info {
  --badge-fg: var(--ld-color-info);
  --badge-bg: var(--ld-color-info-bg);
}

.ld-badge--success {
  --badge-fg: var(--ld-color-success);
  --badge-bg: var(--ld-color-success-bg);
}

.ld-badge--warning {
  --badge-fg: var(--ld-color-warning);
  --badge-bg: var(--ld-color-warning-bg);
}

.ld-badge--danger {
  --badge-fg: var(--ld-color-danger);
  --badge-bg: var(--ld-color-danger-bg);
}

.ld-badge--accent {
  --badge-fg: var(--ld-color-accent);
  --badge-bg: color-mix(in srgb, var(--ld-color-accent) 14%, transparent);
}
</style>
