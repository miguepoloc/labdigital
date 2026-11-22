<script setup lang="ts">
/**
 * Diálogo modal accesible (sin `<dialog>` nativo, que jsdom no implementa del todo): `role="dialog"`,
 * `aria-modal`, foco inicial dentro, Escape para cerrar, foco atrapado con Tab y retorno del foco al
 * cerrar. Se pinta en su sitio con `position: fixed` (sin Teleport).
 */
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { t } from '@/i18n'

const props = withDefaults(
  defineProps<{
    title: string
    /** Impide cerrar (p. ej. mientras se sube un archivo). */
    persistent?: boolean
    wide?: boolean
  }>(),
  { persistent: false, wide: false },
)

const emit = defineEmits<{ close: [] }>()

const titleId = `dlg-${useId()}`
const panel = ref<HTMLElement | null>(null)
let previous: HTMLElement | null = null

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function close() {
  if (!props.persistent) emit('close')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    close()
    return
  }
  if (e.key !== 'Tab' || !panel.value) return
  const items = Array.from(panel.value.querySelectorAll<HTMLElement>(FOCUSABLE))
  if (!items.length) return
  const first = items[0]!
  const last = items[items.length - 1]!
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}

onMounted(async () => {
  previous = document.activeElement as HTMLElement | null
  await nextTick()
  const target = panel.value?.querySelector<HTMLElement>('[autofocus], ' + FOCUSABLE)
  ;(target ?? panel.value)?.focus()
})

onBeforeUnmount(() => {
  previous?.focus?.()
})
</script>

<template>
  <div class="ld-dialog" @keydown="onKeydown">
    <div class="ld-dialog__backdrop" aria-hidden="true" @click="close" />
    <div
      ref="panel"
      class="ld-dialog__panel"
      :class="{ 'ld-dialog__panel--wide': wide }"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      tabindex="-1"
    >
      <header class="ld-dialog__header">
        <h2 :id="titleId" class="ld-dialog__title">{{ title }}</h2>
        <button
          type="button"
          class="ld-dialog__close"
          :aria-label="t('common.close')"
          :disabled="persistent"
          @click="close"
        >
          ×
        </button>
      </header>
      <div class="ld-dialog__body"><slot /></div>
      <footer v-if="$slots.footer" class="ld-dialog__footer"><slot name="footer" /></footer>
    </div>
  </div>
</template>

<style scoped>
.ld-dialog {
  position: fixed;
  inset: 0;
  z-index: calc(var(--ld-z-menu) + 10);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: var(--ld-space-6) var(--ld-space-4);
  overflow-y: auto;
}

.ld-dialog__backdrop {
  position: fixed;
  inset: 0;
  background: rgb(0 20 40 / 0.55);
}

.ld-dialog__panel {
  position: relative;
  width: 100%;
  max-width: 34rem;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-4);
  padding: var(--ld-space-5);
  background: var(--ld-color-surface);
  color: var(--ld-color-text);
  border-radius: var(--ld-radius-lg);
  box-shadow: var(--ld-shadow-lg);
}

.ld-dialog__panel--wide {
  max-width: 46rem;
}

.ld-dialog__panel:focus {
  outline: none;
}

.ld-dialog__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ld-space-3);
}

.ld-dialog__title {
  margin: 0;
  font-size: var(--ld-text-xl);
}

.ld-dialog__close {
  flex: none;
  width: 2.25rem;
  height: 2.25rem;
  border: 0;
  border-radius: var(--ld-radius-sm);
  background: transparent;
  color: inherit;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
}

.ld-dialog__close:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}

.ld-dialog__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--ld-space-2);
}
</style>
