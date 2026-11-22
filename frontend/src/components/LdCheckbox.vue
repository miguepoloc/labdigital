<script setup lang="ts">
import { computed, useId } from 'vue'

const model = defineModel<boolean>({ default: false })

const props = withDefaults(
  defineProps<{
    /** Texto simple; para contenido con enlaces usa el slot por defecto. */
    label?: string
    error?: string | null
    help?: string
    required?: boolean
    disabled?: boolean
    name?: string
    id?: string
  }>(),
  { label: undefined, error: null, help: undefined },
)

const autoId = useId()
const inputId = computed(() => props.id ?? `c-${autoId}`)
const errorId = computed(() => `${inputId.value}-error`)
const helpId = computed(() => `${inputId.value}-help`)
const describedBy = computed(
  () =>
    [props.help ? helpId.value : null, props.error ? errorId.value : null]
      .filter(Boolean)
      .join(' ') || undefined,
)
</script>

<template>
  <div class="ld-field ld-check" :class="{ 'ld-field--invalid': !!error }">
    <div class="ld-check__row">
      <input
        :id="inputId"
        v-model="model"
        class="ld-check__input"
        type="checkbox"
        :name="name"
        :required="required"
        :disabled="disabled"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
      />
      <label class="ld-check__label" :for="inputId">
        <slot>{{ label }}</slot>
      </label>
    </div>
    <p v-if="help" :id="helpId" class="ld-field__help">{{ help }}</p>
    <p :id="errorId" class="ld-field__error" aria-live="polite">{{ error ?? '' }}</p>
  </div>
</template>

<style scoped>
.ld-check__row {
  display: flex;
  align-items: flex-start;
  gap: var(--ld-space-3);
}

.ld-check__input {
  flex: none;
  width: 1.25rem;
  height: 1.25rem;
  margin: 0.15rem 0 0;
  accent-color: var(--ld-color-primary);
  cursor: pointer;
}

.ld-check__input:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}

.ld-check__label {
  cursor: pointer;
  font-size: var(--ld-text-sm);
}

.ld-field--invalid .ld-check__input {
  outline: 2px solid var(--ld-color-danger);
  outline-offset: 1px;
}
</style>
