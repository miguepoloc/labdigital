<script setup lang="ts">
import { useHead } from '@unhead/vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { pageTitle } from '@/lib/head'

// vite-ssg usa unhead: así el título y el idioma también quedan en el HTML prerenderizado.
const route = useRoute()
useHead({
  htmlAttrs: { lang: 'es' },
  title: computed(() => pageTitle(route.meta.title)),
})
</script>

<template>
  <RouterView />
</template>
