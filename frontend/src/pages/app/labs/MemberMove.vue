<script setup lang="ts">
/**
 * «Mover a…»/«Asignar a…» de un estudiante (LD-18): un `<select>` nativo con su etiqueta accesible y un
 * botón que confirma. Separar elegir de aplicar evita mover a alguien al recorrer las opciones con el
 * teclado. Las opciones completas se muestran deshabilitadas.
 */
import { ref } from 'vue'
import LdButton from '@/components/LdButton.vue'
import type { MoveOption } from './teamsAdmin'

const props = defineProps<{
  options: MoveOption[]
  placeholder: string
  selectLabel: string
  submitText: string
  submitLabel: string
  busy?: boolean
}>()
const emit = defineEmits<{ move: [teamId: string] }>()

const target = ref('')

function submit() {
  if (!target.value || props.busy) return
  emit('move', target.value)
  target.value = ''
}
</script>

<template>
  <div class="ld-move">
    <select
      v-model="target"
      class="ld-field__input ld-move__select"
      :aria-label="selectLabel"
      :disabled="busy"
      data-test="move-select"
    >
      <option value="" disabled>{{ placeholder }}</option>
      <option v-for="o in options" :key="o.id" :value="o.id" :disabled="o.disabled">
        {{ o.label }}
      </option>
    </select>
    <LdButton
      size="sm"
      variant="secondary"
      :disabled="!target"
      :loading="busy"
      :aria-label="submitLabel"
      data-test="move-submit"
      @click="submit"
    >
      {{ submitText }}
    </LdButton>
  </div>
</template>

<style scoped>
.ld-move {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
}

.ld-move__select {
  width: auto;
  min-width: 9rem;
  max-width: 100%;
  padding-block: var(--ld-space-1);
  font-size: var(--ld-text-sm);
}
</style>
