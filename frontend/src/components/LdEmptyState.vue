<script setup lang="ts">
withDefaults(defineProps<{ title: string; body?: string; headingLevel?: 2 | 3 }>(), {
  body: undefined,
  headingLevel: 3,
})
</script>

<template>
  <div class="ld-empty">
    <div class="ld-empty__icon" aria-hidden="true">
      <slot name="icon">
        <!-- LED apagado sobre placa: icono genérico de "nada aún". -->
        <svg viewBox="0 0 48 48" width="48" height="48">
          <rect
            x="4"
            y="10"
            width="40"
            height="28"
            rx="4"
            fill="var(--ld-color-pcb)"
            opacity="0.18"
          />
          <circle
            cx="24"
            cy="24"
            r="6"
            fill="none"
            stroke="var(--ld-color-pcb)"
            stroke-width="2.5"
          />
          <path
            d="M14 38v4M34 38v4M14 6v4M34 6v4"
            stroke="var(--ld-color-pcb)"
            stroke-width="2.5"
          />
        </svg>
      </slot>
    </div>
    <component :is="`h${headingLevel}`" class="ld-empty__title">{{ title }}</component>
    <p v-if="body" class="ld-empty__body">{{ body }}</p>
    <div v-if="$slots.default" class="ld-empty__actions"><slot /></div>
  </div>
</template>

<style scoped>
.ld-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--ld-space-2);
  padding: var(--ld-space-6) var(--ld-space-4);
  border: 1px dashed var(--ld-color-border);
  border-radius: var(--ld-radius-lg);
}

.ld-empty__title {
  margin: 0;
  font-size: var(--ld-text-lg);
}

.ld-empty__body {
  margin: 0;
  max-width: 36rem;
  color: var(--ld-color-text-muted);
}

.ld-empty__actions {
  margin-top: var(--ld-space-2);
  display: flex;
  gap: var(--ld-space-2);
}
</style>
