<script setup lang="ts">
withDefaults(
  defineProps<{
    as?: string
    title?: string
    /** Nivel del encabezado del título (h2 por defecto). */
    headingLevel?: 2 | 3 | 4
    padded?: boolean
  }>(),
  { as: 'section', title: undefined, headingLevel: 2, padded: true },
)
</script>

<template>
  <component :is="as" class="ld-card" :class="{ 'ld-card--padded': padded }">
    <header v-if="title || $slots.header" class="ld-card__header">
      <slot name="header">
        <component :is="`h${headingLevel}`" class="ld-card__title">{{ title }}</component>
      </slot>
    </header>
    <div class="ld-card__body"><slot /></div>
    <footer v-if="$slots.footer" class="ld-card__footer"><slot name="footer" /></footer>
  </component>
</template>

<style scoped>
.ld-card {
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-3);
  background: var(--ld-color-surface);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-lg);
  box-shadow: var(--ld-shadow-sm);
}

.ld-card--padded {
  padding: var(--ld-space-5);
}

.ld-card__title {
  margin: 0;
  font-size: var(--ld-text-lg);
}

.ld-card__footer {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-2);
  padding-top: var(--ld-space-3);
  border-top: 1px solid var(--ld-color-border);
}
</style>
