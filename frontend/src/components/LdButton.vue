<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import LdSpinner from './LdSpinner.vue'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'accent' | 'ghost' | 'danger'
    size?: 'sm' | 'md' | 'lg'
    type?: 'button' | 'submit' | 'reset'
    /** Muestra un spinner, deshabilita el botón y marca `aria-busy`. */
    loading?: boolean
    disabled?: boolean
    block?: boolean
    /** Enlace interno (RouterLink). */
    to?: RouteLocationRaw
    /** Enlace externo. */
    href?: string
  }>(),
  { variant: 'primary', size: 'md', type: 'button' },
)

const tag = computed(() => (props.to ? RouterLink : props.href ? 'a' : 'button'))
const isDisabled = computed(() => props.disabled || props.loading)
</script>

<template>
  <component
    :is="tag"
    class="ld-btn"
    :class="[`ld-btn--${variant}`, `ld-btn--${size}`, { 'ld-btn--block': block }]"
    :type="tag === 'button' ? type : undefined"
    v-bind="tag === 'a' ? { href } : to ? { to } : {}"
    :disabled="tag === 'button' ? isDisabled : undefined"
    :aria-disabled="tag !== 'button' && isDisabled ? 'true' : undefined"
    :aria-busy="loading ? 'true' : undefined"
  >
    <LdSpinner v-if="loading" size="sm" decorative />
    <span class="ld-btn__label"><slot /></span>
  </component>
</template>

<style scoped>
.ld-btn {
  --btn-bg: var(--ld-color-primary);
  --btn-bg-hover: var(--ld-color-primary-hover);
  --btn-fg: var(--ld-color-primary-contrast);
  --btn-border: transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--ld-space-2);
  min-height: 2.75rem;
  padding: 0 var(--ld-space-5);
  border: 1px solid var(--btn-border);
  border-radius: var(--ld-radius-md);
  background: var(--btn-bg);
  color: var(--btn-fg);
  font-family: var(--ld-font-heading);
  font-weight: 600;
  font-size: var(--ld-text-md);
  text-decoration: none;
  cursor: pointer;
  transition:
    background-color var(--ld-duration) var(--ld-ease),
    box-shadow var(--ld-duration) var(--ld-ease);
}

.ld-btn:hover:not(:disabled) {
  background: var(--btn-bg-hover);
}

.ld-btn:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}

.ld-btn:disabled,
.ld-btn[aria-disabled='true'] {
  opacity: 0.6;
  cursor: not-allowed;
}

.ld-btn--secondary {
  --btn-bg: transparent;
  --btn-bg-hover: var(--ld-color-surface-2);
  --btn-fg: var(--ld-color-primary);
  --btn-border: currentColor;
}

.ld-btn--accent {
  --btn-bg: var(--ld-color-accent);
  --btn-bg-hover: var(--ld-color-accent-hover);
  --btn-fg: #fff;
}

.ld-btn--ghost {
  --btn-bg: transparent;
  --btn-bg-hover: var(--ld-color-surface-2);
  --btn-fg: var(--ld-color-text);
}

.ld-btn--danger {
  --btn-bg: var(--ld-color-danger);
  --btn-bg-hover: color-mix(in srgb, var(--ld-color-danger) 85%, black);
  --btn-fg: #fff;
}

.ld-btn--sm {
  min-height: 2.25rem;
  padding: 0 var(--ld-space-3);
  font-size: var(--ld-text-sm);
}

.ld-btn--lg {
  min-height: 3.25rem;
  padding: 0 var(--ld-space-6);
  font-size: var(--ld-text-lg);
}

.ld-btn--block {
  display: flex;
  width: 100%;
}
</style>
