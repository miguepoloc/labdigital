<script setup lang="ts">
/** Diálogo modal sencillo y accesible (role=dialog, foco inicial, Esc y fondo cierran, foco vuelve al origen). */
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { t } from '@/i18n'

defineProps<{ title: string }>()
const emit = defineEmits<{ close: [] }>()

const titleId = `dlg-${useId()}`
const panel = ref<HTMLElement | null>(null)
let opener: Element | null = null

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(async () => {
  opener = document.activeElement
  document.addEventListener('keydown', onKey)
  await nextTick()
  panel.value?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  if (opener instanceof HTMLElement) opener.focus()
})
</script>

<template>
  <div class="fd-scrim" @click.self="emit('close')">
    <div
      ref="panel"
      class="fd-panel"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      tabindex="-1"
    >
      <header class="fd-head">
        <h2 :id="titleId">{{ title }}</h2>
        <button
          type="button"
          class="fd-close"
          :aria-label="t('common.close')"
          @click="emit('close')"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </header>
      <div class="fd-body"><slot /></div>
      <footer v-if="$slots.footer" class="fd-foot"><slot name="footer" /></footer>
    </div>
  </div>
</template>

<style scoped>
.fd-scrim {
  position: fixed;
  inset: 0;
  z-index: calc(var(--ld-z-menu) + 10);
  display: grid;
  place-items: center;
  padding: var(--ld-space-4);
  background: rgb(0 0 0 / 0.45);
}

.fd-panel {
  width: min(36rem, 100%);
  max-height: calc(100vh - 2rem);
  overflow: auto;
  background: var(--ld-color-surface);
  color: var(--ld-color-text);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-lg);
  box-shadow: var(--ld-shadow-lg);
}

.fd-panel:focus {
  outline: none;
}

.fd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-3);
  padding: var(--ld-space-4) var(--ld-space-5);
  border-bottom: 1px solid var(--ld-color-border);
}

.fd-head h2 {
  margin: 0;
  font-size: var(--ld-text-lg);
}

.fd-close {
  width: 2.25rem;
  height: 2.25rem;
  border: 0;
  border-radius: var(--ld-radius-md);
  background: transparent;
  cursor: pointer;
}

.fd-close:hover {
  background: var(--ld-color-surface-2);
}

.fd-body {
  padding: var(--ld-space-4) var(--ld-space-5);
}

.fd-foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--ld-space-2);
  padding: var(--ld-space-3) var(--ld-space-5) var(--ld-space-4);
}
</style>
