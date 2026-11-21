<script setup lang="ts">
import { config } from '@/config'
import { t } from '@/i18n'

/**
 * Escudo oficial desde el CDN institucional.
 * `background="auto"`: según el tema; `"dark"`: siempre la versión para fondo oscuro (cabeceras azules).
 */
withDefaults(defineProps<{ background?: 'auto' | 'dark' | 'light'; size?: number }>(), {
  background: 'auto',
  size: 40,
})
</script>

<template>
  <span class="ld-escudo" :style="{ width: `${size}px`, height: `${size}px` }">
    <img
      v-if="background !== 'dark'"
      :class="{ 'ld-escudo--light': background === 'auto' }"
      :src="config.escudo.light"
      :alt="t('app.escudoAlt')"
      :width="size"
      :height="size"
      decoding="async"
    />
    <img
      v-if="background !== 'light'"
      :class="{ 'ld-escudo--dark': background === 'auto' }"
      :src="config.escudo.dark"
      :alt="t('app.escudoAlt')"
      :width="size"
      :height="size"
      decoding="async"
    />
  </span>
</template>

<style scoped>
.ld-escudo {
  display: inline-block;
  flex: none;
}

.ld-escudo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
</style>
