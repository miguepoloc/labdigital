<script setup lang="ts">
import { t } from '@/i18n'

withDefaults(
  defineProps<{
    size?: 'sm' | 'md' | 'lg'
    /** Texto para lectores de pantalla. */
    label?: string
    /** Sin rol ni texto (p. ej. dentro de un botón con `aria-busy`). */
    decorative?: boolean
  }>(),
  { size: 'md', label: undefined },
)
</script>

<template>
  <span
    class="ld-spinner"
    :class="`ld-spinner--${size}`"
    :role="decorative ? undefined : 'status'"
    :aria-hidden="decorative ? 'true' : undefined"
  >
    <span class="ld-spinner__ring" aria-hidden="true" />
    <span v-if="!decorative" class="ld-visually-hidden">{{ label ?? t('app.loading') }}</span>
  </span>
</template>

<style scoped>
.ld-spinner {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ld-spinner__ring {
  width: 1.5rem;
  height: 1.5rem;
  border: 3px solid color-mix(in srgb, currentColor 25%, transparent);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: ld-spin 0.8s linear infinite;
}

.ld-spinner--sm .ld-spinner__ring {
  width: 1rem;
  height: 1rem;
  border-width: 2px;
}

.ld-spinner--lg .ld-spinner__ring {
  width: 2.5rem;
  height: 2.5rem;
  border-width: 4px;
}

@keyframes ld-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
