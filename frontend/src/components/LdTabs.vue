<script setup lang="ts">
/**
 * Pestañas accesibles (patrón WAI-ARIA: flechas, Inicio/Fin). El contenido va en el slot por defecto, que
 * recibe `active`; el panel lleva `role="tabpanel"` enlazado a su pestaña.
 */
import { useId } from 'vue'

export interface TabItem {
  id: string
  label: string
  /** Contador opcional (p. ej. solicitudes pendientes). */
  count?: number | null
}

const props = defineProps<{ tabs: TabItem[]; label: string }>()
const active = defineModel<string>({ required: true })
const uid = useId()

const tabId = (id: string) => `tab-${uid}-${id}`
const panelId = `panel-${uid}`

function onKey(e: KeyboardEvent, index: number) {
  const n = props.tabs.length
  let next = -1
  if (e.key === 'ArrowRight') next = (index + 1) % n
  else if (e.key === 'ArrowLeft') next = (index - 1 + n) % n
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = n - 1
  if (next < 0) return
  e.preventDefault()
  const tab = props.tabs[next]!
  active.value = tab.id
  document.getElementById(tabId(tab.id))?.focus()
}
</script>

<template>
  <div class="ld-tabs">
    <div class="ld-tabs__list" role="tablist" :aria-label="label">
      <button
        v-for="(tab, i) in tabs"
        :id="tabId(tab.id)"
        :key="tab.id"
        type="button"
        role="tab"
        class="ld-tabs__tab"
        :aria-selected="active === tab.id ? 'true' : 'false'"
        :aria-controls="panelId"
        :tabindex="active === tab.id ? 0 : -1"
        :data-test="`tab-${tab.id}`"
        @click="active = tab.id"
        @keydown="onKey($event, i)"
      >
        {{ tab.label }}
        <span v-if="tab.count" class="ld-tabs__count">{{ tab.count }}</span>
      </button>
    </div>
    <div
      :id="panelId"
      class="ld-tabs__panel"
      role="tabpanel"
      :aria-labelledby="tabId(active)"
      tabindex="0"
    >
      <slot :active="active" />
    </div>
  </div>
</template>

<style scoped>
.ld-tabs__list {
  display: flex;
  gap: var(--ld-space-1);
  overflow-x: auto;
  border-bottom: 1px solid var(--ld-color-border);
}

.ld-tabs__tab {
  display: inline-flex;
  align-items: center;
  gap: var(--ld-space-2);
  min-height: 2.75rem;
  padding: 0 var(--ld-space-4);
  border: 0;
  border-bottom: 3px solid transparent;
  background: transparent;
  color: var(--ld-color-text-muted);
  font-family: var(--ld-font-heading);
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.ld-tabs__tab[aria-selected='true'] {
  color: var(--ld-color-primary);
  border-bottom-color: currentColor;
}

.ld-tabs__tab:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}

.ld-tabs__count {
  min-width: 1.4rem;
  padding: 0 0.35rem;
  border-radius: var(--ld-radius-full);
  background: var(--ld-color-accent);
  color: #fff;
  font-size: var(--ld-text-xs);
  line-height: 1.4rem;
  text-align: center;
}

.ld-tabs__panel {
  padding-top: var(--ld-space-5);
}

.ld-tabs__panel:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}
</style>
