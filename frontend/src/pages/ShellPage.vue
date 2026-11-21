<script setup lang="ts">
// Cascarón de la SPA: lo que se ve en /labdigital/app/** antes de que cargue el JS.
import LdSpinner from '@/components/LdSpinner.vue'
</script>

<template>
  <div class="ld-shell-page"><LdSpinner size="lg" /></div>
</template>

<style scoped>
.ld-shell-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  color: var(--ld-color-primary);
}
</style>
